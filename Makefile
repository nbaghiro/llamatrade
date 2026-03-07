.PHONY: dev dev-up dev-down dev-infra dev-setup build test lint clean ci migrate migrate-status migrate-history

# Helper to load .env file
ifneq (,$(wildcard ./.env))
    ENV_FILE := .env
else
    ENV_FILE := .env.example
endif
LOAD_ENV := set -a && [ -f $(ENV_FILE) ] && . ./$(ENV_FILE) && set +a

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
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis:      localhost:6379"
	@echo ""
	@echo "Now run services locally:"
	@echo "  make dev-local                 # All services"
	@echo "  make dev-local SERVICE=auth    # Single service"

# Create virtual environments for all services
dev-setup:
	./scripts/dev-local.sh setup

# Stop infrastructure
dev-infra-down:
	cd infrastructure/docker && docker compose stop postgres redis

# Run services locally
# Usage: make dev-local           - Run ALL services (uses honcho)
#        make dev-local SERVICE=auth  - Run a single service
dev-local:
ifdef SERVICE
	./scripts/dev-local.sh $(SERVICE)
else
	@if ! command -v honcho &> /dev/null; then \
		echo "Installing honcho..."; \
		pip install honcho; \
	fi
	honcho start -f Procfile.dev
endif

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

ci-backend: lint-python test-unit
	@echo "Backend CI completed"

ci-lint:
	./scripts/ci-local.sh --lint-only

ci-test: test-unit test-integration
	@echo "All CI tests completed"

# ===================
# Testing
# ===================
# Run ALL tests (unit + integration)
test: test-unit test-integration
	@echo "All tests completed"

# Run only unit tests (per-service tests)
test-unit:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	echo "=== Running unit tests for all services ==="; \
	for svc in auth strategy billing backtest trading market-data portfolio; do \
		echo ""; \
		echo "=== Testing $$svc ==="; \
		(cd services/$$svc && pytest tests/ -v); \
	done

test-unit-quick:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	echo "=== Running unit tests (quick mode) ==="; \
	for svc in auth strategy billing backtest trading market-data portfolio; do \
		echo "=== $$svc ==="; \
		(cd services/$$svc && pytest tests/ -q); \
	done

# Run only integration tests (requires Docker for testcontainers)
test-integration:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev,integration]" -e "libs/db[dev]"; \
	pytest tests/integration -v --timeout=120

test-integration-quick:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev,integration]" -e "libs/db[dev]"; \
	pytest tests/integration/services -v -m "not slow" --timeout=60

test-security:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev,integration]" -e "libs/db[dev]"; \
	pytest tests/integration/security -v --timeout=60

test-integration-docker:
	docker compose -f docker-compose.test.yml up -d
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/common[dev,integration]" -e "libs/db[dev]"; \
	DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/llamatrade_test \
	REDIS_URL=redis://localhost:6380 \
	pytest tests/integration -v --timeout=120 || true
	docker compose -f docker-compose.test.yml down

# Run tests for specific services
test-auth:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/auth && pytest tests -v

test-strategy:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/strategy && pytest tests -v

test-billing:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/billing && pytest tests -v

test-backtest:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/backtest && pytest tests -v

test-trading:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/trading && pytest tests -v

test-market-data:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/market-data && pytest tests -v

test-portfolio:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/portfolio && pytest tests -v

test-frontend:
	cd apps/web && npm test -- --run --passWithNoTests

# ===================
# Linting & Type Checking
# ===================
lint:
	@echo "=== Python: Ruff (lint) ==="
	ruff check --config pyproject.toml --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" services/ libs/
	@echo "=== Python: Ruff (format) ==="
	ruff format --config pyproject.toml --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" --check services/ libs/
	@echo "=== Python: Pyright (type check) ==="
	npx pyright services/ libs/
	@echo "=== Frontend: ESLint ==="
	cd apps/web && npm run lint
	@echo "=== Frontend: TypeScript ==="
	cd apps/web && npx tsc --noEmit

lint-fix:
	ruff check --config pyproject.toml --fix --unsafe-fixes --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" services/ libs/
	ruff format --config pyproject.toml --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" services/ libs/

lint-python:
	ruff check --config pyproject.toml --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" services/ libs/
	ruff format --config pyproject.toml --exclude "libs/proto/llamatrade_proto/generated/*" --exclude "libs/proto/connectrpc/*" --check services/ libs/
	npx pyright services/ libs/

lint-frontend:
	cd apps/web && npm run lint
	cd apps/web && npx tsc --noEmit

typecheck:
	@echo "=== Python: Pyright ==="
	npx pyright services/ libs/
	@echo "=== Frontend: TypeScript ==="
	cd apps/web && npx tsc --noEmit

# ===================
# Pre-commit Hooks
# ===================
pre-commit-install:
	pip install pre-commit
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

# ===================
# Proto Generation
# ===================
proto:
	@echo "=== Generating proto files (all targets) ==="
	cd libs/proto && buf generate
	@echo "=== Fixing Python imports (bare -> relative) ==="
	@cd libs/proto/llamatrade_proto/generated && \
		for f in *.py; do \
			sed -i '' 's/^import \([a-z_]*_pb2\) as /from . import \1 as /g' "$$f"; \
		done
	@echo '"""Generated protobuf and gRPC code. Do not edit - regenerate with make proto."""' > libs/proto/llamatrade_proto/generated/__init__.py
	@echo "Generated:"
	@echo "  - Python:     libs/proto/llamatrade_proto/generated/"
	@echo "  - TypeScript: apps/web/src/generated/proto/"

proto-python:
	@echo "=== Generating Python proto files ==="
	cd libs/proto && buf generate
	@echo "=== Fixing Python imports (bare -> relative) ==="
	@cd libs/proto/llamatrade_proto/generated && \
		for f in *.py; do \
			sed -i '' 's/^import \([a-z_]*_pb2\) as /from . import \1 as /g' "$$f"; \
		done
	@echo "Generated: libs/proto/llamatrade_proto/generated/"

proto-web:
	@echo "=== Generating TypeScript proto files ==="
	cd libs/proto && buf generate --template buf.gen.web.yaml
	@echo "Generated: apps/web/src/generated/proto/"

proto-lint:
	cd libs/proto && buf lint

proto-breaking:
	cd libs/proto && buf breaking --against '.git#branch=main'

# Database
migrate:
	@echo "Running migrations..."
	@$(LOAD_ENV) && cd libs/db/llamatrade_db/alembic && ../../../../.venv/bin/alembic upgrade head

migrate-status:
	@$(LOAD_ENV) && cd libs/db/llamatrade_db/alembic && ../../../../.venv/bin/alembic current

migrate-history:
	@$(LOAD_ENV) && cd libs/db/llamatrade_db/alembic && ../../../../.venv/bin/alembic history

migrate-new:
	@read -p "Migration name: " name && \
	$(LOAD_ENV) && cd libs/db/llamatrade_db/alembic && ../../../../.venv/bin/alembic revision -m "$$name"

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
	@echo "  make dev-local SERVICE=<name>  - Run ONE service locally"
	@echo ""
	@echo "CI (run locally before pushing):"
	@echo "  make ci             - Run full CI locally (lint + tests)"
	@echo "  make ci-backend     - Run backend CI only"
	@echo "  make ci-lint        - Run linting only"
	@echo "  make ci-test        - Run tests only"
	@echo ""
	@echo "Testing:"
	@echo "  make test                  - Run ALL tests (unit + integration)"
	@echo "  make test-unit             - Run unit tests for all services"
	@echo "  make test-unit-quick       - Run unit tests (quiet mode)"
	@echo "  make test-integration      - Run integration tests (requires Docker)"
	@echo "  make test-integration-quick - Run quick integration tests"
	@echo "  make test-security         - Run tenant isolation tests"
	@echo "  make test-<service>        - Run tests for specific service"
	@echo "                               (auth, strategy, billing, backtest,"
	@echo "                                trading, market-data, portfolio)"
	@echo "  make test-frontend         - Run frontend tests"
	@echo ""
	@echo "Linting & Quality:"
	@echo "  make lint           - Run all linters + type checks"
	@echo "  make lint-fix       - Auto-fix Python lint issues"
	@echo "  make typecheck      - Run type checkers only"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo "  make pre-commit-run - Run pre-commit on all files"
	@echo ""
	@echo "Proto Generation:"
	@echo "  make proto          - Generate Python + TypeScript from protos"
	@echo "  make proto-lint     - Lint proto files"
	@echo "  make proto-breaking - Check for breaking changes"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-staging - Deploy to staging"
	@echo "  make deploy-prod    - Deploy to production"
	@echo ""
	@echo "Default Ports:"
	@echo "  Frontend:    http://localhost:8800"
	@echo "  PostgreSQL:  localhost:5432"
	@echo "  Redis:       localhost:6379"
	@echo ""
	@echo "Service Ports (HTTP + Connect Protocol):"
	@echo "  auth:8810  strategy:8820  backtest:8830  market-data:8840"
	@echo "  trading:8850  portfolio:8860  notification:8870  billing:8880"
