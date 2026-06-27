# ─────────────────────────────────────────────────────────────────────────────
# AI FinOps — Makefile
# ─────────────────────────────────────────────────────────────────────────────
.DEFAULT_GOAL := help
.PHONY: help up down restart logs ps \
        backend frontend \
        install install-backend install-frontend \
        migrate migrate-create migrate-rollback \
        test test-backend test-frontend test-e2e \
        lint lint-backend lint-frontend \
        format format-backend format-frontend \
        typecheck typecheck-backend typecheck-frontend \
        build build-backend build-frontend \
        clean clean-docker clean-pyc \
        pre-commit-install pre-commit-run \
        shell-backend shell-postgres shell-redis shell-clickhouse

# ─── Variables ────────────────────────────────────────────────────────────────
COMPOSE        := docker compose
BACKEND_DIR    := backend
FRONTEND_DIR   := frontend
PYTHON         := python3.13
VENV           := $(BACKEND_DIR)/.venv
PIP            := $(VENV)/bin/pip
UVICORN        := $(VENV)/bin/uvicorn
PYTEST         := $(VENV)/bin/pytest
BLACK          := $(VENV)/bin/black
RUFF           := $(VENV)/bin/ruff
MYPY           := $(VENV)/bin/mypy
ALEMBIC        := $(VENV)/bin/alembic

# ─── Help ─────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@echo ""
	@echo "  AI FinOps — Available Make Targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ─── Docker Compose ───────────────────────────────────────────────────────────
up: ## Start all services (infrastructure + api + frontend)
	$(COMPOSE) up -d

up-infra: ## Start infrastructure services only (postgres, clickhouse, redis)
	$(COMPOSE) up -d postgres clickhouse redis

down: ## Stop all services
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) restart

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

logs-api: ## Tail backend API logs
	$(COMPOSE) logs -f api

ps: ## Show service status
	$(COMPOSE) ps

# ─── Development Shortcuts ────────────────────────────────────────────────────
dev: up-infra ## Start infrastructure and run backend + frontend locally
	@echo "Infrastructure started. Run 'make backend' and 'make frontend' in separate terminals."

backend: ## Run backend API locally (requires venv)
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

frontend: ## Run frontend dev server locally
	cd $(FRONTEND_DIR) && pnpm dev

# ─── Installation ─────────────────────────────────────────────────────────────
install: install-backend install-frontend ## Install all dependencies

install-backend: ## Install backend Python dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e "$(BACKEND_DIR)[dev]"

install-frontend: ## Install frontend Node dependencies
	pnpm install

# ─── Database / Migrations ────────────────────────────────────────────────────
db-check: ## Verify database connectivity using configured DATABASE_URL
	cd $(BACKEND_DIR) && $(PYTHON) ../scripts/dev/check_db.py

migrate: ## Run pending Alembic migrations
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add user table")
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(MSG)"

migrate-rollback: ## Roll back one migration
	cd $(BACKEND_DIR) && $(ALEMBIC) downgrade -1

migrate-history: ## Show migration history
	cd $(BACKEND_DIR) && $(ALEMBIC) history --verbose

# ─── Testing ──────────────────────────────────────────────────────────────────
test: test-backend ## Run all tests

test-backend: ## Run backend test suite
	cd $(BACKEND_DIR) && $(PYTEST) tests/ -v --tb=short --cov=app --cov-report=term-missing

test-frontend: ## Run frontend test suite
	cd $(FRONTEND_DIR) && pnpm test

test-e2e: ## Run end-to-end tests
	cd tests/e2e && pnpm test

test-ci: ## Run tests in CI mode (no coverage interactive output)
	cd $(BACKEND_DIR) && $(PYTEST) tests/ --tb=short --cov=app --cov-report=xml

# ─── Linting ──────────────────────────────────────────────────────────────────
lint: lint-backend lint-frontend ## Run all linters

lint-backend: ## Lint backend with Ruff
	$(RUFF) check $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

lint-frontend: ## Lint frontend with ESLint
	cd $(FRONTEND_DIR) && pnpm lint

# ─── Formatting ───────────────────────────────────────────────────────────────
format: format-backend format-frontend ## Format all code

format-backend: ## Format backend with Black + Ruff
	$(BLACK) $(BACKEND_DIR)/app $(BACKEND_DIR)/tests
	$(RUFF) check --fix $(BACKEND_DIR)/app $(BACKEND_DIR)/tests

format-frontend: ## Format frontend with Prettier
	cd $(FRONTEND_DIR) && pnpm format

# ─── Type Checking ────────────────────────────────────────────────────────────
typecheck: typecheck-backend ## Run all type checkers

typecheck-backend: ## Type check backend with mypy
	$(MYPY) $(BACKEND_DIR)/app

typecheck-frontend: ## Type check frontend with tsc
	cd $(FRONTEND_DIR) && pnpm typecheck

# ─── Build ────────────────────────────────────────────────────────────────────
build: build-backend build-frontend ## Build all production images

build-backend: ## Build backend Docker image
	$(COMPOSE) build api

build-frontend: ## Build frontend Docker image
	$(COMPOSE) build frontend

# ─── Pre-commit ───────────────────────────────────────────────────────────────
pre-commit-install: ## Install pre-commit hooks
	$(VENV)/bin/pre-commit install

pre-commit-run: ## Run pre-commit on all files
	$(VENV)/bin/pre-commit run --all-files

# ─── Cleanup ──────────────────────────────────────────────────────────────────
clean: clean-pyc ## Clean build artifacts

clean-pyc: ## Remove Python bytecode files
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

clean-docker: ## Remove all Docker volumes (DESTRUCTIVE — deletes local data)
	$(COMPOSE) down -v --remove-orphans

# ─── Shells ───────────────────────────────────────────────────────────────────
shell-backend: ## Open shell in backend container
	$(COMPOSE) exec api /bin/bash

shell-postgres: ## Open psql in postgres container
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-aifinops} -d $${POSTGRES_DB:-aifinops}

shell-redis: ## Open redis-cli in redis container
	$(COMPOSE) exec redis redis-cli

shell-clickhouse: ## Open clickhouse-client in clickhouse container
	$(COMPOSE) exec clickhouse clickhouse-client --user $${CLICKHOUSE_USER:-aifinops}

# ─── CI Targets ───────────────────────────────────────────────────────────────
ci: lint typecheck test-ci ## Run full CI pipeline locally
