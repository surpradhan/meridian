"""
Integration tests for the /api/history HTTP endpoints.

Uses FastAPI TestClient with a minimal app (only the history router) and a
patched HistoryManager singleton so each test gets an isolated SQLite database.
"""

import pytest
from datetime import datetime
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def history_manager(tmp_path):
    """Provide a fresh HistoryManager backed by a temp SQLite file."""
    from app.history.manager import HistoryManager
    return HistoryManager(db_path=str(tmp_path / "api_test_history.db"))


@pytest.fixture
def client(history_manager):
    """Minimal TestClient with just the history router, auth bypassed, temp HistoryManager."""
    from app.api.routes.history import router
    from app.auth.dependencies import get_current_user
    from app.auth.store import User

    # Synthetic admin user — no DB connection needed.
    test_user = User(
        id="test-user-id",
        username="tester",
        email="tester@test.com",
        password_hash="",
        role="admin",
        allowed_domains=["sales", "finance", "operations"],
        is_active=True,
        created_at=datetime.utcnow().isoformat(),
    )

    mini_app = FastAPI()
    mini_app.include_router(router)
    # Bypass JWT + AuthStore (which would try to open the PostgreSQL URL as SQLite in CI).
    mini_app.dependency_overrides[get_current_user] = lambda: test_user

    # Routes import get_history_manager lazily inside each handler, so patch at source.
    with patch("app.history.manager.get_history_manager", return_value=history_manager):
        yield TestClient(mini_app)


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------

class TestListHistory:

    def test_empty_history_returns_empty_list(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_saved_entries_appear_in_list(self, client, history_manager):
        history_manager.save("How many sales?", {"domain": "sales", "row_count": 5})
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["question"] == "How many sales?"

    def test_list_returns_newest_first(self, client, history_manager):
        history_manager.save("First", {"domain": "sales", "row_count": 1})
        history_manager.save("Second", {"domain": "sales", "row_count": 2})
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["question"] == "Second"

    def test_list_limit_query_param_respected(self, client, history_manager):
        for i in range(5):
            history_manager.save(f"Query {i}", {"domain": "sales", "row_count": i})
        resp = client.get("/api/history?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_limit_capped_at_200(self, client, history_manager):
        """limit > 200 should be silently capped, not cause an error."""
        resp = client.get("/api/history?limit=999")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/history/{id}
# ---------------------------------------------------------------------------

class TestGetHistoryEntry:

    def test_get_existing_entry(self, client, history_manager):
        hid = history_manager.save("Show ledger", {"domain": "finance", "row_count": 3})
        resp = client.get(f"/api/history/{hid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == hid
        assert data["question"] == "Show ledger"
        assert data["domain"] == "finance"

    def test_get_nonexistent_entry_returns_404(self, client):
        resp = client.get("/api/history/nonexistent-uuid")
        assert resp.status_code == 404

    def test_get_entry_includes_conversation_id(self, client, history_manager):
        hid = history_manager.save(
            "Sales by region",
            {"domain": "sales", "row_count": 7},
            conversation_id="conv-xyz",
        )
        resp = client.get(f"/api/history/{hid}")
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "conv-xyz"


# ---------------------------------------------------------------------------
# DELETE /api/history/{id}
# ---------------------------------------------------------------------------

class TestDeleteHistoryEntry:

    def test_delete_existing_entry(self, client, history_manager):
        hid = history_manager.save("To delete", {"domain": "operations", "row_count": 1})
        resp = client.delete(f"/api/history/{hid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["id"] == hid

    def test_delete_removes_entry_from_list(self, client, history_manager):
        hid = history_manager.save("To delete", {"domain": "operations", "row_count": 1})
        client.delete(f"/api/history/{hid}")
        resp = client.get("/api/history")
        ids = [e["id"] for e in resp.json()]
        assert hid not in ids

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/history/nonexistent-uuid")
        assert resp.status_code == 404

    def test_delete_twice_returns_404_on_second(self, client, history_manager):
        hid = history_manager.save("Once", {"domain": "sales", "row_count": 1})
        client.delete(f"/api/history/{hid}")
        resp = client.delete(f"/api/history/{hid}")
        assert resp.status_code == 404
