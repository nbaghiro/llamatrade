# CLAUDE.md — LlamaTrade

## Project Overview

LlamaTrade is an open-source algorithmic trading platform built as a multi-tenant SaaS application. It enables users to create strategies, backtest against historical data, and execute live trades via Alpaca Markets API.

**Tech Stack:**
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (async), PostgreSQL, Redis
- **Frontend**: React 18, TypeScript 5.3+, Vite, Tailwind CSS, Zustand
- **Infrastructure**: Docker, Kubernetes (GKE), Terraform (GCP)

---

## Engineering Preferences

Use these to guide all recommendations:

- **DRY is important** — flag repetition aggressively
- **Well-tested code is non-negotiable** — I'd rather have too many tests than too few
- **Code should be "engineered enough"** — not under-engineered (fragile, hacky) and not over-engineered (premature abstraction, unnecessary complexity)
- **Err on the side of handling more edge cases**, not fewer; thoughtfulness > speed
- **Bias toward explicit over clever** — readable code beats clever code
- **Async-first** — all I/O operations must use async/await
- **Strict typing enforced** — no `Any` in Python, no `any`/`never` in TypeScript

---

## Code Review Framework

### 1. Architecture Review

Evaluate:
- Overall system design and component boundaries
- Service-to-service communication patterns
- Multi-tenancy enforcement (tenant_id propagation)
- Data flow patterns and potential bottlenecks
- Single points of failure and error propagation
- Security architecture (auth, tenant isolation, API boundaries)

### 2. Code Quality Review

Evaluate:
- Code organization and module structure
- DRY violations — be aggressive here
- Error handling patterns and missing edge cases (call these out explicitly)
- Technical debt hotspots
- Areas that are over-engineered or under-engineered relative to my preferences
- Pydantic validation completeness

### 3. Test Review

Evaluate:
- **Test coverage percentage** — track coverage, target 80% for real implementations (not stubs)
- Test coverage gaps (unit, integration, e2e)
- Test quality and assertion strength
- Missing edge case coverage — be thorough
- Untested failure modes and error paths
- Async test patterns (proper pytest-asyncio usage)
- New code without corresponding tests — call this out explicitly

### 4. Performance Review

Evaluate:
- N+1 queries and database access patterns
- Memory-usage concerns
- Caching opportunities (Redis utilization)
- Slow or high-complexity code paths
- Async bottlenecks (blocking calls in async context)

---

## For Each Issue You Find

For every specific issue (bug, smell, design concern, or risk):

1. Describe the problem concretely, with file and line references
2. Present 2-3 options, including "do nothing" where that's reasonable
3. For each option, specify: implementation effort, risk, impact on other code, and maintenance burden
4. Give me your recommended option and why, mapped to my preferences above
5. Then explicitly ask whether I agree or want to choose a different direction before proceeding

---

## Workflow and Interaction

- Do not assume my priorities on timeline or scale
- After each section, pause and ask for my feedback before moving on
- When making changes, explain the "why" not just the "what"

---

## Before Starting Any Significant Work

Ask if I want one of two options:

**1/ BIG CHANGE**: Work through this interactively, one section at a time (Architecture → Code Quality → Tests → Performance) with at most 4 top issues in each section

**2/ SMALL CHANGE**: Work through interactively ONE question per review section

For each stage of review: output the explanation and pros/cons of each stage's questions AND your opinionated recommendation and why, then use AskUserQuestion. NUMBER issues and give LETTERS for options. Make sure each option clearly labels the issue NUMBER and option LETTER so I don't get confused. Make the recommended option always the 1st option.

---

## Project-Specific Conventions

### Backend (Python/FastAPI)

**File Structure:**
```
services/[name]/
├── src/
│   ├── main.py          # FastAPI app setup, health check
│   ├── models.py        # Pydantic schemas
│   ├── routers/         # APIRouter instances
│   └── services/        # Business logic classes
└── tests/
    └── test_*.py        # pytest test files
```

**Required Patterns:**
- Every service MUST have a `/health` endpoint returning `{"status": "healthy", "service": "name", "version": "..."}`
- All route handlers MUST be async
- Use `Depends()` for dependency injection
- Pydantic schemas MUST use suffixes: `Create`, `Response`, `Update`, `Request`
- Tenant context MUST be extracted via `require_auth` middleware and passed through all layers
- Use `HTTPException` for client errors, let unexpected errors propagate

**Naming:**
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: prefix with `_`

**Tests:**
- All tests must be async: `@pytest.mark.asyncio` or `async def test_*`
- Use `httpx.AsyncClient` with `ASGITransport` for integration tests
- Mock services via `app.dependency_overrides[get_service]`
- Test files: `test_*.py` in `tests/` directory

**Test Coverage Requirements:**
- **Target 80% coverage** for real implementations (currently tracking only, not enforced)
- Run coverage locally: `pytest --cov=src --cov-report=term-missing`
- Generate HTML report: `pytest --cov=src --cov-report=html` (output in `htmlcov/`)
- When adding **real implementations** (not stubs), add corresponding tests
- Coverage is measured on `src/` directories, excluding tests and migrations
- Note: Many services are currently stubbed — focus tests on actual business logic

**What to Test:**
- Happy path for all endpoints
- Error cases and validation failures
- Edge cases (empty inputs, boundary values, invalid data)
- Authentication and authorization (valid/invalid/expired tokens)
- Tenant isolation (ensure no cross-tenant data leakage)
- Service layer business logic
- Database operations (CRUD, constraints, relationships)

**Test Structure:**
```python
# tests/test_[feature].py
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

async def test_feature_happy_path(client):
    """Test description."""
    response = await client.post("/endpoint", json={...})
    assert response.status_code == 200
    assert response.json()["field"] == expected

async def test_feature_validation_error(client):
    """Test invalid input returns 422."""
    response = await client.post("/endpoint", json={"invalid": "data"})
    assert response.status_code == 422

async def test_feature_unauthorized(client):
    """Test missing auth returns 401."""
    response = await client.get("/protected")
    assert response.status_code == 401
```

### Frontend (React/TypeScript)

**File Structure:**
```
apps/web/src/
├── components/
│   ├── common/           # Shared UI (Layout, Logo, Select, ThemeToggle)
│   ├── billing/          # Billing-specific components
│   ├── strategies/       # Strategy list components
│   └── strategy-builder/ # Visual strategy builder (blocks/, panels/)
├── pages/
│   ├── auth/             # LoginPage, RegisterPage
│   ├── billing/          # BillingPage, SubscribePage, PaymentMethodsPage
│   ├── strategies/       # StrategiesPage, StrategyEditorPage
│   ├── portfolio/        # PortfolioPage
│   ├── trading/          # TradingPage, BacktestPage
│   ├── settings/         # SettingsPage
│   └── dashboard/        # DashboardPage
├── services/             # gRPC client, API services
├── store/                # Zustand stores
├── types/                # TypeScript type definitions
├── data/                 # Demo/mock data
└── generated/            # Proto-generated (gitignored, run `make proto`)
```

**Required Patterns:**
- Functional components only (no class components)
- Use Zustand for state management with persist middleware
- API calls via axios instance in `services/api.ts`
- TypeScript strict mode — no `any` without justification
- Tailwind CSS for styling (no CSS files in components)

**Naming:**
- Components: `PascalCase` files matching component name
- Hooks: `use*` prefix
- Types/interfaces: `PascalCase`

### Shared Libraries

- `libs/common`: Middleware, shared models, utilities — import as `llamatrade_common`
- `libs/db`: SQLAlchemy models, database config — import as `llamatrade_db`
- `libs/proto`: Protobuf definitions (source of truth for gRPC APIs)
- `libs/grpc`: Generated Python proto code (gitignored, run `make proto`)
- Changes to libs affect ALL services — test thoroughly

---

## Commands

```bash
# Development
make dev                    # Docker Compose (all services)
make dev-infra              # Start only Postgres + Redis
make dev-local              # Run all services locally

# Proto Generation (required after clone or proto changes)
make proto                  # Generate Python + TypeScript from protos
make proto-lint             # Lint proto files
make proto-breaking         # Check for breaking changes vs main

# Testing
make test                   # Full CI test suite
make test-auth              # Single service tests
make lint                   # All linting

# Test Coverage
cd services/auth && pytest --cov=src --cov-report=term-missing    # Coverage report
cd services/auth && pytest --cov=src --cov-report=html            # HTML report → htmlcov/

# Formatting
ruff check --fix services/ libs/
npm run lint:fix            # Frontend
```

**Note:** Proto-generated files are gitignored. After cloning or pulling proto changes, run `make proto` to regenerate:
- Python: `libs/grpc/llamatrade/`
- TypeScript: `apps/web/src/generated/proto/`

---

## Linting and Formatting

**Python (Ruff):**
- Line length: 100 characters
- Rules: E, F, I, N, W, UP
- Run: `ruff check --fix` and `ruff format`

**TypeScript (ESLint + Prettier):**
- Strict mode enabled
- Run: `npm run lint` in apps/web

**Pre-commit hooks are enforced** — all code must pass ruff, mypy, ESLint, and tsc before commit.

---

## Commit Guidelines

- Use concise, single-line commit messages
- **Do NOT include Co-Authored-By lines** — no Claude co-author attribution
- **Do NOT commit immediately after making changes** — wait for explicit commit instructions
- Multiple unrelated changes may be in progress on the same branch; keep them separate
- Run `./scripts/ci-local.sh` before committing to verify all checks pass

---

## Multi-Tenancy

All operations MUST be tenant-scoped:

1. JWT token contains `tenant_id` in payload
2. Extract via `TenantContext = Depends(require_auth)`
3. Pass `ctx.tenant_id` to all service methods
4. Filter ALL database queries by `tenant_id`
5. Service-to-service calls: propagate via `X-Tenant-ID` header

Never allow cross-tenant data access. When in doubt, add tenant filtering.

---

## Environment Variables

- Configuration via environment variables only (no hardcoded values)
- See `.env.example` for all required variables
- Ports: services 88xx (auth 8810, strategy 8820, etc.), web 8800, billing 8880
- Secrets: `JWT_SECRET`, `ENCRYPTION_KEY`, API keys

---

## Current Project Stage

**Early Development** — Most services have barebones structure:
- Health endpoints work
- Routers exist with full endpoint signatures
- Service methods are mostly stubbed (return `None`, empty lists, or mock data)
- Database queries not yet implemented (except auth user creation)
- Focus on building real implementations before enforcing strict coverage

**Services with real logic to prioritize testing:**
- `market-data` (95% real) — Full Alpaca API integration
- `auth` (60% real) — JWT tokens, bcrypt, user creation
- `backtest` engine (30% real) — Metrics calculations exist
- `strategy` indicators (20% real) — NumPy calculations exist

---

## Things to Avoid

- Blocking calls in async context (use `asyncio.to_thread` if unavoidable)
- Raw SQL queries (use SQLAlchemy ORM)
- Hardcoded configuration values
- `print()` statements (use logging)
- `Any` types in Python — use proper types or generics instead
- `any` or `never` types in TypeScript — use proper types or `unknown` if truly needed
- Class-based React components
- CSS files for component styling (use Tailwind)
- Direct database access outside service layer
- **Adding real implementations without tests** — new business logic needs coverage
