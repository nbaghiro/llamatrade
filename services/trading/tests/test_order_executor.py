"""Test order executor."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from llamatrade_alpaca import AlpacaError, OrderNotFoundError
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
)

from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, RiskCheckResult


@pytest.fixture
def mock_alert_service():
    """Create a mock alert service."""
    service = AsyncMock()
    service.on_order_filled = AsyncMock()
    service.on_order_rejected = AsyncMock()
    service.on_stop_loss_hit = AsyncMock()
    service.on_take_profit_hit = AsyncMock()
    service.on_position_opened = AsyncMock()
    service.on_position_closed = AsyncMock()
    return service


@pytest.fixture
def order_executor(mock_db, mock_alpaca_client, mock_risk_manager):
    """Create order executor with mocked dependencies."""
    return OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
    )


@pytest.fixture
def order_executor_with_alerts(mock_db, mock_alpaca_client, mock_risk_manager, mock_alert_service):
    """Create order executor with alert service."""
    return OrderExecutor(
        db=mock_db,
        alpaca_client=mock_alpaca_client,
        risk_manager=mock_risk_manager,
        alert_service=mock_alert_service,
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
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_MARKET,
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
        assert result.side == ORDER_SIDE_BUY  # Proto enum: 1
        assert result.qty == 10.0
        assert result.status in [ORDER_STATUS_SUBMITTED, ORDER_STATUS_ACCEPTED]
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
            side=ORDER_SIDE_SELL,
            qty=5.0,
            order_type=ORDER_TYPE_LIMIT,
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
        assert result.order_type == ORDER_TYPE_LIMIT  # Proto enum: 2
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
            side=ORDER_SIDE_BUY,
            qty=1000.0,
            order_type=ORDER_TYPE_MARKET,
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
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_MARKET,
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
        mock_order.status = ORDER_STATUS_PENDING
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is True
        assert mock_order.status == ORDER_STATUS_CANCELLED
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
        mock_order.status = ORDER_STATUS_FILLED
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
        """Test mapping common Alpaca statuses to proto enum values."""
        assert order_executor._map_alpaca_status("new") == ORDER_STATUS_SUBMITTED
        assert order_executor._map_alpaca_status("accepted") == ORDER_STATUS_ACCEPTED
        assert order_executor._map_alpaca_status("filled") == ORDER_STATUS_FILLED
        assert order_executor._map_alpaca_status("canceled") == ORDER_STATUS_CANCELLED
        assert order_executor._map_alpaca_status("rejected") == ORDER_STATUS_REJECTED
        assert order_executor._map_alpaca_status("partially_filled") == ORDER_STATUS_PARTIAL
        assert order_executor._map_alpaca_status("expired") == ORDER_STATUS_EXPIRED

    def test_map_unknown_status_passthrough(self, order_executor):
        """Test that unknown statuses default to PENDING."""
        # Unknown statuses now default to ORDER_STATUS_PENDING (1)
        assert order_executor._map_alpaca_status("UNKNOWN") == ORDER_STATUS_PENDING
        assert order_executor._map_alpaca_status("CustomStatus") == ORDER_STATUS_PENDING


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
            status=ORDER_STATUS_FILLED,
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

    async def test_cancel_order_alpaca_api_error(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test canceling an order when Alpaca returns API error."""
        mock_order.status = ORDER_STATUS_SUBMITTED
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        # Alpaca fails to cancel - raises AlpacaError
        mock_alpaca_client.cancel_order.side_effect = AlpacaError("API Error", 500)

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        assert result is False

    async def test_cancel_order_not_found_at_alpaca(
        self,
        order_executor,
        mock_db,
        mock_alpaca_client,
        mock_order,
        tenant_id,
        order_id,
    ):
        """Test canceling an order when Alpaca says not found (handled gracefully)."""
        mock_order.status = ORDER_STATUS_SUBMITTED
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_db.execute.return_value = mock_result

        # Alpaca says order not found - raises OrderNotFoundError
        # This is handled gracefully (order may have been filled/cancelled already)
        mock_alpaca_client.cancel_order.side_effect = OrderNotFoundError("not-found-id")

        result = await order_executor.cancel_order(
            order_id=order_id,
            tenant_id=tenant_id,
        )

        # Should still succeed locally - order is marked cancelled
        assert result is True
        assert mock_order.status == ORDER_STATUS_CANCELLED


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
        mock_order.status = ORDER_STATUS_SUBMITTED
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute.return_value = mock_result

        # Alpaca says order is now filled - use Order model
        mock_alpaca_order = AlpacaOrder(
            id="alpaca-order-123",
            symbol="AAPL",
            qty=10.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.DAY,
            filled_qty=10.0,
            filled_avg_price=150.0,
            created_at=datetime.now(UTC),
        )
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
        mock_order.status = ORDER_STATUS_SUBMITTED
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db.execute.return_value = mock_result

        # Alpaca says order is still new (maps to submitted) - use Order model
        mock_alpaca_order = AlpacaOrder(
            id="alpaca-order-123",
            symbol="AAPL",
            qty=10.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.NEW,  # Maps to "submitted"
            time_in_force=AlpacaTimeInForce.DAY,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now(UTC),
        )
        mock_alpaca_client.get_order.return_value = mock_alpaca_order

        updated = await order_executor.sync_all_pending_orders(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        assert updated == 0


class TestAlertWiring:
    """Tests for alert service integration."""

    async def test_risk_rejection_sends_alert(
        self,
        order_executor_with_alerts,
        mock_risk_manager,
        mock_alert_service,
        tenant_id,
        session_id,
    ):
        """Test that risk check rejection sends alert."""
        mock_risk_manager.check_order.return_value = RiskCheckResult(
            passed=False,
            violations=["Position too large"],
        )

        order = OrderCreate(
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=1000.0,
            order_type=ORDER_TYPE_MARKET,
        )

        with pytest.raises(ValueError, match="Risk check failed"):
            await order_executor_with_alerts.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
            )

        # Verify alert was sent
        mock_alert_service.on_order_rejected.assert_called_once()
        call_kwargs = mock_alert_service.on_order_rejected.call_args.kwargs
        assert call_kwargs["symbol"] == "AAPL"
        assert call_kwargs["side"] == "buy"
        assert "Position too large" in call_kwargs["reason"]

    async def test_alpaca_failure_sends_alert(
        self,
        order_executor_with_alerts,
        mock_db,
        mock_alpaca_client,
        mock_alert_service,
        tenant_id,
        session_id,
    ):
        """Test that Alpaca API failure sends rejection alert."""
        mock_alpaca_client.submit_order.side_effect = Exception("API Error")

        async def mock_refresh(obj):
            from uuid import uuid4

            obj.id = uuid4()

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        order = OrderCreate(
            symbol="GOOGL",
            side=ORDER_SIDE_SELL,
            qty=5.0,
            order_type=ORDER_TYPE_MARKET,
        )

        with pytest.raises(ValueError, match="Failed to submit order"):
            await order_executor_with_alerts.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
            )

        # Verify rejection alert was sent
        mock_alert_service.on_order_rejected.assert_called_once()
        call_kwargs = mock_alert_service.on_order_rejected.call_args.kwargs
        assert call_kwargs["symbol"] == "GOOGL"
        assert "Alpaca API error" in call_kwargs["reason"]
