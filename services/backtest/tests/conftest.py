"""Shared test fixtures for backtest service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_BACKTEST_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def tenant_id():
    return TEST_TENANT_ID


@pytest.fixture
def user_id():
    return TEST_USER_ID


@pytest.fixture
def strategy_id():
    return TEST_STRATEGY_ID


@pytest.fixture
def backtest_id():
    return TEST_BACKTEST_ID


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_market_data_client():
    """Create a mock market data client."""
    client = AsyncMock()
    client.fetch_bars = AsyncMock(return_value={})
    client.check_health = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_backtest_service():
    """Create a mock backtest service."""
    return AsyncMock()


@pytest.fixture
def mock_tenant_context():
    """Create a mock tenant context for auth."""
    return MagicMock(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="test@example.com",
        roles=["user"],
    )


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_backtest_response(backtest_id, tenant_id, strategy_id):
    """Sample backtest response for testing."""
    from llamatrade_proto.generated.backtest_pb2 import BACKTEST_STATUS_PENDING

    from src.models import BacktestResponse

    return BacktestResponse(
        id=backtest_id,
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        strategy_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 12, 31, tzinfo=UTC),
        initial_capital=100000.0,
        status=BACKTEST_STATUS_PENDING,
        progress=0.0,
        error_message=None,
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
    )


@pytest.fixture
def sample_bar_data():
    """Sample bar data for testing."""
    return {
        "timestamp": datetime(2024, 1, 2, 9, 30, tzinfo=UTC),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 10000,
    }


@pytest.fixture
def sample_bars():
    """Sample multi-day bars for backtesting."""
    from datetime import timedelta

    base_date = datetime(2024, 1, 2, tzinfo=UTC)
    bars = []
    price = 100.0

    for i in range(30):  # 30 days of data
        date = base_date + timedelta(days=i)
        # Simple price movement
        price = price * (1 + (0.01 if i % 3 == 0 else -0.005))
        bars.append(
            {
                "timestamp": date,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 10000 + i * 100,
            }
        )

    return {"AAPL": bars}
