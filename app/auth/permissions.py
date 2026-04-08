"""
Permission Utilities

Field masking for sensitive data based on user role.
"""

from typing import Any, Dict, List

# Field name substrings that are considered sensitive
_SENSITIVE_PATTERNS = {
    "salary", "ssn", "social_security", "account_number",
    "credit_card", "card_number", "tax_id", "ein",
    "bank_account", "routing_number", "password", "secret",
    "compensation", "wage", "payroll",
}

_MASK = "***MASKED***"


def _is_sensitive(field_name: str) -> bool:
    lower = field_name.lower()
    return any(pattern in lower for pattern in _SENSITIVE_PATTERNS)


def mask_sensitive_fields(data: Any, role: str) -> Any:
    """Mask sensitive column values for viewer role.

    Admin and analyst roles see all fields.
    Viewer role gets sensitive fields replaced with '***MASKED***'.
    """
    if role in ("admin", "analyst"):
        return data

    if isinstance(data, list):
        return [mask_sensitive_fields(row, role) for row in data]

    if isinstance(data, dict):
        return {
            k: (_MASK if _is_sensitive(k) else mask_sensitive_fields(v, role))
            for k, v in data.items()
        }

    return data
