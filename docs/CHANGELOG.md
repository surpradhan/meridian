# MERIDIAN Changelog

## v0.9.0 — Phase 9: Observability Completion (2026-04-12)

- **Prometheus dual-write**: `MetricsCollector` now writes every counter/histogram/gauge to a dedicated `prometheus_client` registry simultaneously — the in-memory JSON snapshot (`GET /api/admin/metrics`) is unchanged; the Prometheus scrape endpoint is new
- **`/metrics` scrape endpoint**: Prometheus ASGI app mounted at `/metrics`; exempt from rate-limit and concurrent-request middleware so scrapers are never blocked
- **OTLP exporter**: Deprecated `jaeger-thrift` UDP exporter replaced with `OTLPSpanExporter` (HTTP, port 4318); `OTLP_ENDPOINT` env var controls the destination; `JAEGER_AGENT_HOST/PORT` kept as no-op legacy vars
- **Prometheus metrics exposed**:
  - `meridian_queries_started_total`, `meridian_queries_successful_total`, `meridian_queries_failed_total` (counters)
  - `meridian_queries_domain_total{domain=...}` (counter with label)
  - `meridian_query_duration_ms` histogram (buckets: 25 ms … 10 s)
  - `meridian_query_rows` histogram
  - `meridian_last_query_rows` gauge
- **Docker observability stack** (`docker-compose.yml`):
  - `jaeger` (all-in-one 1.55) — UI on `:16686`, OTLP HTTP on `:4318`
  - `prometheus` (v2.48.1) — scrapes `app:8000/metrics` every 15 s
  - `grafana` (10.2.3) — auto-provisioned datasource + dashboard; admin password `meridian`
- **Grafana dashboard** (`monitoring/grafana/provisioning/dashboards/meridian.json`): 8 panels covering queries/min, error rate, p95 latency, cache hit rate, latency percentile time-series, throughput time-series, domain bar chart, rows-returned percentiles
- **Prometheus alert rules** (`monitoring/alerts.yml`): `MeridianDown`, `HighQueryErrorRate` (>10 %), `CriticalQueryErrorRate` (>30 %), `HighQueryLatencyP95` (>2 s), `CriticalQueryLatencyP95` (>5 s), `NoQueryActivity`
- **Tests**: 571+ passing (30 new in `tests/unit/test_phase9_observability.py`)

## v0.8.0 — Phase 8: Security & Observability (2026-04-12)

- **OAuth2 / OIDC SSO**: Google OAuth2 and generic OIDC (Okta, Keycloak, Azure AD, etc.) via `GET /api/auth/oauth/authorize` and `GET /api/auth/oauth/callback`; new users auto-provisioned as `viewer`
- **SQL syntax pre-validation**: `QueryValidator.validate_sql_syntax()` uses in-memory SQLite `EXPLAIN` to catch parse errors before execution; singleton connection with thread-safe lock
- **Plotly charts**: Interactive line/bar/pie charts fully wired in Gradio UI; chart type auto-selected from result shape via `chart_selector.py`
- **Observability wired**: `TracingManager` spans throughout `Orchestrator.process_query` (cache check, routing, agent execute, suggestions, cache store); `QueryMetrics` records per-query counters and histograms
- **Config hardening**: `@model_validator` cross-checks OIDC settings — all three (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER`) must be set together or all omitted
- **`app/auth/constants.py`**: Shared `OAUTH_ONLY_SENTINEL` constant eliminates duplication between `store.py` and `routes.py`
- **Dynamic domain reload**: `reload_domain_agents()` returns `bool`; admin API surfaces failure in HTTP response instead of swallowing it silently
- **UI bug fixes**: Empty-input guard in `run_query`; history `gr.HTML` → `gr.Dataframe` with `gr.SelectData` (click-to-fill); SQLite window function alias expansion in `_render_window_function`; Gradio CSS moved to `launch()` for Gradio 6.x compatibility
- **Tests**: 541+ passing (19 new: OIDC discovery, OAuth email guard, SQL whitespace handling)

## v0.7.0 — Phase 7: Scale & Polish (2026-04-11)

- Async query execution: background job queue with `POST /api/query/execute-async` + polling
- SSE streaming: `POST /api/query/stream` emits tokens progressively via `MeridianStreamingCallback`
- Self-service domain onboarding: `POST /api/admin/domains` registers new domains at runtime without code changes
- Export: `POST /api/query/export` downloads results as JSON, CSV, or Excel
- Query explain mode: `explain=true` on `/execute` returns routing decision + SQL + views breakdown
- Index advisor wired: `IndexOptimizer` records every query; `GET /api/admin/performance` returns recommendations
- Multi-LLM: Groq (`ChatGroq`) preferred when `GROQ_API_KEY` set; OpenAI as fallback
- Load testing suite (`tests/performance/`) + `docs/BENCHMARKS.md`
- Full API documentation (`docs/API.md`)
- **Tests**: 522+ passing (51 new)

## v0.6.0 — Phase 6: Advanced Query Capabilities (2026-04-09)

- Parameterized queries (full SQL injection prevention)
- Window functions (ROW_NUMBER, RANK, SUM, etc.) with whitelist validation
- Common Table Expressions (WITH clauses)
- HAVING clause with operator whitelist
- Multi-hop BFS join pathfinding (auto-injects bridge views)
- Time intelligence: "last quarter", "ytd", "trailing N days" → ISO date ranges
- Auto-visualization hints (line/bar/pie/table) attached to every result
- **Tests**: 441+ passing (65 new)

## v0.5.0 — Phase 5: Enterprise Security (2026-03-xx)

- JWT authentication with role-based access (`viewer`, `admin`)
- Audit logging structure
- CORS configuration per environment
- Rate limiting middleware (60 req/min default)
- API key support
- Production-safety validator (`debug=True` blocked in production)

## v0.4.0 — Phase 4: Conversational Intelligence (2026-02-xx)

- Multi-turn conversation context (session-aware, 60-min expiry)
- Persistent query history (SQLite + REST API at `/api/history`)
- LLM-generated follow-up suggestions wired as Gradio buttons
- LangGraph promoted to primary execution engine (direct-agent fallback retained)
- **Tests**: 297+ passing (62 new)

## v0.3.0 — Phase 3 (roadmap): LLM-Powered NL Understanding (2026-01-xx)

- GPT-4 domain routing with confidence scoring; keyword fallback
- GPT-4 query interpretation (views, filters, aggregations, group-by) in all agents; regex fallback
- Confidence-based clarification threshold (0.4)
- `interpretation_method` field in all results
- Shared LLM client singleton (`get_llm()`)

## v0.2.0 — Phase 2 (roadmap): Activate Scaffolded Features (2025-12-xx)

- Redis caching active (context-scoped cache keys)
- Pagination (LIMIT/OFFSET with metadata)
- OpenTelemetry tracing hooks
- Langsmith integration wired
- Rate limiting active

## v0.1.0 — Phase 1: Foundation (2025-11-xx)

- ViewRegistry with 50+ views across Sales, Finance, Operations
- Sales, Finance, Operations domain agents
- QueryBuilder (SQL generation with auto-JOIN)
- QueryValidator (cardinality, column, view checks)
- REST API (6 endpoints), Gradio UI, Docker
- **Tests**: 235+ passing
