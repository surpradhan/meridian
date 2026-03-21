"""
Distributed Tracing with OpenTelemetry and Jaeger

Provides centralized tracing setup for request tracking, query execution,
and agent processing across the distributed system.
"""

from __future__ import annotations

import logging
from typing import Optional
from contextlib import contextmanager

try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("OpenTelemetry not fully available - using no-op tracer")

try:
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    JAEGER_AVAILABLE = True
except ImportError:
    JAEGER_AVAILABLE = False

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
        jaeger_host: str = "localhost",
        jaeger_port: int = 6831,
        enabled: bool = True,
    ):
        self.service_name = service_name
        self.jaeger_host = jaeger_host
        self.jaeger_port = jaeger_port
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
        """Initialize Jaeger exporter and tracer provider."""
        if not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry not available - using no-op tracer")
            return

        try:
            if JAEGER_AVAILABLE:
                jaeger_exporter = JaegerExporter(
                    agent_host_name=self.config.jaeger_host,
                    agent_port=self.config.jaeger_port,
                )

                resource = Resource.create({
                    "service.name": self.config.service_name,
                    "service.version": "1.0.0",
                })

                self.tracer_provider = TracerProvider(resource=resource)
                self.tracer_provider.add_span_processor(
                    BatchSpanProcessor(jaeger_exporter)
                )

                trace.set_tracer_provider(self.tracer_provider)
                self.tracer = trace.get_tracer(__name__)

                logger.info(
                    f"Tracing initialized: {self.config.service_name} -> "
                    f"{self.config.jaeger_host}:{self.config.jaeger_port}"
                )
            else:
                logger.warning("Jaeger exporter not available - using no-op tracer")
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
        if self.config.enabled:
            FastAPIInstrumentor.instrument_app(app)
            HTTPXClientInstrumentor().instrument()
            logger.info("FastAPI instrumented for tracing")

    def instrument_sqlalchemy(self, engine) -> None:
        """Instrument SQLAlchemy engine."""
        if self.config.enabled:
            SQLAlchemyInstrumentor().instrument(engine=engine)
            logger.info("SQLAlchemy instrumented for tracing")

    def get_tracer(self):
        """Get tracer instance."""
        if self.tracer is None:
            if OTEL_AVAILABLE:
                self.tracer = trace.get_tracer(__name__)
            else:
                # Return a no-op tracer
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
            # Fallback for no-op tracer
            span = _NoOpSpan()
            yield span

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        """Add event to current span."""
        span = trace.get_current_span()
        if span.is_recording():
            span.add_event(name, attributes or {})


def setup_tracing(
    service_name: str = "meridian",
    jaeger_host: str = "localhost",
    jaeger_port: int = 6831,
    enabled: bool = True,
) -> TracingManager:
    """Setup distributed tracing globally.

    Args:
        service_name: Name of service for Jaeger
        jaeger_host: Jaeger collector host
        jaeger_port: Jaeger collector port
        enabled: Whether to enable tracing

    Returns:
        TracingManager instance
    """
    config = TracingConfig(
        service_name=service_name,
        jaeger_host=jaeger_host,
        jaeger_port=jaeger_port,
        enabled=enabled,
    )
    return TracingManager.get_instance(config)


def get_tracer() -> trace.Tracer:
    """Get global tracer instance."""
    manager = TracingManager.get_instance()
    return manager.get_tracer()
