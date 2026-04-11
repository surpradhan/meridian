# MERIDIAN Architecture

## System Overview

MERIDIAN is a multi-agent data navigation platform that uses natural language processing to understand user queries and route them to specialized domain agents. The architecture follows clean code principles with clear separation of concerns.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      REST API (FastAPI)                         │
│                  /api/query/execute, /validate                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   Orchestrator (Coordinator)                    │
│  Routes queries → Domain Agents → Validator → Builder → Executor
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
    │ Router      │  │ Domain       │  │ Query            │
    │ Agent       │  │ Agents (3)   │  │ Validator        │
    │             │  │ - Sales      │  │ - View checks    │
    │ Routes to:  │  │ - Finance    │  │ - Cardinality    │
    │ - Sales     │  │ - Operations │  │ - Limits         │
    │ - Finance   │  │              │  │ - Columns        │
    │ - Operations│  │ Each agent:  │  │ - Performance    │
    └─────────────┘  │ - View ID    │  └──────────────────┘
                     │ - Filters    │
                     │ - Aggregations
                     └──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │View Registry │  │Query Builder │  │Database      │
    │             │  │             │  │Connection    │
    │ Metadata    │  │SQL Generator │  │             │
    │ Joins       │  │JOINs         │  │Execution    │
    │ Columns     │  │WHERE clauses │  │Transactions │
    │ Cardinality │  │Aggregations  │  │             │
    └──────────────┘  └──────────────┘  └──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │Observability │  │Cache Layer   │  │Security      │
    │ - Logging    │  │(Redis)       │  │- Auth        │
    │ - Metrics    │  │- Result      │  │- CORS        │
    │ - Tracing    │  │  Caching     │  │- HTTPS       │
    └──────────────┘  └──────────────┘  └──────────────┘
```

## Core Components

### 1. REST API Layer (`app/api/routes/`)

**Responsibility**: HTTP interface for external clients

**Query endpoints** (`query.py`):
- `POST /api/query/execute` — Process query; supports `explain=true` for routing + SQL breakdown
- `POST /api/query/validate` — Validate without executing
- `GET /api/query/domains` — List available domains
- `GET /api/query/explore` — Explore domain capabilities

**Async job endpoints** (`jobs.py`):
- `POST /api/query/execute-async` — Submit long-running query as background job
- `GET /api/jobs/{job_id}` — Poll status; returns result when `status=complete`
- `DELETE /api/jobs/{job_id}` — Cancel / forget a job
- `GET /api/jobs` — List all jobs for current session

**Streaming endpoint** (`stream.py`):
- `POST /api/query/stream` — Server-Sent Events; emits `token`, `result`, `done` events

**Export endpoint** (`export.py`):
- `POST /api/query/export` — Run query; download result as JSON, CSV, or Excel attachment

**History endpoints** (`history.py`):
- `GET /api/history?limit=N` — List recent queries, newest first
- `GET /api/history/{id}` — Retrieve a single history entry
- `DELETE /api/history/{id}` — Delete a history entry

**Admin endpoints** (`admin.py`, require `role=admin`):
- `POST /api/admin/domains` — Register a dynamic domain
- `GET /api/admin/domains` — List dynamic domains
- `DELETE /api/admin/domains/{name}` — Remove dynamic domain
- `GET /api/admin/performance` — Index advisor report (recommendations + slow queries + patterns)

**Key Features**:
- Request/response validation with Pydantic
- Automatic domain routing with optional `forced_domain`
- `conversation_id` threaded through request/response for multi-turn sessions
- Optional execution tracing and explain mode
- Error handling and logging

### 2. Orchestrator (`app/agents/orchestrator.py`)

**Responsibility**: Coordinates multi-agent workflow with conversation context and history

**Workflow**:
```
Query + conversation_id?
    ↓
[ConversationManager] — get-or-create session context
    ↓
[Cache] — check context-scoped key ({conv_id}::{query})
    ↓ (miss)
[Router / forced_domain] — domain classification
    ↓
[LangGraph graph.invoke()] — primary execution
    ↓ (fallback: direct agent call)
[HistoryManager.save()] — persist result
    ↓
[_generate_suggestions()] — 3 LLM follow-ups
    ↓
Return result + conversation_id + suggestions
```

**Key Methods**:
- `process_query(query, conversation_id, forced_domain)` - Main workflow
- `process_query_with_trace(query, conversation_id, forced_domain)` - Execution trace
- `validate_query_for_domain(domain, query)`
- `get_domain_capabilities(domain)`
- `new_conversation()` / `get_conversation(id)` - Session helpers

### 2a. Conversation Manager (`app/agents/conversation_context.py`)

**Responsibility**: Track multi-turn session state in memory

**Key Details**:
- `ConversationContext` stores message history (user + assistant), last domain/views/result count, and free-form session variables
- `get_context_summary()` returns a pipe-separated string injected into LLM prompts — includes actual recent user query text so the LLM can resolve pronoun references ("the same", "that region")
- Conversations expire after 60 minutes; `ConversationManager` runs periodic cleanup every 100 queries
- Thread-safe: all mutations protected by `threading.Lock`

### 2b. History Manager (`app/history/manager.py`)

**Responsibility**: Persist completed queries to SQLite

**REST API** (registered in `app/api/routes/history.py`):
- `GET /api/history?limit=N` — newest-first list
- `GET /api/history/{id}` — single entry
- `DELETE /api/history/{id}` — delete entry

**Implementation**: Single shared `sqlite3.Connection(check_same_thread=False)` protected by `threading.Lock`; history save failures are swallowed so they never break query processing.

### 3. Router Agent (`app/agents/router.py`)

**Responsibility**: Classify queries to appropriate domain

**Algorithm** (LLM-first, keyword fallback):
1. Call `get_llm()` to get the shared `ChatOpenAI` singleton
2. If LLM available: send domain descriptions + query to GPT-4, parse JSON response `{domain, confidence, reasoning}`
3. Clamp confidence to `[0.0, 1.0]`; reject unknown domain names → fall back to keyword scoring
4. If LLM unavailable or returns unparseable output: keyword scoring (view mentions weighted 2×)
5. Return domain with highest score + confidence

**Domains**:
- **Sales**: customers, products, regions, revenue
- **Finance**: ledger, accounts, transactions, GL
- **Operations**: inventory, warehouses, shipments

### 4. Domain Agents (`app/agents/domain/`)

**Responsibility**: Natural language understanding for specific domains

**Components**:
- `BaseDomainAgent` - Abstract base with common logic
- `SalesAgent` - Sales-specific query processing
- `FinanceAgent` - Finance-specific query processing
- `OperationsAgent` - Operations-specific query processing

**Processing Pipeline** (each agent — LLM-first, regex fallback):
```
Natural Language Query
        ↓
Try LLM Interpretation (_try_llm_interpret)
  • Send query + domain view schemas to GPT-4
  • Parse JSON → QueryRequest (views, filters, aggregations, group_by)
  • On API/parse failure → fall through to regex
        ↓ (LLM success)
Execute LLM QueryRequest
  • On execution failure (e.g. hallucinated view) → fall through to regex
        ↓ (LLM or execution failure)
Regex Fallback
  • Identify Views (keyword matching)
  • Identify Filters (regex patterns)
  • Identify Aggregations (SUM, COUNT, AVG, etc.)
  • Build QueryRequest
        ↓
Execute via Builder
        ↓
Return Results with Confidence + interpretation_method ("llm" | "regex")
```

### 5. LLM Client (`app/agents/llm_client.py`)

**Responsibility**: Provide a single shared LLM instance for the process

**Provider priority** (Groq → OpenAI):
1. If `GROQ_API_KEY` is set → initialize `ChatGroq` (`langchain-groq`), default model `llama-3.3-70b-versatile`
2. Else if `OPENAI_API_KEY` is set → initialize `ChatOpenAI` (`langchain-openai`), default model `gpt-4`
3. Else → return `None` (LLM features disabled, regex fallback used everywhere)

**Design**:
- Module-level singleton (`_client`, `_init_attempted`) — initialized once on first call
- Returns `None` gracefully when no key is configured
- `reset_llm_client()` resets state for test injection

**Usage**: Both `RouterAgent` and `BaseDomainAgent` call `get_llm()` — never instantiate providers directly.

### 6. Query Validator (`app/query/validator.py`)

**Responsibility**: Validate queries before execution

**Validations**:
1. **View Validation**: All views exist in registry
2. **Combination Validation**: Views can be joined properly
3. **Cardinality Validation**: Many-to-many without aggregation = warning
4. **Limit Validation**: Enforces max_result_rows constraint
5. **Column Validation**: Filter/aggregation columns exist
6. **SQL Syntax Validation**: Pre-validates generated SQL via SQLite `EXPLAIN` on an in-memory DB before hitting the real database — catches misspelled keywords, unclosed parentheses, and malformed clauses; fail-open (unexpected validator errors return `True` to avoid blocking valid queries); missing table/column errors are expected and treated as pass

**Features**:
- `validate()` - Full validation
- `validate_sql_syntax(sql)` → `(is_valid, errors)` — syntax pre-check via SQLite EXPLAIN
- `estimate_result_size()` - Row count estimation
- `get_validation_warnings()` - Non-blocking suggestions
- Singleton connection (`_SYNTAX_CONN`) protected by `_SYNTAX_LOCK` (thread-safe, one connection reused across calls)

### 7. Query Builder (`app/query/builder.py`)

**Responsibility**: Generate parameterized SQL from QueryRequest

**Features**:
- `build_query_parameterized()` → `(sql, params)` — production path; all user values as `?` placeholders
- `build_query()` — backward-compatible string API (calls `build_query_parameterized` internally)
- `_build_from_clause()` — Smart JOIN generation with multi-hop BFS via `ViewRegistry.find_join_path`
- `_build_where_clause_parameterized()` — parameterized WHERE, COLLATE NOCASE on strings
- `_build_having_clause_parameterized()` — HAVING with `_SAFE_HAVING_OPS` whitelist, numeric values only
- `_render_window_function()` — OVER (PARTITION BY … ORDER BY …) clause generation
- `_apply_time_expression()` — delegates to `time_intelligence.py`, validates `time_column` against registry

**Smart JOINs**:
- Automatically detects join paths using registry
- Handles one-to-one, one-to-many, many-to-one relationships
- Multi-hop: injects intermediate bridge views via BFS (`find_join_path`)
- Prevents invalid many-to-many joins

### 7a. Time Intelligence (`app/query/time_intelligence.py`)

**Responsibility**: Resolve natural-language temporal expressions into concrete ISO date ranges

**Supported expressions**: `last_quarter`, `this_quarter`, `last_month`, `this_month`, `ytd`/`year_to_date`, `last_year`, `trailing_N_days`

**Key Functions**:
- `resolve_time_expression(expression, reference_date?)` → `(start_date, end_date)` or `None`
- `build_date_filters(expression, date_column, reference_date?)` → filter dict with `__gte__` / `__lte__` keys
- `detect_time_expression(text)` → extract expression from free text

**Integration**: `QueryBuilder._apply_time_expression()` validates `time_column` against registered view columns, then calls `build_date_filters()` and adds results as parameterized WHERE conditions.

### 7b. Visualization Hints (`app/visualization/chart_selector.py`)

**Responsibility**: Infer chart type from query result shape

**Chart selection heuristics**:
- **line**: result has a date/time column + one numeric column (time series)
- **pie**: ≤ 8 rows, exactly one string column + one numeric column (proportional)
- **bar**: ≥ 2 rows with string group + numeric aggregate
- **table**: fallback for any other shape

**Integration**: `Orchestrator._build_visualization_hint()` is called after every query; result dict gains a `visualization` key: `{chart_type, x_axis, y_axis, reason}`.

### 8a. Async Job Store (`app/jobs/store.py`)

**Responsibility**: Background job queue for long-running queries

**Design**:
- `JobStore` wraps `concurrent.futures.ThreadPoolExecutor`; thread-safe `dict[str, JobRecord]` protected by `threading.Lock`
- `submit(fn)` → `job_id` (UUID); runs `fn` in pool; captures result or exception into `JobRecord`
- `cleanup_old_jobs(max_age_seconds)` — prunes completed jobs older than threshold
- Module-level singleton via `get_job_store()`

**States**: `PENDING → RUNNING → COMPLETE | FAILED`

### 8b. Streaming Callback (`app/agents/streaming.py`)

**Responsibility**: Bridge LangChain token events to an async generator

**Design**:
- `MeridianStreamingCallback` extends `BaseCallbackHandler`
- `on_llm_new_token(token)` puts tokens onto a `queue.Queue`; `on_llm_end` / `on_llm_error` signals done via sentinel
- `iter_tokens()` — sync generator for thread consumers
- `aiter_tokens()` — async generator using `asyncio.get_event_loop().run_in_executor` for SSE route

### 8c. Domain Registry (`app/onboarding/registry.py`)

**Responsibility**: Persist and serve dynamically registered domains

**Design**:
- SQLite-backed `dynamic_domains` table (JSON-serialized `DomainConfig`)
- `register(config)` validates slug, rejects conflicts with built-in domains (`sales`, `finance`, `operations`), upserts
- After registration, `_reload_orchestrator()` rebuilds dynamic agents in the running `Orchestrator`
- `DynamicDomainAgent` (in `agent_factory.py`) extends `BaseDomainAgent` from config at runtime

### 8d. Export (`app/export/exporters.py`)

**Responsibility**: Serialize query result rows to downloadable formats

- `to_json(rows)` → UTF-8 bytes via `json.dumps(default=str)`
- `to_csv(rows)` → UTF-8-BOM bytes via `csv.DictWriter`
- `to_excel(rows)` → `.xlsx` bytes via `pandas.DataFrame.to_excel` + `openpyxl`

### 8e. Explain Builder (`app/explain/builder.py`)

**Responsibility**: Build structured explanation from orchestrator result

**`ExplainResponse` fields**: `query`, `routing_decision`, `views_selected`, `filters_extracted`, `aggregations`, `group_by`, `sql_generated`, `join_paths`, `time_resolution`, `interpretation_method`, `confidence`

**Integration**: `POST /api/query/execute` with `explain=true` appends `"explain": ExplainResponse.model_dump()` to the response.

### 8f. OAuth2 / OIDC Manager (`app/auth/oauth.py`)

**Responsibility**: Delegated authentication via Google OAuth2 and generic OIDC providers

**Flow**:
1. `authorize(provider)` — builds provider authorization URL, stores a CSRF `state` token in `_STATE_STORE` (in-process dict), returns redirect URL
2. `handle_callback(provider, code, state)` — validates state, exchanges auth code for tokens, fetches userinfo, auto-provisions new users as `viewer` via `UserStore`
3. Returns a Meridian JWT (same format as username/password login)

**Providers**:
- **Google**: configured via `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- **Generic OIDC**: configured via `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`; endpoints discovered from `{issuer}/.well-known/openid-configuration`

**Design notes**:
- `_STATE_STORE` is in-process memory — multi-worker deployments (Gunicorn `-w N`, Kubernetes) must replace it with a Redis-backed store
- All three OIDC settings are required together (enforced by `@model_validator` in `config.py`); partial config raises `ValueError` at startup

### 8. View Registry (`app/views/registry.py`)

**Responsibility**: Centralized metadata about views

**Contains**:
- View definitions with columns
- Join relationships between views
- Column properties (PK, FK, nullable, type)
- Domain mappings

**Key Methods**:
- `get_view(name)` - Get view metadata
- `find_joins(view1, view2)` - Direct join lookup
- `find_join_path(from_view, to_view)` - BFS shortest join path (multi-hop)
- `get_reachable_views(start_view)` - BFS connectivity set
- `validate_view_combination(views)` - Check if views can be joined

### 9. Database Connection (`app/database/connection.py`)

**Responsibility**: Safe database access

**Features**:
- Connection pooling
- Transaction management
- SQL injection prevention
- Mock database support for testing

### 10. Observability (`app/observability/`)

**Components**:

**Logging** (`logging.py`):
- Structured JSON logging
- Log context for request tracking
- Level-based filtering

**Metrics** (`metrics.py`):
- Counter metrics
- Gauge metrics
- Histogram metrics with percentiles
- Query-specific tracking (duration, rows, domain)

## Data Flow Example

### Query: "How many sales were made?"

```
1. API receives query
   POST /api/query/execute
   {"question": "How many sales were made?"}

2. Orchestrator routes query
   RouterAgent.route() → GPT-4 classifies → "sales" domain, confidence 0.95
   (fallback: keyword scoring if LLM unavailable)

3. Domain agent processes (LLM path)
   SalesAgent._try_llm_interpret() → GPT-4 returns QueryRequest JSON
   selected_views=["sales_fact"], filters={}, aggregations={"sale_id": "COUNT"}
   (fallback: regex _identify_views/_identify_filters/_identify_aggregations)

4. Validator checks
   - sales_fact exists ✓
   - No filters ✓
   - COUNT on sale_id exists ✓
   - No cardinality issues ✓

5. Builder generates SQL
   SELECT COUNT(sale_id) FROM sales_fact

6. Executor runs query
   - Executes SQL
   - Returns results
   - Records metrics

7. API returns response
   {
     "domain": "sales",
     "routing_confidence": 0.95,
     "confidence": 0.85,
     "result": [{"COUNT(sale_id)": 1234}],
     "row_count": 1,
     "state": "complete",
     "conversation_id": "abc-123",
     "suggestions": ["Top 5 customers?", "Break down by region?", "Compare to last month?"],
     "cache_hit": false
   }
```

## State Management

### Query Processing States

```
INITIAL → ROUTING → VALIDATION → EXECUTION → COMPLETE
                         ↓
                        ERROR
```

**State Transitions**:
- INITIAL → ROUTING: Always happens
- ROUTING → VALIDATION: Always happens
- VALIDATION → EXECUTION: Only if no errors
- EXECUTION → COMPLETE: On success
- Any state → ERROR: On exception

## Error Handling

**Error Hierarchy**:
1. **Pydantic Validation** - Request model validation
2. **Router** - Domain classification failures
3. **Agent** - Natural language processing errors
4. **Validator** - Query validation failures
5. **Builder** - SQL generation errors
6. **Executor** - Database execution errors

**Each layer** logs errors and propagates to next layer with context.

## Configuration Management

**Environments**:
1. **Development** (`config/development.yaml`)
   - Debug mode on
   - JSON logging off
   - Database echo on
   - Metrics enabled

2. **Production** (`config/production.yaml`)
   - Debug mode off
   - JSON logging on
   - Database echo off
   - SSL required

**Environment Variables**:
- `ENVIRONMENT` - deployment environment
- `DATABASE_URL` - database connection string
- `LOG_LEVEL` - logging verbosity
- `SECRET_KEY` - security key

## Testing Architecture

**Test Organization**:
```
tests/
├── unit/                        # Fast, isolated tests
│   ├── test_views.py            # View registry (35 tests)
│   ├── test_llm_phase3.py       # LLM routing + interpretation (20 tests)
│   ├── test_phase4.py           # Conversational Intelligence (50 tests)
│   ├── test_phase6.py           # Advanced Query Capabilities (65 tests)
│   └── test_phase7.py           # Scale & Polish unit tests (35 tests)
├── integration/                 # Multi-component tests
│   ├── test_agents.py
│   ├── test_advanced_features.py
│   ├── test_history_api.py
│   ├── test_orchestrator.py
│   ├── test_phase3_phase4.py
│   ├── test_phase7_api.py       # Phase 7 API integration (16 tests)
│   ├── test_ui_queries.py
│   └── test_views.py
├── performance/                 # Load tests (require TEST_SERVER_URL)
│   └── test_load.py             # P50/P95/P99 latency, concurrency (5 tests)
└── fixtures/                    # Test data
    ├── data.py
    └── mocks.py
```

**Total: 541+ tests, all passing**

## Deployment Architecture

**Local Development**:
- Docker Compose with PostgreSQL + Redis
- Auto-reloading FastAPI server
- Structured JSON logging to console

**Production**:
- Containerized application
- External PostgreSQL database
- Redis cache layer
- Prometheus metrics export
- Structured logging to files

**Scalability**:
- Stateless API servers (can run multiple)
- Database connection pooling
- Redis for caching and session management
- Metrics for monitoring

## Design Principles

1. **Separation of Concerns**: Each module has single responsibility
2. **Dependency Injection**: Components receive dependencies, not create them
3. **Interface Segregation**: Small, focused interfaces
4. **Testability**: All components tested independently
5. **Observability**: Comprehensive logging and metrics
6. **Type Safety**: Full type hints throughout

## Future Enhancements

1. **Kubernetes / Helm**: Manifests for cloud deployment at scale
2. **Multi-tenancy**: Row-level security for multiple organizations
3. **Audit Log API**: Expose the audit trail via a REST endpoint
4. **Webhook notifications**: Push job-complete events to caller-supplied URLs
5. **OAuth state in Redis**: Replace in-process `_STATE_STORE` for multi-worker deployments

---

**Last Updated**: 2026-04-12
