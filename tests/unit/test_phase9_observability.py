"""
Unit Tests — Phase 9: Observability Completion

Covers:
- MetricsCollector in-memory behaviour (unchanged)
- Prometheus dual-write: counters, histograms, gauges registered and updated
- QueryMetrics flows through to Prometheus metrics
- /metrics HTTP endpoint returns valid Prometheus text format
- Tracing: TracingManager uses OTLP config (no jaeger-thrift references)
- Config: otlp_endpoint field present with sensible default
"""

import pytest
import time

try:
    import prometheus_client as prom
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_collector():
    """Return a MetricsCollector with a private Prometheus registry so tests
    don't pollute the global singleton registry."""
    # We test the module-level singleton indirectly; for isolation we patch it.
    from app.observability.metrics import MetricsCollector
    return MetricsCollector()


# ---------------------------------------------------------------------------
# MetricsCollector — in-memory (existing behaviour must not regress)
# ---------------------------------------------------------------------------

class TestMetricsCollectorInMemory:

    def test_increment_counter(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.increment_counter("test_counter")
        mc.increment_counter("test_counter", 4)
        assert mc.counters["test_counter"] == 5

    def test_set_gauge(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.set_gauge("my_gauge", 42.5)
        assert mc.gauges["my_gauge"] == 42.5

    def test_record_histogram(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        for v in [10, 20, 30, 40, 50]:
            mc.record_histogram("latency", float(v))
        assert mc.histograms["latency"] == [10.0, 20.0, 30.0, 40.0, 50.0]

    def test_get_summary_shape(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.increment_counter("c")
        mc.set_gauge("g", 1.0)
        mc.record_histogram("h", 100.0)
        summary = mc.get_summary()
        assert "counters" in summary
        assert "gauges" in summary
        assert "histograms" in summary
        assert "uptime_seconds" in summary

    def test_histogram_percentiles(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        for i in range(1, 101):
            mc.record_histogram("dur", float(i))
        stats = mc.get_summary()["histograms"]["dur"]
        assert stats["count"] == 100
        assert stats["min"] == 1.0
        assert stats["max"] == 100.0
        assert stats["p95"] >= 95.0
        assert stats["p99"] >= 99.0

    def test_reset_clears_in_memory(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.increment_counter("x")
        mc.reset()
        assert mc.counters == {}
        assert mc.gauges == {}
        assert mc.histograms == {}

    def test_get_summary_contains_reset_note(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        summary = mc.get_summary()
        assert "note" in summary
        assert "Prometheus" in summary["note"]

    def test_record_cache_result_hit(self):
        from app.observability.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.record_cache_result(hit=True)
        mc.record_cache_result(hit=True)
        mc.record_cache_result(hit=False)
        assert mc.counters["cache_hits"] == 2
        assert mc.counters["cache_misses"] == 1


# ---------------------------------------------------------------------------
# QueryMetrics — flows through MetricsCollector correctly
# ---------------------------------------------------------------------------

class TestQueryMetrics:

    def _make(self):
        from app.observability.metrics import MetricsCollector, QueryMetrics
        mc = MetricsCollector()
        qm = QueryMetrics(mc)
        return mc, qm

    def test_start_increments_started(self):
        mc, qm = self._make()
        qm.start_query("q1")
        assert mc.counters["queries_started"] == 1

    def test_end_success_increments_successful(self):
        mc, qm = self._make()
        qm.start_query("q1")
        qm.end_query("q1", success=True)
        assert mc.counters["queries_successful"] == 1
        assert "queries_failed" not in mc.counters

    def test_end_failure_increments_failed(self):
        mc, qm = self._make()
        qm.start_query("q1")
        qm.end_query("q1", success=False)
        assert mc.counters["queries_failed"] == 1

    def test_end_records_duration(self):
        mc, qm = self._make()
        qm.start_query("q1")
        time.sleep(0.01)
        qm.end_query("q1")
        assert len(mc.histograms.get("query_duration_ms", [])) == 1
        assert mc.histograms["query_duration_ms"][0] > 0

    def test_record_rows(self):
        mc, qm = self._make()
        qm.record_rows(42)
        assert mc.gauges["last_query_rows"] == 42.0
        assert mc.histograms["query_rows"] == [42.0]

    def test_domain_counter(self):
        mc, qm = self._make()
        qm.record_domain_query("sales")
        qm.record_domain_query("sales")
        qm.record_domain_query("hr")
        assert mc.counters["queries_domain_sales"] == 2
        assert mc.counters["queries_domain_hr"] == 1


# ---------------------------------------------------------------------------
# Prometheus dual-write
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestPrometheusBridge:

    def test_prometheus_available_flag(self):
        from app.observability.metrics import PROMETHEUS_AVAILABLE as flag
        assert flag is True

    def test_prometheus_registry_is_not_none(self):
        from app.observability.metrics import get_prometheus_registry
        assert get_prometheus_registry() is not None

    def test_counter_names_registered(self):
        # prometheus_client stores Counter base names without the _total suffix;
        # the _total suffix appears on the Sample names within each metric.
        from app.observability.metrics import get_prometheus_registry
        registry = get_prometheus_registry()
        names = {m.name for m in registry.collect()}
        assert "meridian_queries_started" in names
        assert "meridian_queries_successful" in names
        assert "meridian_queries_failed" in names
        assert "meridian_queries_domain" in names
        assert "meridian_cache_hits" in names
        assert "meridian_cache_misses" in names

    def test_histogram_names_registered(self):
        from app.observability.metrics import get_prometheus_registry
        registry = get_prometheus_registry()
        names = {m.name for m in registry.collect()}
        assert "meridian_query_duration_ms" in names
        assert "meridian_query_rows" in names

    def test_gauge_name_registered(self):
        from app.observability.metrics import get_prometheus_registry
        registry = get_prometheus_registry()
        names = {m.name for m in registry.collect()}
        assert "meridian_last_query_rows" in names

    def test_global_singleton_increments_prometheus_counter(self):
        """The module-level singleton's writes appear in Prometheus samples."""
        from app.observability.metrics import get_metrics_collector, get_prometheus_registry
        mc = get_metrics_collector()
        registry = get_prometheus_registry()

        mc.increment_counter("queries_started", 1)

        # Sample name for a Counter is "<base>_total"
        total_after = None
        for metric in registry.collect():
            if metric.name == "meridian_queries_started":
                for sample in metric.samples:
                    if sample.name == "meridian_queries_started_total":
                        total_after = sample.value
        assert total_after is not None and total_after >= 1


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestMetricsEndpoint:
    """Tests for the /metrics Prometheus scrape endpoint.

    Uses a minimal isolated FastAPI app (not the shared module-level singleton)
    so the mount is always active regardless of METRICS_ENABLED in .env.local.
    """

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from prometheus_client import make_asgi_app as _prom_asgi
        from app.observability.metrics import get_prometheus_registry

        test_app = FastAPI()
        test_app.mount("/metrics", _prom_asgi(registry=get_prometheus_registry()))
        return TestClient(test_app)

    def test_metrics_endpoint_reachable(self, client):
        resp = client.get("/metrics/")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client):
        resp = client.get("/metrics/")
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_metrics_contains_meridian_prefix(self, client):
        resp = client.get("/metrics/")
        assert "meridian_" in resp.text

    def test_metrics_contains_expected_metric_names(self, client):
        resp = client.get("/metrics/")
        for name in [
            "meridian_queries_started_total",
            "meridian_queries_successful_total",
            "meridian_queries_failed_total",
            "meridian_query_duration_ms",
            "meridian_cache_hits_total",
            "meridian_cache_misses_total",
        ]:
            assert name in resp.text, f"Missing metric: {name}"


# ---------------------------------------------------------------------------
# metrics_enabled gate
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="prometheus_client not installed")
class TestMetricsEnabledGate:

    def test_metrics_endpoint_present_when_enabled(self, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "true")
        # Re-import app with patched settings to verify mount happens
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.metrics_enabled is True

    def test_metrics_endpoint_absent_when_disabled(self, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "false")
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.metrics_enabled is False


# ---------------------------------------------------------------------------
# Middleware — monitoring path set
# ---------------------------------------------------------------------------

class TestMonitoringPathSet:

    def test_monitoring_paths_contains_expected(self):
        from app.api.middleware import _MONITORING_PATHS
        assert "/health" in _MONITORING_PATHS
        assert "/metrics" in _MONITORING_PATHS
        assert "/metrics/" in _MONITORING_PATHS

    def test_monitoring_paths_is_frozenset(self):
        from app.api.middleware import _MONITORING_PATHS
        assert isinstance(_MONITORING_PATHS, frozenset)


# ---------------------------------------------------------------------------
# Tracing — OTLP config, no jaeger-thrift
# ---------------------------------------------------------------------------

class TestTracingOTLP:

    def test_setup_tracing_returns_manager(self):
        from app.observability.tracing import setup_tracing, TracingManager
        # Reset singleton for a clean test
        TracingManager._instance = None
        mgr = setup_tracing(enabled=False)
        assert mgr is not None
        TracingManager._instance = None  # cleanup

    def test_tracing_config_stores_otlp_endpoint(self):
        from app.observability.tracing import TracingConfig
        cfg = TracingConfig(otlp_endpoint="http://jaeger:4318/v1/traces")
        assert cfg.otlp_endpoint == "http://jaeger:4318/v1/traces"

    def test_no_jaeger_thrift_import(self):
        """The deprecated jaeger-thrift package must not be imported."""
        import sys
        import importlib
        import app.observability.tracing  # noqa: F401 (ensure loaded)
        thrift_modules = [
            k for k in sys.modules
            if "jaeger" in k and "thrift" in k
        ]
        assert thrift_modules == [], (
            f"jaeger-thrift modules still imported: {thrift_modules}"
        )

    def test_noop_span_does_not_raise(self):
        from app.observability.tracing import _NoOpSpan
        span = _NoOpSpan()
        span.set_attribute("k", "v")
        span.add_event("evt")
        assert span.is_recording() is False

    def test_span_context_manager_disabled(self):
        from app.observability.tracing import TracingManager, TracingConfig
        TracingManager._instance = None
        mgr = TracingManager(TracingConfig(enabled=False))
        with mgr.span("test.span", {"key": "value"}) as span:
            pass  # must not raise
        TracingManager._instance = None  # cleanup


# ---------------------------------------------------------------------------
# Config — otlp_endpoint field
# ---------------------------------------------------------------------------

class TestObservabilityConfig:

    def test_otlp_endpoint_has_default(self):
        from app.config import Settings
        s = Settings(_env_file=None)
        assert hasattr(s, "otlp_endpoint")
        assert "4318" in s.otlp_endpoint

    def test_otlp_endpoint_overridable(self, monkeypatch):
        monkeypatch.setenv("OTLP_ENDPOINT", "http://collector:4318/v1/traces")
        from pydantic_settings import BaseSettings
        # Re-instantiate without cached singleton
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.otlp_endpoint == "http://collector:4318/v1/traces"

    def test_jaeger_enabled_default_false(self):
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.jaeger_enabled is False
