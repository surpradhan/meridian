"""
MERIDIAN FastAPI Application Entry Point

Main application initialization and server setup.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.middleware import setup_middleware
from app.observability.logging import setup_logging

# Initialize logging
setup_logging(settings.log_level)

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
