# MERIDIAN Changelog

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
