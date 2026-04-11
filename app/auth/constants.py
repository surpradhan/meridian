"""
Shared auth constants.

Centralised here to prevent sentinel-value drift between store.py and routes.py.
"""

# Stored as password_hash for OAuth-only accounts that have no password.
# Must never be a valid bcrypt hash — the angle-brackets guarantee that.
OAUTH_ONLY_SENTINEL = "<oauth_only>"
