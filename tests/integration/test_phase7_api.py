"""
Integration Tests for Phase 7 API Endpoints

Routes use lazy imports inside function bodies, so we patch at source:
  - app.views.registry.get_registry
  - app.database.connection.get_db
  - app.agents.orchestrator.Orchestrator
  - app.database.index_optimizer.get_optimizer
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str = "admin", domains=None):
    from app.auth.store import User
    return User(
        id="test-user",
        username="tester",
        email="tester@test.com",
        password_hash="",
        role=role,
        allowed_domains=domains or ["sales", "finance", "operations"],
        is_active=True,
        created_at=datetime.utcnow().isoformat(),
    )


_MOCK_RESULT = {
    "result": [{"region": "WEST", "total": 100}],
    "row_count": 1,
    "sql": "SELECT region, SUM(amount) FROM sales_fact GROUP BY region",
    "views": ["sales_fact"],
    "domain": "sales",
    "routing_confidence": 0.9,
    "confidence": 0.85,
    "state": "complete",
    "cache_hit": False,
    "conversation_id": "conv-123",
    "suggestions": [],
    "interpretation_method": "llm",
}

# Shared context managers for patching the lazy-imported dependencies
_SOURCE_PATCHES = [
    patch("app.views.registry.get_registry", return_value=MagicMock()),
    patch("app.database.connection.get_db", return_value=MagicMock()),
]


def _orch_cls(result=None):
    inst = MagicMock()
    inst.process_query.return_value = result or dict(_MOCK_RESULT)
    cls = MagicMock(return_value=inst)
    return cls


# ---------------------------------------------------------------------------
# 7.1 Async Job API
# ---------------------------------------------------------------------------

class TestAsyncJobAPI:

    @pytest.fixture
    def client(self):
        from app.api.routes.jobs import router
        from app.auth.dependencies import get_current_user
        from app.jobs.store import JobStore

        user = _make_user()
        store = JobStore(max_workers=2)
        cls = _orch_cls()

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_current_user] = lambda: user

        with patch("app.api.routes.jobs.get_job_store", return_value=store), \
             patch("app.agents.orchestrator.Orchestrator", cls), \
             patch("app.views.registry.get_registry", return_value=MagicMock()), \
             patch("app.database.connection.get_db", return_value=MagicMock()):
            yield TestClient(mini_app)

    def test_submit_returns_job_id(self, client):
        resp = client.post("/api/query/execute-async", json={"question": "Total sales by region"})
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_poll_job_eventually_completes(self, client):
        resp = client.post("/api/query/execute-async", json={"question": "Total sales by region"})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        from app.jobs.store import JobStatus
        deadline = time.time() + 5
        status = "pending"
        while time.time() < deadline and status not in ("complete", "failed"):
            poll = client.get(f"/api/jobs/{job_id}")
            assert poll.status_code == 200
            status = poll.json()["status"]
            time.sleep(0.1)
        assert status == "complete"

    def test_get_unknown_job_returns_404(self, client):
        assert client.get("/api/jobs/nonexistent-id-xyz").status_code == 404

    def test_list_jobs_returns_list(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json()["jobs"], list)


# ---------------------------------------------------------------------------
# 7.3 Admin Domain Onboarding API
# ---------------------------------------------------------------------------

class TestAdminDomainAPI:

    @pytest.fixture
    def client(self, tmp_path):
        from app.api.routes.admin import router
        from app.auth.dependencies import get_current_user
        from app.onboarding.registry import DomainRegistry

        user = _make_user(role="admin")
        domain_registry = DomainRegistry(db_path=str(tmp_path / "test_admin.db"))

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_current_user] = lambda: user

        with patch("app.api.routes.admin.get_domain_registry", return_value=domain_registry), \
             patch("app.api.routes.admin._reload_orchestrator", return_value=None):
            yield TestClient(mini_app)

    def test_register_domain(self, client):
        resp = client.post("/api/admin/domains", json={
            "name": "hr", "description": "Human Resources",
            "keywords": ["employee"], "view_names": [],
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "hr"

    def test_list_domains(self, client):
        client.post("/api/admin/domains", json={"name": "mktg", "description": "Marketing", "keywords": []})
        resp = client.get("/api/admin/domains")
        assert resp.status_code == 200
        assert any(d["name"] == "mktg" for d in resp.json())

    def test_delete_domain(self, client):
        client.post("/api/admin/domains", json={"name": "temp2", "description": "Temp", "keywords": []})
        resp = client.delete("/api/admin/domains/temp2")
        assert resp.status_code == 200
        assert resp.json()["name"] == "temp2"

    def test_delete_nonexistent_returns_404(self, client):
        assert client.delete("/api/admin/domains/does-not-exist").status_code == 404

    def test_register_builtin_conflict_returns_409(self, client):
        resp = client.post("/api/admin/domains", json={"name": "sales", "description": "Conflict", "keywords": []})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 7.4 Export API
# ---------------------------------------------------------------------------

class TestExportAPI:

    @pytest.fixture
    def client(self):
        from app.api.routes.export import router
        from app.auth.dependencies import get_current_user

        user = _make_user()
        cls = _orch_cls()

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_current_user] = lambda: user

        with patch("app.agents.orchestrator.Orchestrator", cls), \
             patch("app.views.registry.get_registry", return_value=MagicMock()), \
             patch("app.database.connection.get_db", return_value=MagicMock()):
            yield TestClient(mini_app)

    def test_export_json(self, client):
        resp = client.post("/api/query/export", json={"question": "Total sales", "format": "json"})
        assert resp.status_code == 200
        assert "json" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        import json
        assert isinstance(json.loads(resp.content), list)

    def test_export_csv(self, client):
        resp = client.post("/api/query/export", json={"question": "Total sales", "format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_excel(self, client):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")
        resp = client.post("/api/query/export", json={"question": "Total sales", "format": "excel"})
        assert resp.status_code == 200
        assert "spreadsheet" in resp.headers["content-type"]

    def test_export_default_filename(self, client):
        resp = client.post("/api/query/export", json={"question": "q", "format": "json"})
        assert "meridian_export" in resp.headers["content-disposition"]

    def test_export_custom_filename(self, client):
        resp = client.post("/api/query/export", json={"question": "q", "format": "csv", "filename": "my_report"})
        assert "my_report.csv" in resp.headers["content-disposition"]


# ---------------------------------------------------------------------------
# 7.5 Explain flag on execute endpoint
# ---------------------------------------------------------------------------

class TestExplainFlag:

    @pytest.fixture
    def client(self):
        from app.api.routes.query import router
        from app.auth.dependencies import get_current_user

        user = _make_user()
        cls = _orch_cls()

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_current_user] = lambda: user

        with patch("app.agents.orchestrator.Orchestrator", cls), \
             patch("app.views.registry.get_registry", return_value=MagicMock()), \
             patch("app.database.connection.get_db", return_value=MagicMock()):
            yield TestClient(mini_app)

    def test_explain_false_no_explain_key(self, client):
        resp = client.post("/api/query/execute", json={"question": "Total sales", "explain": False})
        assert resp.status_code == 200
        assert "explain" not in resp.json()

    def test_explain_true_adds_explain_block(self, client):
        resp = client.post("/api/query/execute", json={"question": "Total sales by region", "explain": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "explain" in data
        explain = data["explain"]
        assert "routing_decision" in explain
        assert "sql_generated" in explain
        assert "views_selected" in explain


# ---------------------------------------------------------------------------
# 7.6 Performance admin endpoint
# ---------------------------------------------------------------------------

class TestPerformanceEndpoint:

    @pytest.fixture
    def client(self, tmp_path):
        from app.api.routes.admin import router
        from app.auth.dependencies import get_current_user
        from app.database.index_optimizer import IndexOptimizer
        from app.onboarding.registry import DomainRegistry

        user = _make_user(role="admin")
        optimizer = IndexOptimizer()
        optimizer.analyzer.record_query("sales_fact", ["region"], 150.0)
        domain_registry = DomainRegistry(db_path=str(tmp_path / "test_perf.db"))

        mini_app = FastAPI()
        mini_app.include_router(router)
        mini_app.dependency_overrides[get_current_user] = lambda: user

        # Patch get_optimizer at source since admin.py imports it lazily
        with patch("app.database.index_optimizer.get_optimizer", return_value=optimizer), \
             patch("app.api.routes.admin.get_domain_registry", return_value=domain_registry), \
             patch("app.api.routes.admin._reload_orchestrator"):
            yield TestClient(mini_app)

    def test_performance_endpoint_returns_report(self, client):
        resp = client.get("/api/admin/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "slow_queries" in data
        assert "pattern_analysis" in data
