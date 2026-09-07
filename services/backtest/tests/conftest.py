"""Shared test fixtures for backtest service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.backtest_service import MarketDataFetcher

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
    """Market-data client double, spec-bound to the MarketDataFetcher protocol."""
    client = AsyncMock(spec=MarketDataFetcher)
    client.fetch_bars.return_value = {}
    return client


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _fake_notification_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the shared notification publisher at an in-memory stream."""
    from llamatrade_events import EventBus
    from llamatrade_events.catalog import notifications as notifications_module
    from llamatrade_events.catalog.notifications import NotificationEvents
    from llamatrade_events.testing import FakeTransport

    monkeypatch.setattr(
        notifications_module,
        "_shared",
        NotificationEvents(bus=EventBus(FakeTransport())),
    )
