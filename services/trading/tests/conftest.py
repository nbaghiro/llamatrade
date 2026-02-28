"""Shared test fixtures for trading service."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_ORDER_ID = UUID("55555555-5555-5555-5555-555555555555")
TEST_CREDENTIALS_ID = UUID("66666666-6666-6666-6666-666666666666")


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
def session_id():
    return TEST_SESSION_ID


@pytest.fixture
def order_id():
    return TEST_ORDER_ID


@pytest.fixture
def credentials_id():
    return TEST_CREDENTIALS_ID


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
def mock_alpaca_client():
    """Create a mock Alpaca trading client."""
    client = AsyncMock()
    client.get_account = AsyncMock(
        return_value={
            "id": "test-account",
            "account_number": "123456789",
            "status": "ACTIVE",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "buying_power": "200000.00",
            "equity": "100000.00",
            "currency": "USD",
        }
    )
    client.submit_order = AsyncMock(
        return_value={
            "id": "alpaca-order-123",
            "client_order_id": "test-client-order",
            "symbol": "AAPL",
            "qty": "10",
            "side": "buy",
            "type": "market",
            "status": "accepted",
            "filled_qty": "0",
            "filled_avg_price": None,
            "created_at": "2024-01-15T10:00:00Z",
            "submitted_at": "2024-01-15T10:00:00Z",
            "filled_at": None,
        }
    )
    client.get_order = AsyncMock(
        return_value={
            "id": "alpaca-order-123",
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "150.50",
            "filled_at": "2024-01-15T10:01:00Z",
        }
    )
    client.cancel_order = AsyncMock(return_value=True)
    client.get_positions = AsyncMock(return_value=[])
    client.get_position = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager."""
    from src.models import RiskCheckResult

    manager = AsyncMock()
    manager.check_order = AsyncMock(
        return_value=RiskCheckResult(
            passed=True,
            violations=[],
        )
    )
    manager.get_limits = AsyncMock()
    return manager


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
def mock_trading_session():
    """Create a mock trading session database model."""
    session = MagicMock()
    session.id = TEST_SESSION_ID
    session.tenant_id = TEST_TENANT_ID
    session.strategy_id = TEST_STRATEGY_ID
    session.strategy_version = 1
    session.credentials_id = TEST_CREDENTIALS_ID
    session.name = "Test Session"
    session.mode = "paper"
    session.status = "active"
    session.config = {}
    session.symbols = ["AAPL", "GOOGL"]
    session.started_at = datetime.now(UTC)
    session.stopped_at = None
    session.last_heartbeat = None
    session.error_message = None
    session.created_at = datetime.now(UTC)
    session.created_by = TEST_USER_ID
    return session


@pytest.fixture
def mock_order():
    """Create a mock order database model."""
    order = MagicMock()
    order.id = TEST_ORDER_ID
    order.tenant_id = TEST_TENANT_ID
    order.session_id = TEST_SESSION_ID
    order.alpaca_order_id = "alpaca-order-123"
    order.client_order_id = "client-order-123"
    order.symbol = "AAPL"
    order.side = "buy"
    order.order_type = "market"
    order.time_in_force = "day"
    order.qty = Decimal("10")
    order.limit_price = None
    order.stop_price = None
    order.status = "submitted"
    order.filled_qty = Decimal("0")
    order.filled_avg_price = None
    order.submitted_at = datetime.now(UTC)
    order.filled_at = None
    order.canceled_at = None
    order.failed_at = None
    order.created_at = datetime.now(UTC)
    # Bracket order fields
    order.parent_order_id = None
    order.bracket_type = None
    order.stop_loss_price = None
    order.take_profit_price = None
    return order


@pytest.fixture
def sample_bar_data():
    """Sample bar data for testing."""
    from src.runner.bar_stream import BarData

    return BarData(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 15, 9, 30, tzinfo=UTC),
        open=150.0,
        high=152.0,
        low=149.5,
        close=151.5,
        volume=10000,
        vwap=150.8,
        trade_count=500,
    )


@pytest.fixture
def sample_bars():
    """Sample bars for runner testing."""
    from datetime import timedelta

    from src.runner.bar_stream import BarData

    base_time = datetime(2024, 1, 15, 9, 30, tzinfo=UTC)
    bars = []
    price = 150.0

    for i in range(60):  # 60 minutes of data
        timestamp = base_time + timedelta(minutes=i)
        # Simple price movement
        price = price * (1 + (0.001 if i % 3 == 0 else -0.0005))
        bars.append(
            BarData(
                symbol="AAPL",
                timestamp=timestamp,
                open=price * 0.999,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=1000 + i * 10,
            )
        )

    return bars
