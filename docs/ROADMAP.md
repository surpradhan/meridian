# MERIDIAN Roadmap

## Current State (Phase 9 Complete — April 2026)

| Layer | Maturity | Notes |
|-------|----------|-------|
| NL Understanding | 95% | GPT-4 routing + interpretation; regex fallback; multi-turn context via `ConversationManager` |
| Query Building | 95% | HAVING (operator whitelist), window functions (Pydantic-validated), CTEs, ORDER BY, time intelligence, multi-hop BFS joins, fully parameterized SQL |
| Query Validation | 90% | View/column/cardinality checks, SQL injection prevention, SQL syntax pre-validation via SQLite EXPLAIN |
| REST API | 95% | JWT + OAuth2/OIDC-authenticated endpoints; history API; pagination; rate limiting; admin domain onboarding |
| UI (Gradio) | 90% | History sidebar (clickable), interactive suggestion buttons, multi-turn sessions, Plotly interactive charts, JSON/Excel export buttons |
| Security | 95% | JWT auth + RBAC (admin/analyst/viewer), OAuth2/OIDC SSO (Google + generic OIDC), domain-level access control, audit logging, CORS |
| Observability | 100% | Structured JSON logging; OTel spans → Jaeger via OTLP HTTP; Prometheus `/metrics` scrape endpoint; Grafana dashboard (latency p50/p95/p99, error rate, cache hit, domain breakdown); alert rules |
| Caching & Performance | 75% | Redis cache active with context-scoped keys; async execution; index advisor live |
| Visualization | 95% | Chart-type hints + interactive Plotly charts (line/bar/pie) fully wired in Gradio UI |

**Overall: ~96% — 571+ tests passing (unit + integration)**

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
| 7 | Scale & polish | Complete |
| 8 | Security & observability — OAuth2/OIDC SSO, SQL syntax validation, Plotly charts, observability wiring | Complete |
| 9 | Observability completion — Prometheus dual-write, OTLP/Jaeger export, Grafana dashboards, alert rules | Complete |

---

## Phase 7: Scale & Polish ✅ COMPLETE

**Theme:** *Ready for the demo day*

| Item | Description | Status |
|------|-------------|--------|
| 7.1 Async query execution | Background job queue for long-running queries with status polling endpoint | ✅ |
| 7.2 Streaming responses | Real-time token output via Langchain streaming; SSE via `POST /api/query/stream` | ✅ |
| 7.3 Self-service domain onboarding | Register new domains without code changes via `POST /api/admin/domains` | ✅ |
| 7.4 Export options | JSON, Excel (.xlsx) export alongside existing CSV | ✅ |
| 7.5 Query explain mode | `explain=true` returns routing decision, views, filters, generated SQL | ✅ |
| 7.6 Performance optimization | Index advisor wired into query path; `GET /api/admin/performance` | ✅ |
| 7.7 Load testing | P50/P95/P99 baseline suite in `tests/performance/` | ✅ |
| 7.8 Plotly visualization | Interactive charts wired in Gradio UI *(completed in Phase 8)* | ✅ |

---

## Phase 8: Security & Observability ✅ COMPLETE

**Theme:** *Enterprise-grade authentication and visibility*

| Item | Description | Status |
|------|-------------|--------|
| 8.1 OAuth2 / OIDC SSO | Google OAuth2 + generic OIDC (Okta, Keycloak, etc.) | ✅ |
| 8.2 SQL syntax validation | Pre-validate generated SQL via SQLite EXPLAIN before execution | ✅ |
| 8.3 Plotly charts in UI | Auto-selected line/bar/pie charts rendered inline in Gradio | ✅ |
| 8.4 Observability wiring | OpenTelemetry spans + query metrics throughout orchestrator | ✅ |
| 8.5 Config hardening | OIDC all-or-nothing validation; production SECRET_KEY enforcement | ✅ |

**Phase 8 success criteria met:**
- OAuth login flow works with Google and any OIDC provider
- SQL parse errors caught and reported before hitting the database
- Plotly charts render for all chart types (line/bar/pie/table)
- Every query generates a complete trace with cache, route, agent, and suggestion spans

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
| `app/query/validator.py` | View/column/cardinality/injection checks + SQL syntax pre-validation |
| `app/visualization/chart_selector.py` | Chart-type hint inference from result shape |
| `app/auth/oauth.py` | OAuth2 / OIDC authorization code flow manager |
| `app/auth/routes.py` | Auth REST endpoints (login, register, OAuth authorize/callback) |
| `app/auth/store.py` | SQLite-backed user store with OAuth user provisioning |
| `app/auth/constants.py` | Shared auth constants (OAuth-only sentinel value) |
| `app/database/index_optimizer.py` | Index advisor — wired; `GET /api/admin/performance` |
| `app/observability/tracing.py` | OpenTelemetry — spans wired throughout orchestrator |
| `gradio_app.py` | Gradio UI — history (clickable), suggestions, Plotly charts, export buttons |

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
| 7 — export | JSON/Excel buttons visible and functional in Gradio |
| 8 — OAuth | OAuth login flow works end-to-end with Google or any OIDC provider |
| 8 — SQL validation | Parse errors caught before execution; valid queries unaffected |
| 8 — charts | Plotly charts render for all chart types without clipping |
