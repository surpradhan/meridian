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
- ✅ Intelligent query routing via keyword-based classification
- ✅ Multi-agent orchestration with state machine + LangGraph fallback
- ✅ Safe query generation and execution with validation pipeline
- ✅ REST API serving agent requests (6 endpoints)
- ✅ Gradio chat UI for interactive querying
- ✅ Structured JSON logging throughout pipeline
- ✅ Docker containerization (dev + prod)
- ✅ 158+ passing tests (unit + integration)

### Vision (Next Phases)
- 🔲 LLM-powered natural language understanding (replace regex with GPT-4)
- 🔲 Multi-turn conversational queries with context memory
- 🔲 Enterprise security (auth, row-level access, audit logging)
- 🔲 Advanced SQL capabilities (window functions, CTEs, time intelligence)
- 🔲 Auto-visualization of query results
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
| NL Understanding | 30% | Pure regex/keyword matching; no LLM reasoning |
| Query Building | 80% | Missing HAVING, subqueries, window functions, CTEs |
| Query Validation | 70% | No SQL syntax validation |
| REST API | 60% | No auth, pagination not wired, rate limiting not wired |
| UI (Gradio) | 50% | No query history, no multi-turn, no refinement suggestions |
| Security | 10% | Middleware is a stub; CORS is `*` |
| Observability | 40% | Structured logging complete; metrics/tracing scaffolded but unwired |
| Caching & Performance | 30% | Redis cache code exists but not integrated |

**Overall Product Maturity: ~60%** — Core architecture is sound, testing is comprehensive, code quality is high. The primary gaps are: no LLM-powered understanding (regex-only), production features half-implemented, and no security layer.

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

**Testing:** 158+ tests passing across unit and integration suites.

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

### Phase 3: LLM-Powered NL Understanding (Weeks 3–5)

**Theme:** *"Make the AI actually AI"*
**Goal:** Replace regex with LLM-powered query interpretation — the single highest-impact change

Currently, Meridian's "AI" is keyword matching. The OpenAI API key is configured in `app/config.py` but never called. This phase transforms the product from a keyword search tool into a genuine natural language interface.

#### 3.1 LLM-Powered Domain Routing
- **What:** Replace keyword scoring in `app/agents/router.py` with a GPT-4 classification call
- **Why:** Current routing fails on synonyms ("employees" vs "customers"), ambiguous queries, and multi-domain questions; defaults to Sales with 0.33 confidence on no match
- **Approach:** Few-shot prompt with domain descriptions + view schemas → structured JSON output (domain, confidence, reasoning)
- **Fallback:** Keep existing keyword routing as fallback if LLM call fails
- **Files:** `app/agents/router.py`, `app/config.py`
- **Effort:** Medium

#### 3.2 LLM-Powered Query Interpretation
- **What:** Replace regex extraction in domain agents with structured LLM output (views, filters, aggregations, group-by)
- **Why:** Regex patterns break on natural variation. "Show me our biggest customers in the western region last quarter" should work — and currently doesn't
- **Approach:** Each domain agent sends the question + its view schemas to GPT-4 with a structured output schema (JSON mode). Return `QueryRequest` fields directly.
- **Files:** `app/agents/domain/sales.py`, `app/agents/domain/finance.py`, `app/agents/domain/operations.py`, `app/agents/domain/base_domain.py`
- **Effort:** Medium-Large

#### 3.3 Confidence-Based Clarification
- **What:** When routing or interpretation confidence is below a threshold, ask the user to clarify instead of guessing
- **Why:** Wrong answers erode trust faster than asking for help; currently defaults to Sales with low confidence
- **Files:** `app/agents/orchestrator.py`, `app/api/routes/query.py`, `gradio_app.py`
- **Effort:** Medium

**Success Criteria:**
- "How many employees do we have in the western warehouses?" correctly routes to Operations
- "Show me our biggest customers by revenue in Q4" returns correct aggregated results
- Ambiguous queries trigger a clarification prompt instead of a wrong answer

---

### Phase 4: Conversational Intelligence (Weeks 6–8)

**Theme:** *"Remember what I just asked"*
**Goal:** Multi-turn conversations and query refinement

#### 4.1 Wire Conversation Context
- **What:** Activate `app/agents/conversation_context.py` (450 LOC, already written) for session-based state management
- **Why:** Users naturally refine queries ("now break that down by region", "what about last quarter?"); each query is currently stateless
- **Files:** `app/agents/conversation_context.py`, `app/agents/orchestrator.py`, `app/api/routes/query.py`
- **Effort:** Medium

#### 4.2 Query History & Saved Queries
- **What:** Persist queries + results to database; add history endpoint and UI panel
- **Why:** Users re-ask the same questions weekly; history saves time and builds trust
- **New files:** `app/api/routes/history.py`, DB migration for `query_history` table
- **UI:** History sidebar in Gradio with re-run buttons
- **Effort:** Medium

#### 4.3 Smart Suggestions
- **What:** After returning results, suggest 2-3 related follow-up queries based on the domain and current results
- **Why:** Guides exploration; reduces "blank page" anxiety for non-technical users
- **Approach:** LLM generates follow-up questions given the current query + schema context
- **Files:** `app/agents/orchestrator.py`, `gradio_app.py`
- **Effort:** Medium

#### 4.4 Promote LangGraph as Primary Orchestrator
- **What:** Move `app/agents/langraph_orchestrator.py` (already written, 200 LOC) from fallback to primary orchestration path
- **Why:** Enables conditional branching, retry logic, and multi-step workflows that the linear orchestrator cannot support
- **Files:** `app/agents/langraph_orchestrator.py`, `app/agents/orchestrator.py`
- **Effort:** Medium

**Success Criteria:**
- User asks "total sales by region", then follows up with "just the West" and gets a filtered refinement without re-stating full context
- Query history persists across sessions and is searchable
- Follow-up suggestions appear after each query result

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

### Phase 6: Advanced Query Capabilities (Weeks 13–16)

**Theme:** *"Answer harder questions"*
**Goal:** Handle the complex queries that currently fail silently

#### 6.1 Complex SQL Support
- **What:** Add HAVING, subqueries, window functions, and CTEs to QueryBuilder
- **Why:** "Top 5 customers by revenue" requires window functions; "customers with above-average spend" requires subqueries
- **Files:** `app/query/builder.py`
- **Effort:** Large

#### 6.2 Multi-Hop Join Resolution
- **What:** Implement graph pathfinding for 3+ table joins (TODO exists in `app/agents/domain/base_domain.py:216`)
- **Why:** Cross-domain queries like "shipment volume for our top-selling products" need sales→product→inventory join paths
- **Files:** `app/agents/domain/base_domain.py`, `app/views/registry.py`
- **Effort:** Medium

#### 6.3 Time Intelligence
- **What:** Parse temporal expressions ("last quarter", "year over year", "trailing 30 days") into date filters
- **Why:** Most business questions are time-bounded; currently requires exact date values in the query
- **Approach:** LLM-based date parsing or `dateparser` library integration
- **Files:** Domain agents, `app/query/builder.py`
- **Effort:** Medium

#### 6.4 Data Visualization
- **What:** Auto-generate charts (bar, line, pie) based on query result shape
- **Why:** Tables are the least intuitive format for business users; a chart tells the story instantly
- **Approach:** Plotly integration in Gradio; chart type inferred from GROUP BY + aggregation shape (aggregation → bar; time series → line; proportion → pie)
- **Files:** `gradio_app.py`, new `app/visualization/` module
- **Effort:** Medium-Large

**Success Criteria:**
- "Show me a chart of monthly revenue trends for our top 5 products in Q4" returns a line chart with correct data
- "Shipment volume for our best-selling products" resolves a 3-table join across domains
- "Sales last quarter vs this quarter" correctly interprets relative time expressions

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
| `app/agents/conversation_context.py` | Session state (written, not wired) | 4 |
| `app/agents/langraph_orchestrator.py` | Graph orchestrator (written, fallback only) | 4 |
| `app/api/routes/query.py` | API endpoints | 2, 4, 5 |
| `app/api/middleware.py` | Security & rate limiting stub | 2, 5 |
| `app/cache/manager.py` | Redis caching (written, not wired) | 2 |
| `app/query/builder.py` | SQL generation | 6 |
| `app/query/pagination.py` | Pagination (written, not wired) | 2 |
| `app/query/validator.py` | Query safety checks | 6 |
| `app/observability/tracing.py` | OpenTelemetry (written, not wired) | 2 |
| `app/database/index_optimizer.py` | Index advisor (written, not wired) | 7 |
| `app/config.py` | All settings (many defined, not all used) | 2, 3, 5 |
| `gradio_app.py` | Web UI | 3, 4, 6 |

---

## VERIFICATION PLAN

After each phase, verify with these steps:

1. **Run full test suite:** `make test` — all 158+ tests must continue passing
2. **Manual smoke test via Gradio:** Run sample queries from each domain at `http://localhost:7860`
3. **API test:** Hit each endpoint via curl/httpie and verify response shape at `http://localhost:8000/docs`

**Phase-specific checks:**

| Phase | What to Verify |
|-------|---------------|
| **Phase 2** | Cache hits in Redis (`redis-cli KEYS *`), pagination params in API responses, 429 on rate limit, Jaeger traces at `http://localhost:16686` |
| **Phase 3** | Synonym queries route correctly, ambiguous queries trigger clarification, regex fallback works when LLM unavailable |
| **Phase 4** | Multi-turn refinement works ("total sales by region" → "just the West"), query history persists across page reloads |
| **Phase 5** | Unauthenticated requests return 401, cross-domain access denied, audit log table populates |
| **Phase 6** | "Top N" queries return correct results, time expressions resolve to correct dates, charts render in Gradio |
| **Phase 7** | Streaming tokens appear progressively, new domain onboards in < 30 min, P95 < 2s under load |
