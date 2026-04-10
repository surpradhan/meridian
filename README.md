# MERIDIAN

**Intelligent Data Navigation Platform** — *The True North for Your Data*

MERIDIAN connects natural language business questions to intelligent database queries. It automatically routes questions to domain-specific agents (Sales, Finance, Operations), validates queries for safety, and delivers answers with a full audit trail.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/surpradhan/meridian.git && cd meridian

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dev dependencies
make install-dev

# Configure environment
cp .env.example .env.local
export OPENAI_API_KEY="sk-your-key"

# Run tests to verify setup
make test-unit

# Start the Gradio UI
make ui               # http://localhost:7860

# Or start the REST API
make dev              # http://localhost:8000 (Swagger at /docs)
```

---

## Architecture

```
User Question
    ↓
[Router Agent]      — GPT-4 domain classification (keyword fallback)
    ↓ (Sales / Finance / Operations)
[Domain Agent]      — LLM-powered query interpretation (regex fallback)
    ↓
[Query Validator]   — View/column/cardinality/injection checks
    ↓
[Query Builder]     — Parameterized SQL with JOINs, HAVING, window fns, CTEs
    ↓
[Database]          — Safe execution
    ↓
[Response]          — Result + conversation_id + follow-up suggestions + viz hint
```

Multi-turn sessions are tracked via `ConversationManager`. LangGraph is the primary orchestration engine; direct agent call is the fallback.

---

## Project Structure

```
meridian/
├── gradio_app.py        # Gradio UI
├── app/
│   ├── main.py          # FastAPI entry
│   ├── config.py        # Configuration
│   ├── api/             # REST endpoints
│   ├── agents/          # Router, domain agents, orchestrator, conversation
│   ├── tools/           # Langchain tool definitions
│   ├── views/           # View registry & metadata
│   ├── query/           # Builder, validator, time intelligence, pagination
│   ├── visualization/   # Chart-type hint inference
│   ├── history/         # Query history (SQLite)
│   ├── cache/           # Redis cache manager
│   ├── database/        # Connection & index optimizer
│   └── observability/   # Structured logging, tracing, metrics
├── tests/               # 441+ tests (unit, integration, e2e)
├── docs/                # Documentation
├── docker/              # Docker & Compose configs
├── config/              # Environment YAML configs
└── notebooks/           # Jupyter exploration notebooks
```

---

## Common Commands

```bash
# Installation
make install-dev      # Install dev dependencies

# Code quality
make lint             # flake8
make format           # black + isort
make type-check       # mypy

# Testing
make test             # All tests
make test-unit        # Unit tests only
make test-integration # Integration tests
make test-cov         # With coverage report

# Running
make ui               # Gradio UI — http://localhost:7860
make dev              # FastAPI dev server — http://localhost:8000

make help             # All available commands
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Gradio |
| API | FastAPI + Pydantic |
| AI / Agents | Langchain + LangGraph |
| LLM | OpenAI GPT-4 |
| Database | SQLAlchemy + PostgreSQL (SQLite for dev) |
| Caching | Redis |
| Observability | Langsmith + OpenTelemetry + structured JSON logging |
| Dev tooling | Pytest + Black + MyPy + flake8 |

---

## Configuration

```bash
# Required
OPENAI_API_KEY=sk-...

# Database (SQLite works for local dev)
DATABASE_URL=postgresql://user:pass@localhost:5432/meridian_dev

# Optional observability
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
```

See `.env.example` for all options.

---

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundation — view registry, 3 agents, REST API, Gradio UI, Docker | Complete |
| 2 | Activate scaffolded features — Redis cache, pagination, rate limiting, tracing | Complete |
| 3 | LLM-powered NL — GPT-4 routing + interpretation, confidence-based clarification | Complete |
| 4 | Conversational intelligence — multi-turn context, query history, LangGraph primary | Complete |
| 5 | Enterprise security — JWT auth, RBAC, audit logging, CORS lockdown | Complete |
| 6 | Advanced query — HAVING, window functions, CTEs, parameterized SQL, time intelligence, multi-hop joins, viz hints | Complete |
| 7 | Scale & polish — streaming, async execution, self-service onboarding, export, load testing | In progress |

**441+ tests passing. Version 0.6.0.**

---

## Documentation

- [Setup Guide](docs/SETUP.md) — local development setup
- [Architecture](docs/ARCHITECTURE.md) — system design & component reference
- [Features](docs/FEATURES.md) — advanced capabilities (tracing, caching, pagination, etc.)
- [Roadmap](docs/ROADMAP.md) — phase status, current state, Phase 7 plan

---

## License

MIT — see [LICENSE](LICENSE)
