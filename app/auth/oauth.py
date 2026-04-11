"""
OAuth2 / OIDC Manager

Handles the authorization code flow for Google OAuth2 and generic OIDC providers.

Flow:
1. get_authorize_url(provider, redirect_uri)  → (url, state)
2. handle_callback(provider, code, state, redirect_uri, store)  → Meridian JWT string

State is kept in a short-lived in-memory dict (suitable for single-process dev/demo).
For multi-process production deployments, replace _STATE_STORE with a Redis cache.
"""

import logging
import secrets
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

from app.auth.jwt import create_access_token
from app.auth.providers import GOOGLE_PROVIDER, get_provider_config
from app.auth.store import AuthStore

logger = logging.getLogger(__name__)

# In-memory state store: state_token → {"provider": str, "expires": float}
_STATE_STORE: Dict[str, Dict] = {}
_STATE_TTL_SECONDS = 600  # 10 minutes


def _store_state(provider: str) -> str:
    """Generate and store a CSRF state token, returning it."""
    _purge_expired_states()
    state = secrets.token_urlsafe(32)
    _STATE_STORE[state] = {"provider": provider, "expires": time.time() + _STATE_TTL_SECONDS}
    return state


def _peek_state(state: str) -> Optional[str]:
    """Return the provider for a state token without consuming it. Returns None if invalid/expired."""
    entry = _STATE_STORE.get(state)
    if entry is None or time.time() > entry["expires"]:
        return None
    return entry["provider"]


def _consume_state(state: str) -> None:
    """Remove a state token from the store (call only after validation succeeds)."""
    _STATE_STORE.pop(state, None)


def _purge_expired_states() -> None:
    now = time.time()
    expired = [k for k, v in _STATE_STORE.items() if now > v["expires"]]
    for k in expired:
        del _STATE_STORE[k]


class OAuthManager:
    """Orchestrates OAuth2 / OIDC authorization code flows."""

    def __init__(self, settings):
        self._settings = settings

    def _get_client_credentials(self, provider: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (client_id, client_secret) for the given provider from settings."""
        if provider == "google":
            return self._settings.google_client_id, self._settings.google_client_secret
        if provider == "oidc":
            return self._settings.oidc_client_id, self._settings.oidc_client_secret
        return None, None

    async def _resolve_oidc_endpoints(self) -> Dict[str, str]:
        """Fetch the OIDC discovery document for the configured issuer."""
        issuer = (self._settings.oidc_issuer or "").rstrip("/")
        if not issuer:
            raise ValueError("OIDC_ISSUER is not configured")
        discovery_url = f"{issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            resp = await client.get(discovery_url, timeout=10)
            resp.raise_for_status()
            doc = resp.json()
        return {
            "authorization_url": doc["authorization_endpoint"],
            "token_url": doc["token_endpoint"],
            "userinfo_url": doc.get("userinfo_endpoint", ""),
            "scope": "openid email profile",
        }

    async def _get_provider_endpoints(self, provider: str) -> Dict[str, str]:
        """Return resolved endpoints for the given provider."""
        if provider == "google":
            return GOOGLE_PROVIDER
        if provider == "oidc":
            return await self._resolve_oidc_endpoints()
        raise ValueError(f"Unknown provider: {provider!r}")

    def get_authorize_url(self, provider: str, redirect_uri: str) -> Tuple[str, str]:
        """
        Build the authorization URL synchronously for known providers (Google).

        For generic OIDC this raises ValueError — call get_authorize_url_async instead.

        Returns:
            (authorize_url, state)
        """
        cfg = get_provider_config(provider)
        if cfg is None:
            raise ValueError(
                f"Provider {provider!r} requires async discovery — use get_authorize_url_async()"
            )
        client_id, _ = self._get_client_credentials(provider)
        if not client_id:
            raise ValueError(f"Client ID for provider {provider!r} is not configured")

        state = _store_state(provider)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        url = f"{cfg['authorization_url']}?{urlencode(params)}"
        return url, state

    async def get_authorize_url_async(self, provider: str, redirect_uri: str) -> Tuple[str, str]:
        """Build the authorization URL for any provider (including generic OIDC)."""
        cfg = await self._get_provider_endpoints(provider)
        client_id, _ = self._get_client_credentials(provider)
        if not client_id:
            raise ValueError(f"Client ID for provider {provider!r} is not configured")

        state = _store_state(provider)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "select_account"

        url = f"{cfg['authorization_url']}?{urlencode(params)}"
        return url, state

    async def handle_callback(
        self,
        provider: str,
        code: str,
        state: str,
        redirect_uri: str,
        store: AuthStore,
    ) -> str:
        """
        Exchange authorization code for tokens, validate, and return a Meridian JWT.

        On first login: auto-provisions the user as role=viewer with no domain access.
        On subsequent logins: looks up the existing user by (provider, subject).

        Returns:
            Meridian JWT access token string.
        """
        # Peek first so we can give a specific error before consuming the token.
        # The token is only consumed after both checks pass, preserving it for
        # diagnostics on mismatch (though the caller should restart the flow either way).
        stored_provider = _peek_state(state)
        if stored_provider is None:
            raise ValueError("Invalid or expired OAuth state parameter")
        if stored_provider != provider:
            _consume_state(state)  # consume to prevent reuse even on mismatch
            raise ValueError("OAuth state provider mismatch")

        _consume_state(state)  # state validated — now consume to prevent replay

        cfg = await self._get_provider_endpoints(provider)
        client_id, client_secret = self._get_client_credentials(provider)
        if not client_id or not client_secret:
            raise ValueError(f"OAuth credentials for {provider!r} are not configured")

        # Exchange authorization code for tokens
        async with httpx.AsyncClient() as http:
            token_resp = await http.post(
                cfg["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            access_token = token_data.get("access_token")
            if not access_token:
                raise ValueError("No access_token in OAuth token response")

            # Fetch userinfo
            userinfo_resp = await http.get(
                cfg["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

        subject = userinfo.get("sub")
        email = userinfo.get("email") or ""
        name = userinfo.get("name") or userinfo.get("given_name") or (email.split("@")[0] if "@" in email else "")

        if not subject:
            raise ValueError("OAuth userinfo did not return a 'sub' claim")

        # Look up or create user
        user = store.get_user_by_oauth(provider, subject)
        if user is None:
            # Auto-provision as viewer; admin must grant domain access
            username = _safe_username(name, email, store)
            user = store.create_oauth_user(
                username=username,
                email=email,
                provider=provider,
                subject=subject,
                role="viewer",
            )
            logger.info(
                f"Auto-provisioned OAuth user {username!r} via {provider} (sub={subject!r})"
            )
        else:
            logger.info(f"OAuth login for existing user {user.username!r} via {provider}")

        if not user.is_active:
            raise ValueError("Account is inactive")

        return create_access_token(user.id, user.username, user.role)


def _safe_username(name: str, email: str, store: AuthStore) -> str:
    """Derive a unique, safe username from the OAuth display name or email."""
    import re
    cleaned_name = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip())[:30]
    email_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", email.split("@")[0].lower())[:30]
    base = cleaned_name or email_prefix or "user"
    candidate = base
    suffix = 1
    while store.user_exists(username=candidate, email=""):
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


# Module-level singleton
_manager: Optional[OAuthManager] = None


def get_oauth_manager() -> OAuthManager:
    global _manager
    if _manager is None:
        from app.config import settings
        _manager = OAuthManager(settings)
    return _manager
