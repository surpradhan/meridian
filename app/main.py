"""
MERIDIAN FastAPI Application Entry Point

Main application initialization and server setup.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware import setup_middleware
from app.observability.logging import setup_logging
from app.observability.tracing import setup_tracing

# Initialize logging
setup_logging(settings.log_level)

# Configure Langsmith tracing via environment variables before any LLM calls
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description="Intelligent Data Navigation Platform",
    version=settings.api_version,
    debug=settings.debug,
)

# Add CORS middleware — origins configured via CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Setup additional middleware (auth, logging, etc)
setup_middleware(app)

# Initialize distributed tracing (OTLP HTTP → Jaeger)
tracing = setup_tracing(
    service_name="meridian",
    otlp_endpoint=settings.otlp_endpoint,
    enabled=settings.jaeger_enabled,
)
tracing.instrument_app(app)

# Mount Prometheus /metrics scrape endpoint
from app.observability.metrics import get_prometheus_registry, PROMETHEUS_AVAILABLE
if PROMETHEUS_AVAILABLE:
    from prometheus_client import make_asgi_app as _prom_asgi
    app.mount("/metrics", _prom_asgi(registry=get_prometheus_registry()))

# Register API routes
from app.api.routes import query as query_routes
from app.api.routes import history as history_routes
from app.api.routes import jobs as jobs_routes
from app.api.routes import stream as stream_routes
from app.api.routes import export as export_routes
from app.api.routes import admin as admin_routes
from app.auth import routes as auth_routes

app.include_router(auth_routes.router)
app.include_router(query_routes.router)
app.include_router(history_routes.router)
app.include_router(jobs_routes.router)
app.include_router(stream_routes.router)
app.include_router(export_routes.router)
app.include_router(admin_routes.router)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "service": "MERIDIAN",
        "version": settings.api_version,
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "redoc": "/redoc",
    }


# TODO: Register routes from app.api.router


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
