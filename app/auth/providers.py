"""
OAuth2 / OIDC Provider Definitions

Describes the endpoints and configuration keys for each supported provider.
Google: endpoints are stable and hardcoded.
OIDC:   endpoints are discovered at runtime from the issuer's well-known document.
"""

from typing import Dict, Any, Optional

# Provider name → static endpoint config.
# OIDC provider endpoints are resolved at runtime via discovery.
GOOGLE_PROVIDER: Dict[str, Any] = {
    "name": "google",
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
    "scope": "openid email profile",
}

STATIC_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "google": GOOGLE_PROVIDER,
}


def get_provider_config(provider: str) -> Optional[Dict[str, Any]]:
    """Return static provider config for known providers, or None for generic OIDC."""
    return STATIC_PROVIDERS.get(provider)
