# Pensieve task runner.
#
# Windows users without `make`: use the PowerShell equivalent, which exposes
# identical target names and calls the same underlying commands:
#
#     .\make.ps1 setup
#
# Both front doors delegate to the same scripts, so there is one implementation.

.DEFAULT_GOAL := help
.PHONY: help setup check dev dev-api dev-web test test-api test-web test-pipelines \
        lint lint-py lint-web format seed pipeline gold gold-docker benchmark \
        db-up db-down migrate clean docker-build docker-up docker-down

# Windows venv layout differs from POSIX.
ifeq ($(OS),Windows_NT)
	VENV_BIN := .venv/Scripts
	PY := $(VENV_BIN)/python.exe
else
	VENV_BIN := .venv/bin
	PY := $(VENV_BIN)/python
endif

WEB := apps/web

help: ## Show available targets
	@echo "Pensieve — available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup ----------------------------------------------------------------
setup: ## Create the venv, install Python and npm dependencies, write .env
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[api,pipelines,dev]"
	cd $(WEB) && npm install
	@test -f .env || cp .env.example .env
	@echo ""
	@$(PY) scripts/check_env.py

check: ## Report whether this machine can run each part of the platform
	@$(PY) scripts/check_env.py

# --- Development ----------------------------------------------------------
dev: ## Run the API and the dashboard together (requires `make db-up` first)
	@echo "API  -> http://localhost:8000/docs"
	@echo "Web  -> http://localhost:5173"
	@$(MAKE) -j2 dev-api dev-web

dev-api: ## Run only the FastAPI backend with autoreload
	$(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web: ## Run only the Vite dev server
	cd $(WEB) && npm run dev

# --- Quality --------------------------------------------------------------
test: test-api test-pipelines test-web ## Run every test suite

test-api: ## Backend tests
	$(PY) -m pytest apps/api/tests

test-pipelines: ## Pipeline tests
	$(PY) -m pytest pipelines/tests

test-web: ## Frontend tests
	cd $(WEB) && npm run test

lint: lint-py lint-web ## Lint and type-check everything

lint-py: ## ruff + mypy
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m mypy

lint-web: ## eslint + tsc + prettier
	cd $(WEB) && npm run lint && npm run typecheck && npm run format:check

format: ## Auto-format Python and TypeScript
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .
	cd $(WEB) && npm run format

# --- Data -----------------------------------------------------------------
seed: ## Generate a synthetic dataset (override with ROWS=50000)
	$(PY) scripts/seed_demo_data.py --rows $(or $(ROWS),10000)

pipeline: ## Run the full pipeline: Bronze -> Silver -> Gold
	$(PY) -m pipelines.jobs.run_pipeline

gold: ## Run only the PySpark Silver -> Gold stage (needs JDK 17+)
	$(PY) -m pipelines.jobs.run_gold

gold-docker: ## Run the Gold stage in Docker (use when the local JDK is < 17)
	docker compose --profile spark run --rm spark-job

benchmark: ## Timed pipeline run; records measured results
	$(PY) scripts/benchmark.py

# --- Database -------------------------------------------------------------
db-up: ## Start PostgreSQL only
	docker compose up -d postgres

db-down: ## Stop PostgreSQL
	docker compose stop postgres

migrate: ## Apply Alembic migrations
	cd apps/api && ../../$(PY) -m alembic upgrade head

# --- Docker ---------------------------------------------------------------
docker-build: ## Build all images
	docker compose build

docker-up: ## Start the full stack
	docker compose up --build

docker-down: ## Stop the stack and remove volumes
	docker compose down -v

# --- Housekeeping ---------------------------------------------------------
clean: ## Remove generated data, build output and caches
	$(PY) scripts/clean.py
