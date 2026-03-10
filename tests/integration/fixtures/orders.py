"""Order and position fixtures for integration tests.

Provides fixtures for creating test orders and positions.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Order, Position, TradingSession
from tests.factories import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_PENDING,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    POSITION_SIDE_LONG,
    POSITION_SIDE_SHORT,
    TIME_IN_FORCE_DAY,
    OrderFactory,
    PositionFactory,
)


@pytest.fixture
async def test_order(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Order:
    """Create a test pending order.

    Returns:
        Order model instance in PENDING status
    """
    order = OrderFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        qty=Decimal("10.00000000"),
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        status=ORDER_STATUS_PENDING,
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def test_limit_order(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Order:
    """Create a test limit order.

    Returns:
        Order model instance with limit price
    """
    order = OrderFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="GOOGL",
        side=ORDER_SIDE_BUY,
        qty=Decimal("5.00000000"),
        order_type=ORDER_TYPE_LIMIT,
        time_in_force=TIME_IN_FORCE_DAY,
        status=ORDER_STATUS_PENDING,
        limit_price=Decimal("140.50000000"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def filled_order(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Order:
    """Create a filled order.

    Returns:
        Order model instance in FILLED status
    """
    from tests.factories import ORDER_STATUS_FILLED

    order = OrderFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="MSFT",
        side=ORDER_SIDE_BUY,
        qty=Decimal("20.00000000"),
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        status=ORDER_STATUS_FILLED,
        filled_qty=Decimal("20.00000000"),
        filled_avg_price=Decimal("380.25000000"),
    )
    order.submitted_at = datetime.now(UTC)
    order.filled_at = datetime.now(UTC)
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def sell_order(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Order:
    """Create a sell order.

    Returns:
        Order model instance for selling
    """
    order = OrderFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="AAPL",
        side=ORDER_SIDE_SELL,
        qty=Decimal("5.00000000"),
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        status=ORDER_STATUS_PENDING,
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def multiple_orders(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> list[Order]:
    """Create multiple orders for pagination testing.

    Returns:
        List of 10 Order model instances with various states
    """
    from tests.factories import (
        ORDER_STATUS_CANCELLED,
        ORDER_STATUS_FILLED,
    )

    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
    statuses = [ORDER_STATUS_PENDING, ORDER_STATUS_FILLED, ORDER_STATUS_CANCELLED]
    orders = []

    for i in range(10):
        order = OrderFactory.create(
            tenant_id=active_trading_session.tenant_id,
            session_id=active_trading_session.id,
            symbol=symbols[i % len(symbols)],
            side=ORDER_SIDE_BUY if i % 2 == 0 else ORDER_SIDE_SELL,
            qty=Decimal(str((i + 1) * 5)),
            order_type=ORDER_TYPE_MARKET,
            time_in_force=TIME_IN_FORCE_DAY,
            status=statuses[i % len(statuses)],
        )
        db_session.add(order)
        orders.append(order)

    await db_session.flush()
    for order in orders:
        await db_session.refresh(order)

    return orders


@pytest.fixture
async def test_position(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Position:
    """Create a test long position.

    Returns:
        Position model instance for AAPL
    """
    position = PositionFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="AAPL",
        side=POSITION_SIDE_LONG,
        qty=Decimal("10.00000000"),
        avg_entry_price=Decimal("175.50000000"),
        current_price=Decimal("180.25000000"),
    )
    db_session.add(position)
    await db_session.flush()
    await db_session.refresh(position)
    return position


@pytest.fixture
async def test_short_position(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Position:
    """Create a test short position.

    Returns:
        Position model instance with SHORT side
    """
    position = PositionFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="TSLA",
        side=POSITION_SIDE_SHORT,
        qty=Decimal("5.00000000"),
        avg_entry_price=Decimal("250.00000000"),
        current_price=Decimal("245.00000000"),
    )
    db_session.add(position)
    await db_session.flush()
    await db_session.refresh(position)
    return position


@pytest.fixture
async def multiple_positions(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> list[Position]:
    """Create multiple positions for a trading session.

    Returns:
        List of 3 Position model instances
    """
    symbols = ["AAPL", "GOOGL", "MSFT"]
    prices = [175.50, 140.25, 380.00]
    positions = []

    for symbol, price in zip(symbols, prices, strict=True):
        position = PositionFactory.create(
            tenant_id=active_trading_session.tenant_id,
            session_id=active_trading_session.id,
            symbol=symbol,
            side=POSITION_SIDE_LONG,
            qty=Decimal("10.00000000"),
            avg_entry_price=Decimal(str(price)),
            current_price=Decimal(str(price * 1.02)),  # 2% gain
        )
        db_session.add(position)
        positions.append(position)

    await db_session.flush()
    for position in positions:
        await db_session.refresh(position)

    return positions


@pytest.fixture
async def closed_position(
    db_session: AsyncSession,
    active_trading_session: TradingSession,
) -> Position:
    """Create a closed position with realized P&L.

    Returns:
        Position model instance with is_open=False
    """
    position = PositionFactory.create(
        tenant_id=active_trading_session.tenant_id,
        session_id=active_trading_session.id,
        symbol="NVDA",
        side=POSITION_SIDE_LONG,
        qty=Decimal("0.00000000"),  # Fully closed
        avg_entry_price=Decimal("500.00000000"),
        current_price=Decimal("550.00000000"),
        realized_pl=Decimal("500.00"),  # $50 gain on 10 shares
        is_open=False,
    )
    position.closed_at = datetime.now(UTC)
    db_session.add(position)
    await db_session.flush()
    await db_session.refresh(position)
    return position


@pytest.fixture
async def second_tenant_order(
    db_session: AsyncSession,
    second_tenant_trading_session: TradingSession,
) -> Order:
    """Create an order belonging to the second tenant.

    Used for tenant isolation testing.
    """
    order = OrderFactory.create(
        tenant_id=second_tenant_trading_session.tenant_id,
        session_id=second_tenant_trading_session.id,
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        qty=Decimal("100.00000000"),
        order_type=ORDER_TYPE_MARKET,
        status=ORDER_STATUS_PENDING,
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)
    return order


@pytest.fixture
async def second_tenant_position(
    db_session: AsyncSession,
    second_tenant_trading_session: TradingSession,
) -> Position:
    """Create a position belonging to the second tenant.

    Used for tenant isolation testing.
    """
    position = PositionFactory.create(
        tenant_id=second_tenant_trading_session.tenant_id,
        session_id=second_tenant_trading_session.id,
        symbol="AAPL",
        side=POSITION_SIDE_LONG,
        qty=Decimal("100.00000000"),
        avg_entry_price=Decimal("175.00000000"),
    )
    db_session.add(position)
    await db_session.flush()
    await db_session.refresh(position)
    return position
