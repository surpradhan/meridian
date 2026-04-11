# 🧭 MERIDIAN

**Intelligent Data Navigation Platform**

*The True North for Your Data*

---

## What is MERIDIAN?

MERIDIAN is an AI-powered data navigation platform that connects natural language business questions to intelligent database queries. It uses **Langchain**, **Langraph**, and **LLM** to automatically route queries to domain-specific agents, validate queries for safety, and deliver confident answers.

### The Problem
Modern enterprises have abundant data but struggle to access it:
- ❌ Requires SQL expertise
- ❌ Time-consuming (hours to get answers)
- ❌ High security risk (SQL injection, malformed queries)
- ❌ Limited to pre-built dashboards

### The Solution
MERIDIAN bridges this gap:
- ✅ **Ask in natural language** - No SQL needed
- ✅ **Get answers in seconds** - Instant data access
- ✅ **Safe by default** - Query validation prevents errors
- ✅ **Domain expertise built-in** - Specialized agents understand context

---

## Quick Start (5 minutes)

### 1. Setup
```bash
# Clone or enter project
cd meridian

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
make install-dev

# Configure environment
cp .env.example .env.local
# Set your LLM key (Groq preferred, OpenAI as fallback):
export GROQ_API_KEY="gsk-your-key"
# or: export OPENAI_API_KEY="sk-your-key"
```

### 2. Run Tests
```bash
make test-unit
```

### 3. Start the Gradio UI
```bash
make ui
```

The UI is available at `http://localhost:7860` — ask questions in plain English and get results in tabular format.

### 4. Or Start the API Server
```bash
make dev
```

The REST API is available at `http://localhost:8000` (Swagger docs at `/docs`).

---

## Architecture

```
User Question
    ↓
[Router Agent] ← Detect domain
    ↓ (Sales/Finance/Operations)
[Domain Agent] ← Handle specialized queries
    ↓
[Query Validator] ← Ensure safety
    ↓
[Database] ← Execute safe query
    ↓
[Response] ← Natural language answer
```

---

## Project Structure

```
meridian/
├── gradio_app.py     # Gradio UI entry point
├── app/              # Main application code
│   ├── main.py      # FastAPI entry point
│   ├── config.py    # Configuration management
│   ├── api/         # REST API endpoints
│   ├── agents/      # AI agents (Langchain-based)
│   ├── tools/       # Langchain tool definitions
│   ├── views/       # Data view metadata
│   ├── query/       # Query building, validation & time intelligence
│   ├── visualization/ # Chart-type hints for query results
│   ├── jobs/        # Async job queue & status store (Phase 7)
│   ├── export/      # JSON / CSV / Excel exporters (Phase 7)
│   ├── explain/     # Query explain response builder (Phase 7)
│   ├── onboarding/  # Self-service domain registry (Phase 7)
│   ├── database/    # Database layer + index advisor
│   ├── auth/        # JWT auth, OAuth2/OIDC, RBAC, audit logging
│   ├── observability/ # Logging, metrics & tracing
│   └── core/        # Shared utilities & exceptions
│
├── tests/            # Test suite (unit, integration, performance)
├── docs/             # Documentation
├── scripts/          # Utility scripts
├── docker/           # Docker configuration
├── config/           # Configuration files
└── notebooks/        # Jupyter notebooks
```

---

## Development Roadmap

### Phase 1: Foundation — ✅ COMPLETED
View Registry, Sales/Finance/Operations agents, QueryBuilder, QueryValidator, REST API (6 endpoints), Gradio UI, Docker.

### Phase 2: Activate Scaffolded Features — ✅ COMPLETED
Redis caching, pagination, rate limiting, OpenTelemetry tracing, and Langsmith integration wired and active.

### Phase 3: LLM-Powered NL Understanding — ✅ COMPLETED
GPT-4 domain routing and query interpretation with two-stage regex fallback. Confidence-based clarification (threshold 0.4). Shared LLM client singleton.

### Phase 4: Conversational Intelligence — ✅ COMPLETED
Multi-turn conversation context (session-aware query refinement, context threading, conversation expiry + periodic cleanup), persistent query history (SQLite + REST API at `/api/history`), LLM-generated follow-up suggestions wired as real interactive buttons in the Gradio UI, and LangGraph promoted to primary execution engine (with transparent direct-agent fallback). 297+ tests passing.

### Phase 5: Enterprise Security — ✅ COMPLETED
JWT-based auth scaffolding, audit logging structure, CORS configuration, API key support, security middleware.

### Phase 6: Advanced Query Capabilities — ✅ COMPLETED
Parameterized queries (SQL injection prevention), HAVING clauses with operator whitelisting, window functions (ROW_NUMBER, RANK, SUM, etc.) with Pydantic validation, CTEs, ORDER BY, multi-hop BFS join pathfinding, time intelligence ("last quarter", "ytd", "trailing 30 days"), and auto-visualization hints (line/bar/pie/table). 65 new tests. **441+ tests total passing.**

### Phase 7: Scale & Polish — ✅ COMPLETED
Async query execution with job polling, SSE streaming responses, self-service domain onboarding (register new domains via API without code changes), JSON/CSV/Excel export, query explain mode (routing decision + SQL + filters), index advisor wired into query path, load testing suite, and full API documentation. Multi-LLM provider support (Groq + OpenAI). **522+ tests passing.**

### Phase 8: Security & Observability — ✅ COMPLETED
OAuth2 / OIDC SSO (Google + generic OIDC providers), SQL syntax pre-validation via SQLite EXPLAIN, Plotly interactive charts fully wired in the Gradio UI (line/bar/pie auto-selected), observability spans and query metrics wired throughout the orchestrator, and hardened configuration validation (OIDC all-or-nothing check). **541+ tests passing.**

---

## Common Commands

```bash
# Installation
make install          # Install base dependencies
make install-dev      # Install dev dependencies

# Code Quality
make lint             # Linting (flake8)
make format           # Format code (black + isort)
make type-check       # Type checking (mypy)

# Testing
make test             # Run all tests
make test-unit        # Unit tests only
make test-integration # Integration tests
make test-cov         # With coverage report

# Running
make ui               # Gradio UI (http://localhost:7860)
make dev              # FastAPI dev server (http://localhost:8000)

# Help
make help             # Show all available commands
```

---

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — System design, components, data flow
- **[API Reference](docs/API.md)** — All endpoints with request/response schemas
- **[Benchmarks](docs/BENCHMARKS.md)** — Performance targets and load test guide
- **[Changelog](docs/CHANGELOG.md)** — What changed in each version
- **[Roadmap](docs/ROADMAP.md)** — Phase-by-phase design rationale
- **[Auth Guide](docs/AUTH.md)** — OAuth2/OIDC setup, RBAC, and JWT configuration

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **UI** | Gradio | Interactive web interface |
| **API** | FastAPI | REST API |
| **AI/Agents** | Langchain + Langraph | Agent framework & orchestration |
| **LLM** | Groq / OpenAI (configurable) | Language model (Groq preferred, OpenAI fallback) |
| **Database** | SQLAlchemy + PostgreSQL | Data layer |
| **Observability** | Langsmith + OpenTelemetry | Tracing & monitoring |
| **Development** | Pytest + Black + MyPy | Testing & quality |

---

## Configuration

Configuration is managed through environment variables and `.env` files.

### Key Settings

```bash
# LLM Provider — Groq takes priority when set; OpenAI is the fallback
GROQ_API_KEY=gsk-...          # Preferred
GROQ_MODEL=llama-3.3-70b-versatile

OPENAI_API_KEY=sk-...         # Fallback
OPENAI_MODEL=gpt-4

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/meridian_dev

# Langsmith (Optional - for observability)
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true

# Application
LOG_LEVEL=INFO
DEBUG=true
```

See [.env.example](.env.example) for all available options.

---

## Testing

```bash
# All tests
make test

# Specific test types
make test-unit           # Fast, isolated tests
make test-integration    # Multi-component tests
make test-e2e           # Full workflow tests

# With coverage
make test-cov

# Specific file
pytest tests/unit/test_agents.py -v
```

---

## Deployment

### Local Development
```bash
make ui       # Gradio UI at http://localhost:7860
make dev      # API server at http://localhost:8000 (docs at /docs)
```

### Docker
```bash
docker build -t meridian:latest .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... meridian:latest
```

### Production
See the [Architecture doc](docs/ARCHITECTURE.md) for deployment topology notes.

---

## Development Status

- **Current Phase:** Phase 8 (Security & Observability) COMPLETE — all 8 phases done
- **Version:** 0.8.0
- **Python:** 3.11+
- **License:** MIT

---

## Contributing

We welcome contributions! Open an issue or pull request on GitHub.

---

## License

MIT License - See [LICENSE](LICENSE) file for details

---

**Made with ❤️ by the MERIDIAN Team**

*Navigate your data. Make better decisions. Discover your True North.* 🧭
