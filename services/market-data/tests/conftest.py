"""Test fixtures for market-data service tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import Bar, Quote, Snapshot, Trade

# Test UUIDs for consistent test data
TEST_TENANT_ID = UUID("12345678-1234-1234-1234-123456789012")
TEST_USER_ID = UUID("87654321-4321-4321-4321-210987654321")


# === Test Client Fixtures ===


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_auth_header() -> dict[str, str]:
    """Create mock auth header for testing."""
    return {"Authorization": "Bearer test-token"}


# === Mock Context Fixtures ===


@pytest.fixture
def mock_tenant_context() -> TenantContext:
    """Create a mock tenant context."""
    return TenantContext(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="test@example.com",
        roles=["user"],
    )


@pytest.fixture
def auth_override(mock_tenant_context):
    """Create a dependency override for require_auth."""
    from llamatrade_common.middleware import require_auth

    # The actual require_auth has different signature, so we use a simple lambda
    app.dependency_overrides[require_auth] = lambda: mock_tenant_context
    yield
    app.dependency_overrides.pop(require_auth, None)


# === Redis/Cache Fixtures ===


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.aclose = AsyncMock()
    return redis


@pytest.fixture
def mock_cache(mock_redis):
    """Create a mock MarketDataCache."""
    from src.cache import MarketDataCache

    return MarketDataCache(redis_client=mock_redis)


# === Alpaca Client Fixtures ===


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca client."""
    client = AsyncMock()
    client.get_bars = AsyncMock(return_value=[])
    client.get_multi_bars = AsyncMock(return_value={})
    client.get_latest_bar = AsyncMock(return_value=None)
    client.get_latest_quote = AsyncMock(return_value=None)
    client.get_snapshot = AsyncMock(return_value=None)
    client.get_multi_snapshots = AsyncMock(return_value={})
    client.close = AsyncMock()
    return client


# === Sample Data Fixtures ===


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample Bar for testing."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=UTC),
        open=150.0,
        high=152.5,
        low=149.0,
        close=151.75,
        volume=1000000,
        vwap=150.5,
        trade_count=5000,
    )


@pytest.fixture
def sample_bars(sample_bar) -> list[Bar]:
    """Create a list of sample Bars for testing."""
    return [
        sample_bar,
        Bar(
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=UTC),
            open=151.75,
            high=153.0,
            low=150.5,
            close=152.25,
            volume=1100000,
            vwap=151.75,
            trade_count=5500,
        ),
        Bar(
            timestamp=datetime(2024, 1, 17, 16, 0, 0, tzinfo=UTC),
            open=152.25,
            high=154.0,
            low=151.0,
            close=153.50,
            volume=1200000,
            vwap=152.5,
            trade_count=6000,
        ),
    ]


@pytest.fixture
def sample_quote() -> Quote:
    """Create a sample Quote for testing."""
    return Quote(
        symbol="AAPL",
        bid_price=151.50,
        bid_size=100,
        ask_price=151.55,
        ask_size=200,
        timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_trade() -> Trade:
    """Create a sample Trade for testing."""
    return Trade(
        symbol="AAPL",
        price=151.52,
        size=50,
        timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=UTC),
        exchange="NASDAQ",
    )


@pytest.fixture
def sample_snapshot(sample_bar, sample_quote, sample_trade) -> Snapshot:
    """Create a sample Snapshot for testing."""
    return Snapshot(
        symbol="AAPL",
        latest_trade=sample_trade,
        latest_quote=sample_quote,
        minute_bar=sample_bar,
        daily_bar=sample_bar,
        prev_daily_bar=sample_bar,
    )


# === Service Override Fixtures ===


@pytest.fixture
def mock_market_data_service(sample_bars, sample_bar, sample_quote, sample_snapshot):
    """Create a mock market data service with configured return values."""
    service = MagicMock()
    service.get_bars = AsyncMock(return_value=sample_bars)
    service.get_multi_bars = AsyncMock(return_value={"AAPL": sample_bars})
    service.get_latest_bar = AsyncMock(return_value=sample_bar)
    service.get_latest_quote = AsyncMock(return_value=sample_quote)
    service.get_snapshot = AsyncMock(return_value=sample_snapshot)
    service.get_multi_snapshots = AsyncMock(
        return_value={"AAPL": sample_snapshot, "TSLA": sample_snapshot}
    )
    return service


@pytest.fixture
def service_override(mock_market_data_service):
    """Create a dependency override for get_market_data_service."""
    from src.services.market_data_service import get_market_data_service

    async def mock_get_service():
        return mock_market_data_service

    app.dependency_overrides[get_market_data_service] = mock_get_service
    yield
    app.dependency_overrides.pop(get_market_data_service, None)


# === Cleanup Fixture ===


@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Ensure dependency overrides are cleaned up after each test."""
    yield
    app.dependency_overrides.clear()
