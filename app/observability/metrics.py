"""
Metrics Collection

Collects application metrics for monitoring and alerting.
Provides Prometheus-compatible metrics export.
"""

from typing import Dict, Any
from datetime import datetime
import time


class MetricsCollector:
    """Collects and tracks application metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, list] = {}
        self.start_time = datetime.utcnow()

    def increment_counter(self, name: str, value: int = 1) -> None:
        """
        Increment a counter metric.

        Args:
            name: Counter name
            value: Value to increment by
        """
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        """
        Set a gauge metric value.

        Args:
            name: Gauge name
            value: Value to set
        """
        self.gauges[name] = value

    def record_histogram(self, name: str, value: float) -> None:
        """
        Record a histogram value.

        Args:
            name: Histogram name
            value: Value to record
        """
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics.

        Returns:
            Dict with all collected metrics
        """
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "counters": self.counters,
            "gauges": self.gauges,
            "histograms": {},
        }

        # Calculate histogram statistics
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
        """
        Calculate percentile from values.

        Args:
            values: List of numeric values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        return float(sorted_values[min(index, len(sorted_values) - 1)])

    def reset(self) -> None:
        """Reset all metrics."""
        self.counters = {}
        self.gauges = {}
        self.histograms = {}
        self.start_time = datetime.utcnow()


class QueryMetrics:
    """Tracks metrics for query execution."""

    def __init__(self, collector: MetricsCollector):
        """
        Initialize query metrics tracker.

        Args:
            collector: MetricsCollector instance
        """
        self.collector = collector
        self.start_times: Dict[str, float] = {}

    def start_query(self, query_id: str) -> None:
        """
        Mark query start time.

        Args:
            query_id: Unique query identifier
        """
        self.start_times[query_id] = time.time()
        self.collector.increment_counter("queries_started")

    def end_query(self, query_id: str, success: bool = True) -> None:
        """
        Mark query end time and record metrics.

        Args:
            query_id: Unique query identifier
            success: Whether query succeeded
        """
        if query_id in self.start_times:
            duration = time.time() - self.start_times[query_id]
            self.collector.record_histogram("query_duration_ms", duration * 1000)
            del self.start_times[query_id]

        if success:
            self.collector.increment_counter("queries_successful")
        else:
            self.collector.increment_counter("queries_failed")

    def record_rows(self, row_count: int) -> None:
        """
        Record number of rows returned.

        Args:
            row_count: Number of rows
        """
        self.collector.set_gauge("last_query_rows", float(row_count))
        self.collector.record_histogram("query_rows", float(row_count))

    def record_domain_query(self, domain: str) -> None:
        """
        Record query for a domain.

        Args:
            domain: Domain name
        """
        self.collector.increment_counter(f"queries_domain_{domain}")


# Global metrics instance
_metrics_collector = MetricsCollector()
_query_metrics = QueryMetrics(_metrics_collector)


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector."""
    return _metrics_collector


def get_query_metrics() -> QueryMetrics:
    """Get global query metrics tracker."""
    return _query_metrics
