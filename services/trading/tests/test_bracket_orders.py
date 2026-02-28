"""Test bracket order functionality (stop-loss/take-profit)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from llamatrade_db.models.trading import Order
from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, OrderSide, OrderType, TimeInForce


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
    order.side = "buy"
    order.order_type = "market"
    order.time_in_force = "day"
    order.qty = Decimal("10")
    order.limit_price = None
    order.stop_price = None
    order.status = "filled"
    order.filled_qty = Decimal("10")
    order.filled_avg_price = Decimal("150.00")
    order.stop_loss_price = Decimal("145.00")  # -3.3% SL
    order.take_profit_price = Decimal("165.00")  # +10% TP
    order.parent_order_id = None
    order.bracket_type = None
    order.metadata_ = {"bracket_tif": "gtc"}
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
            side=OrderSide.BUY,
            qty=10.0,
            order_type=OrderType.MARKET,
            stop_loss_price=145.0,
            take_profit_price=165.0,
            bracket_time_in_force=TimeInForce.GTC,
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
        assert captured_order.metadata_ == {"bracket_tif": "gtc"}

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
            side=OrderSide.BUY,
            qty=10.0,
            order_type=OrderType.MARKET,
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
            return {
                "id": f"alpaca-bracket-{call_count}",
                "status": "accepted",
            }

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
        sl_created = [o for o in orders_created if o.bracket_type == "stop_loss"]
        assert len(sl_created) == 1
        assert sl_created[0].side == "sell"  # Exit side opposite of buy
        assert sl_created[0].order_type == "stop_limit"
        assert sl_created[0].parent_order_id == mock_parent_order.id

        # Verify TP order properties
        tp_created = [o for o in orders_created if o.bracket_type == "take_profit"]
        assert len(tp_created) == 1
        assert tp_created[0].side == "sell"
        assert tp_created[0].order_type == "limit"
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
        mock_parent_order.side = "sell"
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
            return_value={"id": "alpaca-123", "status": "accepted"}
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        # Exit side should be BUY for a SELL parent
        assert len(orders_created) == 1
        assert orders_created[0].side == "buy"


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
            return_value={"id": "alpaca-123", "status": "accepted"}
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
        sl_order.status = "filled"

        # The sibling TP order (should be cancelled)
        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.parent_order_id = parent_id
        tp_order.bracket_type = "take_profit"
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = "submitted"
        tp_order.metadata_ = None

        # Mock query to return sibling
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(sl_order)

        # Verify TP was cancelled via Alpaca
        mock_alpaca_client.cancel_order.assert_called_once_with("alpaca-tp-123")
        assert tp_order.status == "cancelled"
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
        tp_order.status = "filled"

        # The sibling SL order (should be cancelled)
        sl_order = MagicMock(spec=Order)
        sl_order.id = uuid4()
        sl_order.parent_order_id = parent_id
        sl_order.bracket_type = "stop_loss"
        sl_order.alpaca_order_id = "alpaca-sl-123"
        sl_order.status = "submitted"
        sl_order.metadata_ = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sl_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        await bracket_order_executor._handle_bracket_fill(tp_order)

        mock_alpaca_client.cancel_order.assert_called_once_with("alpaca-sl-123")
        assert sl_order.status == "cancelled"


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
        sl_order.status = "submitted"

        tp_order = MagicMock(spec=Order)
        tp_order.id = uuid4()
        tp_order.alpaca_order_id = "alpaca-tp-123"
        tp_order.status = "submitted"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sl_order, tp_order]
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await bracket_order_executor.cancel_bracket_orders(
            parent_order_id=parent_id,
            tenant_id=tenant_id,
        )

        assert count == 2
        assert mock_alpaca_client.cancel_order.call_count == 2
        assert sl_order.status == "cancelled"
        assert tp_order.status == "cancelled"

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
        parent_order.status = "submitted"
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
        parent_order.symbol = "AAPL"
        parent_order.side = "buy"
        parent_order.order_type = "market"
        parent_order.qty = Decimal("10")
        parent_order.limit_price = None
        parent_order.stop_price = None
        parent_order.status = "submitted"  # Will change to filled
        parent_order.filled_qty = Decimal("0")
        parent_order.stop_loss_price = Decimal("145.0")
        parent_order.take_profit_price = Decimal("165.0")
        parent_order.parent_order_id = None
        parent_order.bracket_type = None  # Explicitly set to None
        parent_order.filled_avg_price = None
        parent_order.submitted_at = None
        parent_order.created_at = MagicMock()
        parent_order.filled_at = None
        parent_order.metadata_ = {"bracket_tif": "gtc"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = parent_order
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Alpaca says order is filled
        mock_alpaca_client.get_order = AsyncMock(
            return_value={
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "150.50",
                "filled_at": "2024-01-15T10:01:00Z",
            }
        )

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
            return_value={"id": "alpaca-bracket-123", "status": "accepted"}
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
        parent_order.symbol = "AAPL"
        parent_order.side = "buy"
        parent_order.qty = Decimal("10")
        parent_order.order_type = "market"
        parent_order.limit_price = None
        parent_order.stop_price = None
        parent_order.status = "filled"
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
        sl_order.bracket_type = "stop_loss"

        tp_order = MagicMock(spec=Order)
        tp_order.id = tp_order_id
        tp_order.bracket_type = "take_profit"

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
            return_value={"id": "alpaca-123", "status": "accepted"}
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
            return_value={"id": "alpaca-123", "status": "accepted"}
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        assert len(orders_created) == 1
        sl_order = orders_created[0]
        assert sl_order.order_type == "stop_limit"
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
            return_value={"id": "alpaca-123", "status": "accepted"}
        )

        await bracket_order_executor._submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order=mock_parent_order,
            filled_price=150.0,
        )

        assert len(orders_created) == 1
        tp_order = orders_created[0]
        assert tp_order.order_type == "limit"
        assert tp_order.stop_price is None
        assert tp_order.limit_price == Decimal("165.0")
