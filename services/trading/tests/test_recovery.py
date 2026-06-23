"""Crash-recovery tests for the order executor (trading-hardening 3A / 11A).

Covers the stranded-order window (DB row committed PENDING before the broker
submit, then a crash) and the recovery paths that close it: idempotent replay
that adopts a broker order or resumes submission, and the reconciliation sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import OrderExecutor

pytestmark = pytest.mark.asyncio


@pytest.fixture
def executor(mock_db, mock_alpaca_client, mock_risk_manager):
    # publisher=None → ledger emission is a no-op (these orders are unattributed).
    return OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=None,
        event_publisher=None,
    )


def _order_row(*, status=ORDER_STATUS_PENDING, alpaca_order_id=None) -> Order:
    o = Order(
        tenant_id=uuid4(),
        session_id=uuid4(),
        client_order_id="lt-deadbeef",
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("10"),
        status=status,
        filled_qty=Decimal("0"),
    )
    o.id = uuid4()
    o.alpaca_order_id = alpaca_order_id
    o.created_at = datetime.now(UTC)
    o.submitted_at = None
    o.filled_avg_price = None
    o.filled_at = None
    o.parent_order_id = None
    o.bracket_type = None
    o.stop_loss_price = None
    o.take_profit_price = None
    o.limit_price = None
    o.stop_price = None
    o.metadata_ = None
    return o


def _broker_order(status: AlpacaOrderStatus, *, filled_qty: float = 0.0) -> AlpacaOrder:
    return AlpacaOrder(
        id="alpaca-xyz",
        client_order_id="lt-deadbeef",
        symbol="AAPL",
        qty=10.0,
        side=AlpacaOrderSide.BUY,
        order_type=AlpacaOrderType.MARKET,
        status=status,
        time_in_force=AlpacaTimeInForce.DAY,
        filled_qty=filled_qty,
        filled_avg_price=150.0 if filled_qty else None,
        created_at=datetime.now(UTC),
    )


# --------------------------------------------------------------------------- #
# _idempotent_replay
# --------------------------------------------------------------------------- #


async def test_replay_returns_existing_when_already_submitted(executor, mock_alpaca_client):
    existing = _order_row(status=ORDER_STATUS_SUBMITTED, alpaca_order_id="alpaca-1")
    result = await executor._idempotent_replay(existing, "lt-deadbeef")
    assert result is not None
    assert result.alpaca_order_id == "alpaca-1"
    # No broker lookup needed — we already have a broker id.
    mock_alpaca_client.get_order_by_client_id.assert_not_called()


async def test_replay_adopts_broker_order_when_stranded(executor, mock_alpaca_client):
    existing = _order_row(status=ORDER_STATUS_PENDING, alpaca_order_id=None)
    mock_alpaca_client.get_order_by_client_id = AsyncMock(
        return_value=_broker_order(AlpacaOrderStatus.FILLED, filled_qty=10.0)
    )
    result = await executor._idempotent_replay(existing, "lt-deadbeef")
    assert result is not None
    assert existing.alpaca_order_id == "alpaca-xyz"
    assert existing.status == ORDER_STATUS_FILLED


async def test_replay_returns_none_when_never_submitted(executor, mock_alpaca_client):
    existing = _order_row(status=ORDER_STATUS_PENDING, alpaca_order_id=None)
    mock_alpaca_client.get_order_by_client_id = AsyncMock(return_value=None)
    result = await executor._idempotent_replay(existing, "lt-deadbeef")
    assert result is None  # caller resumes submission


# --------------------------------------------------------------------------- #
# submit_order resume path
# --------------------------------------------------------------------------- #


async def test_submit_resumes_stranded_row_without_duplicating(
    executor, mock_db, mock_alpaca_client, tenant_id, session_id
):
    from src.models import OrderCreate

    stranded = _order_row(status=ORDER_STATUS_PENDING, alpaca_order_id=None)
    executor._find_order_by_client_id = AsyncMock(return_value=stranded)
    mock_alpaca_client.get_order_by_client_id = AsyncMock(return_value=None)

    order = OrderCreate(symbol="AAPL", side=ORDER_SIDE_BUY, qty=10.0, order_type=ORDER_TYPE_MARKET)
    result = await executor.submit_order(
        tenant_id=tenant_id,
        session_id=session_id,
        order=order,
        signal_timestamp=datetime.now(UTC),
    )
    assert result is not None
    # Resumed the existing row → dispatched to the broker, no duplicate insert.
    mock_alpaca_client.submit_order.assert_called_once()
    mock_db.add.assert_not_called()


# --------------------------------------------------------------------------- #
# recover_stranded_orders sweep
# --------------------------------------------------------------------------- #


def _execute_returns(rows: list[Order]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


async def test_recover_adopts_orders_found_at_broker(
    executor, mock_db, mock_alpaca_client, tenant_id, session_id
):
    stranded = _order_row(status=ORDER_STATUS_PENDING, alpaca_order_id=None)
    mock_db.execute = AsyncMock(return_value=_execute_returns([stranded]))
    mock_alpaca_client.get_order_by_client_id = AsyncMock(
        return_value=_broker_order(AlpacaOrderStatus.NEW)
    )

    count = await executor.recover_stranded_orders(tenant_id, session_id)
    assert count == 1
    assert stranded.alpaca_order_id == "alpaca-xyz"
    assert stranded.status != ORDER_STATUS_PENDING


async def test_recover_rejects_orders_never_submitted(
    executor, mock_db, mock_alpaca_client, tenant_id, session_id
):
    stranded = _order_row(status=ORDER_STATUS_PENDING, alpaca_order_id=None)
    mock_db.execute = AsyncMock(return_value=_execute_returns([stranded]))
    mock_alpaca_client.get_order_by_client_id = AsyncMock(return_value=None)

    count = await executor.recover_stranded_orders(tenant_id, session_id)
    assert count == 1
    assert stranded.status == ORDER_STATUS_REJECTED
    assert stranded.failed_at is not None


async def test_recover_noop_when_none_stranded(
    executor, mock_db, mock_alpaca_client, tenant_id, session_id
):
    mock_db.execute = AsyncMock(return_value=_execute_returns([]))
    count = await executor.recover_stranded_orders(tenant_id, session_id)
    assert count == 0
    mock_alpaca_client.get_order_by_client_id.assert_not_called()


# --------------------------------------------------------------------------- #
# republish_ledger_for_terminal_orders (4A ledger safety net)
# --------------------------------------------------------------------------- #


def _filled_sleeve_order() -> Order:
    o = _order_row(status=ORDER_STATUS_FILLED, alpaca_order_id="alpaca-1")
    o.sleeve_id = uuid4()
    o.account_id = uuid4()
    o.filled_qty = Decimal("10")
    o.filled_avg_price = Decimal("150")
    o.filled_at = datetime.now(UTC)
    return o


async def test_republish_emits_for_terminal_sleeve_orders(
    mock_db, mock_alpaca_client, mock_risk_manager, tenant_id, session_id
):
    publisher = MagicMock()
    publisher.publish_ledger_fill = AsyncMock()
    ex = OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=None,
        event_publisher=publisher,
    )
    mock_db.execute = AsyncMock(return_value=_execute_returns([_filled_sleeve_order()]))

    count = await ex.republish_ledger_for_terminal_orders(tenant_id, session_id)
    assert count == 1
    publisher.publish_ledger_fill.assert_awaited()  # idempotent re-publish of the fill


async def test_republish_noop_without_publisher(
    mock_db, mock_alpaca_client, mock_risk_manager, tenant_id, session_id
):
    ex = OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=None,
        event_publisher=None,
    )
    count = await ex.republish_ledger_for_terminal_orders(tenant_id, session_id)
    assert count == 0
    mock_db.execute.assert_not_called()
