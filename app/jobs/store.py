"""
Async Job Store

Thread-safe in-memory store for background query execution jobs.
Provides submit/poll/cancel semantics without requiring external infrastructure.
"""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_EXECUTOR_MAX_WORKERS = 10
_DEFAULT_MAX_AGE_SECONDS = 3600  # 1 hour


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class JobRecord:
    """Tracks the lifecycle of a single background job."""

    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    _future: Optional[Future] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
        }


class JobStore:
    """
    Thread-safe in-memory store for query jobs.

    Jobs are executed in a ThreadPoolExecutor so callers can submit and
    immediately return a job_id, then poll GET /api/jobs/{job_id} for results.
    """

    def __init__(self, max_workers: int = _EXECUTOR_MAX_WORKERS):
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="meridian-job")

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> str:
        """Submit a callable to run asynchronously.

        Returns:
            job_id — unique identifier for polling
        """
        job_id = str(uuid.uuid4())
        record = JobRecord(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )

        with self._lock:
            self._jobs[job_id] = record

        future = self._executor.submit(self._run, job_id, fn, args, kwargs)
        with self._lock:
            self._jobs[job_id]._future = future

        logger.info(f"Job {job_id} submitted")
        return job_id

    def _run(self, job_id: str, fn: Callable, args: tuple, kwargs: dict) -> None:
        """Internal runner — updates record on start/complete/fail."""
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.RUNNING
                record.started_at = datetime.utcnow()

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                record = self._jobs.get(job_id)
                if record:
                    record.status = JobStatus.COMPLETE
                    record.result = result
                    record.completed_at = datetime.utcnow()
            logger.info(f"Job {job_id} completed successfully")
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)
            with self._lock:
                record = self._jobs.get(job_id)
                if record:
                    record.status = JobStatus.FAILED
                    record.error = str(e)
                    record.completed_at = datetime.utcnow()

    def get(self, job_id: str) -> Optional[JobRecord]:
        """Return the JobRecord for a given job_id, or None."""
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Attempt to cancel a pending job. Returns True if cancelled."""
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return False
            if record.status == JobStatus.PENDING and record._future:
                cancelled = record._future.cancel()
                if cancelled:
                    record.status = JobStatus.FAILED
                    record.error = "Cancelled by user"
                    record.completed_at = datetime.utcnow()
                return cancelled
            # Already running or done — remove from store
            if record.status in (JobStatus.COMPLETE, JobStatus.FAILED):
                del self._jobs[job_id]
                return True
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return all job records as dicts."""
        with self._lock:
            return [r.to_dict() for r in self._jobs.values()]

    def cleanup_old_jobs(self, max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS) -> int:
        """Remove completed/failed jobs older than max_age_seconds. Returns count removed."""
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        to_remove: List[str] = []

        with self._lock:
            for job_id, record in self._jobs.items():
                if record.status in (JobStatus.COMPLETE, JobStatus.FAILED):
                    if record.completed_at and record.completed_at < cutoff:
                        to_remove.append(job_id)
            for job_id in to_remove:
                del self._jobs[job_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old jobs")
        return len(to_remove)


# Module-level singleton
_store: Optional[JobStore] = None
_store_lock = threading.Lock()


def get_job_store() -> JobStore:
    """Return (or create) the module-level JobStore singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = JobStore()
    return _store
