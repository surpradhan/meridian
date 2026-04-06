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
- `POST /api/query/execute` - Process natural language query (accepts `conversation_id`, returns `suggestions`)
- `POST /api/query/validate` - Validate without executing
- `GET /api/query/domains` - List available domains
- `GET /api/query/explore` - Explore domain capabilities

**History endpoints** (`history.py`):
- `GET /api/history?limit=N` - List recent queries, newest first
- `GET /api/history/{id}` - Retrieve a single history entry
- `DELETE /api/history/{id}` - Delete a history entry

**Key Features**:
- Request/response validation with Pydantic
- Automatic domain routing with optional `forced_domain`
- `conversation_id` threaded through request/response for multi-turn sessions
- Optional execution tracing
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

**Responsibility**: Provide a single shared `ChatOpenAI` instance for the process

**Design**:
- Module-level singleton (`_client`, `_init_attempted`) — initialized once on first call
- Returns `None` gracefully when `OPENAI_API_KEY` is not set or `langchain-openai` is not installed
- `reset_llm_client()` resets state for test injection

**Usage**: Both `RouterAgent` and `BaseDomainAgent` call `get_llm()` — they never instantiate `ChatOpenAI` directly, ensuring at most one connection per process.

### 6. Query Validator (`app/query/validator.py`)

**Responsibility**: Validate queries before execution

**Validations**:
1. **View Validation**: All views exist in registry
2. **Combination Validation**: Views can be joined properly
3. **Cardinality Validation**: Many-to-many without aggregation = warning
4. **Limit Validation**: Enforces max_result_rows constraint
5. **Column Validation**: Filter/aggregation columns exist

**Features**:
- `validate()` - Full validation
- `estimate_result_size()` - Row count estimation
- `get_validation_warnings()` - Non-blocking suggestions

### 7. Query Builder (`app/query/builder.py`)

**Responsibility**: Generate SQL from QueryRequest

**Features**:
- `build_query()` - Full SQL generation
- `_build_from_clause()` - Smart JOIN generation
- Column suggestion
- Aggregation suggestion

**Smart JOINs**:
- Automatically detects join paths using registry
- Handles one-to-one, one-to-many, many-to-one relationships
- Prevents invalid many-to-many joins

### 8. View Registry (`app/views/registry.py`)

**Responsibility**: Centralized metadata about views

**Contains**:
- View definitions with columns
- Join relationships between views
- Column properties (PK, FK, nullable, type)
- Domain mappings

**Key Methods**:
- `get_view(name)` - Get view metadata
- `find_joins(view1, view2)` - Find join path
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
│   └── test_phase4.py           # Conversational Intelligence (50 tests)
├── integration/                 # Multi-component tests
│   ├── test_agents.py
│   ├── test_advanced_features.py
│   ├── test_history_api.py      # History REST API (12 tests)
│   ├── test_orchestrator.py
│   ├── test_phase3_phase4.py
│   ├── test_ui_queries.py
│   └── test_views.py
└── fixtures/                    # Test data
    ├── data.py
    └── mocks.py
```

**Total: 297 tests passing**

**Test Coverage**: 235+ tests, all passing

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

1. **Conversational Intelligence**: Multi-turn queries with session context (`app/agents/conversation_context.py` already written)
2. **Langraph as Primary Orchestrator**: Promote graph-based workflow from fallback to primary path
3. **Rate Limiting**: Per-user query limits (middleware stub exists)
4. **Audit Logging**: Track all queries for compliance
5. **Multi-tenancy**: Support multiple organizations with row-level security
6. **Custom Domains**: User-defined domain agents without code changes
7. **Complex SQL**: HAVING, window functions, CTEs, time intelligence

---

**Last Updated**: 2026-04-06
