"""
Unit tests for Phase 5 auth components:
  - AuthStore (user CRUD, count, audit log)
  - JWT creation and validation (including expiry)
  - Field masking (permissions)
  - Domain access control logic (fail-closed)
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# AuthStore
# ---------------------------------------------------------------------------

class TestAuthStore:

    @pytest.fixture
    def store(self, tmp_path):
        from app.auth.store import AuthStore
        return AuthStore(db_path=str(tmp_path / "test_auth.db"))

    def test_create_and_retrieve_user(self, store):
        user = store.create_user("alice", "alice@example.com", "hashed_pw", role="analyst")
        found = store.get_user_by_username("alice")
        assert found is not None
        assert found.id == user.id
        assert found.username == "alice"
        assert found.role == "analyst"

    def test_get_user_by_id(self, store):
        user = store.create_user("bob", "bob@example.com", "hashed_pw")
        found = store.get_user_by_id(user.id)
        assert found is not None
        assert found.username == "bob"

    def test_get_nonexistent_user_returns_none(self, store):
        assert store.get_user_by_username("nobody") is None
        assert store.get_user_by_id("fake-uuid") is None

    def test_user_exists_by_username(self, store):
        store.create_user("carol", "carol@example.com", "pw")
        assert store.user_exists(username="carol")
        assert not store.user_exists(username="dave")

    def test_user_exists_by_email(self, store):
        store.create_user("eve", "eve@example.com", "pw")
        assert store.user_exists(email="eve@example.com")
        assert not store.user_exists(email="other@example.com")

    def test_allowed_domains_stored_correctly(self, store):
        user = store.create_user(
            "frank", "frank@example.com", "pw",
            role="analyst",
            allowed_domains=["sales", "finance"],
        )
        found = store.get_user_by_id(user.id)
        assert found.allowed_domains == ["sales", "finance"]

    def test_count_users_empty_store(self, store):
        assert store.count_users() == 0

    def test_count_users_after_creation(self, store):
        store.create_user("u1", "u1@e.com", "pw")
        store.create_user("u2", "u2@e.com", "pw")
        assert store.count_users() == 2

    def test_audit_log_write_and_list(self, store):
        store.log_audit(
            action="auth.login",
            resource="/api/auth/login",
            user_id="uid-1",
            username="alice",
            status_code=200,
            client_ip="127.0.0.1",
        )
        entries = store.list_audit(limit=10)
        assert len(entries) == 1
        assert entries[0]["username"] == "alice"
        assert entries[0]["action"] == "auth.login"
        assert entries[0]["status_code"] == 200

    def test_audit_log_anonymous_entry(self, store):
        store.log_audit(action="query.execute", resource="/api/query/execute")
        entries = store.list_audit()
        assert entries[0]["user_id"] is None
        assert entries[0]["username"] is None

    def test_audit_log_failed_login_recorded(self, store):
        store.log_audit(
            action="auth.login.failed",
            resource="/api/auth/login",
            username="attacker",
            status_code=401,
            client_ip="10.0.0.1",
        )
        entries = store.list_audit()
        assert entries[0]["action"] == "auth.login.failed"
        assert entries[0]["status_code"] == 401


# ---------------------------------------------------------------------------
# Domain access control — fail-closed semantics
# ---------------------------------------------------------------------------

class TestUserDomainAccess:

    def _make_user(self, role, allowed_domains):
        from app.auth.store import User
        return User(
            id="u1", username="u", email="u@e.com",
            password_hash="x", role=role,
            allowed_domains=allowed_domains,
            is_active=True, created_at="2026-01-01",
        )

    def test_admin_accesses_all_domains(self):
        user = self._make_user("admin", [])
        assert user.can_access_domain("sales")
        assert user.can_access_domain("finance")
        assert user.can_access_domain("operations")

    def test_analyst_limited_to_allowed_domains(self):
        user = self._make_user("analyst", ["sales"])
        assert user.can_access_domain("sales")
        assert not user.can_access_domain("finance")

    def test_analyst_empty_domains_means_no_access(self):
        """Fail closed: empty allowed_domains grants NO access for non-admins."""
        user = self._make_user("analyst", [])
        assert not user.can_access_domain("sales")
        assert not user.can_access_domain("finance")
        assert not user.can_access_domain("operations")

    def test_viewer_empty_domains_means_no_access(self):
        user = self._make_user("viewer", [])
        assert not user.can_access_domain("sales")

    def test_can_execute_queries_by_role(self):
        from app.auth.store import User

        def make(role):
            return User("u", "u", "u@e.com", "x", role, [], True, "2026-01-01")

        assert make("admin").can_execute_queries() is True
        assert make("analyst").can_execute_queries() is True
        assert make("viewer").can_execute_queries() is False


# ---------------------------------------------------------------------------
# JWT — including expiry
# ---------------------------------------------------------------------------

class TestJWT:
    """Test JWT utilities with a mock settings object."""

    @pytest.fixture(autouse=True)
    def mock_settings(self, monkeypatch):
        import app.auth.jwt as jwt_module
        mock = MagicMock()
        mock.secret_key = "test-secret-key-32-bytes-long-xxx"
        mock.jwt_algorithm = "HS256"
        mock.jwt_expiration_hours = 24
        monkeypatch.setattr(jwt_module, "_settings", lambda: mock)

    def test_create_and_decode_token(self):
        from app.auth.jwt import create_access_token, decode_access_token
        token = create_access_token("uid-1", "alice", "analyst")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "uid-1"
        assert payload["username"] == "alice"
        assert payload["role"] == "analyst"

    def test_invalid_token_returns_none(self):
        from app.auth.jwt import decode_access_token
        assert decode_access_token("not.a.token") is None

    def test_tampered_token_returns_none(self):
        from app.auth.jwt import create_access_token, decode_access_token
        token = create_access_token("uid-1", "alice", "analyst")
        tampered = token[:-5] + "XXXXX"
        assert decode_access_token(tampered) is None

    def test_expired_token_returns_none(self, monkeypatch):
        """A token whose exp is in the past must be rejected."""
        import app.auth.jwt as jwt_module
        from jose import jwt

        # Create a token that expired 1 hour ago
        expired_payload = {
            "sub": "uid-1",
            "username": "alice",
            "role": "analyst",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow() - timedelta(hours=25),
        }
        s = jwt_module._settings()
        expired_token = jwt.encode(expired_payload, s.secret_key, algorithm=s.jwt_algorithm)

        assert jwt_module.decode_access_token(expired_token) is None


# ---------------------------------------------------------------------------
# Field masking
# ---------------------------------------------------------------------------

class TestFieldMasking:

    def test_admin_sees_all_fields(self):
        from app.auth.permissions import mask_sensitive_fields
        data = [{"name": "Alice", "salary": 100000, "ssn": "123-45-6789"}]
        result = mask_sensitive_fields(data, "admin")
        assert result[0]["salary"] == 100000
        assert result[0]["ssn"] == "123-45-6789"

    def test_analyst_sees_all_fields(self):
        from app.auth.permissions import mask_sensitive_fields
        data = {"salary": 80000, "name": "Bob"}
        result = mask_sensitive_fields(data, "analyst")
        assert result["salary"] == 80000

    def test_viewer_gets_sensitive_fields_masked(self):
        from app.auth.permissions import mask_sensitive_fields
        data = [{"name": "Carol", "salary": 90000, "ssn": "987-65-4321"}]
        result = mask_sensitive_fields(data, "viewer")
        assert result[0]["name"] == "Carol"
        assert result[0]["salary"] == "***MASKED***"
        assert result[0]["ssn"] == "***MASKED***"

    def test_viewer_non_sensitive_fields_unchanged(self):
        from app.auth.permissions import mask_sensitive_fields
        data = {"product": "Widget", "total_sales": 5000, "region": "WEST"}
        result = mask_sensitive_fields(data, "viewer")
        assert result["product"] == "Widget"
        assert result["total_sales"] == 5000

    def test_masking_works_on_nested_lists(self):
        from app.auth.permissions import mask_sensitive_fields
        data = [
            {"employee": "Dave", "compensation": 120000},
            {"employee": "Eve", "compensation": 95000},
        ]
        result = mask_sensitive_fields(data, "viewer")
        assert all(r["compensation"] == "***MASKED***" for r in result)

    def test_non_dict_non_list_passthrough(self):
        from app.auth.permissions import mask_sensitive_fields
        assert mask_sensitive_fields("hello", "viewer") == "hello"
        assert mask_sensitive_fields(42, "viewer") == 42
        assert mask_sensitive_fields(None, "viewer") is None


# ---------------------------------------------------------------------------
# Audit log action name derivation
# ---------------------------------------------------------------------------

class TestSemanticAuditActions:

    def test_known_routes_get_semantic_names(self):
        from app.api.middleware import _semantic_action
        assert _semantic_action("POST",   "/api/auth/login")       == "auth.login"
        assert _semantic_action("POST",   "/api/auth/register")    == "auth.register"
        assert _semantic_action("GET",    "/api/auth/me")          == "auth.me"
        assert _semantic_action("POST",   "/api/query/execute")    == "query.execute"
        assert _semantic_action("GET",    "/api/query/domains")    == "query.domains"
        assert _semantic_action("GET",    "/api/history")          == "history.list"
        assert _semantic_action("DELETE", "/api/history/550e8400-e29b-41d4-a716-446655440000") == "history.delete"

    def test_unknown_route_falls_back_gracefully(self):
        from app.api.middleware import _semantic_action
        result = _semantic_action("GET", "/some/unknown/path")
        assert result  # Non-empty string
        assert "GET" in result.upper() or "get" in result
