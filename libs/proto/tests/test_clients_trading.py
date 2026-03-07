"""Tests for llamatrade_proto.clients.trading module."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.auth import TenantContext
from llamatrade_proto.clients.trading import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    OrderUpdate,
    Position,
    TimeInForce,
    TradingClient,
)


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_order_side_values(self) -> None:
        """Test OrderSide enum values."""
        assert OrderSide.BUY.value == "buy"
        assert OrderSide.SELL.value == "sell"

    def test_order_side_count(self) -> None:
        """Test OrderSide has expected number of values."""
        assert len(OrderSide) == 2


class TestOrderType:
    """Tests for OrderType enum."""

    def test_order_type_values(self) -> None:
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"
        assert OrderType.TRAILING_STOP.value == "trailing_stop"

    def test_order_type_count(self) -> None:
        """Test OrderType has expected number of values."""
        assert len(OrderType) == 5


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_order_status_values(self) -> None:
        """Test OrderStatus enum values."""
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.SUBMITTED.value == "submitted"
        assert OrderStatus.ACCEPTED.value == "accepted"
        assert OrderStatus.PARTIAL.value == "partial"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        assert OrderStatus.EXPIRED.value == "expired"

    def test_order_status_count(self) -> None:
        """Test OrderStatus has expected number of values."""
        assert len(OrderStatus) == 8


class TestTimeInForce:
    """Tests for TimeInForce enum."""

    def test_time_in_force_values(self) -> None:
        """Test TimeInForce enum values."""
        assert TimeInForce.DAY.value == "day"
        assert TimeInForce.GTC.value == "gtc"
        assert TimeInForce.IOC.value == "ioc"
        assert TimeInForce.FOK.value == "fok"

    def test_time_in_force_count(self) -> None:
        """Test TimeInForce has expected number of values."""
        assert len(TimeInForce) == 4


class TestOrder:
    """Tests for Order dataclass."""

    def test_create_order_minimal(self) -> None:
        """Test creating Order with required fields."""
        order = Order(
            id="order-123",
            client_order_id=None,
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.SUBMITTED,
            quantity=Decimal("10"),
            filled_quantity=Decimal("0"),
            limit_price=None,
            stop_price=None,
            average_fill_price=None,
            time_in_force=TimeInForce.DAY,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            filled_at=None,
        )

        assert order.id == "order-123"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.type == OrderType.MARKET
        assert order.status == OrderStatus.SUBMITTED
        assert order.quantity == Decimal("10")
        assert order.filled_quantity == Decimal("0")
        assert order.limit_price is None
        assert order.filled_at is None

    def test_create_order_limit(self) -> None:
        """Test creating limit Order."""
        order = Order(
            id="order-456",
            client_order_id="client-789",
            symbol="GOOGL",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            quantity=Decimal("5"),
            filled_quantity=Decimal("5"),
            limit_price=Decimal("150.50"),
            stop_price=None,
            average_fill_price=Decimal("150.45"),
            time_in_force=TimeInForce.GTC,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            filled_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        assert order.client_order_id == "client-789"
        assert order.type == OrderType.LIMIT
        assert order.limit_price == Decimal("150.50")
        assert order.average_fill_price == Decimal("150.45")
        assert order.filled_at == datetime(2024, 1, 15, 10, 30, 0)

    def test_create_order_stop_limit(self) -> None:
        """Test creating stop-limit Order."""
        order = Order(
            id="order-789",
            client_order_id=None,
            symbol="TSLA",
            side=OrderSide.SELL,
            type=OrderType.STOP_LIMIT,
            status=OrderStatus.PENDING,
            quantity=Decimal("20"),
            filled_quantity=Decimal("0"),
            limit_price=Decimal("200.00"),
            stop_price=Decimal("195.00"),
            average_fill_price=None,
            time_in_force=TimeInForce.DAY,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            filled_at=None,
        )

        assert order.type == OrderType.STOP_LIMIT
        assert order.limit_price == Decimal("200.00")
        assert order.stop_price == Decimal("195.00")


class TestPosition:
    """Tests for Position dataclass."""

    def test_create_position_long(self) -> None:
        """Test creating long Position."""
        position = Position(
            symbol="AAPL",
            quantity=Decimal("100"),
            side="long",
            cost_basis=Decimal("15000.00"),
            average_entry_price=Decimal("150.00"),
            current_price=Decimal("160.00"),
            market_value=Decimal("16000.00"),
            unrealized_pnl=Decimal("1000.00"),
            unrealized_pnl_percent=Decimal("6.67"),
        )

        assert position.symbol == "AAPL"
        assert position.quantity == Decimal("100")
        assert position.side == "long"
        assert position.average_entry_price == Decimal("150.00")
        assert position.unrealized_pnl == Decimal("1000.00")

    def test_create_position_short(self) -> None:
        """Test creating short Position."""
        position = Position(
            symbol="TSLA",
            quantity=Decimal("50"),
            side="short",
            cost_basis=Decimal("10000.00"),
            average_entry_price=Decimal("200.00"),
            current_price=Decimal("190.00"),
            market_value=Decimal("9500.00"),
            unrealized_pnl=Decimal("500.00"),
            unrealized_pnl_percent=Decimal("5.00"),
        )

        assert position.side == "short"
        assert position.unrealized_pnl == Decimal("500.00")

    def test_create_position_minimal(self) -> None:
        """Test creating Position with optional fields as None."""
        position = Position(
            symbol="MSFT",
            quantity=Decimal("25"),
            side="long",
            cost_basis=Decimal("5000.00"),
            average_entry_price=Decimal("200.00"),
            current_price=None,
            market_value=None,
            unrealized_pnl=None,
            unrealized_pnl_percent=None,
        )

        assert position.current_price is None
        assert position.market_value is None
        assert position.unrealized_pnl is None


class TestOrderUpdate:
    """Tests for OrderUpdate dataclass."""

    def test_create_order_update(self) -> None:
        """Test creating OrderUpdate."""
        order = Order(
            id="order-123",
            client_order_id=None,
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            quantity=Decimal("10"),
            filled_quantity=Decimal("10"),
            limit_price=None,
            stop_price=None,
            average_fill_price=Decimal("155.50"),
            time_in_force=TimeInForce.DAY,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            filled_at=datetime(2024, 1, 15, 10, 0, 5),
        )

        update = OrderUpdate(
            order=order,
            event_type="fill",
            timestamp=datetime(2024, 1, 15, 10, 0, 5),
        )

        assert update.order is order
        assert update.event_type == "fill"
        assert update.timestamp == datetime(2024, 1, 15, 10, 0, 5)


class TestTradingClientInit:
    """Tests for TradingClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test TradingClient initialization with defaults."""
        client = TradingClient()

        assert client._target == "trading:8850"
        assert client._secure is False
        assert client._stub is None

    def test_init_with_custom_target(self) -> None:
        """Test TradingClient initialization with custom target."""
        client = TradingClient("localhost:9000")

        assert client._target == "localhost:9000"

    def test_init_with_secure(self) -> None:
        """Test TradingClient initialization with secure=True."""
        client = TradingClient(secure=True)

        assert client._secure is True

    def test_init_with_interceptors(self) -> None:
        """Test TradingClient initialization with interceptors."""
        interceptor = object()
        client = TradingClient(interceptors=[interceptor])

        assert client._interceptors == [interceptor]


class TestTradingClientStub:
    """Tests for TradingClient stub property."""

    def test_stub_raises_on_missing_generated_code(self) -> None:
        """Test stub raises RuntimeError when generated code is missing."""
        client = TradingClient()

        with patch("grpc.aio.insecure_channel"):
            with patch.dict("sys.modules", {"llamatrade_proto.generated": None}):
                with pytest.raises((RuntimeError, ImportError)):
                    _ = client.stub


class TestTradingClientSubmitOrder:
    """Tests for TradingClient.submit_order method."""

    @pytest.mark.asyncio
    async def test_submit_order_market_buy(self) -> None:
        """Test submit_order for a market buy order."""
        client = TradingClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        # Create mock proto order
        mock_quantity = MagicMock()
        mock_quantity.value = "10"

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.client_order_id = ""
        mock_order.symbol = "AAPL"
        mock_order.side = 1  # BUY
        mock_order.type = 1  # MARKET
        mock_order.status = 1  # NEW
        mock_order.time_in_force = 1  # DAY
        mock_order.quantity = mock_quantity
        mock_order.HasField = lambda field: field in ["quantity", "created_at"]
        mock_order.filled_quantity = MagicMock(value="0")
        mock_order.limit_price = None
        mock_order.stop_price = None
        mock_order.average_fill_price = None
        mock_order.created_at = mock_created_at
        mock_order.filled_at = None

        mock_response = MagicMock()
        mock_response.order = mock_order

        mock_stub = MagicMock()
        mock_stub.SubmitOrder = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        # Mock the trading_pb2 module
        mock_trading_pb2 = MagicMock()
        mock_trading_pb2.ORDER_SIDE_BUY = 1
        mock_trading_pb2.ORDER_SIDE_SELL = 2
        mock_trading_pb2.ORDER_TYPE_MARKET = 1
        mock_trading_pb2.ORDER_TYPE_LIMIT = 2
        mock_trading_pb2.ORDER_TYPE_STOP = 3
        mock_trading_pb2.ORDER_TYPE_STOP_LIMIT = 4
        mock_trading_pb2.ORDER_TYPE_TRAILING_STOP = 5
        mock_trading_pb2.TIME_IN_FORCE_DAY = 1
        mock_trading_pb2.TIME_IN_FORCE_GTC = 2
        mock_trading_pb2.TIME_IN_FORCE_IOC = 3
        mock_trading_pb2.TIME_IN_FORCE_FOK = 4
        mock_trading_pb2.ORDER_STATUS_SUBMITTED = 2
        mock_trading_pb2.ORDER_STATUS_PENDING = 1
        mock_trading_pb2.ORDER_STATUS_ACCEPTED = 3
        mock_trading_pb2.ORDER_STATUS_PARTIAL = 4
        mock_trading_pb2.ORDER_STATUS_FILLED = 5
        mock_trading_pb2.ORDER_STATUS_CANCELLED = 6
        mock_trading_pb2.ORDER_STATUS_REJECTED = 7
        mock_trading_pb2.ORDER_STATUS_EXPIRED = 8

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.trading_pb2": mock_trading_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.submit_order(
                context=ctx,
                session_id="session-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
            )

        assert result.id == "order-123"
        assert result.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_submit_order_limit_sell(self) -> None:
        """Test submit_order for a limit sell order."""
        client = TradingClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_quantity = MagicMock()
        mock_quantity.value = "5"

        mock_limit_price = MagicMock()
        mock_limit_price.value = "150.50"

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_order = MagicMock()
        mock_order.id = "order-456"
        mock_order.client_order_id = "client-order-789"
        mock_order.symbol = "GOOGL"
        mock_order.side = 2  # SELL
        mock_order.type = 2  # LIMIT
        mock_order.status = 1  # NEW
        mock_order.time_in_force = 2  # GTC
        mock_order.quantity = mock_quantity
        mock_order.HasField = lambda field: field in ["quantity", "limit_price", "created_at"]
        mock_order.filled_quantity = MagicMock(value="0")
        mock_order.limit_price = mock_limit_price
        mock_order.stop_price = None
        mock_order.average_fill_price = None
        mock_order.created_at = mock_created_at
        mock_order.filled_at = None

        mock_response = MagicMock()
        mock_response.order = mock_order

        mock_stub = MagicMock()
        mock_stub.SubmitOrder = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_trading_pb2 = MagicMock()
        mock_trading_pb2.ORDER_SIDE_BUY = 1
        mock_trading_pb2.ORDER_SIDE_SELL = 2
        mock_trading_pb2.ORDER_TYPE_MARKET = 1
        mock_trading_pb2.ORDER_TYPE_LIMIT = 2
        mock_trading_pb2.ORDER_TYPE_STOP = 3
        mock_trading_pb2.ORDER_TYPE_STOP_LIMIT = 4
        mock_trading_pb2.ORDER_TYPE_TRAILING_STOP = 5
        mock_trading_pb2.TIME_IN_FORCE_DAY = 1
        mock_trading_pb2.TIME_IN_FORCE_GTC = 2
        mock_trading_pb2.TIME_IN_FORCE_IOC = 3
        mock_trading_pb2.TIME_IN_FORCE_FOK = 4
        mock_trading_pb2.ORDER_STATUS_SUBMITTED = 2

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.trading_pb2": mock_trading_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.submit_order(
                context=ctx,
                session_id="session-123",
                symbol="GOOGL",
                side=OrderSide.SELL,
                quantity=Decimal("5"),
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                limit_price=Decimal("150.50"),
                client_order_id="client-order-789",
            )

        assert result.id == "order-456"
        assert result.limit_price == Decimal("150.50")


class TestTradingClientCancelOrder:
    """Tests for TradingClient.cancel_order method."""

    @pytest.mark.asyncio
    async def test_cancel_order_calls_stub(self) -> None:
        """Test cancel_order calls the gRPC stub correctly."""
        client = TradingClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_quantity = MagicMock()
        mock_quantity.value = "10"

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.client_order_id = ""
        mock_order.symbol = "AAPL"
        mock_order.side = 1
        mock_order.type = 1
        mock_order.status = 1  # Status mapping tested separately
        mock_order.time_in_force = 1
        mock_order.quantity = mock_quantity
        mock_order.HasField = lambda field: field in ["quantity", "created_at"]
        mock_order.filled_quantity = MagicMock(value="0")
        mock_order.limit_price = None
        mock_order.stop_price = None
        mock_order.average_fill_price = None
        mock_order.created_at = mock_created_at
        mock_order.filled_at = None

        mock_response = MagicMock()
        mock_response.order = mock_order

        mock_stub = MagicMock()
        mock_stub.CancelOrder = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_trading_pb2 = MagicMock()
        mock_trading_pb2.ORDER_SIDE_BUY = 1
        mock_trading_pb2.ORDER_SIDE_SELL = 2
        mock_trading_pb2.ORDER_TYPE_MARKET = 1
        mock_trading_pb2.TIME_IN_FORCE_DAY = 1
        mock_trading_pb2.ORDER_STATUS_SUBMITTED = 2

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.trading_pb2": mock_trading_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.cancel_order(ctx, "order-123")

        # Verify the stub was called
        mock_stub.CancelOrder.assert_called_once()
        assert result.id == "order-123"
        assert result.symbol == "AAPL"


class TestTradingClientGetPositions:
    """Tests for TradingClient.get_positions method."""

    @pytest.mark.asyncio
    async def test_get_positions_returns_list(self) -> None:
        """Test get_positions returns list of positions."""
        client = TradingClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_quantity = MagicMock()
        mock_quantity.value = "100"

        mock_cost_basis = MagicMock()
        mock_cost_basis.value = "15000.00"

        mock_avg_entry = MagicMock()
        mock_avg_entry.value = "150.00"

        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.quantity = mock_quantity
        mock_position.side = 1  # long
        mock_position.cost_basis = mock_cost_basis
        mock_position.average_entry_price = mock_avg_entry
        mock_position.HasField = lambda field: (
            field
            in [
                "quantity",
                "cost_basis",
                "average_entry_price",
            ]
        )
        mock_position.current_price = None
        mock_position.market_value = None
        mock_position.unrealized_pnl = None
        mock_position.unrealized_pnl_percent = None

        mock_response = MagicMock()
        mock_response.positions = [mock_position]

        mock_stub = MagicMock()
        mock_stub.ListPositions = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.trading_pb2": MagicMock(),
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.get_positions(ctx, "session-123")

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].quantity == Decimal("100")
        assert result[0].side == "long"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self) -> None:
        """Test get_positions returns empty list."""
        client = TradingClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_response = MagicMock()
        mock_response.positions = []

        mock_stub = MagicMock()
        mock_stub.ListPositions = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.trading_pb2": MagicMock(),
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.get_positions(ctx, "session-123")

        assert result == []


class TestTradingClientProtoConversion:
    """Tests for TradingClient proto conversion methods."""

    def test_proto_to_position_short(self) -> None:
        """Test _proto_to_position for short position."""
        client = TradingClient()

        mock_quantity = MagicMock()
        mock_quantity.value = "50"

        mock_cost_basis = MagicMock()
        mock_cost_basis.value = "10000.00"

        mock_avg_entry = MagicMock()
        mock_avg_entry.value = "200.00"

        mock_current = MagicMock()
        mock_current.value = "190.00"

        mock_market_value = MagicMock()
        mock_market_value.value = "9500.00"

        mock_pnl = MagicMock()
        mock_pnl.value = "500.00"

        mock_pnl_pct = MagicMock()
        mock_pnl_pct.value = "5.00"

        mock_position = MagicMock()
        mock_position.symbol = "TSLA"
        mock_position.quantity = mock_quantity
        mock_position.side = 2  # short
        mock_position.cost_basis = mock_cost_basis
        mock_position.average_entry_price = mock_avg_entry
        mock_position.current_price = mock_current
        mock_position.market_value = mock_market_value
        mock_position.unrealized_pnl = mock_pnl
        mock_position.unrealized_pnl_percent = mock_pnl_pct
        mock_position.HasField = lambda field: True

        result = client._proto_to_position(mock_position)

        assert result.symbol == "TSLA"
        assert result.side == "short"
        assert result.unrealized_pnl == Decimal("500.00")
