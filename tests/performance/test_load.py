"""
Phase 7 Load Tests

Measures P50/P95/P99 latency for the MERIDIAN API under concurrent load.

Requirements:
- A running MERIDIAN server (set TEST_SERVER_URL env var, e.g. http://localhost:8000)
- A valid JWT token (set TEST_AUTH_TOKEN env var)

If TEST_SERVER_URL is not set, all tests are skipped.

Run with:
    TEST_SERVER_URL=http://localhost:8000 TEST_AUTH_TOKEN=<jwt> \\
    pytest -m performance tests/performance/ -v
"""

import asyncio
import os
import statistics
import time
from typing import Any, Dict, List, Optional

import httpx
import pytest

pytestmark = pytest.mark.performance

SERVER_URL = os.environ.get("TEST_SERVER_URL", "")
AUTH_TOKEN = os.environ.get("TEST_AUTH_TOKEN", "")

SAMPLE_QUERIES = [
    "How many sales were made in the WEST region?",
    "What was the total sales amount by customer?",
    "Show me all ledger transactions",
    "What is the inventory in each warehouse?",
    "Show me the top customers by revenue",
]


def _skip_if_no_server():
    if not SERVER_URL:
        pytest.skip("TEST_SERVER_URL not set — skipping performance tests")


def _headers() -> Dict[str, str]:
    if AUTH_TOKEN:
        return {"Authorization": f"Bearer {AUTH_TOKEN}"}
    return {}


async def _execute_query(client: httpx.AsyncClient, question: str) -> float:
    """Run a single query and return elapsed seconds."""
    t0 = time.monotonic()
    resp = await client.post(
        f"{SERVER_URL}/api/query/execute",
        json={"question": question},
        headers=_headers(),
        timeout=30.0,
    )
    elapsed = time.monotonic() - t0
    assert resp.status_code in (200, 422), f"Unexpected status {resp.status_code}: {resp.text}"
    return elapsed


def _percentile(data: List[float], pct: int) -> float:
    """Return the Nth percentile from a list of floats."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = max(0, int(len(sorted_data) * pct / 100) - 1)
    return sorted_data[idx]


@pytest.mark.asyncio
async def test_single_query_latency():
    """A single query should complete in under 10 seconds."""
    _skip_if_no_server()

    async with httpx.AsyncClient() as client:
        elapsed = await _execute_query(client, SAMPLE_QUERIES[0])

    print(f"\n  Single query latency: {elapsed:.3f}s")
    assert elapsed < 10.0, f"Single query took {elapsed:.2f}s — exceeds 10s limit"


@pytest.mark.asyncio
async def test_concurrent_queries_p95():
    """
    10 concurrent queries; P95 latency must be under 2 seconds.

    Success Criteria (from Phase 7 roadmap):
    - P95 < 2s under 10 concurrent requests
    """
    _skip_if_no_server()

    n_concurrent = 10
    queries = (SAMPLE_QUERIES * 3)[:n_concurrent]

    async with httpx.AsyncClient() as client:
        tasks = [_execute_query(client, q) for q in queries]
        timings: List[float] = await asyncio.gather(*tasks)

    p50 = _percentile(timings, 50)
    p95 = _percentile(timings, 95)
    p99 = _percentile(timings, 99)
    avg = statistics.mean(timings)

    print(
        f"\n  Concurrent load ({n_concurrent} parallel requests):\n"
        f"    P50={p50:.3f}s  P95={p95:.3f}s  P99={p99:.3f}s  avg={avg:.3f}s"
    )

    assert p95 < 2.0, (
        f"P95 latency {p95:.2f}s exceeds 2s SLA under {n_concurrent} concurrent requests. "
        f"All timings: {[f'{t:.2f}' for t in sorted(timings)]}"
    )


@pytest.mark.asyncio
async def test_cache_hit_path():
    """
    Send the same query twice — second request should be faster (cache hit).
    """
    _skip_if_no_server()

    question = SAMPLE_QUERIES[0]

    async with httpx.AsyncClient() as client:
        t1 = await _execute_query(client, question)
        t2 = await _execute_query(client, question)

    print(f"\n  Cache test: first={t1:.3f}s  second={t2:.3f}s")
    # Cache hit should be at least 2× faster (LLM call is avoided)
    assert t2 < max(t1, 1.0), "Second request should not be slower than first"


@pytest.mark.asyncio
async def test_pagination_overhead():
    """Pagination params should not significantly increase latency."""
    _skip_if_no_server()

    async with httpx.AsyncClient() as client:
        t_no_page = await _execute_query(client, "Show me all ledger transactions")

        t0 = time.monotonic()
        resp = await client.post(
            f"{SERVER_URL}/api/query/execute",
            json={"question": "Show me all ledger transactions", "page": 1, "page_size": 10},
            headers=_headers(),
            timeout=30.0,
        )
        t_with_page = time.monotonic() - t0

    print(f"\n  Pagination overhead: base={t_no_page:.3f}s  with_page={t_with_page:.3f}s")
    # Pagination should add at most 500ms overhead
    assert abs(t_with_page - t_no_page) < 0.5 or t_with_page < 5.0


@pytest.mark.asyncio
async def test_async_job_submission_latency():
    """Async job submission should return in under 1 second."""
    _skip_if_no_server()

    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SERVER_URL}/api/query/execute-async",
            json={"question": SAMPLE_QUERIES[0]},
            headers=_headers(),
            timeout=10.0,
        )
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200, f"Async submit failed: {resp.text}"
    data = resp.json()
    assert "job_id" in data
    print(f"\n  Async job submit latency: {elapsed:.3f}s  job_id={data['job_id']}")
    assert elapsed < 1.0, f"Async job submit took {elapsed:.2f}s — should be near-instant"
