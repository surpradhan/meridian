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

### 1. REST API Layer (`app/api/routes/query.py`)

**Responsibility**: HTTP interface for external clients

**Endpoints**:
- `POST /api/query/execute` - Process natural language query
- `POST /api/query/validate` - Validate without executing
- `GET /api/query/domains` - List available domains
- `GET /api/query/explore` - Explore domain capabilities

**Key Features**:
- Request/response validation with Pydantic
- Automatic domain routing
- Optional execution tracing
- Error handling and logging

### 2. Orchestrator (`app/agents/orchestrator.py`)

**Responsibility**: Coordinates multi-agent workflow

**Workflow**:
```
Query → Route → Validate → Execute → Return Results
```

**Key Methods**:
- `process_query(query)` - Main workflow
- `validate_query_for_domain(domain, query)`
- `process_query_with_trace(query)` - Detailed execution trace
- `get_domain_capabilities(domain)`

### 3. Router Agent (`app/agents/router.py`)

**Responsibility**: Classify queries to appropriate domain

**Algorithm**:
1. Extract keywords from query (lowercased)
2. Score each domain based on keyword matches
3. View mentions weighted 2x higher than keywords
4. Return domain with highest score + confidence

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

**Processing Pipeline** (each agent):
```
Natural Language Query
        ↓
Identify Views (keyword matching)
        ↓
Identify Filters (regex patterns)
        ↓
Identify Aggregations (SUM, COUNT, AVG, etc.)
        ↓
Build QueryRequest
        ↓
Execute via Builder
        ↓
Return Results with Confidence
```

### 5. Query Validator (`app/query/validator.py`)

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

### 6. Query Builder (`app/query/builder.py`)

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

### 7. View Registry (`app/views/registry.py`)

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

### 8. Database Connection (`app/database/connection.py`)

**Responsibility**: Safe database access

**Features**:
- Connection pooling
- Transaction management
- SQL injection prevention
- Mock database support for testing

### 9. Observability (`app/observability/`)

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
   RouterAgent.route() → "sales" domain, confidence 0.95

3. Domain agent processes
   SalesAgent._identify_views() → ["sales_fact"]
   SalesAgent._identify_filters() → {}
   SalesAgent._identify_aggregations() → {"sale_id": "COUNT"}

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
     "state": "complete"
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
├── unit/               # Fast, isolated tests
│   ├── test_views.py   # View registry tests
│   └── test_queries.py # Query builder tests
├── integration/        # Multi-component tests
│   ├── test_agents.py
│   ├── test_phase3_phase4.py
│   ├── test_orchestrator.py
│   └── test_views.py (DB integration)
└── fixtures/          # Test data
    ├── data.py
    └── mocks.py
```

**Test Coverage**: 125 tests, all passing

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

1. **Langchain Integration**: Use Langchain for more complex NLU
2. **Langraph Workflows**: Multi-turn conversations and state management
3. **Caching Layer**: Redis for result caching
4. **Rate Limiting**: Per-user query limits
5. **Audit Logging**: Track all queries for compliance
6. **Multi-tenancy**: Support multiple organizations
7. **Custom Domains**: User-defined domain agents
8. **ML-based Routing**: Learn query patterns over time

---

**Last Updated**: 2026-03-19
