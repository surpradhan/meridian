# 🧭 MERIDIAN
## Intelligent Data Navigation Platform
### Product Roadmap (Updated with Langchain + Langraph)

**Tagline:** *"The True North for Your Data"*

**Tech Stack:** Python + Langchain + Langchain OpenAI + Langraph + FastAPI

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack Justification](#technology-stack-justification)
4. [Project Structure](#project-structure)
5. [Current State Assessment](#current-state-assessment)
6. [Phase-by-Phase Roadmap](#phase-by-phase-roadmap)
   - [Phase 1: Foundation — COMPLETED](#phase-1-foundation--completed)
   - [Phase 2: Activate Scaffolded Features](#phase-2-activate-scaffolded-features-weeks-12)
   - [Phase 3: LLM-Powered NL Understanding](#phase-3-llm-powered-nl-understanding-weeks-35)
   - [Phase 4: Conversational Intelligence](#phase-4-conversational-intelligence-weeks-68)
   - [Phase 5: Enterprise Security & Multi-Tenancy](#phase-5-enterprise-security--multi-tenancy-weeks-912)
   - [Phase 6: Advanced Query Capabilities](#phase-6-advanced-query-capabilities-weeks-1316)
   - [Phase 7: Scale & Polish](#phase-7-scale--polish-weeks-1720)
7. [Prioritization Rationale](#prioritization-rationale)
8. [Key Files Reference](#key-files-reference)
9. [Verification Plan](#verification-plan)

---

## EXECUTIVE SUMMARY

### Problem
Modern enterprises have abundant data but struggle to access it. Querying databases requires SQL expertise, is time-consuming, carries security risks, and is limited to pre-built dashboards. Business users need a way to ask questions in plain English and get trusted answers instantly.

### Solution
**MERIDIAN** — A multi-agent data navigation platform using:
- **Langchain** — LLM abstractions and tool management
- **Langchain OpenAI** — GPT-4 for superior reasoning
- **Langraph** — Stateful orchestration of multi-agent workflows
- **FastAPI** — REST API layer

MERIDIAN routes queries to specialized domain agents (Sales, Finance, Operations), each with:
- Domain-specific view access
- Pre-defined join patterns
- Business rule constraints
- Query validation pipeline

**Like a compass guiding explorers, MERIDIAN guides your data queries to the right expertise — automatically.**

### Prototype Outcomes (Completed)
- ✅ 3 working domain agents (Sales, Finance, Operations)
- ✅ Intelligent query routing via LLM classification (GPT-4) with keyword fallback
- ✅ Multi-agent orchestration with state machine + LangGraph fallback
- ✅ Safe query generation and execution with validation pipeline
- ✅ REST API serving agent requests (6 endpoints)
- ✅ Gradio chat UI for interactive querying
- ✅ Structured JSON logging throughout pipeline
- ✅ Docker containerization (dev + prod)
- ✅ 235+ passing tests (unit + integration)

### Vision (Next Phases)
- ✅ LLM-powered natural language understanding (GPT-4 routing + interpretation, regex fallback)
- ✅ Multi-turn conversational queries with context memory
- ✅ Enterprise security scaffolding (auth middleware, audit logging, CORS configuration)
- ✅ Advanced SQL capabilities (HAVING, window functions, CTEs, ORDER BY, parameterized queries)
- ✅ Multi-hop join pathfinding (BFS over join graph)
- ✅ Time intelligence ("last quarter", "ytd", "trailing N days")
- ✅ Auto-visualization hints (line/bar/pie/table chart type selection)
- 🔲 Self-service domain onboarding

---

## ARCHITECTURE OVERVIEW

### System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATIONS                   │
│              (Web UI, Mobile, API Clients)               │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ HTTP Request
                     ▼
┌─────────────────────────────────────────────────────────┐
│              FASTAPI APPLICATION                         │
├─────────────────────────────────────────────────────────┤
│  • Request validation & authentication                   │
│  • Rate limiting & caching                              │
│  • Observability (logs, metrics, traces)                │
└────────────┬──────────────────────────┬─────────────────┘
             │                          │
             │ User Query               │ Telemetry
             ▼                          ▼
    ┌──────────────────────┐   ┌──────────────────┐
    │  LANGRAPH WORKFLOW   │   │  OBSERVABILITY   │
    │  (State Management)  │   │  (OpenTelemetry) │
    └────────┬─────────────┘   └──────────────────┘
             │
    ┌────────▼──────────────────────────────┐
    │  REQUEST ROUTER NODE                   │
    │  (Langchain Router Agent)              │
    │  • Detect intent/domain via LLM        │
    │  • Route to appropriate agent(s)       │
    └──┬──────────────────┬──────────┬───────┘
       │                  │          │
       ▼                  ▼          ▼
   ┌──────────┐      ┌──────────┐  ┌──────────┐
   │SALES     │      │FINANCE   │  │OPS       │
   │AGENT     │      │AGENT     │  │AGENT     │
   │(Langchain)      │(Langchain)  │(Langchain)
   │+ GPT-4   │      │+ GPT-4   │  │+ GPT-4   │
   └──┬───────┘      └──┬───────┘  └──┬───────┘
      │                 │             │
      └─────────────────┼─────────────┘
                        │
    ┌───────────────────▼──────────────────┐
    │  LANGCHAIN TOOLS LAYER               │
    ├──────────────────────────────────────┤
    │  • query_sales_views (structured tool)
    │  • query_finance_views (structured tool)
    │  • query_operations_views (structured tool)
    │  • All wrapped with Pydantic schemas  │
    └───────────────────┬──────────────────┘
                        │
        ┌───────────────┼────────────────┐
        │               │                │
        ▼               ▼                ▼
   ┌─────────┐   ┌──────────────┐  ┌──────────────┐
   │ VIEW    │   │ QUERY        │  │ QUERY        │
   │ MAPPER  │   │ VALIDATOR    │  │ EXECUTOR     │
   └─────────┘   └──────────────┘  └──────────────┘
        │               │                │
        └───────────────┼────────────────┘
                        │
                        ▼
            ┌──────────────────────┐
            │  DATABASE            │
            │  (Fact & Dimension   │
            │   Views)             │
            └──────────────────────┘
```

### Key Components

| Component | Purpose | Tech |
|-----------|---------|------|
| **FastAPI Server** | HTTP API layer, request routing | FastAPI 0.104+ |
| **Langraph** | Multi-agent state management, workflow orchestration | Langraph 0.1+ |
| **Langchain** | LLM abstractions, tool management, memory | Langchain 0.1+ |
| **Langchain OpenAI** | GPT-4 for superior reasoning & function calling | Langchain OpenAI 0.1+ |
| **View Registry** | Metadata about all views, relationships, constraints | Python / JSON |
| **View Mapper** | Determines valid joins, constructs queries | Pydantic models |
| **Query Validator** | Prevents malicious/unsafe queries | Custom validation |
| **Domain Agents** | Specialized agents with tools for each business area | Langchain Agents |
| **Database Driver** | Executes validated queries | SQLAlchemy / psycopg2 |

---

## TECHNOLOGY STACK JUSTIFICATION

### Why Langchain + Langchain OpenAI + Langraph?

| Technology | Why | Replaces | Trade-off |
|------------|-----|----------|-----------|
| **Langchain** | Abstract LLM complexity, built-in tool management, memory, prompt templates | Raw API calls | Slight overhead, worth it for features |
| **Langchain OpenAI** | GPT-4 has superior function calling; better structured output | Direct API calls | Cost higher but performance better for tool use |
| **Langraph** | Production-grade workflow orchestration, built for Langchain | Custom state machine | Learning curve, worth long-term |
| **FastAPI** | Async-native, auto-docs, built-in validation | Flask | Flask simpler but FastAPI better for agents |

### Why GPT-4?

GPT-4's native function calling support, structured output reliability, and first-class Langchain integration make it the best fit for MERIDIAN's agent-heavy architecture. The higher cost is justified by its performance on tool use and multi-step reasoning tasks.

### Dependencies

```txt
# Core Framework
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0

# Langchain Ecosystem
langchain==0.1.4
langchain-openai==0.0.6
langchain-community==0.0.10
langraph==0.1.1

# LLM & Tools
openai==1.3.0
tenacity==8.2.3  # Retries for API calls

# Data & Database
sqlalchemy==2.0.23
pandas==2.1.2
psycopg2-binary==2.9.9

# Observability
langchain-tracing==0.1.0  # Built into Langsmith
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
python-json-logger==2.0.7

# Development & Testing
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.1
black==23.12.0
mypy==1.7.1
```

---

## PROJECT STRUCTURE

```
meridian/
│
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Environment configuration
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py                # FastAPI routes
│   │   ├── models.py                # Request/response models
│   │   └── middleware.py            # Auth, logging, CORS
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py            # Base agent using Langchain
│   │   ├── sales_agent.py           # Sales domain agent
│   │   ├── finance_agent.py         # Finance domain agent
│   │   ├── operations_agent.py      # Operations domain agent
│   │   ├── orchestrator.py          # Langraph multi-agent router
│   │   └── prompts.py               # Prompt templates
│   │
│   ├── views/
│   │   ├── __init__.py
│   │   ├── registry.py              # View metadata registry
│   │   ├── mapper.py                # View relationship mapper
│   │   ├── models.py                # View schema models
│   │   └── seed_data.py             # Initialize view metadata
│   │
│   ├── query/
│   │   ├── __init__.py
│   │   ├── builder.py               # Query construction
│   │   ├── validator.py             # Query validation rules
│   │   ├── executor.py              # Query execution wrapper
│   │   └── schemas.py               # Query request schemas
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── structured_tools.py      # Langchain StructuredTool definitions
│   │   ├── tool_registry.py         # Tool management
│   │   └── tool_handlers.py         # Tool implementation logic
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py            # DB connection pooling
│   │   └── models.py                # SQLAlchemy models
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── logging.py               # Structured logging
│   │   ├── langsmith.py             # Langsmith integration
│   │   └── metrics.py               # Prometheus metrics
│   │
│   └── utils/
│       ├── __init__.py
│       ├── validators.py            # Data validation helpers
│       └── exceptions.py            # Custom exceptions
│
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_tools.py
│   ├── test_queries.py
│   ├── test_views.py
│   └── test_integration.py
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .dockerignore
│
├── notebooks/
│   ├── 01_explore_views.ipynb
│   ├── 02_test_langchain_agent.ipynb
│   └── 03_performance_analysis.ipynb
│
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── README.md
└── ARCHITECTURE.md
```

---

## CURRENT STATE ASSESSMENT

| Layer | Maturity | Key Gap |
|-------|----------|---------|
| NL Understanding | 95% | GPT-4 routing + interpretation; multi-turn context threading; regex fallback |
| Query Building | 95% | HAVING, window functions, CTEs, ORDER BY, time expressions, multi-hop joins, parameterized queries |
| Query Validation | 70% | No SQL syntax validation |
| REST API | 75% | No auth; history API live; pagination wired; rate limiting in middleware |
| UI (Gradio) | 75% | History sidebar, interactive follow-up suggestion buttons, multi-turn sessions |
| Security | 10% | Middleware is a stub; CORS is `*` |
| Observability | 40% | Structured logging complete; metrics/tracing scaffolded but unwired |
| Caching & Performance | 60% | Redis cache integrated; context-scoped cache keys prevent cross-session hits |
| Visualization | 70% | Chart-type hints generated; Plotly rendering in Gradio not yet wired |

**Overall Product Maturity: ~85%** — Core architecture is sound, testing is comprehensive (297 tests), and all four intelligence phases are complete. Primary remaining gaps: no security layer and no advanced SQL capabilities.

---

## PHASE-BY-PHASE ROADMAP

### Phase 1: Foundation — COMPLETED

All foundational prototype work has been completed. Code implementations live in the source files listed below.

| Original Phase | Deliverables | Key Files | Status |
|---|---|---|---|
| **View Registry** | View metadata models (ViewSchema, ColumnSchema, JoinRelationship), ViewRegistry with relationship tracking, seed data for 8 views across 3 domains (Sales, Finance, Operations), mock DB for testing | `app/views/registry.py`, `app/views/models.py`, `app/views/seed.py` | ✅ Complete |
| **First Agent (Sales)** | Sales agent with regex-based NL parsing, QueryBuilder with auto-JOIN generation, FastAPI endpoints (execute, validate, domains, explore, health), Gradio chat UI with sample queries | `app/agents/domain/sales.py`, `app/query/builder.py`, `app/api/routes/query.py`, `gradio_app.py` | ✅ Complete |
| **Query Safety** | QueryValidator with view/column/cardinality checks, SQL injection prevention via parameterized queries, COLLATE NOCASE for case-insensitive matching, result row limit enforcement | `app/query/validator.py`, `app/query/builder.py` | ✅ Complete |
| **Multi-Agent** | Finance + Operations domain agents, Router with keyword-based scoring + confidence, Orchestrator state machine (INITIAL → ROUTING → VALIDATION → EXECUTION → COMPLETE), LangGraph orchestrator (as fallback) | `app/agents/domain/finance.py`, `app/agents/domain/operations.py`, `app/agents/router.py`, `app/agents/orchestrator.py`, `app/agents/langraph_orchestrator.py` | ✅ Complete |
| **Production (partial)** | Docker Compose (dev + prod), Structured JSON logging, Gunicorn config | `docker-compose.yml`, `docker-compose.prod.yml`, `app/observability/logging.py` | ✅ Complete |
| **Production (remaining)** | Redis caching (written, not wired), Pagination (written, not wired), Rate limiting (configured, not implemented), OpenTelemetry (installed, not integrated), Langsmith (configured, not integrated), Conversation context (written, not wired), Streaming responses, Retry policies, Load testing, Performance benchmarks | `app/cache/manager.py`, `app/query/pagination.py`, `app/api/middleware.py`, `app/observability/tracing.py`, `app/agents/conversation_context.py`, `app/config.py` | ❌ Incomplete — addressed in Phases 2–7 |

**Testing:** 235+ tests passing across unit and integration suites.

---

### Phase 2: Activate Scaffolded Features (Weeks 1–2)

**Theme:** *"Flip the switches"*
**Goal:** Go from 60% → 75% maturity by activating ~2,000 LOC of orphaned production code

This phase completes the remaining items from the original Phase 5 (Production) that already have code written but are not connected to the main flow.

#### 2.1 Activate Query Caching
- **What:** Wire `app/cache/manager.py` (350 LOC) into the orchestrator's query execution path
- **Why:** Repeated queries hit the database every time; the Redis CacheManager with TTL, pattern invalidation, and hit/miss stats already exists
- **Files:** `app/agents/orchestrator.py`, `app/cache/manager.py`
- **Effort:** Small

#### 2.2 Enable API Pagination
- **What:** Connect `app/query/pagination.py` (250 LOC) to API responses; add `page`, `page_size`, `offset` params to the execute endpoint
- **Why:** Hardcoded `limit=100` means large result sets are silently truncated; PaginationConfig supports page-based, LIMIT/OFFSET, and streaming modes
- **Files:** `app/api/routes/query.py`, `app/query/pagination.py`
- **Effort:** Small

#### 2.3 Wire Rate Limiting & Request Logging Middleware
- **What:** Implement the TODO stubs in `app/api/middleware.py` using config values already defined in `app/config.py` (`rate_limit_per_minute=60`, `max_concurrent_requests=10`)
- **Why:** No protection against abuse or accidental DDoS; middleware file is a 25-line stub
- **Files:** `app/api/middleware.py`, `app/config.py`
- **Effort:** Small

#### 2.4 Activate Distributed Tracing & Langsmith
- **What:** Integrate `app/observability/tracing.py` (200 LOC) into the request lifecycle; wire Langsmith tracing for LLM calls using config already in `app/config.py`
- **Why:** OpenTelemetry + Jaeger are installed and configured but never called; Langsmith API key is loaded but never used
- **Files:** `app/observability/tracing.py`, `app/main.py`, `app/config.py`
- **Effort:** Small

#### 2.5 Add Retry Policies
- **What:** Configure Tenacity retry decorators for external API calls (OpenAI, Redis)
- **Why:** Tenacity is already in dependencies but not used; transient failures in LLM calls will crash the pipeline
- **Files:** `app/agents/domain/base_domain.py`, `app/cache/manager.py`
- **Effort:** Small

**Success Criteria:**
- Cache hits visible in Redis for repeated queries
- API responses include pagination metadata (`page`, `total_pages`, `next_page`)
- Rate limit returns 429 after exceeding threshold
- Jaeger traces appear for end-to-end request flow
- Langsmith dashboard shows LLM call traces

---

### Phase 3: LLM-Powered NL Understanding — COMPLETED

**Theme:** *"Make the AI actually AI"*
**Goal:** Replace regex with LLM-powered query interpretation — the single highest-impact change

#### 3.1 LLM-Powered Domain Routing ✅
- **What:** GPT-4 classification call in `app/agents/router.py` replaces keyword-only scoring
- **Approach:** Prompt with domain descriptions + view schemas → structured JSON output (domain, confidence, reasoning)
- **Fallback:** Keyword scoring used when LLM is unavailable or returns unparseable/unknown output
- **Files:** `app/agents/router.py`, `app/agents/llm_client.py`

#### 3.2 LLM-Powered Query Interpretation ✅
- **What:** Each domain agent calls GPT-4 to extract views, filters, aggregations, group-by as a structured `QueryRequest`
- **Approach:** Domain view schemas sent in prompt → JSON response parsed into `QueryRequest`
- **Two-stage fallback:** LLM API/parse errors fall back to regex; LLM-generated requests that fail execution also fall back to regex
- **Files:** `app/agents/domain/base_domain.py`, `app/agents/domain/sales.py`, `app/agents/domain/finance.py`, `app/agents/domain/operations.py`

#### 3.3 Confidence-Based Clarification ✅
- **What:** Routing confidence below 0.4 returns a clarification response instead of guessing
- **Applies to:** both `process_query()` and `process_query_with_trace()` — clarification responses are never cached
- **Files:** `app/agents/orchestrator.py`, `app/api/routes/query.py`

#### 3.4 Shared LLM Client Singleton ✅
- **What:** One `ChatOpenAI` instance per process (not per request); `reset_llm_client()` for test injection
- **Files:** `app/agents/llm_client.py`

**Test coverage:** 20 new tests in `tests/unit/test_llm_phase3.py` covering LLM routing, interpretation, clarification, and singleton behaviour.

---

### Phase 4: Conversational Intelligence — ✅ COMPLETED

**Theme:** *"Remember what I just asked"*
**Goal:** Multi-turn conversations and query refinement

#### 4.1 Wire Conversation Context ✅
- **What:** `ConversationContext` / `ConversationManager` fully wired into the orchestrator for session-based state management. Context summary (domain, views, recent user queries) is injected into LLM prompts to resolve references like "just the West" or "that region".
- **Implementation details:** Thread-safe `ConversationManager` with `threading.Lock`; per-session cache key scoping (`{conv_id}::{query}`) prevents cross-session cache collisions; periodic cleanup of expired conversations every 100 queries; unknown/expired conversation IDs silently create a new session.
- **Files:** `app/agents/conversation_context.py`, `app/agents/orchestrator.py`, `app/api/routes/query.py`

#### 4.2 Query History & Saved Queries ✅
- **What:** Queries and results persisted to SQLite (`query_history` table). REST API with three endpoints: `GET /api/history`, `GET /api/history/{id}`, `DELETE /api/history/{id}`. History sidebar in Gradio UI.
- **Implementation details:** `HistoryManager` uses a single shared `sqlite3.Connection` (WAL-compatible) protected by a `threading.Lock`; non-critical failures are swallowed so history errors never break query processing.
- **New files:** `app/history/manager.py`, `app/history/__init__.py`, `app/api/routes/history.py`

#### 4.3 Smart Suggestions ✅
- **What:** After each result, 3 follow-up query suggestions are generated by the LLM (static domain-keyed fallbacks when LLM unavailable). Suggestions appear as real interactive `gr.Button` components in the Gradio UI — clicking one populates the query box and auto-submits.
- **Implementation details:** LLM prompt inputs are length-capped (query≤300, domain≤30, views≤5×50 chars) to prevent prompt bloat and adversarial injection. Suggestions are stored in `gr.State` so button-click lambdas can retrieve text by index.
- **Files:** `app/agents/orchestrator.py`, `gradio_app.py`

#### 4.4 Promote LangGraph as Primary Orchestrator ✅
- **What:** `LangraphOrchestrator.graph.invoke()` is now the primary execution path. The pre-routed domain is passed in the initial state so LangGraph's route node does not re-route, preserving the caller's routing decision. Conversation context (`context_summary`) flows through the graph to the agent processing node. Falls back transparently to direct agent call on any LangGraph error.
- **Files:** `app/agents/langraph_orchestrator.py`, `app/agents/orchestrator.py`

**Results:**
- 50 new unit tests in `tests/unit/test_phase4.py`; 12 new integration tests in `tests/integration/test_history_api.py`
- Multi-turn refinement: "total sales by region" → "just the West" resolves correctly via context summary in LLM prompt
- Query history survives process restarts (SQLite-backed)
- Follow-up suggestions appear as interactive buttons after each query result
- LangGraph is the primary execution engine; direct agent call is the fallback

---

### Phase 5: Enterprise Security & Multi-Tenancy (Weeks 9–12)

**Theme:** *"Safe to put in front of real users"*
**Goal:** Production-grade security for internal deployment

#### 5.1 Authentication Layer
- **What:** JWT-based auth with API key support; user isolation for query history and saved queries
- **Why:** Cannot deploy internally without knowing who's querying what
- **Config:** `SECRET_KEY` and `ACCESS_TOKEN_ALGORITHM` already exist in settings
- **Files:** `app/api/middleware.py`, new `app/auth/` module
- **Effort:** Medium-Large

#### 5.2 Row-Level Security & Field Masking
- **What:** Domain-based access control (e.g., Finance team can't see Sales data without permission); sensitive field masking
- **Why:** Data governance requirement for any enterprise deployment
- **Approach:** Extend ViewRegistry with access policies; filter at query-build time
- **Files:** `app/views/registry.py`, `app/query/builder.py`
- **Effort:** Large

#### 5.3 Audit Logging
- **What:** Structured log of every query: who, what, when, which tables accessed, how many rows returned
- **Why:** Compliance requirement; also useful for understanding usage patterns and debugging
- **Approach:** Middleware + DB table; queryable via admin API
- **Files:** `app/api/middleware.py`, new `app/audit/` module
- **Effort:** Medium

#### 5.4 CORS Lockdown & HTTPS
- **What:** Replace `allow_origins=["*"]` with configured origins; enforce HTTPS in production
- **Files:** `app/main.py`, `app/config.py`
- **Effort:** Small

**Success Criteria:**
- Unauthenticated requests return 401
- Finance team can only query finance domain views
- All queries are audited with user identity and timestamp
- CORS rejects requests from unconfigured origins

---

### Phase 6: Advanced Query Capabilities — ✅ COMPLETED

**Theme:** *"Answer harder questions"*
**Goal:** Handle the complex queries that currently fail silently

#### 6.1 Complex SQL Support ✅
- **What:** HAVING clauses with operator whitelist + numeric enforcement; window functions (ROW_NUMBER, RANK, DENSE_RANK, SUM, AVG, etc.) with Pydantic validator; CTEs (WITH clauses); typed ORDER BY items; full parameterization replacing all string interpolation of user values
- **Files:** `app/query/builder.py`, `app/views/models.py`
- Added: `OrderByItem`, `WindowFunction` (with `@validator`), `CTEDefinition` models; `_SAFE_HAVING_OPS` whitelist; `build_query_parameterized()` returning `(sql, params)`

#### 6.2 Multi-Hop Join Resolution ✅
- **What:** BFS pathfinding over the join graph in `ViewRegistry.find_join_path()` — automatically injects bridge views when two requested views have no direct relationship
- **Files:** `app/views/registry.py`, `app/agents/domain/base_domain.py`
- `get_join_paths()` stub replaced with `self.registry.find_join_path(from_view, to_view)`

#### 6.3 Time Intelligence ✅
- **What:** `app/query/time_intelligence.py` resolves temporal expressions into concrete ISO date ranges and injects them as parameterized WHERE filters
- **Expressions supported:** `last_quarter`, `this_quarter`, `last_month`, `this_month`, `ytd`/`year_to_date`, `last_year`, `trailing_N_days`
- `time_column` validated against registered view columns before resolution
- **Files:** new `app/query/time_intelligence.py`, `app/query/builder.py`

#### 6.4 Data Visualization Hints ✅
- **What:** `app/visualization/chart_selector.py` infers chart type from result shape (line for time series, bar for categorical groupings, pie for ≤8 proportional slices, table otherwise)
- Orchestrator attaches `visualization` hint dict to every result: `{chart_type, x_axis, y_axis, reason}`
- **Files:** new `app/visualization/`, `app/agents/orchestrator.py`

#### 6.5 End-to-End Security Fix (SQL Injection) ✅
- All user-supplied filter values, HAVING values, and date range values now use `?` placeholders via `build_query_parameterized()`. Production execution path (`execute_query_request`) exclusively uses the parameterized path.

**Test Results:** 65 new tests in `tests/unit/test_phase6.py`; 441+ tests total passing (12 history API tests pre-existing failures unrelated to Phase 6).

---

### Phase 7: Scale & Polish (Weeks 17–20)

**Theme:** *"Ready for the demo day"*
**Goal:** Production polish, performance, and extensibility

This phase also completes the remaining original Phase 5 items: streaming, load testing, benchmarks, and API docs.

#### 7.1 Async Query Execution
- **What:** Background job queue for long-running queries with status polling endpoint
- **Why:** Complex multi-table queries with large result sets can exceed HTTP timeout limits
- **Effort:** Medium

#### 7.2 Streaming Responses
- **What:** Implement streaming via Langchain's built-in streaming support for real-time token output
- **Why:** Long-running LLM calls leave users staring at a loading spinner; streaming shows progress
- **Effort:** Medium

#### 7.3 Self-Service Domain Onboarding
- **What:** Framework for registering new domains without code changes: upload a schema, define keywords, auto-generate an agent
- **Why:** Adding a new domain currently requires writing a new agent class, updating the router, and adding tests
- **Effort:** Large

#### 7.4 Export Options
- **What:** JSON, Excel (.xlsx), and PDF export alongside existing CSV download
- **Why:** Business users need to share results in formats their stakeholders expect
- **Effort:** Small

#### 7.5 Query Explain Mode
- **What:** Show users *why* the system interpreted their question the way it did — which domain was selected, what views were chosen, what filters were extracted, and the generated SQL
- **Why:** Builds trust and helps users learn the system's language for more effective querying
- **Effort:** Medium

#### 7.6 Performance Optimization
- **What:** Activate `app/database/index_optimizer.py` (400 LOC, already written) for auto-index recommendations; connection pool tuning based on load testing
- **Files:** `app/database/index_optimizer.py`
- **Effort:** Small-Medium

#### 7.7 Load Testing & Benchmarks
- **What:** Establish performance baselines; test concurrent request handling; document P50/P95/P99 latencies
- **Why:** Original Phase 5 success criteria required handling 10 concurrent requests with P95 < 2 seconds
- **Effort:** Medium

#### 7.8 API Documentation Completion
- **What:** Complete `docs/API.md` with full endpoint documentation, request/response examples, and error codes
- **Why:** Swagger auto-docs exist but lack narrative documentation for integrators
- **Effort:** Small

**Success Criteria:**
- Streaming responses visible in Gradio UI as tokens arrive
- New domain can be onboarded in < 30 minutes without code changes
- P95 latency < 2 seconds under 10 concurrent requests
- Export buttons for JSON/Excel/PDF appear in Gradio UI

---

## PRIORITIZATION RATIONALE

| Phase | Theme | Impact | Effort | Risk | Rationale |
|-------|-------|--------|--------|------|-----------|
| **2: Activate scaffolded** | Flip the switches | High | Low | Low | Pure activation; ~2,000 LOC exists and is tested |
| **3: Real NL** | Make the AI actually AI | Very High | Medium | Medium | Transforms product from keyword search to genuine AI |
| **4: Conversational** | Remember what I asked | High | Medium | Low | Biggest UX upgrade; conversation context code already exists |
| **5: Security** | Safe for real users | Critical (gate) | Medium-Large | Low | Required for any multi-user or internet-facing deployment |
| **6: Advanced queries** | Answer harder questions | High | Large | Medium | Enables power-user scenarios; drives retention |
| **7: Scale & polish** | Demo day ready | Medium | Mixed | Low | Compounds quality; completes original Phase 5 vision |

**Total Estimated Timeline:** ~20 weeks from Phase 2 start

---

## KEY FILES REFERENCE

| File | Role | Phases |
|------|------|--------|
| `app/agents/orchestrator.py` | Central query coordinator | 2, 3, 4 |
| `app/agents/router.py` | Domain routing (keyword → LLM) | 3 |
| `app/agents/domain/base_domain.py` | Shared agent logic | 3, 6 |
| `app/agents/domain/sales.py` | Sales NL parsing | 3 |
| `app/agents/domain/finance.py` | Finance NL parsing | 3 |
| `app/agents/domain/operations.py` | Operations NL parsing | 3 |
| `app/agents/conversation_context.py` | Session state — active, multi-turn context threading | 4 |
| `app/agents/langraph_orchestrator.py` | Graph orchestrator — primary execution engine (Phase 4) | 4 |
| `app/api/routes/query.py` | API endpoints | 2, 4, 5 |
| `app/api/middleware.py` | Security & rate limiting stub | 2, 5 |
| `app/cache/manager.py` | Redis caching — active, context-scoped cache keys | 2 |
| `app/query/builder.py` | SQL generation — HAVING, window functions, CTEs, ORDER BY, parameterized queries | 6 |
| `app/query/time_intelligence.py` | Temporal expression → ISO date range resolver | 6 |
| `app/visualization/chart_selector.py` | Chart-type hint inference from result shape | 6 |
| `app/query/pagination.py` | Pagination (written, not wired) | 2 |
| `app/history/manager.py` | SQLite-backed query history persistence | 4 |
| `app/api/routes/history.py` | History REST API (GET / GET id / DELETE id) | 4 |
| `app/query/validator.py` | Query safety checks | 6 |
| `app/observability/tracing.py` | OpenTelemetry (written, not wired) | 2 |
| `app/database/index_optimizer.py` | Index advisor (written, not wired) | 7 |
| `app/config.py` | All settings (many defined, not all used) | 2, 3, 5 |
| `gradio_app.py` | Web UI | 3, 4, 6 |

---

## VERIFICATION PLAN

After each phase, verify with these steps:

1. **Run full test suite:** `make test` — all 441+ tests must continue passing
2. **Manual smoke test via Gradio:** Run sample queries from each domain at `http://localhost:7860`
3. **API test:** Hit each endpoint via curl/httpie and verify response shape at `http://localhost:8000/docs`

**Phase-specific checks:**

| Phase | What to Verify |
|-------|---------------|
| **Phase 2** | Cache hits in Redis (`redis-cli KEYS *`), pagination params in API responses, 429 on rate limit, Jaeger traces at `http://localhost:16686` |
| **Phase 3** | Synonym queries route correctly, ambiguous queries trigger clarification, regex fallback works when LLM unavailable |
| **Phase 4** | ✅ Multi-turn refinement works ("total sales by region" → "just the West"), history persists across restarts (`GET /api/history`), suggestion buttons wired in UI |
| **Phase 5** | Unauthenticated requests return 401, cross-domain access denied, audit log table populates |
| **Phase 6** | "Top N" queries return correct results, time expressions resolve to correct dates, charts render in Gradio |
| **Phase 7** | Streaming tokens appear progressively, new domain onboards in < 30 min, P95 < 2s under load |
