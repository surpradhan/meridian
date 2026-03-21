# MERIDIAN Development Setup

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized development)
- Git
- PostgreSQL (optional, Docker provides this)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/meridian.git
cd meridian
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
make install
```

Or manually:

```bash
pip install -r requirements-dev.txt
```

### 4. Set Up Environment Variables

```bash
cp .env.example .env.local
# Edit .env.local with your settings
```

### 5. Start Docker Services

```bash
make docker-up
```

This starts PostgreSQL and Redis containers.

### 6. Run Development Server

```bash
make dev
```

The API will be available at `http://localhost:8000`.

## Development Workflow

### Running Tests

```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Run in parallel
make test-fast
```

### Code Quality

```bash
# Check code style and type hints
make check

# Format code
make format

# Run specific checks
make lint
make type-check
```

### Using Docker for Development

The `docker-compose.yml` provides a complete development environment:

```bash
# Start all services
docker-compose up

# Stop services
docker-compose down

# View logs
docker-compose logs -f app

# Run commands in container
docker-compose exec app python -m pytest
```

## Project Structure

```
meridian/
├── app/
│   ├── agents/           # AI agents and orchestrator
│   ├── api/              # REST API endpoints
│   ├── database/         # Database layer
│   ├── observability/    # Logging and metrics
│   ├── query/            # Query validation and building
│   ├── views/            # Data view metadata
│   └── main.py           # FastAPI app initialization
├── tests/                # Test suite
├── docker/               # Docker configuration
├── config/               # Environment configurations
├── Makefile              # Development commands
└── requirements*.txt     # Python dependencies
```

## API Documentation

Once the server is running, visit:

- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)

## Common Tasks

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Create Test Registry

```bash
python -c "
from app.views.registry import create_test_registry
registry = create_test_registry()
print(f'Loaded {len(registry.get_all_views())} views')
"
```

### Run Linter/Formatter

```bash
# Check style
make lint

# Auto-format
make format
```

### Interactive Shell

```bash
make shell
```

This starts a Python REPL with pre-imported components ready to use.

## Troubleshooting

### Port Already in Use

If port 8000 is in use:

```bash
# Change port in dev command
uvicorn app.main:app --reload --port 8001
```

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps

# Restart services
docker-compose restart postgres

# Check database URL in .env.local
echo $DATABASE_URL
```

### Import Errors

```bash
# Reinstall dependencies
pip install -r requirements-dev.txt --force-reinstall

# Clear Python cache
make clean
```

## IDE Setup

### VS Code

1. Install Python extension
2. Select interpreter: `./venv/bin/python`
3. Install Pylance for better type hints
4. Create `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

### PyCharm

1. Configure interpreter: Settings > Project > Python Interpreter
2. Enable Pytest: Settings > Tools > Python Integrated Tools > Default Test Runner
3. Configure code style: Settings > Editor > Code Style > Python

## Next Steps

1. Read the [Architecture Guide](ARCHITECTURE.md)
2. Check [Contributing Guidelines](CONTRIBUTING.md)
3. Review [API Documentation](API.md)
4. Run the test suite: `make test`

## Getting Help

- Check [Troubleshooting Guide](TROUBLESHOOTING.md)
- Open an issue on GitHub
- Review [Architecture Docs](docs/ARCHITECTURE.md)

---

**Last Updated**: 2026-03-19
