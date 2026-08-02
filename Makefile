.PHONY: dev dev-up dev-down dev-infra dev-setup build test test-e2e lint clean ci migrate migrate-status migrate-history seed-demo emails emails-preview

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
	for svc in auth strategy billing backtest trading market-data portfolio agent notification; do \
		echo ""; \
		echo "=== Testing $$svc ==="; \
		(cd services/$$svc && pytest tests/ -v); \
	done

test-unit-quick:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	echo "=== Running unit tests (quick mode) ==="; \
	for svc in auth strategy billing backtest trading market-data portfolio agent notification; do \
		echo "=== $$svc ==="; \
		(cd services/$$svc && pytest tests/ -q); \
	done

# Run integration tests (per-service testcontainers suites; requires Docker)
test-integration:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "services/portfolio[dev,integration]" -e "services/market-data[dev,integration]" -e "libs/events[dev,integration]"; \
	(cd services/portfolio && pytest tests/integration -v --timeout=180) && \
	(cd services/market-data && pytest tests/integration -v --timeout=180) && \
	(cd libs/events && pytest tests/test_integration_kafka.py -v --timeout=180)

test-security:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "services/portfolio[dev,integration]" -e "services/strategy[dev,integration]"; \
	(cd services/portfolio && pytest tests/integration/test_rls.py tests/test_servicer_auth.py -v --timeout=120) && \
	(cd services/strategy && pytest tests/test_tenant_isolation_db.py -v --timeout=120)

test-integration-docker:
	docker compose -f docker-compose.test.yml up -d
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q -e "libs/events[dev,integration]"; \
	(cd libs/events && KAFKA_BOOTSTRAP_SERVERS=localhost:9093 pytest tests/test_integration_kafka.py -v --timeout=180)
	docker compose -f docker-compose.test.yml down

# Zero-mock end-to-end suite: drives the LIVE service mesh over Connect exactly as
# the UI does. Requires the stack up + seeded: `make dev-up && make seed-demo`.
# The suite self-skips if the mesh is unreachable. Set E2E_LIVE_LLM=1 to also run
# the gated agent-chat tests (real LLM); pass --live-alpaca legs are opt-in.
test-e2e:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	pip install -q pytest pytest-asyncio -e libs/proto -e libs/events; \
	echo "=== E2E suite (requires: make dev-up + make seed-demo) ==="; \
	pytest tests/e2e -v --no-cov

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

test-agent:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/agent && pytest tests -v

test-notification:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd services/notification && pytest tests -v

# Proto lib tests: timestamp converters + the servicer-binding conformance guard
# (needs every service importable; `make dev-setup` installs them into .venv).
test-proto:
	@. .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && . .venv/bin/activate); \
	cd libs/proto && pytest tests -v

test-frontend:
	cd apps/web && npm test -- --run --passWithNoTests

# ===================
# Linting & Type Checking
# ===================
lint:
	@echo "=== Checking for suppression comments ==="
	@./scripts/check-no-suppressions.sh
	@echo "=== Python: Ruff (lint) ==="
	ruff check --config pyproject.toml --ignore-noqa services/ libs/ tests/
	@echo "=== Python: Ruff (format) ==="
	ruff format --config pyproject.toml --check services/ libs/ tests/
	@echo "=== Python: Pyright (type check) ==="
	npx pyright services/ libs/
	@echo "=== Frontend: ESLint ==="
	cd apps/web && npm run lint
	@echo "=== Frontend: TypeScript ==="
	cd apps/web && npx tsc --noEmit

lint-fix:
	ruff check --config pyproject.toml --fix --unsafe-fixes services/ libs/ tests/
	ruff format --config pyproject.toml services/ libs/ tests/

lint-python:
	@./scripts/check-no-suppressions.sh
	ruff check --config pyproject.toml --ignore-noqa services/ libs/ tests/
	ruff format --config pyproject.toml --check services/ libs/ tests/
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
			perl -pi -e 's/^import ([a-z_]*_pb2) as /from . import $$1 as /g' "$$f"; \
		done
	@echo '"""Generated protobuf and gRPC code. Do not edit - regenerate with make proto."""' > libs/proto/llamatrade_proto/generated/__init__.py
	@echo "Generated:"
	@echo "  - Python:     libs/proto/llamatrade_proto/generated/"
	@echo "  - TypeScript: apps/core/src/proto/ (@llamatrade/core — shared by web + mobile)"

proto-python:
	@echo "=== Generating Python proto files ==="
	cd libs/proto && buf generate
	@echo "=== Fixing Python imports (bare -> relative) ==="
	@cd libs/proto/llamatrade_proto/generated && \
		for f in *.py; do \
			perl -pi -e 's/^import ([a-z_]*_pb2) as /from . import $$1 as /g' "$$f"; \
		done
	@echo "Generated: libs/proto/llamatrade_proto/generated/"

proto-ts:
	@echo "=== Generating TypeScript proto files (shared @llamatrade/core) ==="
	cd libs/proto && buf generate --template buf.gen.core.yaml
	@echo "Generated: apps/core/src/proto/ (imported by web + mobile)"

proto-lint:
	cd libs/proto && buf lint

proto-breaking:
	cd libs/proto && buf breaking --against '../../.git#branch=main,subdir=libs/proto'

# ===================
# Transactional Emails
# ===================
# Regenerate the committed HTML shells from the React Email templates. The
# emails package is standalone (its own node_modules + lockfile, NOT in the
# root workspace), so install into it directly before rendering.
emails:
	npm install --prefix services/notification/emails && npm run build --prefix services/notification/emails

# Open the rendered-shell gallery (writes tools/email_preview.html, gitignored).
emails-preview:
	.venv/bin/python services/notification/tools/preview_emails.py --open

# ===================
# Secrets / Keys
# ===================
# Generate the RS256 user-token signing keypair the auth service requires in
# staging/production (without it auth cannot start). Writes PEMs to a gitignored
# dir for local dev and prints how to export them. Loading the pair into Secret
# Manager and the auth-jwt-keys Secret is a MANUAL pre-deploy step, not run here;
# see .docs/runbooks/jwt-key-provisioning.md.
JWT_KEY_DIR ?= infrastructure/docker/secrets
gen-jwt-keys:
	@mkdir -p $(JWT_KEY_DIR)
	@openssl genrsa -out $(JWT_KEY_DIR)/jwt-private.pem 2048
	@openssl rsa -in $(JWT_KEY_DIR)/jwt-private.pem -pubout -out $(JWT_KEY_DIR)/jwt-public.pem
	@chmod 600 $(JWT_KEY_DIR)/jwt-private.pem
	@echo ""
	@echo "Wrote $(JWT_KEY_DIR)/jwt-private.pem and jwt-public.pem (gitignored)."
	@echo ""
	@echo "Local dev: export both before 'make dev' to exercise the RS256 path"
	@echo "(omit to keep the HS256-over-JWT_SECRET fallback):"
	@echo '  export AUTH_JWT_PRIVATE_KEY="$$(cat $(JWT_KEY_DIR)/jwt-private.pem)"'
	@echo '  export AUTH_JWT_PUBLIC_KEY="$$(cat $(JWT_KEY_DIR)/jwt-public.pem)"'
	@echo ""
	@echo "Staging/production: load into Secret Manager and the auth-jwt-keys"
	@echo "Secret as a hard pre-deploy step -> .docs/runbooks/jwt-key-provisioning.md"

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

# Seed a polished, internally-consistent demo tenant (demo@llamatrade.ai / demo1234).
# Runs inside the portfolio container to reuse the real ledger kernel. Idempotent:
# re-running purges and recreates the demo tenant only. See scripts/seed_demo_account.py
# and .docs/planning/demo-seed-blueprint.md.
seed-demo:
	@echo "Seeding demo account (demo@llamatrade.ai / demo1234)..."
	docker cp scripts/demo_seed_data llamatrade-portfolio:/app/demo_seed_data
	docker cp scripts/seed_demo_account.py llamatrade-portfolio:/app/seed_demo_account.py
	docker exec -w /app llamatrade-portfolio python seed_demo_account.py

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
	@echo "  make test-security         - Run tenant-isolation and RLS tests"
	@echo "  make test-security         - Run tenant isolation tests"
	@echo "  make test-<service>        - Run tests for specific service"
	@echo "                               (auth, strategy, billing, backtest,"
	@echo "                                trading, market-data, portfolio, agent)"
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
	@echo "Transactional Emails:"
	@echo "  make emails         - Regenerate committed HTML shells from templates"
	@echo "  make emails-preview - Open the rendered-shell gallery"
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
	@echo "  agent:8890"
