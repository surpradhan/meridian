"""
Unit tests for OAuth2/OIDC support.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.oauth import (
    OAuthManager,
    _store_state,
    _peek_state,
    _consume_state,
    _purge_expired_states,
    _STATE_STORE,
    _safe_username,
)
from app.auth.store import AuthStore, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    s = MagicMock()
    s.google_client_id = overrides.get("google_client_id", "gid")
    s.google_client_secret = overrides.get("google_client_secret", "gsecret")
    s.oidc_client_id = overrides.get("oidc_client_id", None)
    s.oidc_client_secret = overrides.get("oidc_client_secret", None)
    s.oidc_issuer = overrides.get("oidc_issuer", None)
    return s


def _make_store():
    store = MagicMock(spec=AuthStore)
    store.get_user_by_oauth.return_value = None
    store.user_exists.return_value = False
    store.create_oauth_user.return_value = User(
        id="uid-1",
        username="alice",
        email="alice@example.com",
        password_hash="",
        role="viewer",
        allowed_domains=[],
        is_active=True,
        created_at="2026-04-11",
        oauth_provider="google",
        oauth_subject="12345",
    )
    return store


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStateManagement:
    def setup_method(self):
        _STATE_STORE.clear()

    def teardown_method(self):
        _STATE_STORE.clear()

    def test_store_and_peek_then_consume(self):
        state = _store_state("google")
        assert len(state) > 20
        # Peek does not consume
        assert _peek_state(state) == "google"
        assert _peek_state(state) == "google"
        # Consume removes it
        _consume_state(state)
        assert _peek_state(state) is None

    def test_peek_unknown_state(self):
        assert _peek_state("not-a-real-state") is None

    def test_expired_state_rejected(self):
        state = _store_state("google")
        _STATE_STORE[state]["expires"] = time.time() - 1  # force expiry
        assert _peek_state(state) is None

    def test_purge_removes_expired(self):
        s1 = _store_state("google")
        s2 = _store_state("google")
        _STATE_STORE[s1]["expires"] = time.time() - 1
        _purge_expired_states()
        assert s1 not in _STATE_STORE
        assert s2 in _STATE_STORE


# ---------------------------------------------------------------------------
# OAuthManager.get_authorize_url
# ---------------------------------------------------------------------------


class TestGetAuthorizeUrl:
    def setup_method(self):
        _STATE_STORE.clear()

    def teardown_method(self):
        _STATE_STORE.clear()

    def test_google_returns_url_and_state(self):
        mgr = OAuthManager(_make_settings())
        url, state = mgr.get_authorize_url("google", "http://localhost:8000/api/auth/oauth/callback")
        assert "accounts.google.com" in url
        assert "client_id=gid" in url
        assert len(state) > 20

    def test_url_encodes_redirect_uri(self):
        """redirect_uri must be percent-encoded, not raw, in the auth URL."""
        mgr = OAuthManager(_make_settings())
        url, _ = mgr.get_authorize_url("google", "http://localhost:8000/api/auth/oauth/callback")
        # urlencode converts : and / in the redirect_uri
        assert "redirect_uri=http%3A" in url or "redirect_uri=http%3a" in url

    def test_google_missing_client_id_raises(self):
        mgr = OAuthManager(_make_settings(google_client_id=None))
        with pytest.raises(ValueError, match="Client ID"):
            mgr.get_authorize_url("google", "http://localhost:8000/callback")

    def test_oidc_raises_for_sync_call(self):
        mgr = OAuthManager(_make_settings())
        with pytest.raises(ValueError, match="async discovery"):
            mgr.get_authorize_url("oidc", "http://localhost:8000/callback")

    def test_unknown_provider_raises(self):
        mgr = OAuthManager(_make_settings())
        with pytest.raises(ValueError):
            mgr.get_authorize_url("facebook", "http://localhost:8000/callback")


# ---------------------------------------------------------------------------
# OAuthManager.handle_callback
# ---------------------------------------------------------------------------


class TestHandleCallback:
    def setup_method(self):
        _STATE_STORE.clear()

    def teardown_method(self):
        _STATE_STORE.clear()

    async def test_invalid_state_raises(self):
        mgr = OAuthManager(_make_settings())
        store = _make_store()
        with pytest.raises(ValueError, match="Invalid or expired"):
            await mgr.handle_callback("google", "code", "bad-state", "http://redir", store)

    async def test_state_provider_mismatch_raises(self):
        state = _store_state("oidc")  # stored as oidc
        mgr = OAuthManager(_make_settings())
        store = _make_store()
        with pytest.raises(ValueError, match="mismatch"):
            await mgr.handle_callback("google", "code", state, "http://redir", store)

    async def test_new_user_auto_provisioned(self):
        """A brand-new OAuth login should create a viewer user and return a JWT."""
        state = _store_state("google")
        mgr = OAuthManager(_make_settings())
        store = _make_store()

        mock_token_resp = MagicMock()
        mock_token_resp.raise_for_status = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "google-at-1"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.raise_for_status = MagicMock()
        mock_userinfo_resp.json.return_value = {
            "sub": "12345",
            "email": "alice@example.com",
            "name": "Alice Example",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_token_resp)
        mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            jwt = await mgr.handle_callback(
                "google", "auth-code", state, "http://localhost:8000/callback", store
            )

        assert jwt  # non-empty JWT
        store.create_oauth_user.assert_called_once()
        call_kwargs = store.create_oauth_user.call_args
        assert call_kwargs.kwargs["provider"] == "google"
        assert call_kwargs.kwargs["role"] == "viewer"

    async def test_existing_user_not_reprovisioned(self):
        """On subsequent logins the existing user is found, not recreated."""
        state = _store_state("google")
        mgr = OAuthManager(_make_settings())
        store = _make_store()

        existing_user = User(
            id="uid-existing",
            username="alice",
            email="alice@example.com",
            password_hash="",
            role="analyst",
            allowed_domains=["sales"],
            is_active=True,
            created_at="2026-01-01",
            oauth_provider="google",
            oauth_subject="12345",
        )
        store.get_user_by_oauth.return_value = existing_user

        mock_token_resp = MagicMock()
        mock_token_resp.raise_for_status = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "google-at-2"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.raise_for_status = MagicMock()
        mock_userinfo_resp.json.return_value = {"sub": "12345", "email": "alice@example.com"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_token_resp)
        mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            jwt = await mgr.handle_callback(
                "google", "auth-code", state, "http://localhost:8000/callback", store
            )

        assert jwt
        store.create_oauth_user.assert_not_called()

    async def test_inactive_user_raises(self):
        state = _store_state("google")
        mgr = OAuthManager(_make_settings())
        store = _make_store()

        inactive = User(
            id="uid-x", username="bob", email="bob@x.com", password_hash="",
            role="viewer", allowed_domains=[], is_active=False, created_at="2026-01-01",
            oauth_provider="google", oauth_subject="99999",
        )
        store.get_user_by_oauth.return_value = inactive

        mock_token_resp = MagicMock()
        mock_token_resp.raise_for_status = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tok"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.raise_for_status = MagicMock()
        mock_userinfo_resp.json.return_value = {"sub": "99999", "email": "bob@x.com"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_token_resp)
        mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(ValueError, match="inactive"):
                await mgr.handle_callback(
                    "google", "code", state, "http://localhost:8000/callback", store
                )


# ---------------------------------------------------------------------------
# _safe_username
# ---------------------------------------------------------------------------


class TestSafeUsername:
    def test_derives_from_name(self):
        store = MagicMock(spec=AuthStore)
        store.user_exists.return_value = False
        assert _safe_username("Alice Example", "alice@example.com", store) == "alice_example"

    def test_falls_back_to_email_prefix(self):
        store = MagicMock(spec=AuthStore)
        store.user_exists.return_value = False
        assert _safe_username("", "carol@x.com", store) == "carol"

    def test_increments_on_collision(self):
        store = MagicMock(spec=AuthStore)
        # First call (base) conflicts; second (base_1) is free
        store.user_exists.side_effect = [True, False]
        result = _safe_username("Alice", "alice@x.com", store)
        assert result == "alice_1"

    def test_empty_name_and_empty_email_falls_back_to_user(self):
        """When both name and email are absent, fall back to 'user'."""
        store = MagicMock(spec=AuthStore)
        store.user_exists.return_value = False
        assert _safe_username("", "", store) == "user"


# ---------------------------------------------------------------------------
# OIDC discovery endpoint resolution
# ---------------------------------------------------------------------------


class TestOidcDiscovery:
    def setup_method(self):
        _STATE_STORE.clear()

    def teardown_method(self):
        _STATE_STORE.clear()

    async def test_resolve_oidc_endpoints_uses_well_known_url(self):
        """Discovery document is fetched from <issuer>/.well-known/openid-configuration."""
        settings = _make_settings(
            oidc_client_id="oidc-id",
            oidc_client_secret="oidc-sec",
            oidc_issuer="https://sso.example.com",
        )
        mgr = OAuthManager(settings)

        discovery_doc = {
            "authorization_endpoint": "https://sso.example.com/authorize",
            "token_endpoint": "https://sso.example.com/token",
            "userinfo_endpoint": "https://sso.example.com/userinfo",
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = discovery_doc

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            endpoints = await mgr._resolve_oidc_endpoints()

        assert endpoints["authorization_url"] == "https://sso.example.com/authorize"
        assert endpoints["token_url"] == "https://sso.example.com/token"
        mock_http.get.assert_called_once()
        call_url = mock_http.get.call_args[0][0]
        assert call_url == "https://sso.example.com/.well-known/openid-configuration"

    async def test_resolve_oidc_endpoints_raises_without_issuer(self):
        settings = _make_settings(oidc_issuer=None)
        mgr = OAuthManager(settings)
        with pytest.raises(ValueError, match="OIDC_ISSUER"):
            await mgr._resolve_oidc_endpoints()

    async def test_oidc_authorize_url_built_from_discovery(self):
        """get_authorize_url_async for 'oidc' resolves endpoints and builds a valid URL."""
        settings = _make_settings(
            oidc_client_id="oidc-id",
            oidc_client_secret="oidc-sec",
            oidc_issuer="https://sso.example.com",
        )
        mgr = OAuthManager(settings)

        discovery_doc = {
            "authorization_endpoint": "https://sso.example.com/authorize",
            "token_endpoint": "https://sso.example.com/token",
            "userinfo_endpoint": "https://sso.example.com/userinfo",
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = discovery_doc

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            url, state = await mgr.get_authorize_url_async("oidc", "http://localhost:8000/callback")

        assert "sso.example.com/authorize" in url
        assert "client_id=oidc-id" in url
        assert len(state) > 20


# ---------------------------------------------------------------------------
# Email None guard in handle_callback
# ---------------------------------------------------------------------------


class TestHandleCallbackEmailGuard:
    def setup_method(self):
        _STATE_STORE.clear()

    def teardown_method(self):
        _STATE_STORE.clear()

    async def test_missing_email_claim_does_not_crash(self):
        """userinfo without 'email' should not raise AttributeError."""
        state = _store_state("google")
        mgr = OAuthManager(_make_settings())
        store = _make_store()

        mock_token_resp = MagicMock()
        mock_token_resp.raise_for_status = MagicMock()
        mock_token_resp.json.return_value = {"access_token": "tok"}

        # No email or name — only sub
        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.raise_for_status = MagicMock()
        mock_userinfo_resp.json.return_value = {"sub": "no-email-user"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_token_resp)
        mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            # Should not raise — user is provisioned without email
            jwt = await mgr.handle_callback(
                "google", "auth-code", state, "http://localhost:8000/callback", store
            )

        assert jwt
        call_kwargs = store.create_oauth_user.call_args
        assert call_kwargs.kwargs["email"] == ""
