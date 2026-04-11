"""
Admin API Routes

Endpoints for:
- Domain onboarding (register / list / delete dynamic domains)
- Performance index recommendations
All require admin role.
"""

import logging
from typing import Any, Dict, List, Optional

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

    reload_warning = _reload_orchestrator()
    logger.info(f"Admin {current_user.username} registered domain {config.name!r}")
    if reload_warning:
        from fastapi.responses import Response
        import json
        headers = {"X-Reload-Warning": reload_warning}
        return Response(
            content=json.dumps(result.model_dump()),
            media_type="application/json",
            headers=headers,
        )
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

    reload_warning = _reload_orchestrator()
    logger.info(f"Admin {current_user.username} deleted domain {name!r}")
    resp: Dict[str, Any] = {"name": name, "message": "Domain deleted"}
    if reload_warning:
        resp["reload_warning"] = reload_warning
    return resp


# ------------------------------------------------------------------
# Metrics
# ------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(_require_admin),
) -> Dict[str, Any]:
    """
    Return in-memory application metrics (query counters, histograms, gauges).

    Metrics are collected by ``MetricsCollector`` and ``QueryMetrics`` during
    normal query processing.  The response is a JSON snapshot; counters reset
    when the process restarts.
    """
    from app.observability.metrics import get_metrics_collector
    return get_metrics_collector().get_summary()


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


def _reload_orchestrator() -> Optional[str]:
    """
    Ask the singleton Orchestrator (if one has been created) to reload
    dynamic domain agents from the registry.

    Returns a warning string if reload failed (so the caller can surface it
    to the admin), or None on success.
    """
    try:
        from app.agents.orchestrator import _get_shared_orchestrator
        orch = _get_shared_orchestrator()
        if orch is not None:
            success = orch.reload_domain_agents()
            if not success:
                msg = (
                    "Domain saved, but orchestrator hot-reload failed — "
                    "check server logs for details. "
                    "The new domain will be active after the next restart."
                )
                logger.error(msg)
                return msg
        return None
    except Exception as e:
        msg = f"Domain saved, but orchestrator hot-reload raised an unexpected error: {e}. The new domain will be active after next restart."
        logger.error(msg, exc_info=True)
        return msg
