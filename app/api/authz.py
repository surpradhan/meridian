"""
Shared query-result authorization and masking.

Every orchestrator result that leaves the system — via the REST `/execute`
endpoint, file export, SSE streaming, or async jobs — must pass through the
same two controls:

1. **Domain access** — the user must be permitted into the domain the query
   was routed to (``can_access_domain``).
2. **Field masking** — sensitive columns are redacted for roles that may not
   see them (``mask_sensitive_fields``).

Centralizing these here keeps all query entry points consistent; previously
they were applied on ``/execute`` only, leaving export/stream/jobs as
RBAC-bypass and PII-disclosure paths.
"""

from typing import Any, Dict

from fastapi import HTTPException

from app.auth.permissions import mask_sensitive_fields
from app.auth.store import User


def _routed_domain(result: Any) -> str:
    """Extract the routed domain from an orchestrator result, if present."""
    if isinstance(result, dict):
        return result.get("domain", "") or ""
    return ""


def enforce_domain_access(result: Dict[str, Any], user: User) -> None:
    """Raise 403 if ``user`` is not permitted into the result's routed domain.

    A no-op when the result carries no domain (e.g. an error result).
    """
    domain = _routed_domain(result)
    if domain and not user.can_access_domain(domain):
        raise HTTPException(
            status_code=403,
            detail=f"Access to domain '{domain}' is not permitted for your account",
        )


def mask_result(result: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Mask sensitive fields in ``result['result']`` in place for ``user``'s role."""
    if isinstance(result, dict) and "result" in result:
        result["result"] = mask_sensitive_fields(result["result"], user.role)
    return result


def authorize_and_mask(result: Dict[str, Any], user: User) -> Dict[str, Any]:
    """Enforce domain access then mask sensitive fields.

    Returns the same ``result`` dict for convenience. Call this on every
    orchestrator result before serializing it to a client.
    """
    enforce_domain_access(result, user)
    return mask_result(result, user)
