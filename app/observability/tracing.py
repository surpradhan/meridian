"""
Distributed Tracing with OpenTelemetry

Exports spans via OTLP HTTP to a Jaeger (or any OTLP-compatible) collector.
The deprecated jaeger-thrift UDP exporter has been replaced with the standard
OTLP HTTP exporter, which Jaeger all-in-one supports natively on port 4318.
"""

from __future__ import annotations

import logging
from typing import Optional
from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    _early_logger = logging.getLogger(__name__)
    _early_logger.warning("OpenTelemetry not fully available - using no-op tracer")

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    INSTRUMENTATION_AVAILABLE = True
except ImportError:
    INSTRUMENTATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value) -> None:
        pass

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        pass

    def is_recording(self) -> bool:
        return False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is unavailable."""

    def start_as_current_span(self, name: str):
        return _NoOpSpan()

    def start_span(self, name: str):
        return _NoOpSpan()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TracingConfig:
    """Configuration for distributed tracing."""

    def __init__(
        self,
        service_name: str = "meridian",
        otlp_endpoint: str = "http://localhost:4318/v1/traces",
        enabled: bool = True,
    ):
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.enabled = enabled


class TracingManager:
    """Manages OpenTelemetry tracing setup and span creation."""

    _instance: Optional["TracingManager"] = None

    def __init__(self, config: TracingConfig):
        self.config = config
        self.tracer_provider: Optional[TracerProvider] = None
        self.tracer: Optional[trace.Tracer] = None

        if config.enabled:
            self._setup_tracer()

    def _setup_tracer(self) -> None:
        """Initialize OTLP exporter and tracer provider."""
        if not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry not available - using no-op tracer")
            return

        try:
            if OTLP_AVAILABLE:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                )

                try:
                    from app.config import settings as _settings
                    _service_version = _settings.api_version
                except Exception:
                    _service_version = "unknown"

                resource = Resource.create({
                    "service.name": self.config.service_name,
                    "service.version": _service_version,
                })

                self.tracer_provider = TracerProvider(resource=resource)
                self.tracer_provider.add_span_processor(
                    BatchSpanProcessor(otlp_exporter)
                )

                trace.set_tracer_provider(self.tracer_provider)
                self.tracer = trace.get_tracer(__name__)

                logger.info(
                    f"Tracing initialized: {self.config.service_name} -> "
                    f"{self.config.otlp_endpoint}"
                )
            else:
                logger.warning("OTLP exporter not available - using no-op tracer")
                self.tracer = trace.get_tracer(__name__) if OTEL_AVAILABLE else None

        except Exception as e:
            logger.error(f"Failed to initialize tracing: {e}")
            if OTEL_AVAILABLE:
                self.tracer = trace.get_tracer(__name__)
            else:
                self.tracer = None

    @classmethod
    def get_instance(cls, config: Optional[TracingConfig] = None) -> "TracingManager":
        """Get or create singleton instance."""
        if cls._instance is None:
            cfg = config or TracingConfig()
            cls._instance = cls(cfg)
        return cls._instance

    def instrument_app(self, app) -> None:
        """Instrument FastAPI application."""
        if self.config.enabled and INSTRUMENTATION_AVAILABLE:
            FastAPIInstrumentor.instrument_app(app)
            HTTPXClientInstrumentor().instrument()
            logger.info("FastAPI instrumented for tracing")

    def instrument_sqlalchemy(self, engine) -> None:
        """Instrument SQLAlchemy engine."""
        if self.config.enabled and INSTRUMENTATION_AVAILABLE:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.info("SQLAlchemy instrumented for tracing")

    def get_tracer(self):
        """Get tracer instance."""
        if self.tracer is None:
            if OTEL_AVAILABLE:
                self.tracer = trace.get_tracer(__name__)
            else:
                return _NoOpTracer()
        return self.tracer

    @contextmanager
    def span(self, name: str, attributes: Optional[dict] = None):
        """Create a span with optional attributes.

        Usage:
            with tracer.span("query_execution", {"query": "SELECT ..."}) as span:
                # Do work
        """
        tracer = self.get_tracer()
        try:
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))
                yield span
        except (AttributeError, TypeError):
            span = _NoOpSpan()
            yield span

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        """Add event to current span."""
        if not OTEL_AVAILABLE:
            return
        span = trace.get_current_span()
        if span.is_recording():
            span.add_event(name, attributes or {})


def setup_tracing(
    service_name: str = "meridian",
    otlp_endpoint: str = "http://localhost:4318/v1/traces",
    enabled: bool = True,
    # Legacy params kept for call-site compatibility; ignored.
    jaeger_host: str = "localhost",
    jaeger_port: int = 6831,
) -> TracingManager:
    """Setup distributed tracing globally.

    Args:
        service_name: Service name tag in Jaeger / Tempo.
        otlp_endpoint: OTLP HTTP collector URL (Jaeger all-in-one default:
            http://<host>:4318/v1/traces).
        enabled: Whether to enable tracing.
        jaeger_host: Deprecated — kept for backward compatibility, not used.
        jaeger_port: Deprecated — kept for backward compatibility, not used.

    Returns:
        TracingManager instance
    """
    config = TracingConfig(
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        enabled=enabled,
    )
    return TracingManager.get_instance(config)


def get_tracer():
    """Get global tracer instance."""
    manager = TracingManager.get_instance()
    return manager.get_tracer()
