# Local Development Setup

Get MERIDIAN running on your local machine in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 13+ (or SQLite for development)
- Git
- OpenAI API key

## Quick Start (5 minutes)

### 1. Clone & Enter Directory
```bash
cd ~/practiceprojects/meridian
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
# For development
make install-dev

# Or manually
pip install -r requirements-dev.txt
```

### 4. Setup Environment
```bash
cp .env.example .env.local
# Edit .env.local and add your OpenAI API key
export OPENAI_API_KEY="sk-your-key"
```

### 5. Run Tests (Verify Setup)
```bash
make test-unit
```

### 6. Start Development Server
```bash
make run-dev
```

The API should be available at `http://localhost:8000`

## Detailed Setup

### Python & Virtual Environment

**macOS/Linux:**
```bash
python3 --version  # Should be 3.11+
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python --version  # Should be 3.11+
python -m venv venv
venv\Scripts\activate
```

### Database Setup

#### Option 1: PostgreSQL (Recommended)

```bash
# macOS (with Homebrew)
brew install postgresql@15
brew services start postgresql@15
createdb meridian_dev

# Linux (Ubuntu/Debian)
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb meridian_dev

# Set DATABASE_URL in .env.local
DATABASE_URL=postgresql://postgres:password@localhost:5432/meridian_dev
```

#### Option 2: SQLite (Quick Development)

```bash
# Edit .env.local
DATABASE_URL=sqlite:///meridian_dev.db
```

### OpenAI API Key

1. Get your API key from https://platform.openai.com/api-keys
2. Add to `.env.local`:
   ```bash
   OPENAI_API_KEY=sk-your-key-here
   ```
3. Verify it works:
   ```bash
   python -c "import openai; print('OpenAI configured')"
   ```

## Available Commands

```bash
# Installation
make install              # Install base requirements
make install-dev         # Install with dev tools
make install-prod        # Install with production tools

# Code Quality
make lint                 # Flake8 linting
make format              # Black + isort formatting
make type-check          # MyPy type checking

# Testing
make test                # Run all tests
make test-unit           # Unit tests only
make test-integration    # Integration tests
make test-e2e            # End-to-end tests
make test-cov            # With coverage report

# Running
make run                 # Run production server
make run-dev             # Run with hot reload

# Utilities
make clean               # Remove build artifacts
make seed-views          # Initialize view metadata

# Help
make help               # Show all available commands
```

## Project Structure

```
meridian/
├── app/                 # Main application
│   ├── main.py         # FastAPI app entry
│   ├── config.py       # Configuration
│   ├── api/            # REST endpoints
│   ├── agents/         # AI agents
│   ├── tools/          # Langchain tools
│   ├── views/          # View metadata
│   ├── query/          # Query logic
│   └── ...
├── tests/              # Test suite
├── docs/               # Documentation
├── scripts/            # Utility scripts
├── notebooks/          # Jupyter notebooks
└── config/             # Configuration files
```

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
    "editor.defaultFormatter": "ms-python.python"
  }
}
```

### PyCharm

1. Set Python interpreter: `Settings → Project → Python Interpreter`
2. Select `./venv/bin/python`
3. Enable linting: `Settings → Tools → Python Integrated Tools`

## Verification

After setup, verify everything works:

```bash
# 1. Check Python and dependencies
python --version
pip list | grep langchain

# 2. Run tests
make test-unit

# 3. Check API startup
make run-dev
# Should see: "Uvicorn running on http://0.0.0.0:8000"

# 4. Try a health check (in another terminal)
curl http://localhost:8000/health
# Should return: {"status": "ok"}
```

## Troubleshooting

### Python Version
```bash
# Make sure you're using 3.11+
python3 --version

# If not, install Python 3.11+
# macOS: brew install python@3.11
# Ubuntu: apt install python3.11
```

### Virtual Environment
```bash
# Deactivate and activate fresh
deactivate
rm -rf venv
python3 -m venv venv
source venv/bin/activate
```

### Dependencies
```bash
# Reinstall cleanly
pip install --upgrade pip
pip install -r requirements-dev.txt --force-reinstall
```

### Database Connection
```bash
# Test PostgreSQL
psql -U postgres -d meridian_dev -c "SELECT 1"

# Check environment variable
echo $DATABASE_URL
```

### OpenAI API
```bash
# Test API key
python -c "from openai import OpenAI; client = OpenAI(); print('OK')"
```

## Next Steps

1. ✅ Complete [SETUP.md](SETUP.md) (you are here)
2. 📖 Read [Quick Start Examples](examples/quickstart.md)
3. 🏗️ Understand [Architecture](ARCHITECTURE.md)
4. 💻 Start [Phase 1 Implementation](../MULTI_AGENT_PROTOTYPE_ROADMAP_v2.md#phase-1)

---

Need help? Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
