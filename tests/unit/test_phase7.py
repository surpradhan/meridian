"""
Unit Tests for Phase 7: Scale & Polish

Covers:
- 7.1 JobStore: submit, poll, cancel, cleanup
- 7.2 MeridianStreamingCallback: token queuing, aiter_tokens
- 7.3 DomainRegistry: register, list, get, delete, SQLite persistence
- 7.4 Exporters: to_json, to_csv, to_excel
- 7.5 ExplainResponse builder: field extraction
- 7.6 IndexOptimizer singleton: get_optimizer, record_query
"""

import asyncio
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 7.1 JobStore
# ---------------------------------------------------------------------------

class TestJobStore:

    def test_submit_returns_job_id(self):
        from app.jobs.store import JobStore, JobStatus
        store = JobStore(max_workers=2)
        job_id = store.submit(lambda: {"done": True})
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_job_completes_successfully(self):
        from app.jobs.store import JobStore, JobStatus
        store = JobStore(max_workers=2)
        job_id = store.submit(lambda: {"answer": 42})
        # Wait for completion
        deadline = time.time() + 5
        while time.time() < deadline:
            record = store.get(job_id)
            if record and record.status == JobStatus.COMPLETE:
                break
            time.sleep(0.05)
        record = store.get(job_id)
        assert record is not None
        assert record.status == JobStatus.COMPLETE
        assert record.result == {"answer": 42}
        assert record.error is None

    def test_job_captures_exception(self):
        from app.jobs.store import JobStore, JobStatus
        store = JobStore(max_workers=2)

        def boom():
            raise ValueError("test error")

        job_id = store.submit(boom)
        deadline = time.time() + 5
        while time.time() < deadline:
            record = store.get(job_id)
            if record and record.status == JobStatus.FAILED:
                break
            time.sleep(0.05)
        record = store.get(job_id)
        assert record.status == JobStatus.FAILED
        assert "test error" in record.error

    def test_get_unknown_job_returns_none(self):
        from app.jobs.store import JobStore
        store = JobStore()
        assert store.get("nonexistent-id") is None

    def test_cancel_completed_job_removes_it(self):
        from app.jobs.store import JobStore, JobStatus
        store = JobStore(max_workers=2)
        job_id = store.submit(lambda: "done")
        deadline = time.time() + 5
        while time.time() < deadline:
            r = store.get(job_id)
            if r and r.status == JobStatus.COMPLETE:
                break
            time.sleep(0.05)
        result = store.cancel(job_id)
        assert result is True
        assert store.get(job_id) is None

    def test_cleanup_removes_old_jobs(self):
        from app.jobs.store import JobStore, JobStatus, JobRecord
        store = JobStore()
        # Insert a fake old completed job directly
        old_record = JobRecord(
            job_id="old-job",
            status=JobStatus.COMPLETE,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            result={"x": 1},
        )
        with store._lock:
            store._jobs["old-job"] = old_record

        removed = store.cleanup_old_jobs(max_age_seconds=1)
        assert removed == 1
        assert store.get("old-job") is None

    def test_singleton_returns_same_instance(self):
        from app.jobs.store import get_job_store
        s1 = get_job_store()
        s2 = get_job_store()
        assert s1 is s2


# ---------------------------------------------------------------------------
# 7.2 MeridianStreamingCallback
# ---------------------------------------------------------------------------

class TestMeridianStreamingCallback:

    def test_iter_tokens_yields_pushed_tokens(self):
        from app.agents.streaming import MeridianStreamingCallback
        cb = MeridianStreamingCallback()
        cb.on_llm_new_token("hello")
        cb.on_llm_new_token(" world")
        cb.on_llm_end(None)
        tokens = list(cb.iter_tokens())
        assert tokens == ["hello", " world"]

    def test_mark_done_ends_iteration(self):
        from app.agents.streaming import MeridianStreamingCallback
        cb = MeridianStreamingCallback()
        cb.on_llm_new_token("tok")
        cb.mark_done()
        tokens = list(cb.iter_tokens())
        assert tokens == ["tok"]

    def test_on_llm_error_ends_iteration(self):
        from app.agents.streaming import MeridianStreamingCallback
        cb = MeridianStreamingCallback()
        cb.on_llm_new_token("before")
        cb.on_llm_error(RuntimeError("oops"))
        tokens = list(cb.iter_tokens())
        assert tokens == ["before"]

    @pytest.mark.asyncio
    async def test_aiter_tokens_yields_tokens(self):
        from app.agents.streaming import MeridianStreamingCallback
        cb = MeridianStreamingCallback()

        def _push():
            cb.on_llm_new_token("a")
            cb.on_llm_new_token("b")
            cb.on_llm_end(None)

        thread = threading.Thread(target=_push)
        thread.start()

        tokens = []
        async for t in cb.aiter_tokens():
            tokens.append(t)
        thread.join()
        assert tokens == ["a", "b"]


# ---------------------------------------------------------------------------
# 7.3 DomainRegistry (onboarding)
# ---------------------------------------------------------------------------

class TestDomainRegistry:

    @pytest.fixture
    def registry(self, tmp_path):
        from app.onboarding.registry import DomainRegistry
        return DomainRegistry(db_path=str(tmp_path / "test_domains.db"))

    def test_register_and_list(self, registry):
        from app.onboarding.models import DomainConfig
        config = DomainConfig(
            name="hr",
            description="Human Resources",
            keywords=["employee", "salary"],
            view_names=["employee_fact"],
        )
        result = registry.register(config)
        assert result.name == "hr"

        domains = registry.list_domains()
        assert any(d.name == "hr" for d in domains)

    def test_get_domain(self, registry):
        from app.onboarding.models import DomainConfig
        config = DomainConfig(name="legal", description="Legal", keywords=["contract"])
        registry.register(config)
        found = registry.get_domain("legal")
        assert found is not None
        assert found.name == "legal"

    def test_get_missing_domain_returns_none(self, registry):
        assert registry.get_domain("nonexistent") is None

    def test_delete_domain(self, registry):
        from app.onboarding.models import DomainConfig
        config = DomainConfig(name="temp", description="Temp", keywords=["tmp"])
        registry.register(config)
        deleted = registry.delete_domain("temp")
        assert deleted is True
        assert registry.get_domain("temp") is None

    def test_delete_missing_returns_false(self, registry):
        assert registry.delete_domain("does_not_exist") is False

    def test_cannot_register_builtin_domain(self, registry):
        from app.onboarding.models import DomainConfig
        config = DomainConfig(name="sales", description="Conflict!", keywords=[])
        with pytest.raises(ValueError, match="built-in"):
            registry.register(config)

    def test_persistence_across_instances(self, tmp_path):
        from app.onboarding.registry import DomainRegistry
        from app.onboarding.models import DomainConfig
        db = str(tmp_path / "persist.db")
        r1 = DomainRegistry(db_path=db)
        r1.register(DomainConfig(name="mktg", description="Marketing", keywords=["ad"]))

        r2 = DomainRegistry(db_path=db)
        assert r2.get_domain("mktg") is not None

    def test_register_updates_existing(self, registry):
        from app.onboarding.models import DomainConfig
        config = DomainConfig(name="it", description="IT", keywords=["server"])
        registry.register(config)
        updated = DomainConfig(name="it", description="IT Updated", keywords=["cloud", "server"])
        registry.register(updated)
        found = registry.get_domain("it")
        assert found.description == "IT Updated"
        assert "cloud" in found.keywords


# ---------------------------------------------------------------------------
# 7.4 Exporters
# ---------------------------------------------------------------------------

class TestExporters:

    SAMPLE_ROWS = [
        {"region": "WEST", "total": 42500.0},
        {"region": "EAST", "total": 38200.0},
    ]

    def test_to_json_produces_valid_json(self):
        from app.export.exporters import to_json
        data = to_json(self.SAMPLE_ROWS)
        assert isinstance(data, bytes)
        parsed = json.loads(data)
        assert len(parsed) == 2
        assert parsed[0]["region"] == "WEST"

    def test_to_json_empty_rows(self):
        from app.export.exporters import to_json
        data = to_json([])
        assert json.loads(data) == []

    def test_to_csv_produces_csv(self):
        from app.export.exporters import to_csv
        data = to_csv(self.SAMPLE_ROWS)
        assert isinstance(data, bytes)
        text = data.decode("utf-8-sig")  # strip BOM
        assert "region" in text
        assert "WEST" in text

    def test_to_csv_empty_rows(self):
        from app.export.exporters import to_csv
        data = to_csv([])
        assert isinstance(data, bytes)

    def test_to_excel_produces_bytes(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")

        from app.export.exporters import to_excel
        data = to_excel(self.SAMPLE_ROWS)
        assert isinstance(data, bytes)
        assert len(data) > 0
        # Verify it's a valid xlsx (PK magic bytes)
        assert data[:2] == b"PK"

    def test_to_excel_empty_rows(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")

        from app.export.exporters import to_excel
        data = to_excel([])
        assert isinstance(data, bytes)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# 7.5 ExplainResponse builder
# ---------------------------------------------------------------------------

class TestExplainBuilder:

    def _make_result(self, **overrides) -> Dict[str, Any]:
        base = {
            "domain": "sales",
            "routing_confidence": 0.92,
            "confidence": 0.85,
            "views": ["sales_fact", "customer_dim"],
            "sql": "SELECT region, SUM(amount) FROM sales_fact GROUP BY region",
            "result": [{"region": "WEST", "total": 100}],
            "row_count": 1,
            "interpretation_method": "llm",
        }
        base.update(overrides)
        return base

    def test_basic_fields_populated(self):
        from app.explain.builder import build_explain_response
        result = self._make_result()
        explain = build_explain_response("Total sales by region", result)
        assert explain.query == "Total sales by region"
        assert explain.routing_decision["domain"] == "sales"
        assert explain.routing_decision["confidence"] == 0.92
        assert explain.views_selected == ["sales_fact", "customer_dim"]
        assert "SELECT" in explain.sql_generated

    def test_join_paths_inferred(self):
        from app.explain.builder import build_explain_response
        result = self._make_result(views=["sales_fact", "region_dim", "territory_dim"])
        explain = build_explain_response("q", result)
        assert len(explain.join_paths) == 2
        assert "sales_fact -> region_dim" in explain.join_paths

    def test_time_resolution_populated(self):
        from app.explain.builder import build_explain_response
        result = self._make_result(
            time_expression="last_quarter",
            time_start="2025-10-01",
            time_end="2025-12-31",
        )
        explain = build_explain_response("q", result)
        assert explain.time_resolution is not None
        assert explain.time_resolution["expression"] == "last_quarter"

    def test_no_time_resolution_when_absent(self):
        from app.explain.builder import build_explain_response
        result = self._make_result()
        explain = build_explain_response("q", result)
        assert explain.time_resolution is None

    def test_model_dump_serializable(self):
        from app.explain.builder import build_explain_response
        result = self._make_result()
        explain = build_explain_response("q", result)
        data = explain.model_dump()
        assert isinstance(data, dict)
        json.dumps(data)  # must be JSON-serializable


# ---------------------------------------------------------------------------
# 7.6 IndexOptimizer singleton
# ---------------------------------------------------------------------------

class TestIndexOptimizerSingleton:

    def test_get_optimizer_returns_instance(self):
        from app.database.index_optimizer import get_optimizer, IndexOptimizer
        opt = get_optimizer()
        assert isinstance(opt, IndexOptimizer)

    def test_singleton_same_object(self):
        from app.database.index_optimizer import get_optimizer
        assert get_optimizer() is get_optimizer()

    def test_record_query_updates_patterns(self):
        from app.database.index_optimizer import IndexOptimizer
        opt = IndexOptimizer()
        opt.analyzer.record_query("test_table", ["col_a"], 200.0)
        assert len(opt.analyzer.patterns) == 1
        key = "test_table:col_a"
        assert opt.analyzer.patterns[key].frequency == 1

    def test_analyze_workload_returns_dict(self):
        from app.database.index_optimizer import IndexOptimizer
        opt = IndexOptimizer()
        result = opt.analyze_workload()
        assert "recommendations" in result
        assert "slow_queries" in result
        assert "pattern_analysis" in result

    def test_slow_query_tracked(self):
        from app.database.index_optimizer import IndexOptimizer
        opt = IndexOptimizer()
        opt.analyzer.record_query("slow_table", ["col_x"], 500.0)  # > 100ms threshold
        assert len(opt.analyzer.slow_queries) == 1
        assert opt.analyzer.slow_queries[0]["table"] == "slow_table"
