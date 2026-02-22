.PHONY: dev dev-up dev-down dev-infra dev-setup build test lint clean ci

# ===================
# Development (Docker - all services)
# ===================
dev:
	cd infrastructure/docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-up:
	cd infrastructure/docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

dev-down:
	cd infrastructure/docker && docker compose down

# ===================
# Development (Local Python - faster hot-reload)
# ===================
# Start only PostgreSQL and Redis in Docker
dev-infra:
	cd infrastructure/docker && docker compose -f docker-compose.yml up -d postgres redis
	@echo ""
	@echo "Infrastructure running:"
	@echo "  PostgreSQL: localhost:47532"
	@echo "  Redis:      localhost:47379"
	@echo ""
	@echo "Now run services locally:"
	@echo "  ./scripts/dev-local.sh auth"
	@echo "  ./scripts/dev-local.sh strategy"
	@echo "  etc."

# Create virtual environments for all services
dev-setup:
	./scripts/dev-local.sh setup

# Stop infrastructure
dev-infra-down:
	cd infrastructure/docker && docker compose stop postgres redis

# Run all services locally (requires honcho: pip install honcho)
dev-local:
	@if ! command -v honcho &> /dev/null; then \
		echo "Installing honcho..."; \
		pip install honcho; \
	fi
	honcho start -f Procfile.dev

# Build
build:
	cd infrastructure/docker && docker-compose build

build-prod:
	cd infrastructure/docker && docker-compose -f docker-compose.yml build

# ===================
# CI (Local) - Mimics GitHub Actions
# ===================
ci:
	./scripts/ci-local.sh

ci-backend:
	./scripts/ci-local.sh --backend-only

ci-lint:
	./scripts/ci-local.sh --lint-only

ci-test:
	./scripts/ci-local.sh --test-only

# Testing (runs services in isolation like CI)
test:
	./scripts/ci-local.sh --test-only

test-backend:
	./scripts/ci-local.sh --test-only --backend-only

test-frontend:
	./scripts/ci-local.sh --test-only --frontend-only

test-auth:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev]" -e "libs/db[dev]" -e "services/auth[dev]"; \
	cd services/auth && pytest tests -v

test-strategy:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev]" -e "libs/db[dev]" -e "services/strategy[dev]"; \
	cd services/strategy && pytest tests -v

# ===================
# Linting & Type Checking
# ===================
lint:
	@echo "=== Python: Ruff (lint) ==="
	ruff check --config pyproject.toml services/ libs/
	@echo "=== Python: Ruff (format) ==="
	ruff format --config pyproject.toml --check services/ libs/
	@echo "=== Python: Mypy (type check) ==="
	@# Run mypy per-service to avoid "Duplicate module named src" error
	mypy libs/common --ignore-missing-imports
	mypy services/auth --ignore-missing-imports
	mypy services/strategy --ignore-missing-imports
	mypy services/backtest --ignore-missing-imports
	mypy services/market-data --ignore-missing-imports
	mypy services/trading --ignore-missing-imports
	mypy services/portfolio --ignore-missing-imports
	mypy services/notification --ignore-missing-imports
	mypy services/billing --ignore-missing-imports
	@echo "=== Frontend: ESLint ==="
	cd apps/web && npm run lint
	@echo "=== Frontend: TypeScript ==="
	cd apps/web && npx tsc --noEmit

lint-fix:
	ruff check --config pyproject.toml --fix --unsafe-fixes services/ libs/
	ruff format --config pyproject.toml services/ libs/

lint-python:
	ruff check --config pyproject.toml services/ libs/
	ruff format --config pyproject.toml --check services/ libs/
	@# Run mypy per-service to avoid "Duplicate module named src" error
	mypy libs/common --ignore-missing-imports
	mypy services/auth --ignore-missing-imports
	mypy services/strategy --ignore-missing-imports
	mypy services/backtest --ignore-missing-imports
	mypy services/market-data --ignore-missing-imports
	mypy services/trading --ignore-missing-imports
	mypy services/portfolio --ignore-missing-imports
	mypy services/notification --ignore-missing-imports
	mypy services/billing --ignore-missing-imports

lint-frontend:
	cd apps/web && npm run lint
	cd apps/web && npx tsc --noEmit

typecheck:
	@# Run mypy per-service to avoid "Duplicate module named src" error
	mypy libs/common --ignore-missing-imports
	mypy services/auth --ignore-missing-imports
	mypy services/strategy --ignore-missing-imports
	mypy services/backtest --ignore-missing-imports
	mypy services/market-data --ignore-missing-imports
	mypy services/trading --ignore-missing-imports
	mypy services/portfolio --ignore-missing-imports
	mypy services/notification --ignore-missing-imports
	mypy services/billing --ignore-missing-imports
	cd apps/web && npx tsc --noEmit

# ===================
# Pre-commit Hooks
# ===================
pre-commit-install:
	pip install pre-commit
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

# Database
migrate:
	@echo "Running migrations..."

# Deployment
deploy-staging:
	kubectl apply -k infrastructure/k8s/overlays/staging

deploy-prod:
	kubectl apply -k infrastructure/k8s/overlays/production

# Infrastructure
tf-init:
	cd infrastructure/terraform && terraform init

tf-plan:
	cd infrastructure/terraform && terraform plan

tf-apply:
	cd infrastructure/terraform && terraform apply

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	cd infrastructure/docker && docker-compose down -v --rmi local 2>/dev/null || true

# Help
help:
	@echo "LlamaTrade Development Commands"
	@echo ""
	@echo "Development (Docker - simpler setup):"
	@echo "  make dev            - Start all services in Docker with hot-reload"
	@echo "  make dev-up         - Start services in background"
	@echo "  make dev-down       - Stop all services"
	@echo ""
	@echo "Development (Local Python - faster hot-reload):"
	@echo "  make dev-setup      - Create virtual environments for all services"
	@echo "  make dev-infra      - Start only PostgreSQL + Redis in Docker"
	@echo "  make dev-local      - Run ALL services locally (uses honcho)"
	@echo "  ./scripts/dev-local.sh <service>  - Run ONE service locally"
	@echo ""
	@echo "CI (run locally before pushing):"
	@echo "  make ci             - Run full CI locally (lint + tests)"
	@echo "  make ci-backend     - Run backend CI only"
	@echo "  make ci-lint        - Run linting only"
	@echo "  make ci-test        - Run tests only"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test           - Run all tests (in isolation)"
	@echo "  make test-auth      - Run auth service tests"
	@echo "  make test-strategy  - Run strategy service tests"
	@echo "  make lint           - Run all linters + type checks"
	@echo "  make lint-fix       - Auto-fix Python lint issues"
	@echo "  make typecheck      - Run type checkers only"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo "  make pre-commit-run - Run pre-commit on all files"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-staging - Deploy to staging"
	@echo "  make deploy-prod    - Deploy to production"
	@echo ""
	@echo "Default Ports (all use 47xxx range):"
	@echo "  Frontend:    http://localhost:47300"
	@echo "  API Gateway: http://localhost:47800"
	@echo "  PostgreSQL:  localhost:47532"
	@echo "  Redis:       localhost:47379"
	@echo ""
	@echo "Service Ports:"
	@echo "  auth:47810  strategy:47820  backtest:47830  market-data:47840"
	@echo "  trading:47850  portfolio:47860  notification:47870  billing:47880"
