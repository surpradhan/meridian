# MERIDIAN API Documentation

**Version:** 1.0  
**Base URL:** `http://localhost:8000`  
**Interactive docs:** `http://localhost:8000/docs` (Swagger UI) / `http://localhost:8000/redoc`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Query Endpoints](#query-endpoints)
3. [Async Job Endpoints](#async-job-endpoints)
4. [Streaming Endpoint](#streaming-endpoint)
5. [Export Endpoint](#export-endpoint)
6. [History Endpoints](#history-endpoints)
7. [Admin Endpoints](#admin-endpoints)
8. [Auth Endpoints](#auth-endpoints)
9. [Error Codes](#error-codes)
10. [Pagination Guide](#pagination-guide)
11. [Rate Limiting](#rate-limiting)

---

## Authentication

All endpoints (except `/health` and `/auth/login`, `/auth/register`) require a Bearer JWT token.

### Obtain a Token

```http
POST /auth/login
Content-Type: application/json

{"username": "alice", "password": "changeme"}
```

**Response:**
```json
{"access_token": "<jwt>", "token_type": "bearer"}
```

Use the token in all subsequent requests:

```http
Authorization: Bearer <jwt>
```

Tokens expire after 30 minutes by default. Request a new one using the same endpoint.

---

## Query Endpoints

### Execute a Query

```http
POST /api/query/execute
Authorization: Bearer <jwt>
Content-Type: application/json
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | Natural language question |
| `auto_route` | bool | No (default: true) | Auto-detect domain |
| `domain` | string | No | Force domain: `sales`, `finance`, `operations`, or any registered dynamic domain |
| `trace` | bool | No (default: false) | Include execution trace |
| `explain` | bool | No (default: false) | Include explain block (routing decision, SQL, filters) |
| `page` | int | No (default: 1) | Result page number |
| `page_size` | int | No (default: 100, max: 10000) | Rows per page |
| `conversation_id` | string | No | Session ID for multi-turn conversations |

**Example request:**
```json
{
  "question": "What are total sales by region for last quarter?",
  "explain": true
}
```

**Example response:**
```json
{
  "result": [
    {"region": "WEST", "total_sales": 42500.00},
    {"region": "EAST", "total_sales": 38200.00}
  ],
  "row_count": 2,
  "sql": "SELECT region, SUM(amount) FROM sales_fact WHERE ...",
  "views": ["sales_fact"],
  "domain": "sales",
  "routing_confidence": 0.95,
  "confidence": 0.88,
  "state": "complete",
  "conversation_id": "conv_abc123",
  "suggestions": ["Show top 5 customers by revenue", "..."],
  "pagination": {"page": 1, "page_size": 100, "total_rows": 2, "total_pages": 1},
  "explain": {
    "query": "What are total sales by region for last quarter?",
    "routing_decision": {"domain": "sales", "confidence": 0.95},
    "views_selected": ["sales_fact"],
    "filters_extracted": {},
    "aggregations": {"amount": "SUM"},
    "group_by": ["region"],
    "sql_generated": "SELECT region, SUM(amount) ...",
    "join_paths": [],
    "time_resolution": {"expression": "last_quarter", "start": "2025-10-01", "end": "2025-12-31"},
    "interpretation_method": "llm",
    "confidence": 0.88
  }
}
```

### Validate a Query (dry run)

```http
POST /api/query/validate
```

Same request body. Returns `{"is_valid": true, "errors": [], "domain": "sales", "confidence": 0.9}` without executing the query.

### List Available Domains

```http
GET /api/query/domains
```

### Explore a Domain

```http
GET /api/query/explore?domain=sales
```

Returns available views, columns, and keywords for the domain.

### Health Check

```http
GET /api/query/health
```

No auth required.

---

## Async Job Endpoints

For queries that may take longer than an HTTP timeout.

### Submit Async Query

```http
POST /api/query/execute-async
Authorization: Bearer <jwt>
Content-Type: application/json

{"question": "Show all ledger transactions for last year"}
```

**Response (immediate):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Job submitted. Poll GET /api/jobs/{job_id} for results."
}
```

### Poll Job Status

```http
GET /api/jobs/{job_id}
Authorization: Bearer <jwt>
```

**Response (pending/running):**
```json
{"job_id": "...", "status": "running", "created_at": "...", "result": null, "error": null}
```

**Response (complete):**
```json
{
  "job_id": "...",
  "status": "complete",
  "created_at": "2026-01-01T10:00:00",
  "completed_at": "2026-01-01T10:00:05",
  "result": { /* same as /execute response */ },
  "error": null
}
```

### Cancel a Job

```http
DELETE /api/jobs/{job_id}
```

### List All Jobs

```http
GET /api/jobs
```

---

## Streaming Endpoint

Real-time token streaming using Server-Sent Events (SSE).

```http
POST /api/query/stream
Authorization: Bearer <jwt>
Content-Type: application/json

{"question": "Summarize our Q4 sales performance"}
```

**Response:** `Content-Type: text/event-stream`

Events emitted:
```
data: {"type": "token", "content": "Based"}
data: {"type": "token", "content": " on"}
...
data: {"type": "result", "data": { /* full query result */ }}
data: {"type": "done"}
```

**JavaScript client example:**
```javascript
const resp = await fetch('/api/query/stream', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: 'Show top customers' })
});
const reader = resp.body.getReader();
// ... read tokens as they arrive
```

---

## Export Endpoint

Run a query and download results as a file.

```http
POST /api/query/export
Authorization: Bearer <jwt>
Content-Type: application/json
```

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | Natural language query |
| `format` | string | `"json"`, `"csv"`, or `"excel"` |
| `filename` | string | Base filename (without extension, default: `meridian_export`) |
| `domain` | string | Optional domain override |

**Example:**
```json
{"question": "Total sales by region", "format": "excel", "filename": "q4_sales"}
```

Returns a file download with `Content-Disposition: attachment; filename="q4_sales.xlsx"`.

---

## History Endpoints

```http
GET  /api/history               # List all saved queries (last 100)
GET  /api/history/{id}          # Get a specific history entry
DELETE /api/history/{id}        # Delete a history entry
```

History entries include the original question, result, domain, and timestamp.

---

## Admin Endpoints

All admin endpoints require a JWT token with `role: admin`.

### Domain Onboarding

```http
POST   /api/admin/domains       # Register a new domain
GET    /api/admin/domains       # List dynamic domains
DELETE /api/admin/domains/{name}  # Remove a dynamic domain
```

**Register domain example:**
```json
{
  "name": "hr",
  "description": "Human Resources — headcount, salaries, departments",
  "keywords": ["employee", "headcount", "salary", "department", "hire"],
  "view_names": ["employee_fact", "department_dim"]
}
```

Requirements:
- `name` must be a lowercase slug (`^[a-z][a-z0-9_]*$`)
- `name` cannot conflict with built-in domains (`sales`, `finance`, `operations`)
- Views in `view_names` must be registered in the ViewRegistry

### Performance Report

```http
GET /api/admin/performance
```

Returns:
```json
{
  "recommendations": [
    {
      "table": "sales_fact",
      "columns": ["region"],
      "index_name": "idx_sales_fact_region",
      "sql": "CREATE INDEX idx_sales_fact_region ON sales_fact (region);",
      "benefit": "HIGH",
      "reason": "Frequently accessed (127 times, avg 145.3ms)",
      "priority": 10
    }
  ],
  "slow_queries": {"slow_query_count": 3, "slowest_tables": [...]},
  "pattern_analysis": {"total_patterns": 12, "total_queries": 847, "tables": [...]}
}
```

---

## Auth Endpoints

```http
POST /auth/register    # Create a new user account
POST /auth/login       # Obtain a JWT token
GET  /auth/me          # Get current user info
```

### Register

```json
{"username": "alice", "password": "secure_password", "email": "alice@company.com"}
```

Default role is `viewer`. Admins can be created by an existing admin.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request — invalid query or parameters |
| 401 | Unauthenticated — missing or invalid token |
| 403 | Forbidden — role does not have permission |
| 404 | Not found — resource (job, history entry, domain) does not exist |
| 409 | Conflict — e.g. domain name already taken |
| 422 | Validation error — request body schema violation |
| 429 | Rate limit exceeded — retry after the indicated interval |
| 500 | Internal server error — query execution failed |

**Error response shape:**
```json
{"detail": "Human-readable error message"}
```

---

## Pagination Guide

Add `page` and `page_size` to any `/execute` request:

```json
{"question": "...", "page": 2, "page_size": 25}
```

Responses include:
```json
"pagination": {
  "page": 2,
  "page_size": 25,
  "total_rows": 150,
  "total_pages": 6,
  "has_next": true,
  "has_prev": true
}
```

---

## Rate Limiting

- Default: **60 requests per minute** per token
- Max concurrent: **10 simultaneous requests**
- Exceeding either limit returns HTTP 429 with a `Retry-After` header

Configure via environment variables:
```
RATE_LIMIT_PER_MINUTE=60
MAX_CONCURRENT_REQUESTS=10
```

---

## Multi-Turn Conversations

Pass `conversation_id` across requests to maintain context:

```json
// First request
{"question": "Total sales by region"}
// Response includes: "conversation_id": "conv_xyz"

// Follow-up request
{"question": "Just the West", "conversation_id": "conv_xyz"}
// System resolves "Just the West" using prior context
```

Conversations expire after 30 minutes of inactivity.
