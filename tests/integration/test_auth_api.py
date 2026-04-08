"""
Integration tests for Phase 5 auth API endpoints.

Covers:
  - Bootstrap registration (first user → forced admin)
  - Admin-only registration after bootstrap
  - Login success / failure
  - Failed login audit logging
  - /me endpoint
  - All protected routes reject unauthenticated requests
  - Analyst with empty allowed_domains is denied domain access (fail-closed)
  - History user-scoping
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared mock settings (avoids pydantic_settings import in this test env)
# ---------------------------------------------------------------------------

def _mock_settings():
    s = MagicMock()
    s.secret_key = "test-secret-for-integration-tests-32b"
    s.jwt_algorithm = "HS256"
    s.jwt_expiration_hours = 24
    return s


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_store(tmp_path):
    from app.auth.store import AuthStore
    return AuthStore(db_path=str(tmp_path / "auth_test.db"))


@pytest.fixture
def auth_client(auth_store):
    """Minimal app with only the auth router, backed by a temp AuthStore."""
    import app.auth.jwt as jwt_module
    from app.auth.routes import router
    from app.auth.store import get_auth_store

    mini_app = FastAPI()
    mini_app.include_router(router)
    mini_app.dependency_overrides[get_auth_store] = lambda: auth_store

    with patch.object(jwt_module, "_settings", _mock_settings):
        yield TestClient(mini_app)


@pytest.fixture
def admin_token(auth_client):
    """Register the first (bootstrap) admin and return their token."""
    auth_client.post("/api/auth/register", json={
        "username": "admin",
        "email": "admin@example.com",
        "password": "adminpassword",
    })
    resp = auth_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "adminpassword",
    })
    return resp.json()["access_token"]


@pytest.fixture
def analyst_token(auth_client, admin_token):
    """Admin creates an analyst with sales access; return analyst token."""
    auth_client.post(
        "/api/auth/register",
        json={
            "username": "analyst",
            "email": "analyst@example.com",
            "password": "analystpassword",
            "role": "analyst",
            "allowed_domains": ["sales"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = auth_client.post("/api/auth/login", json={
        "username": "analyst",
        "password": "analystpassword",
    })
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Bootstrap registration
# ---------------------------------------------------------------------------

class TestBootstrapRegistration:

    def test_first_registration_is_open_no_auth_required(self, auth_client):
        resp = auth_client.post("/api/auth/register", json={
            "username": "firstuser",
            "email": "first@example.com",
            "password": "password123",
            "role": "viewer",  # Will be overridden to admin
        })
        assert resp.status_code == 201
        # Bootstrap forces admin role regardless of what was requested
        assert resp.json()["role"] == "admin"

    def test_second_registration_without_auth_is_rejected(self, auth_client, admin_token):
        resp = auth_client.post("/api/auth/register", json={
            "username": "seconduser",
            "email": "second@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_admin_can_register_new_users(self, auth_client, admin_token):
        resp = auth_client.post(
            "/api/auth/register",
            json={
                "username": "newanalyst",
                "email": "newanalyst@example.com",
                "password": "password123",
                "role": "analyst",
                "allowed_domains": ["sales"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "analyst"

    def test_non_admin_cannot_register_new_users(self, auth_client, admin_token, analyst_token):
        resp = auth_client.post(
            "/api/auth/register",
            json={
                "username": "hacker",
                "email": "hacker@example.com",
                "password": "password123",
                "role": "admin",
            },
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Registration validation
# ---------------------------------------------------------------------------

class TestRegisterValidation:

    def test_invalid_role_returns_400(self, auth_client, admin_token):
        resp = auth_client.post(
            "/api/auth/register",
            json={"username": "bad", "email": "bad@e.com", "password": "password123", "role": "superadmin"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    def test_duplicate_username_returns_409(self, auth_client, admin_token):
        auth_client.post(
            "/api/auth/register",
            json={"username": "dupe", "email": "dupe@e.com", "password": "password123", "role": "viewer"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = auth_client.post(
            "/api/auth/register",
            json={"username": "dupe", "email": "other@e.com", "password": "password123"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    def test_short_password_returns_422(self, auth_client, admin_token):
        resp = auth_client.post(
            "/api/auth/register",
            json={"username": "shortpw", "email": "s@e.com", "password": "pw"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_success_returns_token(self, auth_client, admin_token):
        resp = auth_client.post("/api/auth/login", json={
            "username": "admin",
            "password": "adminpassword",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in_hours"] > 0

    def test_login_wrong_password_returns_401(self, auth_client, admin_token):
        resp = auth_client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self, auth_client):
        resp = auth_client.post("/api/auth/login", json={
            "username": "nobody",
            "password": "password",
        })
        assert resp.status_code == 401

    def test_failed_login_logged_to_audit(self, auth_client, auth_store):
        """Failed login attempts must appear in the audit log."""
        auth_client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "badpassword",
        })
        entries = auth_store.list_audit()
        failed = [e for e in entries if e["action"] == "auth.login.failed"]
        assert len(failed) == 1
        assert failed[0]["username"] == "nonexistent"
        assert failed[0]["status_code"] == 401

    def test_successful_login_logged_to_audit(self, auth_client, auth_store, admin_token):
        entries = auth_store.list_audit()
        success = [e for e in entries if e["action"] == "auth.login"]
        assert any(e["username"] == "admin" for e in success)


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------

class TestMe:

    def test_me_returns_profile_with_valid_token(self, auth_client, admin_token):
        resp = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "password_hash" not in data

    def test_me_without_token_returns_401(self, auth_client):
        resp = auth_client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, auth_client):
        resp = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not.a.valid.token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# All protected routes require authentication
# ---------------------------------------------------------------------------

class TestProtectedRoutes:

    @pytest.fixture
    def full_client(self, auth_store):
        import app.auth.jwt as jwt_module
        from app.api.routes.query import router as query_router
        from app.api.routes.history import router as history_router
        from app.auth.store import get_auth_store

        mini_app = FastAPI()
        mini_app.include_router(query_router)
        mini_app.include_router(history_router)
        mini_app.dependency_overrides[get_auth_store] = lambda: auth_store

        with patch.object(jwt_module, "_settings", _mock_settings):
            yield TestClient(mini_app)

    def test_execute_without_auth_returns_401(self, full_client):
        assert full_client.post("/api/query/execute", json={"question": "show sales"}).status_code == 401

    def test_validate_without_auth_returns_401(self, full_client):
        assert full_client.post("/api/query/validate", json={"question": "test"}).status_code == 401

    def test_domains_without_auth_returns_401(self, full_client):
        assert full_client.get("/api/query/domains").status_code == 401

    def test_explore_without_auth_returns_401(self, full_client):
        assert full_client.get("/api/query/explore?domain=sales").status_code == 401

    def test_history_list_without_auth_returns_401(self, full_client):
        assert full_client.get("/api/history").status_code == 401

    def test_history_get_without_auth_returns_401(self, full_client):
        assert full_client.get("/api/history/some-id").status_code == 401

    def test_history_delete_without_auth_returns_401(self, full_client):
        assert full_client.delete("/api/history/some-id").status_code == 401


# ---------------------------------------------------------------------------
# Domain access — analyst with empty allowed_domains is denied (fail-closed)
# ---------------------------------------------------------------------------

class TestDomainAccessControl:

    @pytest.fixture
    def restricted_client(self, auth_store):
        """Client with a locked-down analyst (no allowed_domains)."""
        import app.auth.jwt as jwt_module
        from app.api.routes.query import router as query_router
        from app.auth.store import get_auth_store, User
        from app.auth.dependencies import get_current_user

        # Analyst with no domain access
        locked_analyst = User(
            id="analyst-1",
            username="locked",
            email="locked@e.com",
            password_hash="x",
            role="analyst",
            allowed_domains=[],  # No domains — should be denied everywhere
            is_active=True,
            created_at="2026-01-01",
        )

        mini_app = FastAPI()
        mini_app.include_router(query_router)
        mini_app.dependency_overrides[get_auth_store] = lambda: auth_store
        mini_app.dependency_overrides[get_current_user] = lambda: locked_analyst

        with patch.object(jwt_module, "_settings", _mock_settings):
            yield TestClient(mini_app)

    def test_explore_denied_when_no_domain_access(self, restricted_client):
        resp = restricted_client.get("/api/query/explore?domain=sales")
        assert resp.status_code == 403

    def test_viewer_cannot_execute_queries(self, auth_store):
        """viewer role is blocked from execute regardless of domain access."""
        import app.auth.jwt as jwt_module
        from app.api.routes.query import router as query_router
        from app.auth.store import get_auth_store, User
        from app.auth.dependencies import get_current_user

        viewer = User(
            id="v1", username="viewer", email="v@e.com",
            password_hash="x", role="viewer",
            allowed_domains=["sales"], is_active=True, created_at="2026-01-01",
        )

        mini_app = FastAPI()
        mini_app.include_router(query_router)
        mini_app.dependency_overrides[get_auth_store] = lambda: auth_store
        mini_app.dependency_overrides[get_current_user] = lambda: viewer

        with patch.object(jwt_module, "_settings", _mock_settings):
            client = TestClient(mini_app)
            resp = client.post("/api/query/execute", json={"question": "show sales"})
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# History user scoping
# ---------------------------------------------------------------------------

class TestHistoryUserScoping:

    @pytest.fixture
    def history_manager(self, tmp_path):
        from app.history.manager import HistoryManager
        return HistoryManager(db_path=str(tmp_path / "scope_test.db"))

    def test_list_returns_only_own_entries(self, history_manager):
        history_manager.save("My query", {"domain": "sales"}, user_id="user-1")
        history_manager.save("Other query", {"domain": "finance"}, user_id="user-2")

        results = history_manager.list(user_id="user-1")
        assert len(results) == 1
        assert results[0]["question"] == "My query"

    def test_list_without_user_id_returns_all(self, history_manager):
        history_manager.save("Q1", {"domain": "sales"}, user_id="user-1")
        history_manager.save("Q2", {"domain": "finance"}, user_id="user-2")

        results = history_manager.list()
        assert len(results) == 2

    def test_user_id_persisted_on_save(self, history_manager):
        hid = history_manager.save("Query", {"domain": "sales"}, user_id="user-99")
        entry = history_manager.get(hid)
        assert entry["user_id"] == "user-99"
