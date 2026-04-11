"""
Async Job API Routes

Submit long-running queries as background jobs and poll for results.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user, require_role
from app.auth.store import User
from app.jobs.store import JobStatus, get_job_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


class AsyncQueryRequest(BaseModel):
    """Submit an async query job."""

    question: str = Field(..., min_length=1, description="Natural language question")
    domain: Optional[str] = Field(default=None, description="Override domain routing")
    conversation_id: Optional[str] = Field(default=None, description="Conversation session ID")
    page_size: Optional[int] = Field(default=100, ge=1, le=10000)

    class Config:
        json_schema_extra = {
            "example": {
                "question": "What are total sales by region for last quarter?",
            }
        }


class JobSubmitResponse(BaseModel):
    """Returned immediately after job submission."""

    job_id: str
    status: str = JobStatus.PENDING.value
    message: str = "Job submitted. Poll GET /api/jobs/{job_id} for results."


@router.post("/api/query/execute-async", response_model=JobSubmitResponse)
async def submit_async_query(
    request: AsyncQueryRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Submit a query as a background job and return immediately.

    Poll ``GET /api/jobs/{job_id}`` to check status and retrieve results.
    """
    if not current_user.can_execute_queries():
        raise HTTPException(status_code=403, detail="Your role does not permit query execution.")

    from app.agents.orchestrator import get_shared_or_new_orchestrator

    orchestrator = get_shared_or_new_orchestrator()
    store = get_job_store()
    job_id = store.submit(
        orchestrator.process_query,
        request.question,
        request.conversation_id,
        request.domain,
    )

    logger.info(f"Async job {job_id} submitted by {current_user.username}")
    return JobSubmitResponse(
        job_id=job_id,
        status=JobStatus.PENDING.value,
        message=f"Job submitted. Poll GET /api/jobs/{job_id} for results.",
    )


@router.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Poll the status and result of a background job."""
    store = get_job_store()
    record = store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return record.to_dict()


@router.delete("/api/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cancel a pending job or remove a completed one."""
    store = get_job_store()
    removed = store.cancel(job_id)
    if not removed:
        record = store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        raise HTTPException(status_code=409, detail=f"Job {job_id!r} is already {record.status.value} and cannot be cancelled")
    return {"job_id": job_id, "message": "Job cancelled/removed"}


@router.get("/api/jobs")
async def list_jobs(
    current_user: User = Depends(require_role("admin")),
) -> Dict[str, Any]:
    """List all jobs in the store. Restricted to admin role."""
    store = get_job_store()
    jobs = store.list_jobs()
    return {"jobs": jobs, "count": len(jobs)}
