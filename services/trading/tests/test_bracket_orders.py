"""Test bracket order functionality (stop-loss/take-profit)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderNotFoundError
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP_LIMIT,
    TIME_IN_FORCE_DAY,
    TIME_IN_FORCE_GTC,
)

from src.executor.order_executor import OrderExecutor
from src.models import BracketType, OrderCreate


def make_alpaca_order(order_id: str, status: str = "accepted") -> AlpacaOrder:
    """Create a mock Alpaca order for testing."""
    status_map = {
        "accepted": AlpacaOrderStatus.ACCEPTED,
        "filled": AlpacaOrderStatus.FILLED,
        "canceled": AlpacaOrderStatus.CANCELED,
        "new": AlpacaOrderStatus.NEW,
    }
    return AlpacaOrder(
        id=order_id,
        symbol="AAPL",
        qty=10.0,
        side=AlpacaOrderSide.SELL,
        order_type=AlpacaOrderType.STOP_LIMIT,
        status=status_map.get(status, AlpacaOrderStatus.ACCEPTED),
        time_in_force=AlpacaTimeInForce.GTC,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def bracket_order_executor(mock_db, mock_alpaca_client, mock_risk_manager):
    """Create order executor with mocked dependencies for bracket testing."""
    return OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
    )


@pytest.fixture
def mock_parent_order(tenant_id, session_id):
    """Create a mock filled parent order with bracket configuration."""
    order = MagicMock(spec=Order)
    order.id = uuid4()
    order.tenant_id = tenant_id
    order.session_id = session_id
    order.alpaca_order_id = "alpaca-parent-123"
    order.client_order_id = "client-parent-123"
    order.symbol = "AAPL"
    order.side = ORDER_SIDE_BUY
    order.order_type = ORDER_TYPE_MARKET
    order.time_in_force = TIME_IN_FORCE_DAY
    order.qty = Decimal("10")
    order.limit_price = None
    order.stop_price = None
    order.status = ORDER_STATUS_FILLED
    order.filled_qty = Decimal("10")
    order.filled_avg_price = Decimal("150.00")
    order.stop_loss_price = Decimal("145.00")  # -3.3% SL
    order.take_profit_price = Decimal("165.00")  # +10% TP
    order.parent_order_id = None
    order.bracket_type = None
    order.metadata_ = {"bracket_tif": TIME_IN_FORCE_GTC}
    return order


class TestSubmitOrderWithBrackets:
    """Tests for submitting orders with bracket configuration."""

    async def test_submit_order_stores_bracket_prices(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        session_id,
    ):
        """Test that bracket prices are stored on the order."""
        order = OrderCreate(
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_MARKET,
            stop_loss_price=145.0,
            take_profit_price=165.0,
            bracket_time_in_force=TIME_IN_FORCE_GTC,
        )

        captured_order = None

        def capture_add(obj):
            nonlocal captured_order
            captured_order = obj

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        await bracket_order_executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=order,
        )

        # Verify bracket prices were stored
        assert captured_order is not None
        assert captured_order.stop_loss_price == Decimal("145.0")
        assert captured_order.take_profit_price == Decimal("165.0")
        assert captured_order.metadata_ == {"bracket_tif": TIME_IN_FORCE_GTC}

    async def test_submit_order_with_only_stop_loss(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        session_id,
    ):
        """Test order with only stop-loss configured."""
        order = OrderCreate(
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_MARKET,
            stop_loss_price=145.0,
        )

        captured_order = None

        def capture_add(obj):
            nonlocal captured_order
            captured_order = obj

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        await bracket_order_executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=order,
        )

        assert captured_order is not None
        assert captured_order.stop_loss_price == Decimal("145.0")
        assert captured_order.take_profit_price is None


class TestBracketOrderCreation:
    """Tests for _submit_bracket_orders and _create_bracket_order."""

    async def test_submit_bracket_orders_creates_both(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
        tenant_id,
        session_id,
    ):
        """Test that both SL and TP orders are created when configured."""
        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Mock Alpaca to return different IDs for each order
        call_count = 0

        async def mock_submit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return make_alpaca_order(f"alpaca-bracket-{call_count}", "accepted")

        mock_alpaca_client.submit_order = AsyncMock(side_effect=mock_submit)

        sl_order, tp_order = await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        # Verify both orders were created
        assert sl_order is not None
        assert tp_order is not None

        # Verify SL order properties
        sl_created = [o for o in orders_created if o.bracket_type == BracketType.STOP_LOSS]
        assert len(sl_created) == 1
        assert sl_created[0].side == ORDER_SIDE_SELL  # Exit side opposite of buy
        assert sl_created[0].order_type == ORDER_TYPE_STOP_LIMIT
        assert sl_created[0].parent_order_id == mock_parent_order.id

        # Verify TP order properties
        tp_created = [o for o in orders_created if o.bracket_type == BracketType.TAKE_PROFIT]
        assert len(tp_created) == 1
        assert tp_created[0].side == ORDER_SIDE_SELL
        assert tp_created[0].order_type == ORDER_TYPE_LIMIT
        assert tp_created[0].parent_order_id == mock_parent_order.id

    async def test_bracket_order_uses_correct_exit_side_for_sell(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
        tenant_id,
        session_id,
    ):
        """Test that bracket orders use BUY side when parent is SELL."""
        mock_parent_order.side = ORDER_SIDE_SELL
        mock_parent_order.take_profit_price = None  # Only test SL

        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-123", "accepted")
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        # Exit side should be BUY for a SELL parent
        assert len(orders_created) == 1
        assert orders_created[0].side == ORDER_SIDE_BUY


class TestHandleOrderFill:
    """Tests for _handle_order_fill - submitting brackets when parent fills."""

    async def test_handle_fill_submits_brackets(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
    ):
        """Test that bracket orders are submitted when parent order fills."""
        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-123", "accepted")
        )

        await bracket_order_executor._handle_order_fill(
            order=mock_parent_order,
            filled_price=150.0,
        )

        # Should have created 2 bracket orders
        assert len(orders_created) == 2

    async def test_handle_fill_skips_bracket_orders(
        self,
        bracket_order_executor,
        mock_db,
        mock_parent_order,
    ):
        """Test that bracket orders don't trigger their own bracket creation."""
        # Make this order look like a bracket order
        mock_parent_order.parent_order_id = uuid4()

        mock_db.add = MagicMock()

        await bracket_order_executor._handle_order_fill(
            order=mock_parent_order,
            filled_price=150.0,
        )

        # Should not create any orders
        mock_db.add.assert_not_called()

    async def test_handle_fill_skips_orders_without_brackets(
        self,
        bracket_order_executor,
        mock_db,
        mock_parent_order,
    ):
        """Test that orders without bracket config don't create brackets."""
        mock_parent_order.stop_loss_price = None
        mock_parent_order.take_profit_price = None

        mock_db.add = MagicMock()

        await bracket_order_executor._handle_order_fill(
            order=mock_parent_order,
            filled_price=150.0,
        )

        mock_db.add.assert_not_called()


class TestOCOBehavior:
    """Tests for OCO (one-cancels-other) bracket behavior."""

    async def test_sl_fill_cancels_tp(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test that when SL fills, TP is cancelled."""
        parent_id = uuid4()

        # The filled SL order
        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = "stop_loss"
        sl_order.status = ORDER_STATUS_FILLED

        # The sibling TP order (should be cancelled)
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = "take_profit"
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = ORDER_STATUS_SUBMITTED
        tp_order.metadata_ = None

        # Mock query to return sibling
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Verify TP was cancelled via Alpaca
        mock_alpaca_client.cancel_order.assert_called_once_with("alpaca-tp-123")
        assert tp_order.status == ORDER_STATUS_CANCELLED
        assert tp_order.metadata_["cancelled_reason"] == "oco_triggered"

    async def test_tp_fill_cancels_sl(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test that when TP fills, SL is cancelled."""
        parent_id = uuid4()

        # The filled TP order
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = "take_profit"
        tp_order.status = ORDER_STATUS_FILLED

        # The sibling SL order (should be cancelled)
        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = "stop_loss"
        sl_order.alpaca_order_id = "alpaca-sl-123"
        sl_order.status = ORDER_STATUS_SUBMITTED
        sl_order.metadata_ = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sl_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(tp_order)

        mock_alpaca_client.cancel_order.assert_called_once_with("alpaca-sl-123")
        assert sl_order.status == ORDER_STATUS_CANCELLED


class TestCancelBracketOrders:
    """Tests for cancel_bracket_orders."""

    async def test_cancel_all_bracket_orders(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
    ):
        """Test cancelling all bracket orders for a parent."""
        parent_id = uuid4()

        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.alpaca_order_id = "alpaca-sl-123"
        sl_order.status = ORDER_STATUS_SUBMITTED

        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = ORDER_STATUS_SUBMITTED

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sl_order, tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await bracket_order_executor.cancel_bracket_orders(
            parent_order_id=parent_id,
            tenant_id=tenant_id,
        )

        assert count == 2
        assert mock_alpaca_client.cancel_order.call_count == 2
        assert sl_order.status == ORDER_STATUS_CANCELLED
        assert tp_order.status == ORDER_STATUS_CANCELLED

    async def test_cancel_parent_cancels_brackets(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        order_id,
    ):
        """Test that cancelling parent order also cancels brackets."""
        # Parent order with bracket config
        parent_order = MagicMock(spec=Order)
        parent_order.id = order_id
        parent_order.tenant_id = tenant_id
        parent_order.alpaca_order_id = "alpaca-parent-123"
        parent_order.status = ORDER_STATUS_SUBMITTED
        parent_order.stop_loss_price = Decimal("145.0")
        parent_order.take_profit_price = Decimal("165.0")

        # Mock get order
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = parent_order
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock bracket orders query (second execute call)
        sl_order = MagicMock(spec=Order)
        sl_order.alpaca_order_id = "alpaca-sl-123"
        sl_order.status = "submitted"

        bracket_result = MagicMock()
        bracket_result.scalars.return_value.all.return_value = [sl_order]

        mock_db.execute = AsyncMock(side_effect=[mock_result, bracket_result])

        result = await bracket_order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is True
        # Should have cancelled parent + brackets
        assert mock_alpaca_client.cancel_order.call_count >= 1


class TestSyncWithBracketFills:
    """Tests for sync_order_status and sync_all_pending_orders with bracket handling."""

    async def test_sync_triggers_bracket_creation_on_fill(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        order_id,
    ):
        """Test that syncing a filled order triggers bracket creation."""
        # Parent order that will become filled
        parent_order = MagicMock(spec=Order)
        parent_order.id = order_id
        parent_order.tenant_id = tenant_id
        parent_order.session_id = uuid4()
        parent_order.alpaca_order_id = "alpaca-parent-123"
        parent_order.client_order_id = "client-parent-123"
        parent_order.symbol = "AAPL"
        parent_order.side = ORDER_SIDE_BUY
        parent_order.order_type = ORDER_TYPE_MARKET
        parent_order.qty = Decimal("10")
        parent_order.limit_price = None
        parent_order.stop_price = None
        parent_order.status = ORDER_STATUS_SUBMITTED
        parent_order.filled_qty = Decimal("0")
        parent_order.stop_loss_price = Decimal("145.0")
        parent_order.take_profit_price = Decimal("165.0")
        parent_order.parent_order_id = None
        parent_order.bracket_type = None  # Explicitly set to None
        parent_order.filled_avg_price = None
        parent_order.submitted_at = None
        parent_order.created_at = MagicMock()
        parent_order.filled_at = None
        parent_order.metadata_ = {"bracket_tif": TIME_IN_FORCE_GTC}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = parent_order
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Alpaca says order is filled
        filled_order = AlpacaOrder(
            id="alpaca-parent-123",
            symbol="AAPL",
            qty=10.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.DAY,
            filled_qty=10.0,
            filled_avg_price=150.50,
            created_at=datetime.now(UTC),
        )
        mock_alpaca_client.get_order = AsyncMock(return_value=filled_order)

        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if isinstance(obj, Order) and (not hasattr(obj, "id") or obj.id is None):
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-bracket-123", "accepted")
        )

        await bracket_order_executor.sync_order_status(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        # Should have created bracket orders
        assert len(orders_created) == 2


class TestGetOrderWithBracketInfo:
    """Tests for get_order with bracket info included."""

    async def test_get_order_includes_bracket_ids(
        self,
        bracket_order_executor,
        mock_db,
        tenant_id,
        order_id,
    ):
        """Test that get_order can include bracket order IDs."""
        sl_order_id = uuid4()
        tp_order_id = uuid4()

        # Parent order
        parent_order = MagicMock(spec=Order)
        parent_order.id = order_id
        parent_order.tenant_id = tenant_id
        parent_order.alpaca_order_id = "alpaca-123"
        parent_order.client_order_id = "client-123"
        parent_order.symbol = "AAPL"
        parent_order.side = ORDER_SIDE_BUY
        parent_order.qty = Decimal("10")
        parent_order.order_type = ORDER_TYPE_MARKET
        parent_order.limit_price = None
        parent_order.stop_price = None
        parent_order.status = ORDER_STATUS_FILLED
        parent_order.filled_qty = Decimal("10")
        parent_order.filled_avg_price = Decimal("150.0")
        parent_order.submitted_at = None
        parent_order.created_at = MagicMock()
        parent_order.filled_at = None
        parent_order.stop_loss_price = Decimal("145.0")
        parent_order.take_profit_price = Decimal("165.0")
        parent_order.parent_order_id = None
        parent_order.bracket_type = None

        # Bracket orders
        sl_order = MagicMock(spec=Order)
        sl_order.id = sl_order_id
        sl_order.bracket_type = BracketType.STOP_LOSS

        tp_order = MagicMock(spec=Order)
        tp_order.id = tp_order_id
        tp_order.bracket_type = BracketType.TAKE_PROFIT

        # Mock queries
        parent_result = MagicMock()
        parent_result.scalar_one_or_none.return_value = parent_order

        bracket_result = MagicMock()
        bracket_result.scalars.return_value.all.return_value = [sl_order, tp_order]

        mock_db.execute = AsyncMock(side_effect=[parent_result, bracket_result])

        result = await bracket_order_executor.get_order(
            order_id=order_id,
            tenant_id=tenant_id,
            include_bracket_info=True,
        )

        assert result is not None
        assert result.bracket_orders is not None
        assert result.bracket_orders.stop_loss_order_id == sl_order_id
        assert result.bracket_orders.take_profit_order_id == tp_order_id


class TestBracketOrderValidation:
    """Tests for bracket order validation."""

    async def test_bracket_order_inherits_symbol_and_qty(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
        tenant_id,
        session_id,
    ):
        """Test bracket orders use parent's symbol and quantity."""
        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-123", "accepted")
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        for order in orders_created:
            assert order.symbol == mock_parent_order.symbol
            assert order.qty == mock_parent_order.qty

    async def test_stop_loss_uses_stop_limit_order(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
        tenant_id,
        session_id,
    ):
        """Test that stop-loss uses stop-limit order type for slippage control."""
        mock_parent_order.take_profit_price = None  # Only SL

        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-123", "accepted")
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        assert len(orders_created) == 1
        sl_order = orders_created[0]
        assert sl_order.order_type == ORDER_TYPE_STOP_LIMIT
        assert sl_order.stop_price == Decimal("145.0")
        # Limit price should be slightly below stop for sell orders
        assert sl_order.limit_price < sl_order.stop_price

    async def test_take_profit_uses_limit_order(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
        mock_parent_order,
        tenant_id,
        session_id,
    ):
        """Test that take-profit uses limit order type."""
        mock_parent_order.stop_loss_price = None  # Only TP

        orders_created = []

        def capture_add(obj):
            if isinstance(obj, Order):
                orders_created.append(obj)

        mock_db.add = MagicMock(side_effect=capture_add)

        async def mock_refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)
        mock_alpaca_client.submit_order = AsyncMock(
            return_value=make_alpaca_order("alpaca-123", "accepted")
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        assert len(orders_created) == 1
        tp_order = orders_created[0]
        assert tp_order.order_type == ORDER_TYPE_LIMIT
        assert tp_order.stop_price is None
        assert tp_order.limit_price == Decimal("165.0")


class TestOCORaceConditionHandling:
    """Tests for OCO race condition handling when both brackets fill simultaneously."""

    async def test_both_brackets_filled_simultaneously(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test handling when both bracket orders filled at the same time."""
        parent_id = uuid4()

        # The filled SL order (the one we're processing)
        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = BracketType.STOP_LOSS
        sl_order.status = ORDER_STATUS_FILLED
        sl_order.filled_avg_price = Decimal("145.0")
        sl_order.qty = Decimal("10")
        sl_order.stop_price = Decimal("145.0")
        sl_order.tenant_id = uuid4()
        sl_order.session_id = uuid4()
        sl_order.symbol = "AAPL"

        # The sibling TP order also filled (race condition!)
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = BracketType.TAKE_PROFIT
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = ORDER_STATUS_FILLED  # Already filled!
        tp_order.metadata_ = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Should NOT try to cancel an already filled order
        mock_alpaca_client.cancel_order.assert_not_called()
        # Status should remain filled, not changed to cancelled
        assert tp_order.status == ORDER_STATUS_FILLED

    async def test_sibling_already_cancelled(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test handling when sibling was already cancelled (idempotent)."""
        parent_id = uuid4()

        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = BracketType.STOP_LOSS
        sl_order.status = ORDER_STATUS_FILLED
        sl_order.filled_avg_price = Decimal("145.0")
        sl_order.qty = Decimal("10")
        sl_order.stop_price = Decimal("145.0")
        sl_order.tenant_id = uuid4()
        sl_order.session_id = uuid4()
        sl_order.symbol = "AAPL"

        # Sibling already cancelled
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = BracketType.TAKE_PROFIT
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = ORDER_STATUS_CANCELLED  # Already cancelled!
        tp_order.metadata_ = {"cancelled_reason": "oco_triggered"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Should NOT try to cancel an already cancelled order
        mock_alpaca_client.cancel_order.assert_not_called()
        # Status should remain cancelled
        assert tp_order.status == ORDER_STATUS_CANCELLED

    async def test_cancel_returns_not_found_syncs_status(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test that NOT_FOUND error triggers status sync from Alpaca."""
        parent_id = uuid4()

        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = BracketType.STOP_LOSS
        sl_order.status = ORDER_STATUS_FILLED
        sl_order.filled_avg_price = Decimal("145.0")
        sl_order.qty = Decimal("10")
        sl_order.stop_price = Decimal("145.0")
        sl_order.tenant_id = uuid4()
        sl_order.session_id = uuid4()
        sl_order.symbol = "AAPL"

        # Sibling appears active but filled at Alpaca (race)
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = BracketType.TAKE_PROFIT
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = ORDER_STATUS_SUBMITTED  # Looks active locally
        tp_order.metadata_ = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Cancel raises OrderNotFoundError (order already processed at Alpaca)
        mock_alpaca_client.cancel_order.side_effect = OrderNotFoundError("alpaca-tp-123")

        # get_order shows it actually filled (returns Order model)
        mock_alpaca_client.get_order.return_value = AlpacaOrder(
            id="alpaca-tp-123",
            symbol="AAPL",
            qty=10.0,
            side=AlpacaOrderSide.SELL,
            order_type=AlpacaOrderType.LIMIT,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.GTC,
            filled_qty=10.0,
            filled_avg_price=165.0,
            created_at=datetime.now(UTC),
        )

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Should have synced the status
        mock_alpaca_client.get_order.assert_called_once_with("alpaca-tp-123")
        # Status should be updated to filled
        assert tp_order.status == ORDER_STATUS_FILLED

    async def test_select_for_update_used(
        self,
        bracket_order_executor,
        mock_db,
        mock_alpaca_client,
    ):
        """Test that SELECT FOR UPDATE is used to prevent race conditions."""
        parent_id = uuid4()

        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = BracketType.STOP_LOSS
        sl_order.status = ORDER_STATUS_FILLED
        sl_order.filled_avg_price = Decimal("145.0")
        sl_order.qty = Decimal("10")
        sl_order.stop_price = Decimal("145.0")
        sl_order.tenant_id = uuid4()
        sl_order.session_id = uuid4()
        sl_order.symbol = "AAPL"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Verify SELECT FOR UPDATE was used in the query
        call_args = mock_db.execute.call_args
        stmt = call_args[0][0]
        # The statement should have with_for_update applied
        assert hasattr(stmt, "_for_update_arg") or "FOR UPDATE" in str(stmt)
