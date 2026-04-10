# MERIDIAN Roadmap

## Current State (Phase 6 Complete — April 2026)

| Layer | Maturity | Notes |
|-------|----------|-------|
| NL Understanding | 95% | GPT-4 routing + interpretation; regex fallback; multi-turn context via `ConversationManager` |
| Query Building | 95% | HAVING (operator whitelist), window functions (Pydantic-validated), CTEs, ORDER BY, time intelligence, multi-hop BFS joins, fully parameterized SQL |
| Query Validation | 70% | View/column/cardinality checks, SQL injection prevention; no SQL syntax validation yet |
| REST API | 90% | JWT-authenticated endpoints; history API; pagination; rate limiting; 8 endpoints |
| UI (Gradio) | 75% | History sidebar, interactive suggestion buttons, multi-turn sessions; Plotly chart rendering not yet wired |
| Security | 85% | JWT auth + RBAC (admin/analyst/viewer), domain-level access control, audit logging, CORS; no SSO/OAuth yet |
| Observability | 40% | Structured JSON logging complete; OpenTelemetry + Langsmith scaffolded but not wired to live infrastructure |
| Caching & Performance | 65% | Redis cache active with context-scoped keys; async execution and connection pool tuning pending |
| Visualization | 70% | Chart-type hints generated for every result; Plotly rendering in Gradio not yet wired |

**Overall: ~93% — 468 tests passing (unit + integration)**

---

## Phase Status

| Phase | Theme | Status |
|-------|-------|--------|
| 1 | Foundation — view registry, 3 agents, QueryBuilder, QueryValidator, REST API (6 endpoints), Gradio UI, Docker | Complete |
| 2 | Activate scaffolded features — Redis cache, pagination, rate limiting, OpenTelemetry, Langsmith, retry policies | Complete |
| 3 | LLM-powered NL — GPT-4 routing + interpretation with two-stage regex fallback, confidence-based clarification (threshold 0.4), shared LLM client singleton | Complete |
| 4 | Conversational intelligence — session-aware context threading, SQLite query history (`/api/history`), LLM follow-up suggestions as interactive Gradio buttons, LangGraph as primary engine | Complete |
| 5 | Enterprise security — JWT auth + RBAC, audit logging, CORS lockdown, API key support | Complete |
| 6 | Advanced query — HAVING, window functions, CTEs, ORDER BY, full parameterization, multi-hop BFS join pathfinding, time intelligence, visualization hints | Complete |
| 7 | Scale & polish | In progress |

---

## Phase 7: Scale & Polish

**Theme:** *Ready for the demo day*

| Item | Description | Effort |
|------|-------------|--------|
| 7.1 Async query execution | Background job queue for long-running queries with status polling endpoint | Medium |
| 7.2 Streaming responses | Real-time token output via Langchain streaming; progress visible in Gradio instead of a spinner | Medium |
| 7.3 Self-service domain onboarding | Register new domains without code changes: upload schema, define keywords, auto-generate agent | Large |
| 7.4 Export options | JSON, Excel (.xlsx), PDF export alongside existing CSV | Small |
| 7.5 Query explain mode | Show users which domain was selected, what views/filters were extracted, and the generated SQL | Medium |
| 7.6 Performance optimization | Activate `app/database/index_optimizer.py` (already written); connection pool tuning from load test results | Small–Medium |
| 7.7 Load testing | Establish P50/P95/P99 baselines; target P95 < 2s under 10 concurrent requests | Medium |
| 7.8 Plotly visualization | Wire `visualization` hint from orchestrator result into Gradio chart rendering | Small |

**Phase 7 success criteria:**
- Streaming tokens visible in Gradio as they arrive
- New domain onboardable in < 30 minutes without code changes
- P95 latency < 2 seconds under 10 concurrent requests
- Export buttons for JSON/Excel/PDF in Gradio UI

---

## Key Files Reference

| File | Role |
|------|------|
| `app/agents/orchestrator.py` | Central query coordinator; wires cache, conversation, LangGraph, history, suggestions |
| `app/agents/router.py` | Domain routing — LLM-first (GPT-4 JSON), keyword fallback |
| `app/agents/domain/base_domain.py` | Shared LLM interpret → execute → regex fallback pipeline |
| `app/agents/langraph_orchestrator.py` | LangGraph graph — primary execution engine |
| `app/agents/conversation_context.py` | Session state — multi-turn context threading |
| `app/history/manager.py` | SQLite-backed query history persistence |
| `app/api/routes/query.py` | Execute, validate, domains, explore endpoints |
| `app/api/routes/history.py` | History REST API (GET / GET id / DELETE id) |
| `app/cache/manager.py` | Redis caching — context-scoped keys, TTL, hit/miss stats |
| `app/query/builder.py` | SQL generation — HAVING, window fns, CTEs, ORDER BY, parameterized |
| `app/query/time_intelligence.py` | Temporal expression → ISO date range resolver |
| `app/query/validator.py` | View/column/cardinality/injection checks |
| `app/visualization/chart_selector.py` | Chart-type hint inference from result shape |
| `app/database/index_optimizer.py` | Index advisor — written, wiring planned for Phase 7 |
| `app/observability/tracing.py` | OpenTelemetry — scaffolded, wiring planned for Phase 7 |
| `gradio_app.py` | Gradio UI — history sidebar, suggestion buttons, multi-turn sessions |

---

## Verification Checklist (per phase)

```bash
# After any phase: all 441+ tests must continue passing
make test

# Manual smoke test
make ui
# → run sample queries from each domain at http://localhost:7860

# API check
make dev
# → verify endpoint shapes at http://localhost:8000/docs
```

| Phase | What to Verify |
|-------|---------------|
| 7 — streaming | Streaming tokens appear progressively in Gradio |
| 7 — onboarding | New domain registers and routes queries without code changes |
| 7 — load | P95 < 2s with `locust` or `k6` at 10 concurrent users |
| 7 — export | JSON/Excel/PDF buttons visible and functional in Gradio |
