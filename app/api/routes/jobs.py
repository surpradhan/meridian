"""
Async Job API Routes

Submit long-running queries as background jobs and poll for results.
"""

import copy
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.authz import enforce_domain_access, mask_result
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
        user_id=current_user.id,
    )

    logger.info(f"Async job {job_id} submitted by {current_user.username}")
    return JobSubmitResponse(
        job_id=job_id,
        status=JobStatus.PENDING.value,
        message=f"Job submitted. Poll GET /api/jobs/{job_id} for results.",
    )


def _owns_job(record: Any, user: User) -> bool:
    """A user may access a job they submitted; admins may access any job."""
    return user.role == "admin" or record.user_id == user.id


@router.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Poll the status and result of a background job."""
    store = get_job_store()
    record = store.get(job_id)
    # Return the same 404 for missing and unauthorized jobs so existence of
    # another user's job isn't disclosed.
    if record is None or not _owns_job(record, current_user):
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    payload = record.to_dict()
    result = payload.get("result")
    if isinstance(result, dict):
        # The job routes to a domain asynchronously, so enforce domain access
        # here (raises 403 if the owner isn't permitted into the routed domain),
        # then mask sensitive fields. Work on a copy so the stored record — which
        # other roles (e.g. an admin) may later read — is never mutated.
        enforce_domain_access(result, current_user)
        payload["result"] = mask_result(copy.deepcopy(result), current_user)
    # Don't leak internal exception text from a failed job to the client.
    if payload.get("error"):
        payload["error"] = "Job execution failed"
    return payload


@router.delete("/api/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cancel a pending job or remove a completed one."""
    store = get_job_store()
    record = store.get(job_id)
    if record is None or not _owns_job(record, current_user):
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    removed = store.cancel(job_id)
    if not removed:
        # Re-fetch: cancel() returns False for running jobs (can't be cancelled).
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
