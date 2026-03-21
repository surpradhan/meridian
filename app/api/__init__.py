"""API layer for MERIDIAN."""

from fastapi import APIRouter
from app.api.routes import query

router = APIRouter()
router.include_router(query.router)

__all__ = ["router"]
