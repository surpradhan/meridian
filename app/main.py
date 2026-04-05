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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup additional middleware (auth, logging, etc)
setup_middleware(app)

# Initialize distributed tracing
tracing = setup_tracing(
    service_name="meridian",
    jaeger_host=settings.jaeger_agent_host,
    jaeger_port=settings.jaeger_agent_port,
    enabled=settings.jaeger_enabled,
)
tracing.instrument_app(app)

# Register API routes
from app.api.routes import query as query_routes

app.include_router(query_routes.router)


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
