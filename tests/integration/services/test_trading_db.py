"""Trading service integration tests with real database.

These tests verify trading functionality against a real PostgreSQL database:
1. Order CRUD operations (create, read, update status)
2. Position tracking
3. Risk config persistence
4. Event store operations

Uses testcontainers for real PostgreSQL database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from llamatrade_db.models.audit import DailyPnL, RiskConfig
from llamatrade_db.models.trading import Order, Position, TradingSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_CREDENTIALS_ID = UUID("55555555-5555-5555-5555-555555555555")

# Proto int constants for enum values
# OrderSide: BUY=1, SELL=2
ORDER_SIDE_BUY = 1
ORDER_SIDE_SELL = 2

# OrderStatus: PENDING=1, SUBMITTED=2, ACCEPTED=3, PARTIAL=4, FILLED=5, CANCELLED=6, REJECTED=7, EXPIRED=8
ORDER_STATUS_PENDING = 1
ORDER_STATUS_SUBMITTED = 2
ORDER_STATUS_FILLED = 5
ORDER_STATUS_CANCELLED = 6

# OrderType: MARKET=1, LIMIT=2, STOP=3, STOP_LIMIT=4, TRAILING_STOP=5
ORDER_TYPE_MARKET = 1
ORDER_TYPE_LIMIT = 2
ORDER_TYPE_STOP_LIMIT = 4

# TimeInForce: DAY=1, GTC=2, IOC=3, FOK=4, OPG=5, CLS=6
TIME_IN_FORCE_DAY = 1
TIME_IN_FORCE_GTC = 2

# PositionSide: LONG=1, SHORT=2
POSITION_SIDE_LONG = 1

# SessionStatus: ACTIVE=1, PAUSED=2, STOPPED=3, ERROR=4
SESSION_STATUS_ACTIVE = 1

# ExecutionMode: PAPER=1, LIVE=2
EXECUTION_MODE_PAPER = 1

# BracketType: STOP_LOSS=1, TAKE_PROFIT=2
BRACKET_TYPE_STOP_LOSS = 1
BRACKET_TYPE_TAKE_PROFIT = 2


@pytest.fixture
async def trading_session(db_session: AsyncSession) -> TradingSession:
    """Create a test trading session."""
    session = TradingSession(
        id=TEST_SESSION_ID,
        tenant_id=TEST_TENANT_ID,
        strategy_id=TEST_STRATEGY_ID,
        strategy_version=1,
        credentials_id=TEST_CREDENTIALS_ID,
        name="Test Session",
        mode=EXECUTION_MODE_PAPER,  # Proto int: PAPER=1
        status=SESSION_STATUS_ACTIVE,  # Proto int: ACTIVE=1
        symbols=["AAPL", "GOOGL"],
        created_by=TEST_USER_ID,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


class TestOrderCRUD:
    """Order CRUD operation tests with real database."""

    async def test_create_order(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test creating an order in the database."""
        order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("10"),
            status=ORDER_STATUS_PENDING,  # Proto int: PENDING=1
            filled_qty=Decimal("0"),
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # Verify order was created
        assert order.id is not None
        assert order.symbol == "AAPL"
        assert order.qty == Decimal("10")
        assert order.status == ORDER_STATUS_PENDING

    async def test_read_order_by_id(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test reading an order by ID."""
        # Create order
        order_id = uuid4()
        order = Order(
            id=order_id,
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="GOOGL",
            side=ORDER_SIDE_SELL,  # Proto int: SELL=2
            order_type=ORDER_TYPE_LIMIT,  # Proto int: LIMIT=2
            time_in_force=TIME_IN_FORCE_GTC,  # Proto int: GTC=2
            qty=Decimal("5"),
            limit_price=Decimal("150.00"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
        )
        db_session.add(order)
        await db_session.commit()

        # Read order back
        result = await db_session.execute(select(Order).where(Order.id == order_id))
        fetched = result.scalar_one_or_none()

        assert fetched is not None
        assert fetched.id == order_id
        assert fetched.symbol == "GOOGL"
        assert fetched.limit_price == Decimal("150.00")

    async def test_update_order_status_to_filled(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test updating an order status when filled."""
        # Create order
        order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("10"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        order_id = order.id

        # Update to filled
        order.status = ORDER_STATUS_FILLED  # Proto int: FILLED=5
        order.filled_qty = Decimal("10")
        order.filled_avg_price = Decimal("152.50")
        order.filled_at = datetime.now(UTC)
        await db_session.commit()

        # Verify update
        result = await db_session.execute(select(Order).where(Order.id == order_id))
        updated = result.scalar_one()
        assert updated.status == ORDER_STATUS_FILLED
        assert updated.filled_qty == Decimal("10")
        assert updated.filled_avg_price == Decimal("152.50")

    async def test_list_orders_with_filters(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test listing orders with various filters."""
        # Create multiple orders
        orders = [
            Order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                client_order_id=str(uuid4()),
                symbol="AAPL",
                side=ORDER_SIDE_BUY,  # Proto int: BUY=1
                order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
                time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
                qty=Decimal("10"),
                status=ORDER_STATUS_FILLED,  # Proto int: FILLED=5
                filled_qty=Decimal("10"),
            ),
            Order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                client_order_id=str(uuid4()),
                symbol="GOOGL",
                side=ORDER_SIDE_SELL,  # Proto int: SELL=2
                order_type=ORDER_TYPE_LIMIT,  # Proto int: LIMIT=2
                time_in_force=TIME_IN_FORCE_GTC,  # Proto int: GTC=2
                qty=Decimal("5"),
                status=ORDER_STATUS_PENDING,  # Proto int: PENDING=1
                filled_qty=Decimal("0"),
            ),
            Order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                client_order_id=str(uuid4()),
                symbol="AAPL",
                side=ORDER_SIDE_SELL,  # Proto int: SELL=2
                order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
                time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
                qty=Decimal("5"),
                status=ORDER_STATUS_CANCELLED,  # Proto int: CANCELLED=6
                filled_qty=Decimal("0"),
            ),
        ]
        for order in orders:
            db_session.add(order)
        await db_session.commit()

        # Filter by status
        result = await db_session.execute(
            select(Order)
            .where(Order.tenant_id == TEST_TENANT_ID)
            .where(Order.status == ORDER_STATUS_FILLED)
        )
        filled_orders = result.scalars().all()
        assert len(filled_orders) == 1
        assert filled_orders[0].symbol == "AAPL"

        # Filter by symbol
        result = await db_session.execute(
            select(Order).where(Order.tenant_id == TEST_TENANT_ID).where(Order.symbol == "AAPL")
        )
        aapl_orders = result.scalars().all()
        assert len(aapl_orders) == 2

    async def test_tenant_isolation(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test that orders are isolated by tenant."""
        other_tenant_id = uuid4()
        other_session_id = uuid4()

        # Create session for other tenant
        other_session = TradingSession(
            id=other_session_id,
            tenant_id=other_tenant_id,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=1,
            credentials_id=TEST_CREDENTIALS_ID,
            name="Other Tenant Session",
            mode=EXECUTION_MODE_PAPER,  # Proto int: PAPER=1
            status=SESSION_STATUS_ACTIVE,  # Proto int: ACTIVE=1
            symbols=["MSFT"],
            created_by=uuid4(),
        )
        db_session.add(other_session)
        await db_session.commit()

        # Create orders for both tenants
        our_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("10"),
            status=ORDER_STATUS_PENDING,  # Proto int: PENDING=1
            filled_qty=Decimal("0"),
        )
        their_order = Order(
            tenant_id=other_tenant_id,
            session_id=other_session_id,
            client_order_id=str(uuid4()),
            symbol="MSFT",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("20"),
            status=ORDER_STATUS_PENDING,  # Proto int: PENDING=1
            filled_qty=Decimal("0"),
        )
        db_session.add(our_order)
        db_session.add(their_order)
        await db_session.commit()

        # Query should only return our tenant's orders
        result = await db_session.execute(select(Order).where(Order.tenant_id == TEST_TENANT_ID))
        orders = result.scalars().all()
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"


class TestPositionTracking:
    """Position tracking tests with real database."""

    async def test_create_position(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test creating a position."""
        position = Position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            side=POSITION_SIDE_LONG,  # Proto int: LONG=1
            qty=Decimal("10"),
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("155.00"),
            cost_basis=Decimal("1500.00"),
            market_value=Decimal("1550.00"),
            unrealized_pl=Decimal("50.00"),
            unrealized_plpc=Decimal("0.0333"),  # 3.33% as decimal
            is_open=True,
            opened_at=datetime.now(UTC),
        )
        db_session.add(position)
        await db_session.commit()
        await db_session.refresh(position)

        assert position.id is not None
        assert position.qty == Decimal("10")
        assert position.unrealized_pl == Decimal("50.00")

    async def test_update_position_on_partial_fill(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test updating position after partial fill."""
        # Create initial position
        position = Position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            side=POSITION_SIDE_LONG,  # Proto int: LONG=1
            qty=Decimal("10"),
            avg_entry_price=Decimal("150.00"),
            current_price=Decimal("150.00"),
            cost_basis=Decimal("1500.00"),
            market_value=Decimal("1500.00"),
            unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"),
            is_open=True,
            opened_at=datetime.now(UTC),
        )
        db_session.add(position)
        await db_session.commit()
        await db_session.refresh(position)
        position_id = position.id

        # Simulate adding 5 more shares at $160
        old_qty = position.qty
        old_cost = position.cost_basis
        add_qty = Decimal("5")
        add_price = Decimal("160.00")
        add_cost = add_qty * add_price

        position.qty = old_qty + add_qty
        position.cost_basis = old_cost + add_cost
        position.avg_entry_price = position.cost_basis / position.qty
        position.current_price = Decimal("160.00")
        position.market_value = position.qty * position.current_price
        position.unrealized_pl = position.market_value - position.cost_basis
        await db_session.commit()

        # Verify update
        result = await db_session.execute(select(Position).where(Position.id == position_id))
        updated = result.scalar_one()
        assert updated.qty == Decimal("15")
        # (1500 + 800) / 15 = 2300/15 = 153.333...
        assert float(updated.avg_entry_price) == pytest.approx(153.333333, rel=0.0001)

    async def test_close_position(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test closing a position."""
        # Create position
        position = Position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="GOOGL",
            side=POSITION_SIDE_LONG,  # Proto int: LONG=1
            qty=Decimal("5"),
            avg_entry_price=Decimal("140.00"),
            current_price=Decimal("145.00"),
            cost_basis=Decimal("700.00"),
            market_value=Decimal("725.00"),
            unrealized_pl=Decimal("25.00"),
            unrealized_plpc=Decimal("0.0357"),  # 3.57% as decimal
            is_open=True,
            opened_at=datetime.now(UTC),
        )
        db_session.add(position)
        await db_session.commit()
        await db_session.refresh(position)

        # Close position
        position.is_open = False
        position.realized_pl = position.unrealized_pl
        position.unrealized_pl = Decimal("0")
        position.qty = Decimal("0")
        await db_session.commit()

        # Verify position is closed
        result = await db_session.execute(
            select(Position)
            .where(Position.tenant_id == TEST_TENANT_ID)
            .where(Position.symbol == "GOOGL")
            .where(Position.is_open.is_(True))
        )
        open_positions = result.scalars().all()
        assert len(open_positions) == 0


class TestRiskConfigPersistence:
    """Risk config persistence tests with real database."""

    async def test_create_risk_config(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test creating risk configuration."""
        config = RiskConfig(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            max_position_value=Decimal("10000.00"),
            max_daily_loss_value=Decimal("1000.00"),
            max_order_value=Decimal("5000.00"),
            allowed_symbols=["AAPL", "GOOGL", "MSFT"],
            is_active=True,
        )
        db_session.add(config)
        await db_session.commit()
        await db_session.refresh(config)

        assert config.id is not None
        assert config.max_position_value == Decimal("10000.00")
        assert config.allowed_symbols == ["AAPL", "GOOGL", "MSFT"]

    async def test_session_config_overrides_tenant(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test session-specific config overrides tenant-wide config."""
        # Create tenant-wide config
        tenant_config = RiskConfig(
            tenant_id=TEST_TENANT_ID,
            session_id=None,  # Tenant-wide
            max_position_value=Decimal("5000.00"),
            max_daily_loss_value=Decimal("500.00"),
            max_order_value=Decimal("2500.00"),
            is_active=True,
        )
        db_session.add(tenant_config)

        # Create session-specific config
        session_config = RiskConfig(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            max_position_value=Decimal("20000.00"),  # Higher limit
            max_daily_loss_value=Decimal("2000.00"),
            max_order_value=Decimal("10000.00"),
            is_active=True,
        )
        db_session.add(session_config)
        await db_session.commit()

        # Query for session-specific config
        result = await db_session.execute(
            select(RiskConfig)
            .where(RiskConfig.tenant_id == TEST_TENANT_ID)
            .where(RiskConfig.session_id == TEST_SESSION_ID)
            .where(RiskConfig.is_active.is_(True))
        )
        config = result.scalar_one_or_none()

        assert config is not None
        assert config.max_position_value == Decimal("20000.00")

    async def test_deactivate_old_config(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test that old configs can be deactivated."""
        # Create initial config
        old_config = RiskConfig(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            max_position_value=Decimal("5000.00"),
            is_active=True,
        )
        db_session.add(old_config)
        await db_session.commit()
        await db_session.refresh(old_config)

        # Deactivate old config
        old_config.is_active = False
        await db_session.commit()

        # Create new config
        new_config = RiskConfig(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            max_position_value=Decimal("10000.00"),
            is_active=True,
        )
        db_session.add(new_config)
        await db_session.commit()

        # Only new config should be active
        result = await db_session.execute(
            select(RiskConfig)
            .where(RiskConfig.tenant_id == TEST_TENANT_ID)
            .where(RiskConfig.session_id == TEST_SESSION_ID)
            .where(RiskConfig.is_active.is_(True))
        )
        active_configs = result.scalars().all()
        assert len(active_configs) == 1
        assert active_configs[0].max_position_value == Decimal("10000.00")


class TestDailyPnLTracking:
    """Daily P&L tracking tests with real database."""

    async def test_create_daily_pnl_record(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test creating daily P&L record."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        daily_pnl = DailyPnL(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            date=today,
            realized_pnl=Decimal("150.00"),
            unrealized_pnl=Decimal("50.00"),
            total_pnl=Decimal("200.00"),
            equity_start=Decimal("10000.00"),
            equity_high=Decimal("10250.00"),
            equity_low=Decimal("9950.00"),
            equity_end=Decimal("10200.00"),
            max_drawdown_pct=Decimal("0.5"),
            trades_count=5,
            winning_trades=3,
            losing_trades=2,
        )
        db_session.add(daily_pnl)
        await db_session.commit()
        await db_session.refresh(daily_pnl)

        assert daily_pnl.id is not None
        assert daily_pnl.total_pnl == Decimal("200.00")
        assert daily_pnl.trades_count == 5

    async def test_update_daily_pnl_metrics(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test updating daily P&L metrics throughout the day."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create initial record
        daily_pnl = DailyPnL(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            date=today,
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            equity_start=Decimal("10000.00"),
            equity_high=Decimal("10000.00"),
            equity_low=Decimal("10000.00"),
            equity_end=Decimal("10000.00"),
            max_drawdown_pct=Decimal("0"),
            trades_count=0,
            winning_trades=0,
            losing_trades=0,
        )
        db_session.add(daily_pnl)
        await db_session.commit()
        await db_session.refresh(daily_pnl)
        pnl_id = daily_pnl.id

        # Update with new trade
        daily_pnl.realized_pnl = Decimal("100.00")
        daily_pnl.total_pnl = Decimal("100.00")
        daily_pnl.equity_end = Decimal("10100.00")
        daily_pnl.equity_high = Decimal("10100.00")
        daily_pnl.trades_count = 1
        daily_pnl.winning_trades = 1
        await db_session.commit()

        # Verify update
        result = await db_session.execute(select(DailyPnL).where(DailyPnL.id == pnl_id))
        updated = result.scalar_one()
        assert updated.realized_pnl == Decimal("100.00")
        assert updated.trades_count == 1

    async def test_drawdown_calculation(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test max drawdown tracking."""
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        daily_pnl = DailyPnL(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            date=today,
            realized_pnl=Decimal("-500.00"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("-500.00"),
            equity_start=Decimal("10000.00"),
            equity_high=Decimal("10200.00"),  # Hit a high of 10200
            equity_low=Decimal("9500.00"),  # Dropped to 9500
            equity_end=Decimal("9500.00"),
            max_drawdown_pct=Decimal("6.86"),  # (10200 - 9500) / 10200 * 100
            trades_count=3,
            winning_trades=1,
            losing_trades=2,
        )
        db_session.add(daily_pnl)
        await db_session.commit()

        # Verify drawdown is stored
        result = await db_session.execute(
            select(DailyPnL)
            .where(DailyPnL.tenant_id == TEST_TENANT_ID)
            .where(DailyPnL.session_id == TEST_SESSION_ID)
        )
        record = result.scalar_one()
        assert float(record.max_drawdown_pct) == pytest.approx(6.86, rel=0.01)


class TestBracketOrders:
    """Bracket order relationship tests with real database."""

    async def test_parent_child_relationship(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test parent-child order relationship for brackets."""
        # Create parent order
        parent_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_MARKET,  # Proto int: MARKET=1
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("10"),
            status=ORDER_STATUS_FILLED,  # Proto int: FILLED=5
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),
            take_profit_price=Decimal("160.00"),
        )
        db_session.add(parent_order)
        await db_session.commit()
        await db_session.refresh(parent_order)
        parent_id = parent_order.id

        # Create stop-loss bracket order
        sl_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_SELL,  # Proto int: SELL=2
            order_type=ORDER_TYPE_STOP_LIMIT,  # Proto int: STOP_LIMIT=4
            time_in_force=TIME_IN_FORCE_GTC,  # Proto int: GTC=2
            qty=Decimal("10"),
            stop_price=Decimal("145.00"),
            limit_price=Decimal("144.85"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
            parent_order_id=parent_id,
            bracket_type=BRACKET_TYPE_STOP_LOSS,  # 1 = stop_loss
        )
        db_session.add(sl_order)

        # Create take-profit bracket order
        tp_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_SELL,  # Proto int: SELL=2
            order_type=ORDER_TYPE_LIMIT,  # Proto int: LIMIT=2
            time_in_force=TIME_IN_FORCE_GTC,  # Proto int: GTC=2
            qty=Decimal("10"),
            limit_price=Decimal("160.00"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
            parent_order_id=parent_id,
            bracket_type=BRACKET_TYPE_TAKE_PROFIT,  # 2 = take_profit
        )
        db_session.add(tp_order)
        await db_session.commit()

        # Query bracket orders by parent
        result = await db_session.execute(select(Order).where(Order.parent_order_id == parent_id))
        brackets = result.scalars().all()
        assert len(brackets) == 2
        bracket_types = {b.bracket_type for b in brackets}
        assert bracket_types == {BRACKET_TYPE_STOP_LOSS, BRACKET_TYPE_TAKE_PROFIT}

    async def test_cancel_brackets_on_parent_cancel(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
    ):
        """Test canceling bracket orders when parent is canceled."""
        # Create parent and brackets
        parent_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_BUY,  # Proto int: BUY=1
            order_type=ORDER_TYPE_LIMIT,  # Proto int: LIMIT=2
            time_in_force=TIME_IN_FORCE_DAY,  # Proto int: DAY=1
            qty=Decimal("10"),
            limit_price=Decimal("150.00"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
            stop_loss_price=Decimal("145.00"),
        )
        db_session.add(parent_order)
        await db_session.commit()
        await db_session.refresh(parent_order)
        parent_id = parent_order.id

        sl_order = Order(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            client_order_id=str(uuid4()),
            symbol="AAPL",
            side=ORDER_SIDE_SELL,  # Proto int: SELL=2
            order_type=ORDER_TYPE_STOP_LIMIT,  # Proto int: STOP_LIMIT=4
            time_in_force=TIME_IN_FORCE_GTC,  # Proto int: GTC=2
            qty=Decimal("10"),
            status=ORDER_STATUS_SUBMITTED,  # Proto int: SUBMITTED=2
            filled_qty=Decimal("0"),
            parent_order_id=parent_id,
            bracket_type=BRACKET_TYPE_STOP_LOSS,  # 1 = stop_loss
        )
        db_session.add(sl_order)
        await db_session.commit()

        # Cancel parent
        parent_order.status = ORDER_STATUS_CANCELLED  # Proto int: CANCELLED=6
        parent_order.canceled_at = datetime.now(UTC)

        # Cancel brackets
        result = await db_session.execute(select(Order).where(Order.parent_order_id == parent_id))
        brackets = result.scalars().all()
        for bracket in brackets:
            bracket.status = ORDER_STATUS_CANCELLED  # Proto int: CANCELLED=6
            bracket.canceled_at = datetime.now(UTC)
        await db_session.commit()

        # Verify all cancelled
        result = await db_session.execute(
            select(Order)
            .where(Order.parent_order_id == parent_id)
            .where(Order.status != ORDER_STATUS_CANCELLED)
        )
        active_brackets = result.scalars().all()
        assert len(active_brackets) == 0
