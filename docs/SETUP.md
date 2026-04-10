# Local Development Setup

Get MERIDIAN running on your local machine in under 10 minutes.

## Prerequisites

- Python 3.11+
- Git
- OpenAI API key ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))
- PostgreSQL 13+ **or** use SQLite for quick local dev (no install needed)
- Docker & Docker Compose (optional — for containerized services)

---

## Quick Start

```bash
# 1. Enter the project directory
cd ~/practiceprojects/meridian

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dev dependencies
make install-dev
# or: pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env.local
# Edit .env.local — set OPENAI_API_KEY and DATABASE_URL at minimum

# 5. Verify setup
make test-unit
# Should show all tests passing

# 6. Start the app
make ui     # Gradio UI at http://localhost:7860
# or
make dev    # FastAPI at http://localhost:8000 (Swagger at /docs)
```

---

## Database Setup

### Option A: SQLite (fastest for local dev)

```bash
# In .env.local:
DATABASE_URL=sqlite:///meridian_dev.db
```

No installation needed — SQLite is bundled with Python.

### Option B: PostgreSQL (recommended for realistic testing)

**macOS (Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
createdb meridian_dev
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb meridian_dev
```

**In `.env.local`:**
```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/meridian_dev
```

### Option C: Docker services

```bash
# Starts PostgreSQL + Redis
make docker-up
# or: docker-compose up -d
```

---

## Environment Variables

Key variables to set in `.env.local`:

```bash
# Required
OPENAI_API_KEY=sk-your-key-here

# Database (choose one)
DATABASE_URL=sqlite:///meridian_dev.db
# DATABASE_URL=postgresql://postgres:password@localhost:5432/meridian_dev

# Optional — Langsmith observability
LANGSMITH_API_KEY=lsv2_your-key-here
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=meridian

# Optional — Redis cache
REDIS_HOST=localhost
REDIS_PORT=6379

# App settings
LOG_LEVEL=INFO
DEBUG=true
```

See `.env.example` for the full list.

---

## Available Commands

```bash
# Installation
make install          # Base requirements only
make install-dev      # With dev tools (pytest, black, mypy, etc.)
make install-prod     # With production extras

# Running
make ui               # Gradio UI — http://localhost:7860
make dev              # FastAPI with hot reload — http://localhost:8000
make run              # FastAPI production mode

# Testing
make test             # All tests
make test-unit        # Unit tests only (fast, no DB needed)
make test-integration # Integration tests
make test-e2e         # End-to-end tests
make test-cov         # All tests + HTML coverage report
make test-fast        # Parallel test run

# Code quality
make lint             # flake8
make format           # black + isort
make type-check       # mypy
make check            # All quality checks at once

# Docker
make docker-up        # Start PostgreSQL + Redis
make docker-down      # Stop services

# Utilities
make seed-views       # Initialize view metadata in DB
make shell            # Python REPL with app components pre-imported
make clean            # Remove build artifacts
make clean-db         # Reset local database

make help             # Full command list
```

---

## IDE Setup

### VS Code

Create `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.linting.flake8Args": ["--max-line-length=100"],
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length=100"],
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "ms-python.python",
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

### PyCharm

1. Set interpreter: `Settings → Project → Python Interpreter → ./venv/bin/python`
2. Enable pytest: `Settings → Tools → Python Integrated Tools → Default Test Runner → pytest`
3. Enable black: `Settings → Tools → Black`

---

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

---

## Verification

After setup, confirm everything works:

```bash
# Check Python and key dependencies
python --version          # Should be 3.11+
pip show langchain        # Should show version

# Run unit tests (no external services needed)
make test-unit

# Check API starts cleanly
make dev
# Should print: Uvicorn running on http://0.0.0.0:8000

# Health check (in another terminal)
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

---

## Troubleshooting

### Python version wrong
```bash
python3 --version        # macOS: brew install python@3.11
                         # Ubuntu: apt install python3.11
```

### Virtual environment issues
```bash
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
```

### Dependency conflicts
```bash
pip install --upgrade pip
pip install -r requirements-dev.txt --force-reinstall
```

### PostgreSQL connection refused
```bash
# Check it's running
docker-compose ps       # if using Docker
brew services list      # if using Homebrew
psql -U postgres -d meridian_dev -c "SELECT 1"   # direct check

# Verify DATABASE_URL
echo $DATABASE_URL
```

### OpenAI key not working
```bash
python -c "from openai import OpenAI; client = OpenAI(); print('OK')"
```

### Port 8000 already in use
```bash
uvicorn app.main:app --reload --port 8001
```

---

## Next Steps

1. Read [Architecture](ARCHITECTURE.md) — understand how the system fits together
2. Read [Features](FEATURES.md) — advanced capabilities (caching, tracing, pagination, etc.)
3. Read [Roadmap](ROADMAP.md) — current state and Phase 7 plan
4. Explore the API — visit `http://localhost:8000/docs` after starting `make dev`
