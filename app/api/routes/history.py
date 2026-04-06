"""
Query History API Routes

Endpoints for retrieving and managing persisted query history.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_history(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return the most recent query history entries, newest first.

    Args:
        limit: Maximum entries to return (default 50, max 200)

    Returns:
        List of history entries with id, question, domain, row_count, created_at
    """
    from app.history.manager import get_history_manager

    limit = min(limit, 200)
    return get_history_manager().list(limit=limit)


@router.get("/{history_id}", response_model=Dict[str, Any])
async def get_history_entry(history_id: str) -> Dict[str, Any]:
    """
    Return a single history entry by ID.

    Args:
        history_id: UUID of the history entry

    Returns:
        History entry dict

    Raises:
        HTTPException 404: If entry not found
    """
    from app.history.manager import get_history_manager

    entry = get_history_manager().get(history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")
    return entry


@router.delete("/{history_id}")
async def delete_history_entry(history_id: str) -> Dict[str, Any]:
    """
    Delete a history entry.

    Args:
        history_id: UUID of the history entry

    Returns:
        Confirmation dict

    Raises:
        HTTPException 404: If entry not found
    """
    from app.history.manager import get_history_manager

    deleted = get_history_manager().delete(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")
    return {"deleted": True, "id": history_id}
