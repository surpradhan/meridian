"""
Application Configuration

Handles environment-based configuration using Pydantic Settings.
Supports .env files and environment variables.
"""

import os
import secrets
import warnings
from typing import List, Literal, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


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
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4", description="OpenAI model to use")

    # Groq (takes priority over OpenAI when set)
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model to use")

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

    # Security / Authentication
    secret_key: str = Field(
        default_factory=lambda: secrets.token_hex(32),
        description="JWT signing secret key (set via SECRET_KEY env var in production)",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiry in hours")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:7860", "http://localhost:8000"],
        description="Allowed CORS origins",
    )
    enforce_https: bool = Field(default=False, description="Redirect HTTP to HTTPS in production")
    audit_log_enabled: bool = Field(default=True, description="Enable audit logging")

    # OAuth / SSO (Phase 8)
    google_client_id: Optional[str] = Field(default=None, description="Google OAuth2 client ID")
    google_client_secret: Optional[str] = Field(default=None, description="Google OAuth2 client secret")
    oidc_issuer: Optional[str] = Field(default=None, description="Generic OIDC issuer URL (e.g. https://accounts.google.com or Okta URL)")
    oidc_client_id: Optional[str] = Field(default=None, description="Generic OIDC client ID")
    oidc_client_secret: Optional[str] = Field(default=None, description="Generic OIDC client secret")
    oauth_redirect_base_url: str = Field(default="http://localhost:8000", description="Base URL for OAuth callback redirect")

    class Config:
        env_file = [".env", ".env.local"]
        env_file_encoding = "utf-8"
        case_sensitive = False

    @model_validator(mode="after")
    def validate_oidc_config(self) -> "Settings":
        """Ensure OIDC settings are either all present or all absent."""
        oidc_fields = {
            "oidc_client_id": self.oidc_client_id,
            "oidc_client_secret": self.oidc_client_secret,
            "oidc_issuer": self.oidc_issuer,
        }
        provided = {k for k, v in oidc_fields.items() if v}
        if provided and provided != set(oidc_fields):
            missing = sorted(set(oidc_fields) - provided)
            raise ValueError(
                f"Incomplete OIDC configuration: {missing} must also be set when using OIDC. "
                "Either configure all three (OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_ISSUER) "
                "or leave all unset."
            )
        return self

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Catch dangerous misconfigurations before the app starts."""
        if self.environment != "production":
            return self

        # Secret key must be explicitly set — the random default rotates every restart
        if "SECRET_KEY" not in os.environ:
            warnings.warn(
                "SECRET_KEY is not set via environment variable. "
                "All JWT tokens will be invalidated on every restart. "
                "Set SECRET_KEY in production!",
                stacklevel=2,
            )

        # Debug mode leaks stack traces in API error responses
        if self.debug:
            raise ValueError(
                "debug=True is not allowed in production. Set DEBUG=false (or omit it)."
            )

        # Warn if CORS origins still point at localhost
        _dev_origins = {"http://localhost:3000", "http://localhost:7860", "http://localhost:8000"}
        if set(self.cors_origins) == _dev_origins:
            warnings.warn(
                "CORS_ORIGINS is still set to development localhost defaults in production. "
                "Set CORS_ORIGINS to your actual frontend origin(s).",
                stacklevel=2,
            )

        return self

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
