"""Bracket-order rollback: a failed SL/TP leg cancels submitted legs and alerts.

Drives ``_submit_bracket_orders`` with a spec'd broker double whose stop-loss /
take-profit submissions raise, proving the atomic rollback contract: submitted
legs are cancelled at the broker, both DB rows are marked rejected with the
rollback marker, and the CRITICAL unprotected-position alert fires.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import AlpacaError, TradingClient
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_REJECTED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
    TIME_IN_FORCE_GTC,
)

from src.executor.order_executor import OrderExecutor
from src.services.alert_service import AlertService


def _accepted_alpaca_order(order_id: str) -> AlpacaOrder:
    return AlpacaOrder(
        id=order_id,
        symbol="AAPL",
        qty=Decimal("10"),
        side=AlpacaOrderSide.SELL,
        order_type=AlpacaOrderType.STOP_LIMIT,
        status=AlpacaOrderStatus.ACCEPTED,
        time_in_force=AlpacaTimeInForce.GTC,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def broker() -> AsyncMock:
    """Spec'd broker double so drift from the real TradingClient surface fails loudly."""
    return AsyncMock(spec=TradingClient)


@pytest.fixture
def alerts() -> AsyncMock:
    return AsyncMock(spec=AlertService)


@pytest.fixture
def parent_order(tenant_id, session_id) -> MagicMock:
    order = MagicMock(spec=Order)
    order.id = uuid4()
    order.tenant_id = tenant_id
    order.session_id = session_id
    order.symbol = "AAPL"
    order.side = ORDER_SIDE_BUY
    order.order_type = ORDER_TYPE_MARKET
    order.time_in_force = TIME_IN_FORCE_DAY
    order.qty = Decimal("10")
    order.status = ORDER_STATUS_FILLED
    order.filled_qty = Decimal("10")
    order.filled_avg_price = Decimal("150.00")
    order.stop_loss_price = Decimal("145.00")
    order.take_profit_price = Decimal("165.00")
    order.parent_order_id = None
    order.metadata_ = {"bracket_tif": TIME_IN_FORCE_GTC}
    order.sleeve_id = None
    order.account_id = None
    return order


@pytest.fixture
def executor(mock_db, broker, mock_risk_manager, alerts) -> OrderExecutor:
    return OrderExecutor(
        db=mock_db,
        alpaca_client=broker,
        risk_manager=mock_risk_manager,
        alert_service=alerts,
    )


class TestBracketRollback:
    async def test_tp_failure_rolls_back_submitted_sl_and_alerts(
        self, executor, mock_db, broker, alerts, parent_order, tenant_id, session_id
    ):
        """SL submits, TP raises: the SL is cancelled at the broker, both rows are
        rejected with the rollback marker, and the CRITICAL alert fires."""
        broker.submit_order = AsyncMock(
            side_effect=[_accepted_alpaca_order("alpaca-sl-1"), AlpacaError("tp rejected")]
        )
        broker.cancel_order = AsyncMock(return_value=None)

        sl_order, tp_order = await executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=parent_order,
            filled_price=150.0,
        )

        assert (sl_order, tp_order) == (None, None)
        broker.cancel_order.assert_awaited_once_with("alpaca-sl-1")

        rejected = [obj for (obj,), _ in mock_db.add.call_args_list if isinstance(obj, Order)]
        assert len(rejected) == 2
        for row in rejected:
            assert row.status == ORDER_STATUS_REJECTED
            assert row.failed_at is not None
            assert row.metadata_ is not None
            assert row.metadata_["rollback"] is True
            assert "tp rejected" in row.metadata_["error"]

        alerts.on_strategy_error.assert_awaited_once()
        error_text = alerts.on_strategy_error.await_args.kwargs["error"]
        assert "CRITICAL" in error_text
        assert "unprotected" in error_text
        assert "AAPL" in error_text

    async def test_sl_failure_before_any_submission_rolls_back_nothing(
        self, executor, mock_db, broker, alerts, parent_order, tenant_id, session_id
    ):
        """The first (SL) leg raising leaves nothing at the broker to cancel."""
        broker.submit_order = AsyncMock(side_effect=AlpacaError("sl rejected"))
        broker.cancel_order = AsyncMock(return_value=None)

        result = await executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=parent_order,
            filled_price=150.0,
        )

        assert result == (None, None)
        broker.cancel_order.assert_not_awaited()
        rejected = [obj for (obj,), _ in mock_db.add.call_args_list if isinstance(obj, Order)]
        assert all(row.status == ORDER_STATUS_REJECTED for row in rejected)
        alerts.on_strategy_error.assert_awaited_once()
        assert "CRITICAL" in alerts.on_strategy_error.await_args.kwargs["error"]

    async def test_rollback_cancel_failure_is_contained(
        self, executor, broker, alerts, parent_order, tenant_id, session_id
    ):
        """A broker error during rollback cancellation is logged, never raised."""
        broker.submit_order = AsyncMock(
            side_effect=[_accepted_alpaca_order("alpaca-sl-2"), AlpacaError("tp rejected")]
        )
        broker.cancel_order = AsyncMock(side_effect=AlpacaError("cancel also down"))

        result = await executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=parent_order,
            filled_price=150.0,
        )

        assert result == (None, None)
        broker.cancel_order.assert_awaited_once_with("alpaca-sl-2")
        alerts.on_strategy_error.assert_awaited_once()

    async def test_rollback_helper_cancels_every_submitted_id(self, executor, broker):
        broker.cancel_order = AsyncMock(side_effect=[None, AlpacaError("gone"), None])

        await executor._rollback_bracket_orders(["id-1", "id-2", "id-3"])

        assert [c.args[0] for c in broker.cancel_order.await_args_list] == [
            "id-1",
            "id-2",
            "id-3",
        ]
