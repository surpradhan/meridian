"""
Admin API Routes

Endpoints for:
- Domain onboarding (register / list / delete dynamic domains)
- Performance index recommendations
All require admin role.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_role
from app.auth.store import User
from app.onboarding.models import DomainConfig
from app.onboarding.registry import get_domain_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_require_admin = require_role("admin")


# ------------------------------------------------------------------
# Domain Onboarding
# ------------------------------------------------------------------


@router.post("/domains", response_model=DomainConfig)
async def register_domain(
    config: DomainConfig,
    current_user: User = Depends(_require_admin),
) -> DomainConfig:
    """
    Register a new dynamic business domain.

    After registration the orchestrator will accept queries routed to this
    domain on the next request (no restart required).

    Raises 409 if the domain name conflicts with a built-in domain.
    """
    registry = get_domain_registry()
    try:
        result = registry.register(config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Hot-reload the orchestrator's domain agents
    _reload_orchestrator()

    logger.info(f"Admin {current_user.username} registered domain {config.name!r}")
    return result


@router.get("/domains", response_model=List[DomainConfig])
async def list_domains(
    current_user: User = Depends(_require_admin),
) -> List[DomainConfig]:
    """List all dynamically-registered domains."""
    registry = get_domain_registry()
    return registry.list_domains()


@router.delete("/domains/{name}")
async def delete_domain(
    name: str,
    current_user: User = Depends(_require_admin),
) -> Dict[str, Any]:
    """Remove a dynamic domain by name."""
    registry = get_domain_registry()
    deleted = registry.delete_domain(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Domain {name!r} not found")

    _reload_orchestrator()
    logger.info(f"Admin {current_user.username} deleted domain {name!r}")
    return {"name": name, "message": "Domain deleted"}


# ------------------------------------------------------------------
# Performance / Index Advisor
# ------------------------------------------------------------------


@router.get("/performance")
async def get_performance_report(
    current_user: User = Depends(_require_admin),
) -> Dict[str, Any]:
    """
    Return index recommendations and slow-query analysis from the
    IndexOptimizer that has been recording query patterns at runtime.
    """
    from app.database.index_optimizer import get_optimizer
    optimizer = get_optimizer()
    return optimizer.analyze_workload()


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------


def _reload_orchestrator() -> None:
    """
    Ask the singleton Orchestrator (if one has been created) to reload
    dynamic domain agents from the registry.

    Swallows all errors — the API call has already succeeded; a failed
    reload just means the new domain won't be available until the next
    fresh Orchestrator instantiation.
    """
    try:
        from app.agents.orchestrator import _get_shared_orchestrator
        orch = _get_shared_orchestrator()
        if orch is not None:
            orch.reload_domain_agents()
    except Exception as e:
        logger.warning(f"Orchestrator hot-reload after domain change failed: {e}")
