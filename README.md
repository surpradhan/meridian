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
export OPENAI_API_KEY="sk-your-key"
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
│   ├── views/       # Data view metadata (Phase 1)
│   ├── query/       # Query building & validation (Phase 2-3)
│   ├── database/    # Database layer
│   ├── observability/ # Logging & tracing
│   └── core/        # Shared utilities & exceptions
│
├── tests/            # Test suite (unit, integration, e2e)
├── docs/             # Documentation
├── scripts/          # Utility scripts
├── docker/           # Docker configuration
├── config/           # Configuration files
└── notebooks/        # Jupyter notebooks
```

---

## Development Roadmap

### Phase 1: Foundation — ✅ COMPLETED
View Registry, Sales/Finance/Operations agents, QueryBuilder, QueryValidator, REST API (6 endpoints), Gradio UI, Docker, 158+ tests.

### Phase 2: Activate Scaffolded Features (Weeks 1–2)
Wire Redis caching, pagination, rate limiting, OpenTelemetry tracing, and Langsmith integration — all code written, not yet connected.

### Phase 3: LLM-Powered NL Understanding (Weeks 3–5)
Replace regex-based routing and query parsing with GPT-4 classification and structured output. Confidence-based clarification.

### Phase 4: Conversational Intelligence (Weeks 6–8)
Multi-turn conversations, query history, smart follow-up suggestions, LangGraph as primary orchestrator.

### Phase 5: Enterprise Security (Weeks 9–12)
JWT auth, row-level access control, audit logging, CORS lockdown.

### Phase 6: Advanced Query Capabilities (Weeks 13–16)
Window functions, CTEs, subqueries, multi-hop joins, time intelligence ("last quarter"), auto-visualization with Plotly.

### Phase 7: Scale & Polish (Weeks 17–20)
Streaming responses, async execution, self-service domain onboarding, export options, load testing.

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

- **[Setup Guide](docs/SETUP.md)** - Local development setup
- **[Architecture](docs/ARCHITECTURE.md)** - System design details
- **[API Documentation](docs/API.md)** - REST API endpoints
- **[Implementation Roadmap](docs/MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md)** - Phase breakdown & code
- **[Contributing](docs/CONTRIBUTING.md)** - Development guidelines

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **UI** | Gradio | Interactive web interface |
| **API** | FastAPI | REST API |
| **AI/Agents** | Langchain + Langraph | Agent framework & orchestration |
| **LLM** | OpenAI GPT-4 | Language model |
| **Database** | SQLAlchemy + PostgreSQL | Data layer |
| **Observability** | Langsmith + OpenTelemetry | Tracing & monitoring |
| **Development** | Pytest + Black + MyPy | Testing & quality |

---

## Configuration

Configuration is managed through environment variables and `.env` files.

### Key Settings

```bash
# OpenAI (Required)
OPENAI_API_KEY=sk-...

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
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for cloud deployment (AWS, GCP, Azure).

---

## Development Status

- **Current Phase:** Phase 1 (Foundation) COMPLETE → Next: Phase 2 (Activate Scaffolded Features)
- **Version:** 0.2.0
- **Python:** 3.11+
- **License:** MIT

---

## Contributing

We welcome contributions! See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

---

## License

MIT License - See [LICENSE](LICENSE) file for details

---

**Made with ❤️ by the MERIDIAN Team**

*Navigate your data. Make better decisions. Discover your True North.* 🧭
