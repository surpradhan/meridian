"""
Integration test for the fully assembled application (app.main:app).

The existing API integration tests build their own bare FastAPI() mini-apps and
never call setup_middleware(), so the production middleware stack was never
exercised end-to-end. That gap let a 503-on-every-request bug ship: the
ConcurrentRequestMiddleware admission check rejected every request even when the
concurrency semaphore was completely free.

These tests load the real app — with the full middleware stack wired by
setup_middleware() — and assert ordinary requests succeed.
"""

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_root_passes_through_middleware_stack():
    """GET / must succeed (not 503) through the assembled middleware stack."""
    resp = _client().get("/")
    assert resp.status_code != 503
    assert resp.status_code == 200


def test_health_passes_through_middleware_stack():
    """GET /health must succeed through the assembled middleware stack.

    Note: /health is in _MONITORING_PATHS, so ConcurrentRequestMiddleware
    short-circuits before touching the semaphore — this is a smoke test of the
    stack, NOT a regression guard for the limiter bug. test_root_* (where / is
    a non-monitored path that goes through the semaphore) is what covers the
    regression.
    """
    resp = _client().get("/health")
    assert resp.status_code != 503
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_repeated_requests_do_not_exhaust_concurrency_limiter():
    """Sequential requests release their slot — none should hit the 503 limiter."""
    client = _client()
    for _ in range(25):
        assert client.get("/").status_code == 200
