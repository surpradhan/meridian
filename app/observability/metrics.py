"""
Metrics Collection

Collects application metrics for monitoring and alerting.
Dual-write: in-memory store (for /api/admin/metrics JSON snapshot) AND
Prometheus registry (for /metrics scrape endpoint).
"""

from typing import Dict, Any
from datetime import datetime
import time

try:
    import prometheus_client as prom
    _PROM = prom.CollectorRegistry(auto_describe=True)

    # --- counters ---
    _prom_queries_started = prom.Counter(
        "meridian_queries_started_total",
        "Total number of queries received",
        registry=_PROM,
    )
    _prom_queries_successful = prom.Counter(
        "meridian_queries_successful_total",
        "Total number of queries completed successfully",
        registry=_PROM,
    )
    _prom_queries_failed = prom.Counter(
        "meridian_queries_failed_total",
        "Total number of queries that failed",
        registry=_PROM,
    )
    _prom_queries_by_domain = prom.Counter(
        "meridian_queries_domain_total",
        "Queries per business domain",
        labelnames=["domain"],
        registry=_PROM,
    )

    # --- histograms ---
    _prom_query_duration = prom.Histogram(
        "meridian_query_duration_ms",
        "Query end-to-end duration in milliseconds",
        buckets=[25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
        registry=_PROM,
    )
    _prom_query_rows = prom.Histogram(
        "meridian_query_rows",
        "Number of rows returned per query",
        buckets=[1, 5, 10, 50, 100, 250, 500, 1000, 5000],
        registry=_PROM,
    )

    # --- gauge ---
    _prom_last_query_rows = prom.Gauge(
        "meridian_last_query_rows",
        "Row count of the most recently completed query",
        registry=_PROM,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    _PROM = None


def get_prometheus_registry():
    """Return the Prometheus CollectorRegistry used by Meridian, or None."""
    return _PROM


class MetricsCollector:
    """Collects and tracks application metrics.

    Every write goes to both the in-memory store (returned by get_summary())
    and to the Prometheus registry (scraped at /metrics).
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, list] = {}
        self.start_time = datetime.utcnow()

    def increment_counter(self, name: str, value: int = 1) -> None:
        """Increment a counter metric."""
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value

        if PROMETHEUS_AVAILABLE:
            if name == "queries_started":
                _prom_queries_started.inc(value)
            elif name == "queries_successful":
                _prom_queries_successful.inc(value)
            elif name == "queries_failed":
                _prom_queries_failed.inc(value)
            elif name.startswith("queries_domain_"):
                domain = name[len("queries_domain_"):]
                _prom_queries_by_domain.labels(domain=domain).inc(value)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge metric value."""
        self.gauges[name] = value

        if PROMETHEUS_AVAILABLE and name == "last_query_rows":
            _prom_last_query_rows.set(value)

    def record_histogram(self, name: str, value: float) -> None:
        """Record a histogram value."""
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)

        if PROMETHEUS_AVAILABLE:
            if name == "query_duration_ms":
                _prom_query_duration.observe(value)
            elif name == "query_rows":
                _prom_query_rows.observe(value)

    def get_summary(self) -> Dict[str, Any]:
        """Get a JSON snapshot of all in-memory metrics."""
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "counters": self.counters,
            "gauges": self.gauges,
            "histograms": {},
        }

        for name, values in self.histograms.items():
            if values:
                summary["histograms"][name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "p95": self._percentile(values, 95),
                    "p99": self._percentile(values, 99),
                }

        return summary

    @staticmethod
    def _percentile(values: list, percentile: int) -> float:
        """Calculate percentile from values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        return float(sorted_values[min(index, len(sorted_values) - 1)])

    def reset(self) -> None:
        """Reset all in-memory metrics (Prometheus counters are not reset)."""
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
        self.start_time = datetime.utcnow()


class QueryMetrics:
    """Tracks metrics for query execution."""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector
        self.start_times: Dict[str, float] = {}

    def start_query(self, query_id: str) -> None:
        """Mark query start time."""
        self.start_times[query_id] = time.time()
        self.collector.increment_counter("queries_started")

    def end_query(self, query_id: str, success: bool = True) -> None:
        """Mark query end time and record metrics."""
        if query_id in self.start_times:
            duration = time.time() - self.start_times[query_id]
            self.collector.record_histogram("query_duration_ms", duration * 1000)
            del self.start_times[query_id]

        if success:
            self.collector.increment_counter("queries_successful")
        else:
            self.collector.increment_counter("queries_failed")

    def record_rows(self, row_count: int) -> None:
        """Record number of rows returned."""
        self.collector.set_gauge("last_query_rows", float(row_count))
        self.collector.record_histogram("query_rows", float(row_count))

    def record_domain_query(self, domain: str) -> None:
        """Record query for a domain."""
        self.collector.increment_counter(f"queries_domain_{domain}")


# Global singletons
_metrics_collector = MetricsCollector()
_query_metrics = QueryMetrics(_metrics_collector)


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    return _metrics_collector


def get_query_metrics() -> QueryMetrics:
    """Get global query metrics tracker."""
    return _query_metrics
