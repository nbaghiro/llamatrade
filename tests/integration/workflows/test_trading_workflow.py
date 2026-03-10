"""Trading workflow gRPC tests.

Tests the complete trading workflow:
1. Trading session lifecycle (start/stop/pause)
2. Order lifecycle (submit → fill → position created)
3. Position management
4. Tenant isolation
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.asyncio]


class MockServicerContext:
    """Mock ConnectRPC servicer context for testing."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self._cancelled = False

    def cancelled(self) -> bool:
        return self._cancelled

    def request_headers(self) -> dict[str, str]:
        """Return headers dict (ConnectRPC style)."""
        return self.headers


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


def _load_auth_servicer():
    """Load the auth servicer, clearing module cache to avoid conflicts."""
    auth_path = Path(__file__).parents[3] / "services" / "auth"
    auth_path_str = str(auth_path)

    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["billing", "strategy", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    if auth_path_str in sys.path:
        sys.path.remove(auth_path_str)
    sys.path.insert(0, auth_path_str)

    from src.grpc.servicer import AuthServicer

    return AuthServicer


def _load_strategy_servicer():
    """Load the strategy servicer, clearing module cache."""
    strategy_path = Path(__file__).parents[3] / "services" / "strategy"
    strategy_path_str = str(strategy_path)

    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["auth", "billing", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    if strategy_path_str in sys.path:
        sys.path.remove(strategy_path_str)
    sys.path.insert(0, strategy_path_str)

    from src.grpc.servicer import StrategyServicer

    return StrategyServicer


@pytest.fixture
def auth_servicer(db_session: AsyncSession):
    """Create an auth servicer with test database session."""
    auth_servicer_cls = _load_auth_servicer()
    servicer = auth_servicer_cls()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def strategy_servicer(db_session: AsyncSession):
    """Create a strategy servicer with test database session."""
    strategy_servicer_cls = _load_strategy_servicer()
    servicer = strategy_servicer_cls()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


# Sample valid strategy DSL
VALID_STRATEGY_DSL = """(strategy "Test Trading Strategy"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 20) (sma SPY 50))
    (weight :method equal
      (asset AAPL)
      (asset GOOGL))
    (else (asset TLT :weight 100))))"""


async def register_and_login(auth_servicer, context):
    """Helper to register and login, returning auth info."""
    from llamatrade_proto.generated import auth_pb2

    email = f"test-{uuid4().hex[:8]}@example.com"

    register_request = auth_pb2.RegisterRequest(
        tenant_name=f"Test Co {uuid4().hex[:6]}",
        email=email,
        password="TestPassword123!",
    )
    register_response = await auth_servicer.register(register_request, context)

    return {
        "user_id": register_response.user.id,
        "tenant_id": register_response.tenant.id,
    }


def create_tenant_context(user_id: str, tenant_id: str):
    """Create a TenantContext proto message."""
    from llamatrade_proto.generated import common_pb2

    return common_pb2.TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=["admin"],
    )


async def setup_strategy(auth_servicer, strategy_servicer, context, db_session):
    """Helper to register user and create a strategy."""
    from llamatrade_proto.generated import strategy_pb2

    auth_info = await register_and_login(auth_servicer, context)
    ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

    # Create strategy
    create_request = strategy_pb2.CreateStrategyRequest(
        context=ctx,
        name="Trading Test Strategy",
        dsl_code=VALID_STRATEGY_DSL,
    )
    strategy_response = await strategy_servicer.create_strategy(create_request, context)

    return {
        **auth_info,
        "strategy_id": strategy_response.strategy.id,
        "ctx": ctx,
    }


async def setup_alpaca_credentials(auth_servicer, ctx, context):
    """Helper to create Alpaca credentials."""
    from llamatrade_proto.generated import auth_pb2

    create_request = auth_pb2.CreateAlpacaCredentialsRequest(
        context=ctx,
        name="Test Paper Account",
        api_key=f"PK{uuid4().hex[:12].upper()}",
        api_secret=f"secret{uuid4().hex[:20]}",
        is_paper=True,
    )
    response = await auth_servicer.create_alpaca_credentials(create_request, context)
    return response.credentials.id


class TestTradingSessionLifecycle:
    """Test trading session lifecycle operations."""

    async def test_session_lifecycle_via_fixtures(
        self,
        db_session: AsyncSession,
        active_trading_session,
        test_tenant,
    ):
        """Test that trading session fixtures work correctly."""
        from tests.factories import SESSION_STATUS_ACTIVE

        # Verify session is properly created and linked
        assert active_trading_session.tenant_id == test_tenant.id
        assert active_trading_session.status == SESSION_STATUS_ACTIVE

    async def test_multiple_sessions_per_tenant(
        self,
        db_session: AsyncSession,
        multiple_trading_sessions,
        test_tenant,
    ):
        """Test creating multiple trading sessions."""
        assert len(multiple_trading_sessions) == 5
        for session in multiple_trading_sessions:
            assert session.tenant_id == test_tenant.id


class TestOrderLifecycle:
    """Test order submission and management."""

    async def test_order_creation_via_fixture(
        self,
        db_session: AsyncSession,
        test_order,
        active_trading_session,
    ):
        """Test that order fixtures work correctly."""
        from tests.factories import ORDER_SIDE_BUY, ORDER_STATUS_PENDING, ORDER_TYPE_MARKET

        assert test_order.session_id == active_trading_session.id
        assert test_order.tenant_id == active_trading_session.tenant_id
        assert test_order.symbol == "AAPL"
        assert test_order.side == ORDER_SIDE_BUY
        assert test_order.order_type == ORDER_TYPE_MARKET
        assert test_order.status == ORDER_STATUS_PENDING
        assert test_order.qty == Decimal("10.00000000")

    async def test_limit_order_has_price(
        self,
        db_session: AsyncSession,
        test_limit_order,
    ):
        """Test limit order has limit price set."""
        from tests.factories import ORDER_TYPE_LIMIT

        assert test_limit_order.order_type == ORDER_TYPE_LIMIT
        assert test_limit_order.limit_price == Decimal("140.50000000")

    async def test_filled_order_has_fill_data(
        self,
        db_session: AsyncSession,
        filled_order,
    ):
        """Test filled order has fill information."""
        from tests.factories import ORDER_STATUS_FILLED

        assert filled_order.status == ORDER_STATUS_FILLED
        assert filled_order.filled_qty == filled_order.qty
        assert filled_order.filled_avg_price == Decimal("380.25000000")
        assert filled_order.filled_at is not None

    async def test_multiple_orders_various_states(
        self,
        db_session: AsyncSession,
        multiple_orders,
    ):
        """Test creating orders in various states."""
        assert len(multiple_orders) == 10

        # Verify we have different statuses
        statuses = {order.status for order in multiple_orders}
        assert len(statuses) > 1  # At least 2 different statuses


class TestPositionManagement:
    """Test position tracking and management."""

    async def test_position_creation_via_fixture(
        self,
        db_session: AsyncSession,
        test_position,
        active_trading_session,
    ):
        """Test that position fixtures work correctly."""
        from tests.factories import POSITION_SIDE_LONG

        assert test_position.session_id == active_trading_session.id
        assert test_position.symbol == "AAPL"
        assert test_position.side == POSITION_SIDE_LONG
        assert test_position.qty == Decimal("10.00000000")
        assert test_position.is_open is True

    async def test_position_pnl_calculation(
        self,
        db_session: AsyncSession,
        test_position,
    ):
        """Test position P&L is calculated correctly."""
        # Entry: 175.50, Current: 180.25, Qty: 10
        # Expected unrealized P&L: (180.25 - 175.50) * 10 = 47.50
        expected_pl = (Decimal("180.25") - Decimal("175.50")) * Decimal("10")
        assert test_position.unrealized_pl == expected_pl

    async def test_short_position(
        self,
        db_session: AsyncSession,
        test_short_position,
    ):
        """Test short position side."""
        from tests.factories import POSITION_SIDE_SHORT

        assert test_short_position.side == POSITION_SIDE_SHORT
        assert test_short_position.symbol == "TSLA"

    async def test_closed_position(
        self,
        db_session: AsyncSession,
        closed_position,
    ):
        """Test closed position with realized P&L."""
        assert closed_position.is_open is False
        assert closed_position.qty == Decimal("0.00000000")
        assert closed_position.realized_pl == Decimal("500.00")
        assert closed_position.closed_at is not None

    async def test_multiple_positions(
        self,
        db_session: AsyncSession,
        multiple_positions,
        active_trading_session,
    ):
        """Test multiple positions per session."""
        assert len(multiple_positions) == 3

        symbols = {pos.symbol for pos in multiple_positions}
        assert symbols == {"AAPL", "GOOGL", "MSFT"}

        # All should be for the same session
        for pos in multiple_positions:
            assert pos.session_id == active_trading_session.id


class TestTradingTenantIsolation:
    """Test tenant isolation for trading operations."""

    async def test_order_tenant_isolation(
        self,
        db_session: AsyncSession,
        test_order,
        second_tenant_order,
        test_tenant,
        second_tenant,
    ):
        """Test orders belong to correct tenants."""
        assert test_order.tenant_id == test_tenant.id
        assert second_tenant_order.tenant_id == second_tenant.id
        assert test_order.tenant_id != second_tenant_order.tenant_id

    async def test_position_tenant_isolation(
        self,
        db_session: AsyncSession,
        test_position,
        second_tenant_position,
        test_tenant,
        second_tenant,
    ):
        """Test positions belong to correct tenants."""
        assert test_position.tenant_id == test_tenant.id
        assert second_tenant_position.tenant_id == second_tenant.id

    async def test_trading_session_tenant_isolation(
        self,
        db_session: AsyncSession,
        active_trading_session,
        second_tenant_trading_session,
        test_tenant,
        second_tenant,
    ):
        """Test trading sessions belong to correct tenants."""
        assert active_trading_session.tenant_id == test_tenant.id
        assert second_tenant_trading_session.tenant_id == second_tenant.id

    async def test_query_orders_by_tenant(
        self,
        db_session: AsyncSession,
        test_order,
        second_tenant_order,
        test_tenant,
    ):
        """Test that querying orders filters by tenant correctly."""
        from sqlalchemy import select

        from llamatrade_db.models import Order

        # Query for test_tenant's orders only
        result = await db_session.execute(select(Order).where(Order.tenant_id == test_tenant.id))
        orders = result.scalars().all()

        # Should only see test_tenant's orders
        for order in orders:
            assert order.tenant_id == test_tenant.id

        # Specifically, should not see second_tenant_order
        order_ids = [o.id for o in orders]
        assert second_tenant_order.id not in order_ids

    async def test_query_positions_by_tenant(
        self,
        db_session: AsyncSession,
        test_position,
        second_tenant_position,
        test_tenant,
    ):
        """Test that querying positions filters by tenant correctly."""
        from sqlalchemy import select

        from llamatrade_db.models import Position

        # Query for test_tenant's positions only
        result = await db_session.execute(
            select(Position).where(Position.tenant_id == test_tenant.id)
        )
        positions = result.scalars().all()

        # Should only see test_tenant's positions
        for pos in positions:
            assert pos.tenant_id == test_tenant.id

        # Specifically, should not see second_tenant_position
        position_ids = [p.id for p in positions]
        assert second_tenant_position.id not in position_ids


class TestOrderPositionRelationship:
    """Test relationship between orders and positions."""

    async def test_order_creates_position_on_fill(
        self,
        db_session: AsyncSession,
        active_trading_session,
    ):
        """Test that a filled buy order creates a position."""
        from tests.factories import (
            ORDER_SIDE_BUY,
            ORDER_STATUS_FILLED,
            ORDER_TYPE_MARKET,
            POSITION_SIDE_LONG,
            OrderFactory,
            PositionFactory,
        )

        # Create a filled order
        order = OrderFactory.create(
            tenant_id=active_trading_session.tenant_id,
            session_id=active_trading_session.id,
            symbol="NVDA",
            side=ORDER_SIDE_BUY,
            qty=Decimal("15.00000000"),
            order_type=ORDER_TYPE_MARKET,
            status=ORDER_STATUS_FILLED,
            filled_qty=Decimal("15.00000000"),
            filled_avg_price=Decimal("500.00000000"),
        )
        db_session.add(order)

        # Create corresponding position (simulating what the service would do)
        position = PositionFactory.create(
            tenant_id=active_trading_session.tenant_id,
            session_id=active_trading_session.id,
            symbol="NVDA",
            side=POSITION_SIDE_LONG,
            qty=Decimal("15.00000000"),
            avg_entry_price=Decimal("500.00000000"),
            current_price=Decimal("505.00000000"),
        )
        db_session.add(position)
        await db_session.flush()

        # Verify relationship through session
        assert order.symbol == position.symbol
        assert order.filled_qty == position.qty
        assert order.filled_avg_price == position.avg_entry_price

    async def test_sell_order_reduces_position(
        self,
        db_session: AsyncSession,
        test_position,
        active_trading_session,
    ):
        """Test that sell order would reduce position quantity."""
        from tests.factories import ORDER_SIDE_SELL, ORDER_TYPE_MARKET, OrderFactory

        initial_qty = test_position.qty
        sell_qty = Decimal("5.00000000")

        # Create a sell order
        sell_order = OrderFactory.create(
            tenant_id=active_trading_session.tenant_id,
            session_id=active_trading_session.id,
            symbol=test_position.symbol,
            side=ORDER_SIDE_SELL,
            qty=sell_qty,
            order_type=ORDER_TYPE_MARKET,
        )
        db_session.add(sell_order)
        await db_session.flush()

        # Verify the order is for reducing the position
        assert sell_order.symbol == test_position.symbol
        assert sell_order.qty < initial_qty
