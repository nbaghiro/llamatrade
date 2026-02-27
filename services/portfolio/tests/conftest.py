"""Shared test fixtures for portfolio service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_TRANSACTION_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def tenant_id() -> UUID:
    """Return test tenant ID."""
    return TEST_TENANT_ID


@pytest.fixture
def user_id() -> UUID:
    """Return test user ID."""
    return TEST_USER_ID


@pytest.fixture
def transaction_id() -> UUID:
    """Return test transaction ID."""
    return TEST_TRANSACTION_ID


@pytest.fixture
def mock_tenant_context() -> TenantContext:
    """Create a mock tenant context for auth."""
    return TenantContext(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="test@example.com",
        roles=["user"],
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_market_data_client() -> AsyncMock:
    """Create a mock market data client."""
    client = AsyncMock()
    client.get_latest_price = AsyncMock(return_value=150.0)
    client.get_prices = AsyncMock(return_value={"AAPL": 150.0, "GOOGL": 140.0})
    client.close = AsyncMock()
    return client


@pytest.fixture
async def authenticated_client(mock_tenant_context: TenantContext) -> AsyncClient:
    """Create async test client with authentication context."""
    # Override the require_auth dependency to return our mock context
    app.dependency_overrides[require_auth] = lambda: mock_tenant_context

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clear dependency overrides after test
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
async def client() -> AsyncClient:
    """Create async test client without authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_positions() -> list[dict]:
    """Sample positions data for testing."""
    return [
        {
            "symbol": "AAPL",
            "qty": 100,
            "side": "long",
            "avg_entry_price": 145.0,
            "current_price": 150.0,
            "cost_basis": 14500.0,
        },
        {
            "symbol": "GOOGL",
            "qty": 50,
            "side": "long",
            "avg_entry_price": 135.0,
            "current_price": 140.0,
            "cost_basis": 6750.0,
        },
    ]


@pytest.fixture
def sample_portfolio_summary(sample_positions: list[dict]) -> MagicMock:
    """Create a mock portfolio summary model."""
    summary = MagicMock()
    summary.tenant_id = TEST_TENANT_ID
    summary.equity = Decimal("100000")
    summary.cash = Decimal("50000")
    summary.buying_power = Decimal("100000")
    summary.portfolio_value = Decimal("50000")
    summary.daily_pl = Decimal("500")
    summary.daily_pl_percent = Decimal("0.005")
    summary.total_pl = Decimal("5000")
    summary.total_pl_percent = Decimal("0.05")
    summary.positions = sample_positions
    summary.position_count = 2
    summary.updated_at = datetime.now(UTC)
    summary.last_synced_at = datetime.now(UTC)
    return summary


@pytest.fixture
def sample_portfolio_history() -> list[MagicMock]:
    """Create sample portfolio history records."""
    history = []
    base_equity = 100000
    for i in range(30):
        record = MagicMock()
        record.tenant_id = TEST_TENANT_ID
        record.snapshot_date = date(2024, 1, 1) + (date(2024, 1, 2) - date(2024, 1, 1)) * i
        # Simulate some growth
        equity = base_equity * (1 + 0.001 * i)
        record.equity = Decimal(str(equity))
        record.cash = Decimal(str(equity * 0.5))
        record.portfolio_value = Decimal(str(equity * 0.5))
        record.daily_return = Decimal("0.001") if i > 0 else None
        record.cumulative_return = Decimal(str(0.001 * i)) if i > 0 else None
        history.append(record)
    return history


@pytest.fixture
def sample_transaction() -> MagicMock:
    """Create a sample transaction model."""
    tx = MagicMock()
    tx.id = TEST_TRANSACTION_ID
    tx.tenant_id = TEST_TENANT_ID
    tx.transaction_type = "buy"
    tx.symbol = "AAPL"
    tx.side = "buy"
    tx.qty = Decimal("100")
    tx.price = Decimal("150.00")
    tx.amount = Decimal("15000.00")
    tx.fees = Decimal("0.00")
    tx.net_amount = Decimal("15000.00")
    tx.description = "Buy 100 AAPL"
    tx.transaction_date = datetime.now(UTC)
    return tx
