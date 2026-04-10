"""
Query History API Routes

Endpoints for retrieving and managing persisted query history.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.store import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Return the authenticated user's most recent query history, newest first."""
    from app.history.manager import get_history_manager

    limit = min(limit, 200)
    # Admins see all history; regular users see only their own.
    uid = None if current_user.role == "admin" else current_user.id
    return get_history_manager().list(limit=limit, user_id=uid)


@router.get("/{history_id}", response_model=Dict[str, Any])
async def get_history_entry(
    history_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return a single history entry owned by the authenticated user.

    Raises:
        HTTPException 404: If entry not found or belongs to another user
    """
    from app.history.manager import get_history_manager

    entry = get_history_manager().get(history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")

    # Non-admins can only view their own history
    if current_user.role != "admin" and entry.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")

    return entry


@router.delete("/{history_id}")
async def delete_history_entry(
    history_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a history entry owned by the authenticated user.

    Raises:
        HTTPException 404: If entry not found or belongs to another user
    """
    from app.history.manager import get_history_manager

    manager = get_history_manager()
    entry = manager.get(history_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")

    # Non-admins can only delete their own history
    if current_user.role != "admin" and entry.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")

    deleted = manager.delete(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"History entry {history_id!r} not found")
    return {"deleted": True, "id": history_id}
