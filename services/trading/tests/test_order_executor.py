"""Test order executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, OrderSide, OrderStatus, OrderType, RiskCheckResult


@pytest.fixture
def order_executor(mock_db, mock_alpaca_client, mock_risk_manager):
    """Create order executor with mocked dependencies."""
    return OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
    )


class TestSubmitOrder:
    """Tests for submit_order."""

    async def test_submit_market_order_success(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        session_id,
    ):
        """Test submitting a market order successfully."""
        order = OrderCreate(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=10.0,
            order_type=OrderType.MARKET,
        )

        # Mock the database refresh to set an ID
        async def mock_refresh(obj):
            from uuid import uuid4

            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await order_executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=order,
        )

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.side == "buy"
        assert result.qty == 10.0
        assert result.status in [OrderStatus.SUBMITTED, OrderStatus.ACCEPTED]
        mock_db.add.assert_called_once()
        mock_alpaca_client.submit_order.assert_called_once()

    async def test_submit_limit_order_success(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        session_id,
    ):
        """Test submitting a limit order successfully."""
        order = OrderCreate(
            symbol="GOOGL",
            side=OrderSide.SELL,
            qty=5.0,
            order_type=OrderType.LIMIT,
            limit_price=150.0,
        )

        async def mock_refresh(obj):
            from uuid import uuid4

            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await order_executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=order,
        )

        assert result is not None
        assert result.symbol == "GOOGL"
        assert result.order_type == "limit"
        mock_alpaca_client.submit_order.assert_called_once()

    async def test_submit_order_risk_check_failed(
        self,
        order_executor,
        mock_risk_manager,
        tenant_id,
        session_id,
    ):
        """Test order rejection due to risk check failure."""
        mock_risk_manager.check_order.return_value = RiskCheckResult(
            passed=False,
            violations=["Order value exceeds limit"],
        )

        order = OrderCreate(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=1000.0,
            order_type=OrderType.MARKET,
        )

        with pytest.raises(ValueError, match="Risk check failed"):
            await order_executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
            )

    async def test_submit_order_alpaca_failure(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        tenant_id,
        session_id,
    ):
        """Test handling Alpaca API failure."""
        mock_alpaca_client.submit_order.side_effect = Exception("API Error")

        async def mock_refresh(obj):
            from uuid import uuid4

            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        order = OrderCreate(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=10.0,
            order_type=OrderType.MARKET,
        )

        with pytest.raises(ValueError, match="Failed to submit order"):
            await order_executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
            )

        # Verify order was marked as rejected
        mock_db.commit.assert_called()


class TestGetOrder:
    """Tests for get_order."""

    async def test_get_order_found(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test getting an existing order."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.get_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        assert result.id == order_id
        assert result.symbol == "AAPL"

    async def test_get_order_not_found(
        self,
        order_executor,
        mock_db,
        tenant_id,
        order_id,
    ):
        """Test getting a non-existent order."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await order_executor.get_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is None


class TestCancelOrder:
    """Tests for cancel_order."""

    async def test_cancel_pending_order(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test canceling a pending order."""
        mock_order.status = "pending"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is True
        assert mock_order.status == "cancelled"
        mock_alpaca_client.cancel_order.assert_called_once()
        mock_db.commit.assert_called()

    async def test_cancel_filled_order_fails(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test that canceling a filled order fails."""
        mock_order.status = "filled"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is False

    async def test_cancel_nonexistent_order(
        self,
        order_executor,
        mock_db,
        tenant_id,
        order_id,
    ):
        """Test canceling a non-existent order."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is False


class TestSyncOrderStatus:
    """Tests for sync_order_status."""

    async def test_sync_order_status_filled(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test syncing an order that has been filled."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.sync_order_status(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is not None
        mock_alpaca_client.get_order.assert_called_once_with("alpaca-order-123")
        mock_db.commit.assert_called()

    async def test_sync_order_without_alpaca_id(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test syncing an order without an Alpaca ID."""
        mock_order.alpaca_order_id = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.sync_order_status(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is None


class TestMapAlpacaStatus:
    """Tests for _map_alpaca_status."""

    def test_map_common_statuses(self, order_executor):
        """Test mapping common Alpaca statuses."""
        assert order_executor._map_alpaca_status("new") == "submitted"
        assert order_executor._map_alpaca_status("accepted") == "accepted"
        assert order_executor._map_alpaca_status("filled") == "filled"
        assert order_executor._map_alpaca_status("canceled") == "cancelled"
        assert order_executor._map_alpaca_status("rejected") == "rejected"
        assert order_executor._map_alpaca_status("partially_filled") == "partial"
        assert order_executor._map_alpaca_status("expired") == "expired"

    def test_map_unknown_status_passthrough(self, order_executor):
        """Test that unknown statuses pass through as lowercase."""
        assert order_executor._map_alpaca_status("UNKNOWN") == "unknown"
        assert order_executor._map_alpaca_status("CustomStatus") == "customstatus"


class TestListOrders:
    """Tests for list_orders."""

    async def test_list_orders_no_filters(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
    ):
        """Test listing orders without filters."""
        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock orders query
        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = [mock_order]

        mock_db.execute.side_effect = [mock_count_result, mock_orders_result]

        orders, total = await order_executor.list_orders(
            tenant_id=tenant_id,
        )

        assert total == 1
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"

    async def test_list_orders_with_session_filter(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
        session_id,
    ):
        """Test listing orders filtered by session."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = [mock_order]

        mock_db.execute.side_effect = [mock_count_result, mock_orders_result]

        orders, total = await order_executor.list_orders(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        assert total == 1
        assert len(orders) == 1

    async def test_list_orders_with_status_filter(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
    ):
        """Test listing orders filtered by status."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = [mock_order]

        mock_db.execute.side_effect = [mock_count_result, mock_orders_result]

        orders, total = await order_executor.list_orders(
            tenant_id=tenant_id,
            status=OrderStatus.FILLED,
        )

        assert total == 1

    async def test_list_orders_pagination(
        self,
        order_executor,
        mock_db,
        mock_order,
        tenant_id,
    ):
        """Test listing orders with pagination."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = [mock_order]

        mock_db.execute.side_effect = [mock_count_result, mock_orders_result]

        orders, total = await order_executor.list_orders(
            tenant_id=tenant_id,
            page=2,
            page_size=10,
        )

        assert total == 50
        assert len(orders) == 1

    async def test_list_orders_empty(
        self,
        order_executor,
        mock_db,
        tenant_id,
    ):
        """Test listing orders when none exist."""
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_orders_result = MagicMock()
        mock_orders_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_orders_result]

        orders, total = await order_executor.list_orders(
            tenant_id=tenant_id,
        )

        assert total == 0
        assert len(orders) == 0


class TestCancelOrderAlpacaFailure:
    """Tests for cancel_order when Alpaca fails."""

    async def test_cancel_order_alpaca_fails(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test canceling an order when Alpaca returns False."""
        mock_order.status = "submitted"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        # Alpaca fails to cancel
        mock_alpaca_client.cancel_order.return_value = False

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is False


class TestSyncOrderStatusEdgeCases:
    """Edge case tests for sync_order_status."""

    async def test_sync_order_alpaca_returns_none(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test syncing when Alpaca returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        # Alpaca returns None
        mock_alpaca_client.get_order.return_value = None

        result = await order_executor.sync_order_status(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        # Should return current order state
        assert result is not None
        assert result.id == order_id


class TestSyncAllPendingOrders:
    """Tests for sync_all_pending_orders."""

    async def test_sync_all_pending_no_orders(
        self,
        order_executor,
        mock_db,
        tenant_id,
        session_id,
    ):
        """Test syncing when no pending orders exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        updated = await order_executor.sync_all_pending_orders(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        assert updated == 0

    async def test_sync_all_pending_updates_orders(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        session_id,
    ):
        """Test syncing pending orders that get updated."""
        mock_order.status = "submitted"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute.return_value = mock_result

        # Alpaca says order is now filled - use dict since code uses .get()
        mock_alpaca_order = {
            "status": "filled",
            "filled_qty": "10.0",
            "filled_avg_price": "150.0",
            "filled_at": None,
        }
        mock_alpaca_client.get_order.return_value = mock_alpaca_order

        updated = await order_executor.sync_all_pending_orders(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        assert updated == 1
        mock_db.commit.assert_called()

    async def test_sync_all_pending_no_status_change(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        session_id,
    ):
        """Test syncing when order status hasn't changed."""
        mock_order.status = "submitted"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute.return_value = mock_result

        # Alpaca says order is still submitted (new -> submitted mapping) - use dict
        mock_alpaca_order = {
            "status": "new",  # Maps to "submitted"
            "filled_qty": None,
            "filled_avg_price": None,
            "filled_at": None,
        }
        mock_alpaca_client.get_order.return_value = mock_alpaca_order

        updated = await order_executor.sync_all_pending_orders(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        assert updated == 0
