.PHONY: help install dev ui test lint format clean docker-up docker-down

help:
	@echo "MERIDIAN Development Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install         - Install development dependencies"
	@echo "  make install-prod    - Install production dependencies only"
	@echo ""
	@echo "Development:"
	@echo "  make dev             - Run development server (API)"
	@echo "  make ui              - Run Gradio UI on port 7860"
	@echo "  make docker-up       - Start Docker containers (dev)"
	@echo "  make docker-down     - Stop Docker containers"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test            - Run all tests"
	@echo "  make test-cov        - Run tests with coverage report"
	@echo "  make test-fast       - Run tests in parallel"
	@echo "  make lint            - Run linting (flake8)"
	@echo "  make type-check      - Run type checking (mypy)"
	@echo "  make format          - Format code with black & isort"
	@echo "  make check           - Run all checks (lint, type, format)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           - Remove build artifacts and cache"
	@echo "  make clean-db        - Reset development database"

install:
	pip install -r requirements-dev.txt

install-prod:
	pip install -r requirements-prod.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

ui:
	python gradio_app.py

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

test-fast:
	pytest tests/ -v -n auto

lint:
	flake8 app tests

type-check:
	mypy app --ignore-missing-imports

format:
	black app tests
	isort app tests

check: lint type-check

clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '.pytest_cache' -delete
	find . -type d -name '.mypy_cache' -delete
	find . -type d -name 'htmlcov' -delete
	find . -type f -name '.coverage' -delete
	find . -type d -name '*.egg-info' -delete

clean-db:
	@read -p "This will reset the development database. Continue? [y/N] " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker-compose up -d postgres; \
		sleep 3; \
		alembic upgrade head; \
	fi

shell:
	python -i -c "from app.views.registry import create_test_registry; from app.database.connection import DbConnection; from app.agents.orchestrator import Orchestrator; registry = create_test_registry(); db = DbConnection(is_mock=True); orchestrator = Orchestrator(registry, db); print('Available: registry, db, orchestrator')"
