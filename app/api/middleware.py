"""
API Middleware Setup

Configures CORS, authentication, logging, and other middleware.
"""

import time
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client": request.client.host if request.client else "unknown",
            },
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window in-memory rate limiter (per IP, per minute)."""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # Maps IP -> list of request timestamps within the current window
        self._windows: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Health and monitoring endpoints are exempt
        if request.url.path in ("/health", "/api/query/health") or request.url.path.startswith("/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0

        # Evict timestamps outside the 1-minute window
        timestamps = self._windows[client_ip]
        timestamps[:] = [t for t in timestamps if t > window_start]

        # Evict the entry entirely when the window is empty to prevent unbounded growth.
        if not timestamps and client_ip in self._windows:
            del self._windows[client_ip]
            timestamps = self._windows[client_ip]  # re-create via defaultdict

        if len(timestamps) >= self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for {client_ip} "
                f"({len(timestamps)}/{self.requests_per_minute} req/min)"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Maximum {self.requests_per_minute} requests per minute",
                },
                headers={"Retry-After": "60"},
            )

        timestamps.append(now)
        return await call_next(request)


class ConcurrentRequestMiddleware(BaseHTTPMiddleware):
    """Reject requests when too many are in-flight simultaneously."""

    def __init__(self, app, max_concurrent: int = 10):
        super().__init__(app)
        self.max_concurrent = max_concurrent
        # Lazily created inside the event loop on first request to avoid
        # DeprecationWarning (Python 3.10+) / error (Python 3.12+) from
        # creating Semaphore before the loop is running.
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def dispatch(self, request: Request, call_next):
        # Monitoring endpoints must never be blocked by the concurrency limiter
        if request.url.path in ("/health",) or request.url.path.startswith("/metrics"):
            return await call_next(request)

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)

        # Single atomic acquire with timeout=0 — avoids the peek-then-acquire race.
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Server busy",
                    "detail": f"Maximum {self.max_concurrent} concurrent requests reached",
                },
                headers={"Retry-After": "5"},
            )

        try:
            return await call_next(request)
        finally:
            self._semaphore.release()


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS when enforce_https=True in production."""

    async def dispatch(self, request: Request, call_next):
        try:
            from app.config import settings
            if (
                settings.enforce_https
                and settings.is_production()
                and request.url.scheme == "http"
            ):
                https_url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(url=https_url, status_code=301)
        except Exception:
            pass
        return await call_next(request)


def _semantic_action(method: str, path: str) -> str:
    """Map an HTTP method + path to a short semantic action string.

    Path parameters (UUIDs, arbitrary IDs) are normalised to {id} so that
    audit queries like "all history deletes" work without wildcards.
    """
    import re
    # Normalise any UUID-like segment to {id}
    clean = re.sub(r"/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "/{id}", path)
    # Also normalise any remaining path segment that looks like a raw ID
    clean = re.sub(r"/[0-9a-f-]{10,}", "/{id}", clean)

    _MAP: Dict[tuple, str] = {
        ("POST",   "/api/auth/login"):        "auth.login",
        ("POST",   "/api/auth/register"):     "auth.register",
        ("GET",    "/api/auth/me"):           "auth.me",
        ("POST",   "/api/query/execute"):     "query.execute",
        ("POST",   "/api/query/validate"):    "query.validate",
        ("GET",    "/api/query/domains"):     "query.domains",
        ("GET",    "/api/query/explore"):     "query.explore",
        ("GET",    "/api/history"):           "history.list",
        ("GET",    "/api/history/{id}"):      "history.get",
        ("DELETE", "/api/history/{id}"):      "history.delete",
    }
    return _MAP.get((method, clean), f"{method.lower()}:{path}")


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Write an audit log entry for every request after it completes.

    Extracts the authenticated user from the JWT (if present) without
    raising — unauthenticated requests are logged as anonymous.
    """

    # Paths that don't need audit entries (health probes, static assets)
    _SKIP_PATHS = {"/health", "/api/query/health", "/", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.url.path in self._SKIP_PATHS:
            return response

        try:
            from app.config import settings
            if not settings.audit_log_enabled:
                return response
        except Exception:
            return response

        # Best-effort user extraction from Bearer token
        user_id: Optional[str] = None
        username: Optional[str] = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from app.auth.jwt import decode_access_token
                payload = decode_access_token(auth_header[7:])
                if payload:
                    user_id = payload.get("sub")
                    username = payload.get("username")
        except Exception:
            pass

        method = request.method
        path = request.url.path
        action = _semantic_action(method, path)
        client_ip = request.client.host if request.client else "unknown"

        try:
            from app.auth.store import get_auth_store
            get_auth_store().log_audit(
                action=action,
                resource=path,
                user_id=user_id,
                username=username,
                status_code=response.status_code,
                client_ip=client_ip,
            )
        except Exception as exc:
            logger.warning(f"AuditLogMiddleware: write failed — audit trail may be incomplete: {exc}")

        return response


def setup_middleware(app: FastAPI) -> None:
    """Setup request logging, rate limiting, and concurrency middleware.

    Args:
        app: FastAPI application instance
    """
    try:
        from app.config import settings
        rate_limit = settings.rate_limit_per_minute
        max_concurrent = settings.max_concurrent_requests
    except Exception:
        rate_limit = 60
        max_concurrent = 10

    app.add_middleware(ConcurrentRequestMiddleware, max_concurrent=max_concurrent)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=rate_limit)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    logger.info(
        f"Middleware configured: rate_limit={rate_limit}/min, "
        f"max_concurrent={max_concurrent}"
    )
