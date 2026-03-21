"""
Application Configuration

Handles environment-based configuration using Pydantic Settings.
Supports .env files and environment variables.
"""

from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment",
    )
    debug: bool = Field(default=True, description="Enable debug mode")

    # FastAPI
    api_title: str = Field(default="MERIDIAN", description="API title")
    api_version: str = Field(default="0.1.0", description="API version")
    log_level: str = Field(default="INFO", description="Logging level")

    # OpenAI
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4", description="OpenAI model to use")

    # Langsmith (Optional)
    langsmith_api_key: str = Field(default="", description="Langsmith API key")
    langsmith_project: str = Field(default="meridian", description="Langsmith project name")
    langsmith_tracing: bool = Field(default=False, description="Enable Langsmith tracing")

    # Database
    database_url: str = Field(
        default="sqlite:///meridian.db",
        description="Database connection URL",
    )
    database_pool_size: int = Field(default=5, description="Connection pool size")
    database_max_overflow: int = Field(default=10, description="Max overflow connections")

    # Redis (Optional)
    redis_url: str = Field(default="", description="Redis connection URL")
    cache_enabled: bool = Field(default=False, description="Enable caching")

    # Application Settings
    max_query_time_seconds: int = Field(
        default=30,
        description="Maximum query execution time",
    )
    max_concurrent_requests: int = Field(default=10, description="Max concurrent requests")
    rate_limit_per_minute: int = Field(default=60, description="Rate limit per minute")

    # Observability
    metrics_enabled: bool = Field(default=False, description="Enable metrics")
    jaeger_enabled: bool = Field(default=False, description="Enable Jaeger tracing")
    jaeger_agent_host: str = Field(default="localhost", description="Jaeger agent host")
    jaeger_agent_port: int = Field(default=6831, description="Jaeger agent port")

    class Config:
        env_file = [".env", ".env.local"]
        env_file_encoding = "utf-8"
        case_sensitive = False

    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"


# Create global settings instance
try:
    settings = Settings()
except Exception as e:
    # Provide helpful error message if configuration fails
    import sys
    print(f"Error loading configuration: {e}", file=sys.stderr)
    print("Make sure .env or .env.local is properly configured", file=sys.stderr)
    sys.exit(1)
