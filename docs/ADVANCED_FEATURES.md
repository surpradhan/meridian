# MERIDIAN Advanced Features (Phase 5 Extensions)

This document covers the advanced features implemented beyond the core Phase 5 infrastructure. These features provide production-grade capabilities for distributed systems, performance optimization, and multi-turn conversations.

## Table of Contents

1. [Distributed Tracing](#distributed-tracing)
2. [Query Caching](#query-caching)
3. [Result Pagination](#result-pagination)
4. [Langraph Integration](#langraph-integration)
5. [Conversation Context](#conversation-context)
6. [Index Optimization](#index-optimization)

---

## Distributed Tracing

### Overview

Distributed tracing with **OpenTelemetry** and **Jaeger** provides end-to-end visibility into query execution across multiple components. Track requests from API entry through domain agents, validators, and database execution.

### Features

- **Request Tracing**: Track individual requests across all components
- **Span Management**: Create spans for each major operation
- **Automatic Instrumentation**: FastAPI and SQLAlchemy auto-instrumented
- **Jaeger Integration**: Export traces to Jaeger for visualization
- **Performance Metrics**: Identify bottlenecks in query pipeline

### Usage

```python
from app.observability import setup_tracing, get_tracer

# Setup tracing globally
setup_tracing(
    service_name="meridian",
    jaeger_host="localhost",
    jaeger_port=6831,
    enabled=True,
)

# Use tracer in code
tracer = get_tracer()

with tracer.start_as_current_span("query_processing") as span:
    span.set_attribute("query", "SELECT * FROM sales")
    # Execute query
    span.set_attribute("rows_returned", 42)
```

### Span Context Manager

```python
from app.observability.tracing import TracingManager

manager = TracingManager.get_instance()

with manager.span("agent_processing", {"domain": "finance"}) as span:
    # Your agent code here
    manager.add_event("agent_completed")
```

### Configuration

```yaml
# config/production.yaml
observability:
  tracing:
    enabled: true
    jaeger_host: jaeger.example.com
    jaeger_port: 6831
    service_name: meridian
```

### Docker Setup for Jaeger

```bash
# Run Jaeger all-in-one
docker run -d \
  -p 5775:5775/udp \
  -p 16686:16686 \
  jaegertracing/all-in-one

# Access UI at http://localhost:16686
```

---

## Query Caching

### Overview

Redis-based caching layer for query results reduces database load, improves response times, and supports horizontal scaling. Cache keys are deterministic hashes of query + parameters.

### Features

- **Result Caching**: Cache query results with configurable TTL
- **Automatic Key Generation**: Deterministic keys based on query content
- **Selective Invalidation**: Invalidate specific queries or patterns
- **Cache Statistics**: Track hit/miss rates and performance
- **Graceful Degradation**: Works with or without Redis

### Usage

```python
from app.cache import setup_cache, get_cache

# Initialize cache
setup_cache(
    host="localhost",
    port=6379,
    ttl_seconds=3600,
    enabled=True,
)

cache = get_cache()

# Get cached result (or None)
result = cache.get("SELECT * FROM sales WHERE region = ?", {"region": "WEST"})

if result is None:
    # Execute query
    result = execute_query(...)
    # Cache the result
    cache.set("SELECT * FROM sales WHERE region = ?", result, {"region": "WEST"})

# Invalidate cache
cache.invalidate_query("SELECT * FROM sales WHERE region = ?", {"region": "WEST"})
```

### Integration with Query Executor

```python
from app.cache import get_cache

def execute_query_with_cache(query, params):
    cache = get_cache()

    # Try cache first
    cached = cache.get(query, params)
    if cached:
        return cached

    # Execute and cache
    result = db.execute(query)
    cache.set(query, result, params, ttl_seconds=1800)

    return result
```

### Cache Statistics

```python
cache = get_cache()
stats = cache.get_stats()

print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

### Cache Invalidation Strategies

```python
# Clear all cache
cache.clear()

# Invalidate pattern (e.g., all sales queries)
cache.invalidate("query:*sales*")

# Invalidate specific query
cache.invalidate_query(query, params)

# Reset statistics
cache.reset_stats()
```

---

## Result Pagination

### Overview

Efficient pagination for large result sets with multiple strategies: page-based, offset-based, and streaming. Prevents memory overload and improves API response times.

### Features

- **Page-Based Pagination**: Traditional page/page_size navigation
- **Offset-Based Pagination**: LIMIT/OFFSET style queries
- **Streaming Results**: Generator-based chunking for massive datasets
- **Metadata**: Provides pagination info (has_next, total_pages, etc.)
- **Configurable Limits**: Min/max page sizes enforced

### Usage: Page-Based

```python
from app.query import Paginator

paginator = Paginator()
rows = execute_query(...)  # Returns all 10,000 rows

# Get page 1 with 100 rows per page
page = paginator.paginate(rows, page=1, page_size=100)

print(f"Page {page.page} of {page.total_pages}")
print(f"Rows: {page.offset} to {page.offset + page.page_size}")
print(f"Has next: {page.has_next}")

# Convert to JSON response
response = page.to_dict()
```

### Usage: Offset-Based

```python
paginator = Paginator()

# Get rows 100-200
page_data, info = paginator.paginate_with_limit(
    rows,
    limit=100,
    offset=100
)

print(f"Returned {info['returned_rows']} rows")
print(f"Has more: {info['has_more']}")
```

### Usage: Streaming

```python
from app.query import StreamingResult

stream = StreamingResult(rows, chunk_size=1000)

# Iterate through chunks
for chunk in stream:
    send_to_client(chunk)

# Get metadata
metadata = stream.to_stream_response()
```

### API Integration

```python
@app.get("/api/query/results/{query_id}")
async def get_query_results(
    query_id: str,
    page: int = 1,
    page_size: int = 100,
):
    # Get cached query result
    rows = cache.get(query_id)

    # Paginate
    paginator = Paginator()
    paginated = paginator.paginate(rows, page, page_size)

    return paginated.to_dict()
```

---

## Langraph Integration

### Overview

**Langraph** provides a robust workflow orchestration engine replacing the basic state machine. Better support for:
- Conditional routing between steps
- Error handling with recovery paths
- Visualization of workflow graph
- Extensible workflow patterns

### Features

- **StateGraph Workflow**: Directed acyclic graph for query processing
- **Conditional Edges**: Route based on step outputs
- **Error Recovery**: Dedicated error handling paths
- **Graph Visualization**: ASCII representation of workflow
- **Scalable Design**: Supports complex multi-step workflows

### Architecture

```
┌──────────┐
│  ROUTE   │  (Router: classify domain)
└─────┬────┘
      │
      ▼
┌──────────────────┐
│ PROCESS_AGENT    │  (Domain agent: interpret query)
└─────┬────────────┘
      │
      ├─ Error ──────┐
      │              ▼
      │           ┌──────┐
      │           │ ERROR│
      │           └──────┘
      │
      ▼
┌──────────────┐
│   VALIDATE   │  (Validator: check query)
└─────┬────────┘
      │
      ▼
┌──────────────┐
│   EXECUTE    │  (Execute query)
└─────┬────────┘
      │
      ├─ Error ──────┐
      │              ▼
      │           ┌──────┐
      │           │ ERROR│
      │           └──────┘
      │
      ▼
┌──────────────┐
│   COMPLETE   │  (Mark success)
└──────────────┘
```

### Usage

```python
from app.agents import LangraphOrchestrator

# Create orchestrator
orchestrator = LangraphOrchestrator(registry, db)

# Process query (uses Langraph workflow)
result = orchestrator.process_query("How many sales?")

# View workflow graph
graph_ascii = orchestrator.get_workflow_graph()
print(graph_ascii)
```

### Extending the Workflow

```python
# Create custom StateGraph with additional nodes
from langraph.graph import StateGraph

workflow = StateGraph(dict)

# Add your custom nodes
workflow.add_node("custom_step", your_function)

# Add edges
workflow.add_edge("previous_step", "custom_step")
workflow.add_edge("custom_step", "next_step")
```

---

## Conversation Context

### Overview

Manages multi-turn conversations with persistent state across queries. Track message history, previous results, and context variables for intelligent follow-up queries.

### Features

- **Message History**: Persist full conversation with timestamps
- **Context Variables**: Store domain, recent views, result counts
- **Session Variables**: Custom key-value storage for application state
- **Automatic Cleanup**: Expire old conversations
- **Natural Language Summary**: Context for LLM prompts

### Usage

```python
from app.agents import ConversationContext, get_conversation_manager

manager = get_conversation_manager()

# Create new conversation
conversation = manager.create_conversation()

# Add messages
conversation.add_user_message("What are total sales?")
conversation.update_context(domain="sales", result_count=1500)
conversation.add_assistant_message("Total sales: 1500", {"row_count": 1500})

# Follow-up query
conversation.add_user_message("By region?")

# Get context for follow-up
context_summary = conversation.get_context_summary()
print(context_summary)
# Output: "Last domain queried: sales | Last query returned 1500 rows"
```

### Multi-Turn Flow

```python
# Turn 1
conv.add_user_message("Show me sales by region")
result1 = process_query(...)
conv.update_context(domain="sales", views=["sales_fact", "region"])
conv.add_assistant_message(f"Found {result1['row_count']} sales", result1)

# Turn 2 (follow-up)
conv.add_user_message("Top 5 regions?")
# Context shows we're in sales domain with region data
context = conv.get_context_summary()
# Helps agent understand we want top regions from sales data

# Turn 3 (reference previous)
conv.add_user_message("What about the second region?")
# Can reference previous result (second region) from context
previous_result = conv.get_message_history(limit=1)[0]
```

### Session Variables

```python
conversation = get_conversation_manager().create_conversation()

# Store filter preferences
conversation.set_session_variable("default_region", "WEST")
conversation.set_session_variable("fiscal_year", 2024)

# Reference in follow-up queries
region = conversation.get_session_variable("default_region")
```

### Conversation Management

```python
manager = get_conversation_manager()

# List active conversations
stats = manager.get_stats()
print(f"Active: {stats['active_conversations']}")

# Cleanup expired conversations
cleaned = manager.cleanup_expired()

# Retrieve conversation by ID
conv = manager.get_conversation(conversation_id)
```

---

## Index Optimization

### Overview

Analyzes query patterns and recommends database indexes. Tracks slow queries, identifies access patterns, and generates SQL for optimal indexing.

### Features

- **Query Pattern Analysis**: Track column access patterns
- **Slow Query Detection**: Identify queries exceeding threshold
- **Index Recommendations**: Generate CREATE INDEX statements
- **Priority Scoring**: Recommend highest-impact indexes first
- **Query Plan Tips**: Domain-specific optimization advice

### Usage

```python
from app.database import IndexOptimizer

optimizer = IndexOptimizer()

# Record queries (typically done automatically)
optimizer.analyzer.record_query("sales_fact", ["customer_id"], 45.0)
optimizer.analyzer.record_query("sales_fact", ["customer_id"], 52.0)
optimizer.analyzer.record_query("sales_fact", ["customer_id", "date"], 120.0)

# Get recommendations
analysis = optimizer.analyze_workload()

print("Index Recommendations:")
for rec in analysis["recommendations"]:
    print(f"  {rec['sql']}")
    print(f"    Benefit: {rec['benefit']}")
    print(f"    Reason: {rec['reason']}")
```

### Slow Query Analysis

```python
optimizer = IndexOptimizer()

# ... record some slow queries ...

summary = optimizer.analyzer.get_slow_query_summary()

print(f"Slow queries: {summary['slow_query_count']}")
for table in summary["slowest_tables"]:
    print(f"  {table['table']}: {table['count']} slow queries")
```

### Pattern Summary

```python
summary = optimizer.analyzer.get_pattern_summary()

print(f"Total patterns: {summary['total_patterns']}")
print(f"Total accesses: {summary['total_queries']}")

for table in summary["tables"]:
    print(f"  {table['table']}: {table['total_accesses']} accesses")
```

### Integration with Query Builder

```python
from app.database import IndexOptimizer

optimizer = IndexOptimizer()

def execute_query_with_tracking(table, columns, sql):
    start = time.time()
    result = db.execute(sql)
    elapsed_ms = (time.time() - start) * 1000

    # Record for analysis
    optimizer.analyzer.record_query(table, columns, elapsed_ms)

    return result
```

### Tips for Specific Table

```python
tips = optimizer.get_query_plan_tips("sales_fact")
for tip in tips:
    print(f"  {tip}")

# Output:
#   ⚠️ Queries on this table are slow (avg > 200ms). Consider adding indexes...
#   💡 Consider composite index on (customer_id, date) for multi-column queries.
```

---

## Quick Start: All Features Together

```python
from app.main import app
from app.config import get_settings
from app.observability import setup_logging, setup_tracing, setup_metrics
from app.cache import setup_cache
from app.agents import (
    LangraphOrchestrator,
    get_conversation_manager,
)
from app.database import IndexOptimizer

# Setup observability
setup_logging(config.logging)
setup_tracing(service_name="meridian")
setup_metrics()

# Setup caching
setup_cache(enabled=True)

# Setup Langraph orchestrator
orchestrator = LangraphOrchestrator(registry, db)

# Setup conversation management
conv_manager = get_conversation_manager()

# Setup index optimization
optimizer = IndexOptimizer()

# Process multi-turn conversation
conversation = conv_manager.create_conversation()

# Turn 1
conversation.add_user_message("What are sales by region?")
result1 = orchestrator.process_query("Show sales by region")
conversation.update_context(domain="sales", result_count=10)

# Turn 2
conversation.add_user_message("Top 3 regions?")
context_summary = conversation.get_context_summary()
result2 = orchestrator.process_query(f"Top 3 regions (context: {context_summary})")

# Analyze performance
analysis = optimizer.analyze_workload()
print("Index recommendations:", analysis["recommendations"])
```

---

## Configuration

### Environment Variables

```bash
# Tracing
TRACING_ENABLED=true
JAEGER_HOST=localhost
JAEGER_PORT=6831

# Caching
CACHE_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_TTL_SECONDS=3600

# Pagination
PAGINATION_DEFAULT_PAGE_SIZE=100
PAGINATION_MAX_PAGE_SIZE=10000

# Conversation
CONVERSATION_MAX_HISTORY=50
CONVERSATION_MAX_AGE_MINUTES=60
```

### YAML Configuration

```yaml
# config/production.yaml
observability:
  tracing:
    enabled: true
    jaeger_host: jaeger.example.com

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

## Performance Impact

### Tracing Overhead
- **Impact**: ~5-10% per request
- **Benefit**: Complete request visibility
- **Recommendation**: Enable in staging/production

### Caching Benefits
- **Impact**: 5-50x faster for cached queries
- **Memory**: Redis memory usage ~1MB per 10k cached results
- **TTL**: Balance freshness vs. performance

### Pagination Benefits
- **Memory**: O(page_size) instead of O(total_rows)
- **Response Time**: Constant regardless of total row count
- **Network**: Smaller payloads

### Index Optimization Benefits
- **Query Speed**: 10-100x faster with proper indexes
- **Storage**: Minimal overhead per index
- **Maintenance**: Automatic recommendations

---

## Testing

Run comprehensive tests:

```bash
# All advanced feature tests
pytest tests/integration/test_advanced_features.py -v

# Specific test class
pytest tests/integration/test_advanced_features.py::TestDistributedTracing -v

# With coverage
pytest tests/integration/test_advanced_features.py --cov=app
```

---

## Troubleshooting

### Tracing Not Working
1. Check Jaeger is running: `docker ps | grep jaeger`
2. Verify network connectivity to Jaeger host
3. Check logs for connection errors

### Cache Misses
1. Verify Redis is running: `redis-cli ping`
2. Check key format in `_make_key()`
3. Ensure TTL isn't too short

### Slow Pagination
1. Ensure page_size is reasonable (< 10000)
2. Consider streaming for very large result sets
3. Use offset-based for deep pagination

### Memory Issues
1. Check conversation history limits
2. Reduce chunk_size in streaming
3. Monitor Redis memory usage
4. Run `cleanup_expired()` periodically

---

## Next Steps

1. **Production Deployment**
   - Deploy Jaeger for tracing
   - Setup Redis cluster for caching
   - Configure proper TTLs and memory limits

2. **Advanced Workflows**
   - Create custom Langraph nodes
   - Implement parallel query execution
   - Add workflow validation steps

3. **Monitoring**
   - Setup dashboards for cache hit rates
   - Monitor slow query trends
   - Track conversation engagement patterns

---

## References

- [OpenTelemetry](https://opentelemetry.io/)
- [Jaeger Tracing](https://www.jaegertracing.io/)
- [Redis Documentation](https://redis.io/docs/)
- [Langraph](https://langchain-ai.github.io/langraph/)
