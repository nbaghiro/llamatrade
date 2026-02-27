# Testing Guide

This guide covers testing practices, patterns, and conventions for LlamaTrade.

---

## Philosophy

From CLAUDE.md:

> **Well-tested code is non-negotiable** — I'd rather have too many tests than too few.

Testing priorities:
1. Business logic in service layer
2. Edge cases and error handling
3. Tenant isolation (no cross-tenant data leakage)
4. Database operations and constraints
5. API validation and error responses

---

## Test Structure

### Directory Layout

```
services/auth/
├── src/
│   ├── main.py
│   ├── services/
│   │   └── auth_service.py
│   └── routers/
│       └── auth.py
└── tests/
    ├── conftest.py          # Shared fixtures
    ├── test_auth_service.py # Service layer tests
    ├── test_auth_router.py  # API endpoint tests
    └── test_integration.py  # Cross-component tests
```

### File Naming

- Test files: `test_*.py`
- Test functions: `test_*` or `async def test_*`
- Group by component: `test_<service>.py`, `test_<router>.py`

---

## Running Tests

### All Tests

```bash
make test
```

### Single Service

```bash
make test-auth
make test-strategy
make test-backtest
```

### With Coverage

```bash
cd services/auth
pytest --cov=src --cov-report=term-missing

# HTML report
pytest --cov=src --cov-report=html
# Open htmlcov/index.html
```

### Specific Tests

```bash
# Single file
pytest tests/test_auth_service.py

# Single test
pytest tests/test_auth_service.py::test_create_user

# By keyword
pytest -k "user"

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

---

## Test Patterns

### Async Tests

All tests must be async (FastAPI is async-first):

```python
import pytest

@pytest.mark.asyncio
async def test_something():
    result = await some_async_function()
    assert result is not None
```

Or use `async def` directly (pytest-asyncio auto-marks):

```python
async def test_something():
    result = await some_async_function()
    assert result is not None
```

### API Integration Tests

Use `httpx.AsyncClient` with `ASGITransport`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### Mocking Dependencies

Use FastAPI's dependency override:

```python
from src.main import app
from src.dependencies import get_auth_service

class MockAuthService:
    async def get_user(self, user_id):
        return {"id": user_id, "email": "test@example.com"}

@pytest.fixture
def mock_auth_service():
    mock = MockAuthService()
    app.dependency_overrides[get_auth_service] = lambda: mock
    yield mock
    app.dependency_overrides.clear()

async def test_with_mock(client, mock_auth_service):
    response = await client.get("/users/123")
    assert response.status_code == 200
```

### Database Fixtures

For tests requiring a real database:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from llamatrade_db.base import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/llamatrade_test"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

### Tenant Isolation Tests

Always test that tenants cannot access each other's data:

```python
async def test_tenant_isolation(client, auth_headers_tenant_a, auth_headers_tenant_b):
    # Create strategy as tenant A
    response = await client.post(
        "/strategies",
        headers=auth_headers_tenant_a,
        json={"name": "My Strategy"}
    )
    strategy_id = response.json()["id"]

    # Tenant A can access
    response = await client.get(
        f"/strategies/{strategy_id}",
        headers=auth_headers_tenant_a
    )
    assert response.status_code == 200

    # Tenant B cannot access
    response = await client.get(
        f"/strategies/{strategy_id}",
        headers=auth_headers_tenant_b
    )
    assert response.status_code == 404  # Not 403 - don't leak existence
```

---

## What to Test

### Happy Path

Test normal operations work correctly:

```python
async def test_create_user_success(client, auth_headers):
    response = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": "new@example.com",
            "password": "SecurePass123!"
        }
    )
    assert response.status_code == 201
    assert response.json()["email"] == "new@example.com"
    assert "id" in response.json()
```

### Validation Errors

Test that invalid input returns 422:

```python
async def test_create_user_invalid_email(client, auth_headers):
    response = await client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": "not-an-email",
            "password": "SecurePass123!"
        }
    )
    assert response.status_code == 422
    assert "email" in response.json()["detail"][0]["loc"]
```

### Authentication Errors

Test missing/invalid auth:

```python
async def test_protected_endpoint_no_auth(client):
    response = await client.get("/strategies")
    assert response.status_code == 401

async def test_protected_endpoint_invalid_token(client):
    response = await client.get(
        "/strategies",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
```

### Not Found Errors

Test 404 for missing resources:

```python
async def test_get_strategy_not_found(client, auth_headers):
    response = await client.get(
        "/strategies/00000000-0000-0000-0000-000000000000",
        headers=auth_headers
    )
    assert response.status_code == 404
```

### Edge Cases

Test boundary conditions:

```python
async def test_pagination_first_page(client, auth_headers):
    response = await client.get(
        "/strategies?page=1&page_size=10",
        headers=auth_headers
    )
    assert response.status_code == 200

async def test_pagination_beyond_last_page(client, auth_headers):
    response = await client.get(
        "/strategies?page=999&page_size=10",
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

async def test_empty_string_name(client, auth_headers):
    response = await client.post(
        "/strategies",
        headers=auth_headers,
        json={"name": ""}
    )
    assert response.status_code == 422
```

### Service Layer Tests

Test business logic directly:

```python
async def test_calculate_sharpe_ratio():
    from src.services.metrics import calculate_sharpe_ratio

    returns = [0.01, -0.02, 0.03, 0.01, -0.01]
    sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)

    assert sharpe is not None
    assert isinstance(sharpe, float)

async def test_calculate_sharpe_ratio_insufficient_data():
    from src.services.metrics import calculate_sharpe_ratio

    returns = [0.01]  # Only one data point
    sharpe = calculate_sharpe_ratio(returns)

    assert sharpe is None  # Not enough data
```

---

## Coverage Requirements

**Target: 80% coverage** for real implementations.

Coverage is measured on `src/` directories, excluding:
- Tests (`tests/`)
- Migrations (`alembic/`)
- Generated code (`generated/`)

### Checking Coverage

```bash
cd services/auth
pytest --cov=src --cov-report=term-missing
```

Output shows uncovered lines:

```
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
src/main.py                20      2    90%   45-46
src/services/auth.py       80     10    88%   23-25, 67-72
-----------------------------------------------------
TOTAL                     100     12    88%
```

### Focus Areas

Prioritize testing:
1. **market-data** (95% real) — Full Alpaca integration
2. **auth** (60% real) — JWT, bcrypt, user creation
3. **backtest** engine (30% real) — Metrics calculations
4. **strategy** indicators (20% real) — NumPy calculations

Many services are currently stubbed. Focus tests on actual business logic, not stubs.

---

## Fixtures Reference

### Common Fixtures (conftest.py)

```python
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.fixture
async def client():
    """HTTP client for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "00000000-0000-0000-0000-000000000001"

@pytest.fixture
def user_id():
    """Test user ID."""
    return "00000000-0000-0000-0000-000000000002"

@pytest.fixture
def auth_headers(tenant_id, user_id):
    """Auth headers with valid JWT."""
    from src.auth import create_access_token

    token = create_access_token(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=["admin"]
    )
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_strategy():
    """Sample strategy config."""
    return {
        "name": "Test Strategy",
        "description": "A test strategy",
        "strategy_type": "mean_reversion",
        "config": {
            "symbols": ["AAPL"],
            "entry": {"indicator": "rsi", "operator": "<", "value": 30},
            "exit": {"indicator": "rsi", "operator": ">", "value": 70}
        }
    }
```

---

## CI Integration

Tests run automatically on:
- Every push
- Every pull request
- Pre-commit hook (optional)

### Local CI Check

Before pushing, run the full CI suite:

```bash
./scripts/ci-local.sh
```

This runs:
1. Linting (ruff, mypy, eslint)
2. Type checking
3. Unit tests
4. Integration tests
5. Coverage check

---

## Troubleshooting

### Tests Hang

Usually a database connection issue:

```bash
# Check if test database is running
docker ps | grep postgres

# Reset test database
dropdb llamatrade_test
createdb llamatrade_test
```

### Import Errors

Ensure packages are installed in editable mode:

```bash
cd libs/common && pip install -e .
cd libs/db && pip install -e .
cd libs/grpc && pip install -e .
```

### Async Warnings

If you see "RuntimeWarning: coroutine was never awaited":

```python
# Wrong
def test_something():
    result = async_function()  # Missing await

# Correct
async def test_something():
    result = await async_function()
```

### Flaky Tests

Tests that sometimes pass/fail usually have:
- Time-dependent logic (use `freezegun`)
- Database state leakage (use transactions/rollback)
- External service dependencies (use mocks)
