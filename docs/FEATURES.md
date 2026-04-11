# MERIDIAN Features

Advanced capabilities available in the platform. Most features are configurable via environment variables or `config/production.yaml`.

## Table of Contents

1. [Distributed Tracing](#distributed-tracing)
2. [Query Caching](#query-caching)
3. [Result Pagination](#result-pagination)
4. [LangGraph Orchestration](#langgraph-orchestration)
5. [Conversation Context](#conversation-context)
6. [Index Optimization](#index-optimization)
7. [Time Intelligence](#time-intelligence)
8. [Visualization Hints & Plotly Charts](#visualization-hints--plotly-charts)
9. [OAuth2 / OIDC SSO](#oauth2--oidc-sso)
10. [SQL Syntax Validation](#sql-syntax-validation)

---

## Distributed Tracing

End-to-end request visibility via **OpenTelemetry** and **Jaeger**. Tracks requests from API entry through routing, domain agents, validation, and database execution.

```python
from app.observability import setup_tracing, get_tracer

setup_tracing(service_name="meridian", jaeger_host="localhost", jaeger_port=6831)

tracer = get_tracer()
with tracer.start_as_current_span("query_processing") as span:
    span.set_attribute("query", "SELECT * FROM sales")
    # ... execute query ...
    span.set_attribute("rows_returned", 42)
```

**Docker Jaeger (local):**
```bash
docker run -d -p 16686:16686 -p 6831:6831/udp jaegertracing/all-in-one
# UI at http://localhost:16686
```

**Config:**
```bash
TRACING_ENABLED=true
JAEGER_HOST=localhost
JAEGER_PORT=6831
```

Langsmith tracing for LLM calls is also supported — set `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`.

---

## Query Caching

Redis-based caching with deterministic cache keys (hash of query + parameters + conversation ID). Supports TTL, pattern invalidation, hit/miss stats, and graceful degradation when Redis is unavailable.

```python
from app.cache import setup_cache, get_cache

setup_cache(host="localhost", port=6379, ttl_seconds=3600)

cache = get_cache()

# Cache lookup
result = cache.get("SELECT * FROM sales WHERE region = ?", {"region": "WEST"})
if result is None:
    result = execute_query(...)
    cache.set("SELECT * FROM sales WHERE region = ?", result, {"region": "WEST"})

# Invalidate
cache.invalidate_query(query, params)
cache.clear()  # flush all

# Stats
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

**Config:**
```bash
CACHE_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_TTL_SECONDS=3600
```

Note: cache keys are scoped per conversation (`{conv_id}::{query}`) to prevent cross-session collisions.

---

## Result Pagination

Prevents memory overload for large result sets. Three modes: page-based, offset-based, and streaming.

**Page-based:**
```python
from app.query import Paginator

paginator = Paginator()
page = paginator.paginate(rows, page=1, page_size=100)

print(f"Page {page.page} of {page.total_pages}, has_next={page.has_next}")
response = page.to_dict()
```

**Offset-based:**
```python
page_data, info = paginator.paginate_with_limit(rows, limit=100, offset=100)
print(f"Returned {info['returned_rows']} rows, has_more={info['has_more']}")
```

**Streaming (large datasets):**
```python
from app.query import StreamingResult

stream = StreamingResult(rows, chunk_size=1000)
for chunk in stream:
    send_to_client(chunk)
```

**Config:**
```bash
PAGINATION_DEFAULT_PAGE_SIZE=100
PAGINATION_MAX_PAGE_SIZE=10000
```

---

## LangGraph Orchestration

LangGraph is the **primary execution engine** as of Phase 4. The orchestrator builds a `StateGraph` with nodes for routing, agent processing, validation, and execution. Falls back transparently to a direct agent call on any LangGraph error.

```
ROUTE → PROCESS_AGENT → VALIDATE → EXECUTE → COMPLETE
                  ↓                    ↓
                ERROR               ERROR
```

```python
from app.agents import LangraphOrchestrator

orchestrator = LangraphOrchestrator(registry, db)
result = orchestrator.process_query("How many sales last quarter?")

# View the compiled graph structure
print(orchestrator.get_workflow_graph())
```

The pre-routed domain is passed in the initial state so LangGraph's route node does not re-classify, preserving the caller's routing decision. Conversation context flows through the graph to the agent processing node.

---

## Conversation Context

Multi-turn session state persisted in memory. Tracks message history, last domain/views/result count, and free-form session variables. Context summary is injected into LLM prompts so follow-up references like "just the West" or "that region" resolve correctly.

```python
from app.agents import get_conversation_manager

manager = get_conversation_manager()
conversation = manager.create_conversation()

# Turn 1
conversation.add_user_message("Show sales by region")
conversation.update_context(domain="sales", result_count=1500)
conversation.add_assistant_message("Found 1500 sales rows", result)

# Turn 2 — context is injected into LLM prompt automatically
conversation.add_user_message("Just the West region?")
context_summary = conversation.get_context_summary()
# → "Last domain queried: sales | Last query returned 1500 rows | Recent: Show sales by region"

# Session variables
conversation.set_session_variable("default_region", "WEST")
region = conversation.get_session_variable("default_region")

# Management
stats = manager.get_stats()   # active conversation count
manager.cleanup_expired()     # remove conversations older than 60 min
```

Conversations expire after 60 minutes. Cleanup runs automatically every 100 queries. All mutations are thread-safe via `threading.Lock`.

**Config:**
```bash
CONVERSATION_MAX_HISTORY=50
CONVERSATION_MAX_AGE_MINUTES=60
```

---

## Index Optimization

Analyzes query patterns to recommend database indexes. Tracks slow queries and generates `CREATE INDEX` SQL for the highest-impact columns.

```python
from app.database import IndexOptimizer

optimizer = IndexOptimizer()

# Record queries (typically wired into execute_query automatically)
optimizer.analyzer.record_query("sales_fact", ["customer_id"], elapsed_ms=45.0)
optimizer.analyzer.record_query("sales_fact", ["customer_id", "date"], elapsed_ms=120.0)

# Get recommendations
analysis = optimizer.analyze_workload()
for rec in analysis["recommendations"]:
    print(rec["sql"])    # CREATE INDEX ...
    print(rec["reason"]) # why this index helps

# Slow query summary
summary = optimizer.analyzer.get_slow_query_summary()
print(f"Slow queries: {summary['slow_query_count']}")

# Domain-specific tips
tips = optimizer.get_query_plan_tips("sales_fact")
for tip in tips:
    print(tip)
```

The index optimizer module (`app/database/index_optimizer.py`) is written and tested. Full wiring into the execution path is planned for Phase 7.

---

## Time Intelligence

Resolves natural-language temporal expressions into concrete ISO date ranges, injected as parameterized WHERE filters.

**Supported expressions:** `last_quarter`, `this_quarter`, `last_month`, `this_month`, `ytd` / `year_to_date`, `last_year`, `trailing_N_days`

```python
from app.query.time_intelligence import resolve_time_expression, detect_time_expression

# Resolve expression to date range
start, end = resolve_time_expression("last_quarter")
# → ("2025-10-01", "2025-12-31")

# Detect expression in free text
expr = detect_time_expression("Show me sales from last quarter")
# → "last_quarter"
```

In the query builder, `time_column` is validated against registered view columns before the expression is resolved and injected as parameterized WHERE conditions. This prevents both invalid column references and SQL injection.

---

## Visualization Hints & Plotly Charts

Every orchestrator result includes a `visualization` key with an inferred chart type, and the Gradio UI renders it as an interactive Plotly chart.

**Chart selection heuristics:**

| Condition | Chart type |
|-----------|-----------|
| Date/time column + one numeric column | `line` |
| ≤8 rows, one string + one numeric column | `pie` |
| ≥2 rows with string group + numeric aggregate | `bar` |
| Everything else | `table` |

```python
# Result shape from orchestrator
{
    "result": [...],
    "visualization": {
        "chart_type": "bar",
        "x_axis": "region",
        "y_axis": "total_revenue",
        "reason": "Categorical grouping with numeric aggregate"
    }
}
```

The Gradio UI (`gradio_app.py`) reads the `visualization` hint and renders a full Plotly figure via `build_plotly_figure()`. Charts are interactive (hover, zoom, pan) and appear alongside the tabular results. The chart type and axis mapping are determined automatically — no configuration needed.

---

## OAuth2 / OIDC SSO

MERIDIAN supports delegated login via **Google OAuth2** and any **generic OIDC provider** (Okta, Keycloak, Azure AD, etc.).

**Setup — Google:**
```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

**Setup — Generic OIDC (Okta, Keycloak, etc.):**
```bash
OIDC_ISSUER=https://your-provider.example.com
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

All three OIDC variables must be set together (or all left unset) — the server rejects partial OIDC configuration at startup.

**Flow:**
1. `GET /api/auth/oauth/authorize?provider=google` → returns `{ redirect_url, state }`
2. User logs in at provider, consents
3. Provider redirects to `GET /api/auth/oauth/callback?code=...&state=...`
4. Server validates state, exchanges code, provisions user if new, returns Meridian JWT

New OAuth users are auto-provisioned as `viewer` with no domain access; an admin must grant permissions.

> ⚠️ **Multi-worker deployments**: OAuth state tokens are stored in-process memory. Running multiple workers (Gunicorn `-w 4`, Kubernetes) requires replacing `_STATE_STORE` in `app/auth/oauth.py` with a Redis-backed store.

See [docs/AUTH.md](AUTH.md) for the full authentication and RBAC guide.

---

## SQL Syntax Validation

Before executing a generated SQL query against the real database, `QueryValidator.validate_sql_syntax()` parses it through SQLite's `EXPLAIN` on a schema-less in-memory database. This catches SQL parse errors (misspelled keywords, unclosed parentheses, malformed clauses) without touching live data.

```python
from app.query.validator import get_validator

validator = get_validator()
valid, errors = validator.validate_sql_syntax(
    "SELECT region, SUM(amount) FROM sales_fact GROUP BY region LIMIT 100"
)
# valid=True, errors=[]

valid, errors = validator.validate_sql_syntax("SELEKT region FROM sales_fact")
# valid=False, errors=["SQL syntax error: near 'SELEKT': syntax error"]
```

**Design decisions:**
- **Fail-open**: unexpected validator errors log at `ERROR` level but return `True` to avoid blocking valid queries due to validator bugs
- **Missing tables/columns are expected**: the in-memory DB has no schema; those errors are treated as pass
- **Singleton connection**: a module-level `_SYNTAX_CONN` (protected by `_SYNTAX_LOCK`) avoids creating a new connection on every call
- **DDL skipped**: `CREATE`, `ALTER`, `DROP` are not `EXPLAIN`-able in SQLite and are never emitted by the builder anyway

---

## Configuration Reference

```yaml
# config/production.yaml
observability:
  tracing:
    enabled: true
    jaeger_host: jaeger.example.com
    jaeger_port: 6831

cache:
  enabled: true
  redis_host: redis.example.com
  ttl_seconds: 3600

pagination:
  default_page_size: 100
  max_page_size: 10000

conversation:
  max_history: 50
  max_age_minutes: 60
```

---

## Testing

```bash
# Advanced feature integration tests
pytest tests/integration/test_advanced_features.py -v

# Specific feature
pytest tests/integration/test_advanced_features.py::TestDistributedTracing -v

# Phase 6 query capability tests (65 tests)
pytest tests/unit/test_phase6.py -v
```
