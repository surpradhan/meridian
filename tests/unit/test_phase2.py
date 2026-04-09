"""
Unit Tests for Phase 2: Activate Scaffolded Features

Covers:
- Pagination (2.2): Paginator slicing, metadata, edge cases
- Rate limiting (2.3): RateLimitMiddleware allows/rejects requests
- Concurrent request limiting (2.3): ConcurrentRequestMiddleware
- Cache behaviour (2.1): CacheManager hit/miss/disabled
- LLM retry (2.5): invoke_llm_with_retry retries on transient errors, not others
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

try:
    import tenacity
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False


# ---------------------------------------------------------------------------
# 2.2 Pagination
# ---------------------------------------------------------------------------

class TestPaginator:

    def _rows(self, n: int):
        return [{"id": i, "value": i * 10} for i in range(1, n + 1)]

    # --- slice correctness ---

    @pytest.mark.parametrize("page,page_size,total,expected_ids", [
        (1, 10, 25, list(range(1, 11))),   # first page
        (2, 10, 25, list(range(11, 21))),  # middle page
        (3, 10, 25, list(range(21, 26))),  # partial last page
        (1, 25, 25, list(range(1, 26))),   # single full page
    ])
    def test_page_slice(self, page, page_size, total, expected_ids):
        from app.query.pagination import Paginator
        result = Paginator().paginate(self._rows(total), page=page, page_size=page_size)
        assert [r["id"] for r in result.rows] == expected_ids

    # --- metadata ---

    @pytest.mark.parametrize("page,page_size,total,has_next,has_prev,next_p,prev_p,total_pages", [
        (1, 10, 25, True,  False, 2,    None, 3),
        (2, 10, 25, True,  True,  3,    1,    3),
        (3, 10, 25, False, True,  None, 2,    3),
        (1, 25, 25, False, False, None, None, 1),
    ])
    def test_page_metadata(self, page, page_size, total, has_next, has_prev, next_p, prev_p, total_pages):
        from app.query.pagination import Paginator
        result = Paginator().paginate(self._rows(total), page=page, page_size=page_size)
        assert result.has_next is has_next
        assert result.has_previous is has_prev
        assert result.next_page == next_p
        assert result.previous_page == prev_p
        assert result.total_pages == total_pages
        assert result.total_rows == total

    # --- edge cases ---

    def test_empty_result_set(self):
        from app.query.pagination import Paginator
        result = Paginator().paginate([], page=1, page_size=10)
        assert result.rows == []
        assert result.total_rows == 0
        assert result.total_pages == 0

    def test_out_of_range_page_clamped(self):
        from app.query.pagination import Paginator
        rows = self._rows(5)
        assert Paginator().paginate(rows, page=99, page_size=5).page == 1
        assert Paginator().paginate(rows, page=0,  page_size=5).page == 1

    def test_page_size_clamped_to_max(self):
        from app.query.pagination import Paginator, PaginationConfig
        config = PaginationConfig(max_page_size=50)
        result = Paginator(config).paginate(self._rows(100), page=1, page_size=999)
        assert len(result.rows) == 50

    # --- to_dict shape ---

    def test_to_dict_shape(self):
        from app.query.pagination import Paginator
        d = Paginator().paginate(self._rows(15), page=1, page_size=5).to_dict()
        assert set(d.keys()) == {"data", "pagination"}
        p = d["pagination"]
        assert p["page"] == 1
        assert p["total_pages"] == 3
        assert p["total_rows"] == 15
        assert p["has_next"] is True
        assert p["has_previous"] is False

    # --- limit/offset variant ---

    def test_paginate_with_limit_offset(self):
        from app.query.pagination import Paginator
        rows = [{"id": i} for i in range(20)]
        page_rows, info = Paginator().paginate_with_limit(rows, limit=5, offset=10)
        assert [r["id"] for r in page_rows] == list(range(10, 15))
        assert info["offset"] == 10
        assert info["total_rows"] == 20
        assert info["has_more"] is True


# ---------------------------------------------------------------------------
# 2.3 Rate Limiting Middleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:

    def _make_request(self, client_ip: str = "127.0.0.1", path: str = "/api/query/execute"):
        req = MagicMock()
        req.url.path = path
        req.client.host = client_ip
        return req

    def _ok_next(self):
        from starlette.responses import JSONResponse
        async def _next(req):
            return JSONResponse({"ok": True})
        return _next

    def _make_middleware(self, requests_per_minute: int = 5):
        from app.api.middleware import RateLimitMiddleware
        from starlette.applications import Starlette
        return RateLimitMiddleware(Starlette(), requests_per_minute=requests_per_minute)

    def test_allows_requests_under_limit(self):
        middleware = self._make_middleware(requests_per_minute=5)
        ok_next = self._ok_next()

        async def run():
            for _ in range(5):
                resp = await middleware.dispatch(self._make_request(), ok_next)
                assert resp.status_code == 200

        asyncio.run(run())

    def test_rejects_over_limit_with_429(self):
        middleware = self._make_middleware(requests_per_minute=2)
        ok_next = self._ok_next()

        async def run():
            req = self._make_request()
            for _ in range(2):
                await middleware.dispatch(req, ok_next)
            resp = await middleware.dispatch(req, ok_next)
            assert resp.status_code == 429

        asyncio.run(run())

    def test_rate_limit_response_has_retry_after_header(self):
        middleware = self._make_middleware(requests_per_minute=1)
        ok_next = self._ok_next()

        async def run():
            req = self._make_request()
            await middleware.dispatch(req, ok_next)
            resp = await middleware.dispatch(req, ok_next)
            assert resp.status_code == 429
            assert "Retry-After" in resp.headers

        asyncio.run(run())

    def test_health_check_exempt_from_rate_limit(self):
        middleware = self._make_middleware(requests_per_minute=1)
        ok_next = self._ok_next()

        async def run():
            # Exhaust the limit on a regular path
            await middleware.dispatch(self._make_request(path="/api/query/execute"), ok_next)
            # Health check must still pass
            resp = await middleware.dispatch(self._make_request(path="/health"), ok_next)
            assert resp.status_code == 200

        asyncio.run(run())

    def test_different_ips_tracked_independently(self):
        middleware = self._make_middleware(requests_per_minute=1)
        ok_next = self._ok_next()

        async def run():
            await middleware.dispatch(self._make_request("10.0.0.1"), ok_next)
            resp_a = await middleware.dispatch(self._make_request("10.0.0.1"), ok_next)
            assert resp_a.status_code == 429

            resp_b = await middleware.dispatch(self._make_request("10.0.0.2"), ok_next)
            assert resp_b.status_code == 200

        asyncio.run(run())


# ---------------------------------------------------------------------------
# 2.3 Concurrent Request Middleware
# ---------------------------------------------------------------------------

class TestConcurrentRequestMiddleware:

    def _make_middleware(self, max_concurrent: int):
        from app.api.middleware import ConcurrentRequestMiddleware
        from starlette.applications import Starlette
        return ConcurrentRequestMiddleware(Starlette(), max_concurrent=max_concurrent)

    def test_semaphore_starts_as_none(self):
        """Semaphore is created lazily on first dispatch, not at init time."""
        middleware = self._make_middleware(max_concurrent=5)
        assert middleware._semaphore is None

    def test_rejects_when_semaphore_exhausted(self):
        """Returns 503 when all concurrent slots are occupied."""
        from starlette.responses import JSONResponse
        middleware = self._make_middleware(max_concurrent=1)

        async def ok_next(req):
            return JSONResponse({"ok": True})

        async def run():
            # Pre-initialise and drain the semaphore inside the running loop
            middleware._semaphore = asyncio.Semaphore(1)
            await middleware._semaphore.acquire()  # holds the only slot

            req = MagicMock()
            req.url.path = "/api/query/execute"
            req.client.host = "127.0.0.1"

            resp = await middleware.dispatch(req, ok_next)
            assert resp.status_code == 503

            middleware._semaphore.release()

        asyncio.run(run())

    def test_max_concurrent_stored_on_instance(self):
        middleware = self._make_middleware(max_concurrent=7)
        assert middleware.max_concurrent == 7


# ---------------------------------------------------------------------------
# 2.1 Cache Manager
# ---------------------------------------------------------------------------

class TestCacheManager:

    def _make_cache(self, enabled=False):
        """Return a fresh CacheManager with no Redis connection."""
        from app.cache.manager import CacheManager, CacheConfig
        CacheManager._instance = None
        return CacheManager(CacheConfig(enabled=enabled))

    def test_get_returns_none_when_disabled(self):
        assert self._make_cache().get("SELECT 1") is None

    def test_set_returns_false_when_disabled(self):
        assert self._make_cache().set("SELECT 1", [{"a": 1}]) is False

    def test_get_result_returns_none_when_disabled(self):
        assert self._make_cache().get_result("some query") is None

    def test_set_result_returns_false_when_disabled(self):
        assert self._make_cache().set_result("some query", {"result": []}) is False

    def test_miss_increments_miss_counter(self):
        cache = self._make_cache()
        cache.get("q1")
        cache.get("q2")
        assert cache.stats["misses"] == 2

    def test_get_stats_shape(self):
        stats = self._make_cache().get_stats()
        assert {"hit_rate", "hits", "misses", "sets", "deletes"}.issubset(stats)

    def test_reset_stats(self):
        cache = self._make_cache()
        cache.stats["hits"] = 10
        cache.stats["misses"] = 5
        cache.reset_stats()
        assert cache.stats == {"hits": 0, "misses": 0, "sets": 0, "deletes": 0}

    def test_cache_key_is_deterministic(self):
        cache = self._make_cache()
        assert cache._make_key("SELECT 1") == cache._make_key("SELECT 1")

    def test_cache_key_differs_per_query(self):
        cache = self._make_cache()
        assert cache._make_key("SELECT 1") != cache._make_key("SELECT 2")

    def test_redis_hit(self):
        from app.cache.manager import CacheManager, CacheConfig
        CacheManager._instance = None
        cache = CacheManager(CacheConfig(enabled=True))
        cached_data = [{"id": 1, "val": "x"}]
        cache.client = MagicMock()
        cache.client.get.return_value = json.dumps(cached_data)

        assert cache.get("SELECT 1") == cached_data
        assert cache.stats["hits"] == 1

    def test_redis_miss(self):
        from app.cache.manager import CacheManager, CacheConfig
        CacheManager._instance = None
        cache = CacheManager(CacheConfig(enabled=True))
        cache.client = MagicMock()
        cache.client.get.return_value = None

        assert cache.get("SELECT 1") is None
        assert cache.stats["misses"] == 1

    def test_redis_set_calls_setex(self):
        from app.cache.manager import CacheManager, CacheConfig
        CacheManager._instance = None
        cache = CacheManager(CacheConfig(enabled=True, ttl_seconds=60))
        cache.client = MagicMock()

        assert cache.set("SELECT 1", [{"id": 1}]) is True
        assert cache.stats["sets"] == 1
        cache.client.setex.assert_called_once()


# ---------------------------------------------------------------------------
# 2.5 LLM Retry
# ---------------------------------------------------------------------------

class TestLLMRetry:
    """
    Tests for invoke_llm_with_retry in app.agents.llm_client.

    Retry-behaviour tests (actually exercising the retry loop) are skipped
    when tenacity is not installed, because without it the decorator is a
    no-op that passes through immediately.

    The non-retry tests (success path, fallback integration) run regardless.
    """

    def test_success_on_first_call(self):
        from app.agents.llm_client import invoke_llm_with_retry
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="ok")

        result = invoke_llm_with_retry(llm, "hello")

        assert result.content == "ok"
        llm.invoke.assert_called_once_with("hello")

    @pytest.mark.skipif(not TENACITY_AVAILABLE, reason="tenacity not installed")
    def test_retries_on_transient_error_then_succeeds(self):
        from app.agents.llm_client import invoke_llm_with_retry, _TRANSIENT_LLM_ERRORS
        llm = MagicMock()
        success = MagicMock(content="success")
        # Raise the first transient error type, succeed on second attempt
        llm.invoke.side_effect = [_TRANSIENT_LLM_ERRORS[0]("transient"), success]

        result = invoke_llm_with_retry(llm, "hello")

        assert result.content == "success"
        assert llm.invoke.call_count == 2

    @pytest.mark.skipif(not TENACITY_AVAILABLE, reason="tenacity not installed")
    def test_does_not_retry_on_non_transient_error(self):
        """ValueError (bad input) must NOT be retried — it reraises immediately."""
        from app.agents.llm_client import invoke_llm_with_retry
        llm = MagicMock()
        llm.invoke.side_effect = ValueError("bad prompt")

        with pytest.raises(ValueError, match="bad prompt"):
            invoke_llm_with_retry(llm, "hello")

        # Only one attempt — no retry for non-transient errors
        assert llm.invoke.call_count == 1

    @pytest.mark.skipif(not TENACITY_AVAILABLE, reason="tenacity not installed")
    def test_reraises_after_all_retries_exhausted(self):
        """After 3 failed attempts, the last transient error is reraised."""
        from app.agents.llm_client import invoke_llm_with_retry, _TRANSIENT_LLM_ERRORS
        llm = MagicMock()
        err = _TRANSIENT_LLM_ERRORS[0]("always fails")
        llm.invoke.side_effect = err

        with pytest.raises(_TRANSIENT_LLM_ERRORS[0]):
            invoke_llm_with_retry(llm, "hello")

        assert llm.invoke.call_count == 3

    def test_base_domain_falls_back_to_none_on_retry_exhaustion(self):
        """_try_llm_interpret returns None when invoke_llm_with_retry raises."""
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.query.builder import QueryBuilder
        from app.agents.domain.sales import SalesAgent
        from app.agents.llm_client import reset_llm_client

        reset_llm_client()
        reset_db()
        registry = create_test_registry()
        agent = SalesAgent(registry, DbConnection(is_mock=True), QueryBuilder(registry))

        with patch("app.agents.domain.base_domain.get_llm", return_value=MagicMock()), \
             patch("app.agents.domain.base_domain.invoke_llm_with_retry",
                   side_effect=RuntimeError("exhausted")):
            result = agent._try_llm_interpret("show me sales data")

        assert result is None

    def test_router_falls_back_to_keywords_on_retry_exhaustion(self):
        """RouterAgent falls back to keyword routing when invoke_llm_with_retry raises."""
        from app.agents.router import RouterAgent
        from app.views.registry import create_test_registry
        from app.database.connection import reset_db
        from app.agents.llm_client import reset_llm_client

        reset_llm_client()
        reset_db()
        router = RouterAgent(create_test_registry())

        with patch("app.agents.router.get_llm", return_value=MagicMock()), \
             patch("app.agents.router.invoke_llm_with_retry",
                   side_effect=RuntimeError("exhausted")):
            domain, confidence = router.route("total sales by region")

        assert domain in ("sales", "finance", "operations")
        assert 0.0 <= confidence <= 1.0
