# MERIDIAN Performance Benchmarks

## Overview

This document describes how to run load tests, what the performance targets are,
and where to find results.

---

## Targets (Phase 7 SLA)

| Metric | Target |
|--------|--------|
| Single query (no cache) | < 10s |
| P50 latency (10 concurrent) | < 1s |
| P95 latency (10 concurrent) | **< 2s** |
| P99 latency (10 concurrent) | < 5s |
| Async job submission | < 1s |
| Cache hit response | < 500ms |

---

## Running the Tests

### Prerequisites

1. Start the MERIDIAN API server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. Obtain a JWT token (or use a test token from the dev environment):
   ```bash
   curl -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "changeme"}'
   ```

3. Export environment variables:
   ```bash
   export TEST_SERVER_URL=http://localhost:8000
   export TEST_AUTH_TOKEN=<your-jwt-token>
   ```

### Running

```bash
# Run only performance tests
pytest -m performance tests/performance/ -v -s

# Run with timing output
pytest -m performance tests/performance/ -v -s --tb=short
```

### Excluding from CI

The default test run excludes performance tests:

```ini
# pytest.ini
addopts = -v --strict-markers --tb=short --disable-warnings
```

To run all tests including performance:
```bash
pytest tests/ -m "not skip"
```

---

## What the Tests Cover

| Test | Description |
|------|-------------|
| `test_single_query_latency` | Single query end-to-end |
| `test_concurrent_queries_p95` | 10 parallel requests, measures P50/P95/P99 |
| `test_cache_hit_path` | Same query twice — verifies cache benefit |
| `test_pagination_overhead` | Pagination should add < 500ms |
| `test_async_job_submission_latency` | Job submit should return < 1s |

---

## Index Optimizer

After running a workload, query the performance endpoint to see index recommendations:

```bash
curl -H "Authorization: Bearer $TEST_AUTH_TOKEN" \
  http://localhost:8000/api/admin/performance | jq .
```

This returns:
- `recommendations` — suggested CREATE INDEX statements with priority and reason
- `slow_queries` — tables with the most slow queries
- `pattern_analysis` — access frequency per table

---

## Tuning Tips

- **Redis caching** significantly reduces P95 for repeated queries. Ensure `REDIS_URL` is set.
- **Connection pool** size is configured via `DATABASE_POOL_SIZE` (default: 5). Increase for high concurrency.
- **LLM routing** is the largest latency contributor. Enable `CACHE_ENABLED=true` and ensure Redis is running.
- **Async execution** (`POST /api/query/execute-async`) is recommended for queries expected to run > 2s.
