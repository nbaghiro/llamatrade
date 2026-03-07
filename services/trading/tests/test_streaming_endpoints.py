"""Tests for gRPC streaming endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.streaming import OrderUpdate, PositionUpdate


class MockServicerContext:
    """Mock gRPC servicer context."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


class TestStreamOrderUpdates:
    """Tests for StreamOrderUpdates endpoint."""

    async def test_stream_order_updates_yields_updates(self) -> None:
        """Test that order updates are streamed correctly."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())
        order_id = str(uuid4())

        # Create mock subscriber that yields updates
        mock_subscriber = MagicMock()

        async def mock_subscribe_orders(sid: str) -> list[OrderUpdate]:
            yield OrderUpdate(
                session_id=session_id,
                order_id=order_id,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                status="filled",
                filled_qty=10.0,
                filled_avg_price=150.50,
                update_type="filled",
            )
            # Stop after one update
            return

        mock_subscriber.subscribe_orders = mock_subscribe_orders
        mock_subscriber.close = AsyncMock()

        # Create mock request
        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.session_id = session_id

        context = MockServicerContext()

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.StreamOrderUpdates(mock_request, context):
                responses.append(response)
                # Cancel after first response to stop the loop
                context.cancel()

            assert len(responses) == 1
            # Proto OrderUpdate has embedded Order message
            update = responses[0]
            assert update.order.id == order_id
            assert update.order.symbol == "AAPL"
            assert update.event_type == "fill"

    async def test_stream_order_updates_closes_on_cancel(self) -> None:
        """Test that subscriber is closed when stream is cancelled."""
        from collections.abc import AsyncIterator

        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        # Create mock subscriber that yields then checks cancelled
        mock_subscriber = MagicMock()

        async def mock_subscribe_orders(sid: str) -> AsyncIterator[OrderUpdate]:
            # Yield one update first
            yield OrderUpdate(
                session_id=session_id,
                order_id="order-123",
                alpaca_order_id=None,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                status="submitted",
            )
            # Then would continue but context is cancelled

        mock_subscriber.subscribe_orders = mock_subscribe_orders
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.session_id = session_id

        context = MockServicerContext()
        context.cancel()  # Pre-cancel

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.StreamOrderUpdates(mock_request, context):
                responses.append(response)

            # Context was pre-cancelled, so should break after first check
            # The generator yields one update, then we check cancelled and break
            assert len(responses) <= 1
            mock_subscriber.close.assert_called_once()

    async def test_stream_order_updates_handles_exception(self) -> None:
        """Test that exceptions are logged and subscriber is closed."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_subscribe_orders_error(sid: str) -> list[OrderUpdate]:
            raise RuntimeError("Redis connection failed")
            yield  # Make it a generator

        mock_subscriber.subscribe_orders = mock_subscribe_orders_error
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.session_id = session_id

        context = MockServicerContext()

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            with pytest.raises(RuntimeError, match="Redis connection failed"):
                async for _ in servicer.StreamOrderUpdates(mock_request, context):
                    pass

            # Subscriber should still be closed
            mock_subscriber.close.assert_called_once()


class TestStreamPositionUpdates:
    """Tests for StreamPositionUpdates endpoint."""

    async def test_stream_position_updates_yields_updates(self) -> None:
        """Test that position updates are streamed correctly."""
        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_subscribe_positions(sid: str) -> list[PositionUpdate]:
            yield PositionUpdate(
                session_id=session_id,
                symbol="AAPL",
                qty=100.0,
                side="long",
                cost_basis=15000.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
                update_type="opened",
            )
            return

        mock_subscriber.subscribe_positions = mock_subscribe_positions
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.session_id = session_id

        context = MockServicerContext()

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.StreamPositionUpdates(mock_request, context):
                responses.append(response)
                context.cancel()

            assert len(responses) == 1
            # Proto PositionUpdate has embedded Position message
            update = responses[0]
            assert update.position.symbol == "AAPL"
            assert update.event_type == "opened"

    async def test_stream_position_updates_closes_on_cancel(self) -> None:
        """Test that subscriber is closed when stream is cancelled."""
        from collections.abc import AsyncIterator

        from src.grpc.servicer import TradingServicer

        session_id = str(uuid4())

        mock_subscriber = MagicMock()

        async def mock_subscribe_positions(sid: str) -> AsyncIterator[PositionUpdate]:
            # Yield one update first
            yield PositionUpdate(
                session_id=session_id,
                symbol="AAPL",
                qty=100.0,
                side="long",
                cost_basis=15000.0,
                market_value=15000.0,
                unrealized_pnl=0.0,
                unrealized_pnl_percent=0.0,
                current_price=150.0,
                update_type="opened",
            )
            # Then would continue but context is cancelled

        mock_subscriber.subscribe_positions = mock_subscribe_positions
        mock_subscriber.close = AsyncMock()

        mock_request = MagicMock()
        mock_request.context.tenant_id = str(uuid4())
        mock_request.session_id = session_id

        context = MockServicerContext()
        context.cancel()

        servicer = TradingServicer()

        with patch("src.grpc.servicer.get_trading_event_subscriber", return_value=mock_subscriber):
            responses = []
            async for response in servicer.StreamPositionUpdates(mock_request, context):
                responses.append(response)

            # Context was pre-cancelled, so should break after first check
            assert len(responses) <= 1
            mock_subscriber.close.assert_called_once()


class TestProtoConversion:
    """Tests for proto conversion helper methods."""

    def test_to_proto_order_update_full(self) -> None:
        """Test converting OrderUpdate with all fields."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id="alpaca-789",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="limit",
            status="filled",
            filled_qty=10.0,
            filled_avg_price=150.50,
            update_type="filled",
        )

        proto = servicer._to_proto_order_update(update)

        # Check embedded Order message
        assert proto.order.id == "order-456"
        assert proto.order.session_id == "session-123"
        assert proto.order.client_order_id == "alpaca-789"
        assert proto.order.symbol == "AAPL"
        assert proto.order.filled_quantity.value == "10.0"
        assert proto.order.average_fill_price.value == "150.5"
        # Check event_type
        assert proto.event_type == "fill"

    def test_to_proto_order_update_minimal(self) -> None:
        """Test converting OrderUpdate with minimal fields."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id=None,
            symbol="AAPL",
            side="sell",
            qty=5.0,
            order_type="market",
            status="submitted",
            # update_type defaults to "status_change"
        )

        proto = servicer._to_proto_order_update(update)

        assert proto.order.id == "order-456"
        assert proto.order.symbol == "AAPL"
        assert proto.order.client_order_id == ""  # Not set
        assert proto.event_type == "status_change"  # Default update_type

    def test_to_proto_order_update_status_mapping(self) -> None:
        """Test that all order statuses are mapped correctly."""
        from llamatrade_proto.generated import trading_pb2

        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()

        test_cases = [
            ("submitted", trading_pb2.ORDER_STATUS_SUBMITTED),
            ("pending", trading_pb2.ORDER_STATUS_PENDING),
            ("accepted", trading_pb2.ORDER_STATUS_ACCEPTED),
            ("partial", trading_pb2.ORDER_STATUS_PARTIAL),
            ("filled", trading_pb2.ORDER_STATUS_FILLED),
            ("cancelled", trading_pb2.ORDER_STATUS_CANCELLED),
            ("rejected", trading_pb2.ORDER_STATUS_REJECTED),
            ("expired", trading_pb2.ORDER_STATUS_EXPIRED),
        ]

        for status_str, expected_proto in test_cases:
            update = OrderUpdate(
                session_id="session-123",
                order_id="order-456",
                alpaca_order_id=None,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                status=status_str,
            )
            proto = servicer._to_proto_order_update(update)
            assert proto.order.status == expected_proto, f"Status {status_str} not mapped correctly"

    def test_to_proto_order_update_event_type_mapping(self) -> None:
        """Test that update_type maps to event_type correctly."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()

        test_cases = [
            ("submitted", "new"),
            ("filled", "fill"),
            ("partial", "partial_fill"),
            ("cancelled", "cancelled"),
            ("rejected", "rejected"),
            ("status_change", "status_change"),
        ]

        for update_type, expected_event_type in test_cases:
            update = OrderUpdate(
                session_id="session-123",
                order_id="order-456",
                alpaca_order_id=None,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                status="filled",
                update_type=update_type,
            )
            proto = servicer._to_proto_order_update(update)
            assert proto.event_type == expected_event_type

    def test_to_proto_position_update_full(self) -> None:
        """Test converting PositionUpdate with all fields."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = PositionUpdate(
            session_id="session-123",
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
        )

        proto = servicer._to_proto_position_update(update)

        # Check embedded Position message
        assert proto.position.session_id == "session-123"
        assert proto.position.symbol == "AAPL"
        assert proto.position.quantity.value == "100.0"
        assert proto.position.cost_basis.value == "15000.0"
        assert proto.position.market_value.value == "15500.0"
        assert proto.position.unrealized_pnl.value == "500.0"
        assert proto.position.unrealized_pnl_percent.value == "3.33"
        assert proto.position.current_price.value == "155.0"
        # Check average_entry_price (cost_basis / qty)
        assert proto.position.average_entry_price.value == "150.0"
        # Check event_type
        assert proto.event_type == "opened"

    def test_to_proto_position_update_short_side(self) -> None:
        """Test converting short position."""
        from llamatrade_proto.generated import trading_pb2

        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = PositionUpdate(
            session_id="session-123",
            symbol="AAPL",
            qty=50.0,
            side="short",
            cost_basis=7500.0,
            market_value=7200.0,
            unrealized_pnl=300.0,
            unrealized_pnl_percent=4.0,
            current_price=144.0,
            update_type="change",
        )

        proto = servicer._to_proto_position_update(update)

        assert proto.position.side == trading_pb2.POSITION_SIDE_SHORT
        assert proto.event_type == "change"

    def test_to_proto_order_update_with_timestamp(self) -> None:
        """Test that timestamp is properly converted."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id=None,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
            timestamp="2025-01-06T12:00:00+00:00",
        )

        proto = servicer._to_proto_order_update(update)

        # Timestamp should be set
        assert proto.timestamp.seconds > 0

    def test_to_proto_position_update_with_timestamp(self) -> None:
        """Test that timestamp is properly converted."""
        from src.grpc.servicer import TradingServicer

        servicer = TradingServicer()
        update = PositionUpdate(
            session_id="session-123",
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
            timestamp="2025-01-06T12:00:00Z",
        )

        proto = servicer._to_proto_position_update(update)

        # Timestamp should be set
        assert proto.timestamp.seconds > 0
