"""
Export API Routes

Download query results as JSON, CSV, or Excel.
"""

import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.store import User
from app.export.exporters import to_csv, to_excel, to_json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])

_CONTENT_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTENSIONS = {"json": "json", "csv": "csv", "excel": "xlsx"}


class ExportRequest(BaseModel):
    """Run a query and export results in the requested format."""

    question: str = Field(..., min_length=1)
    domain: Optional[str] = None
    conversation_id: Optional[str] = None
    format: Literal["json", "csv", "excel"] = Field(
        default="csv", description="Export format"
    )
    filename: Optional[str] = Field(
        default=None,
        description="Base filename (without extension). Defaults to 'meridian_export'.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "Show total sales by region",
                "format": "excel",
                "filename": "sales_report",
            }
        }


@router.post("/api/query/export")
async def export_query(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Execute a query and return results as a downloadable file.

    Supported formats:
    - ``json`` — pretty-printed JSON array
    - ``csv``  — UTF-8 CSV with BOM (Excel compatible)
    - ``excel`` — .xlsx workbook
    """
    if not current_user.can_execute_queries():
        raise HTTPException(status_code=403, detail="Your role does not permit query execution.")

    # Run the query
    try:
        from app.agents.orchestrator import get_shared_or_new_orchestrator

        orchestrator = get_shared_or_new_orchestrator()
        result = orchestrator.process_query(
            request.question,
            conversation_id=request.conversation_id,
            forced_domain=request.domain,
        )
    except Exception as e:
        logger.error(f"Export query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    rows = result.get("result") or []
    fmt = request.format

    # Serialize
    try:
        if fmt == "json":
            content = to_json(rows)
        elif fmt == "csv":
            content = to_csv(rows)
        else:
            content = to_excel(rows)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    base_name = request.filename or "meridian_export"
    ext = _EXTENSIONS[fmt]
    filename = f"{base_name}.{ext}"

    return Response(
        content=content,
        media_type=_CONTENT_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
