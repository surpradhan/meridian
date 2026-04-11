"""Self-service domain onboarding for MERIDIAN."""

from app.onboarding.models import DomainConfig
from app.onboarding.registry import DomainRegistry, get_domain_registry

__all__ = ["DomainConfig", "DomainRegistry", "get_domain_registry"]
