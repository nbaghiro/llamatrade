"""Tests for trading gRPC servicer methods."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import grpc.aio
import pytest

# Test UUIDs (matching conftest.py)
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_ORDER_ID = UUID("55555555-5555-5555-5555-555555555555")

pytestmark = pytest.mark.asyncio


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self) -> None:
        self.code = None
        self.details = None
        self._cancelled = False

    async def abort(self, code, details: str) -> None:
        """Mock abort that raises an exception."""
        self.code = code
        self.details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    def cancelled(self) -> bool:
        return self._cancelled


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def trading_servicer():
    """Create a trading servicer instance."""
    from src.grpc.servicer import TradingServicer

    return TradingServicer()


def make_mock_order(
    id: UUID = TEST_ORDER_ID,
    tenant_id: UUID = TEST_TENANT_ID,
    session_id: UUID = TEST_SESSION_ID,
    symbol: str = "AAPL",
    side: str = "BUY",
    quantity: Decimal = Decimal("10"),
    order_type: str = "MARKET",
    status: str = "SUBMITTED",
    filled_quantity: Decimal = Decimal("0"),
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    average_fill_price: Decimal | None = None,
    client_order_id: str | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock order object for servicer tests."""
    from src.models import OrderSide, OrderStatus, OrderType

    order = MagicMock()
    order.id = id
    order.tenant_id = tenant_id
    order.session_id = session_id
    order.symbol = symbol
    order.side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
    order.quantity = quantity
    order.order_type = OrderType.MARKET if order_type == "MARKET" else OrderType.LIMIT
    order.status = {
        "SUBMITTED": OrderStatus.SUBMITTED,
        "PENDING": OrderStatus.PENDING,
        "FILLED": OrderStatus.FILLED,
        "CANCELLED": OrderStatus.CANCELLED,
    }.get(status, OrderStatus.SUBMITTED)
    order.filled_quantity = filled_quantity
    order.limit_price = limit_price
    order.stop_price = stop_price
    order.average_fill_price = average_fill_price
    order.client_order_id = client_order_id
    order.created_at = created_at or datetime.now(UTC)
    return order


def make_mock_position(
    id: UUID | None = None,
    symbol: str = "AAPL",
    quantity: Decimal = Decimal("100"),
    side: str = "long",
    cost_basis: Decimal = Decimal("15000"),
    average_entry_price: Decimal = Decimal("150"),
    current_price: Decimal = Decimal("155"),
    market_value: Decimal = Decimal("15500"),
    unrealized_pnl: Decimal = Decimal("500"),
) -> MagicMock:
    """Create a mock position object for servicer tests."""
    position = MagicMock()
    position.id = id or uuid4()
    position.symbol = symbol
    position.quantity = quantity
    position.side = side
    position.cost_basis = cost_basis
    position.average_entry_price = average_entry_price
    position.current_price = current_price
    position.market_value = market_value
    position.unrealized_pnl = unrealized_pnl
    return position


def create_mock_executor(
    submit_order_return=None,
    cancel_order_return=True,
    get_order_return=None,
    list_orders_return=None,
):
    """Create a mock executor with configured return values."""
    mock_executor = MagicMock()
    mock_executor.submit_order = AsyncMock(return_value=submit_order_return)
    mock_executor.cancel_order = AsyncMock(return_value=cancel_order_return)
    mock_executor.get_order = AsyncMock(return_value=get_order_return)
    mock_executor.list_orders = AsyncMock(return_value=list_orders_return or ([], 0))
    return mock_executor


def create_mock_position_service(
    get_position_return=None,
    list_positions_return=None,
):
    """Create a mock position service with configured return values."""
    mock_service = MagicMock()
    mock_service.get_position = AsyncMock(return_value=get_position_return)
    mock_service.list_positions = AsyncMock(return_value=list_positions_return or [])
    return mock_service


class TestSubmitOrder:
    """Tests for SubmitOrder gRPC method."""

    async def test_submit_order_success(self, trading_servicer, grpc_context):
        """Test successfully submitting a market order."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_order = make_mock_order()
        mock_executor = create_mock_executor(submit_order_return=mock_order)

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.SubmitOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="AAPL",
                side=trading_pb2.ORDER_SIDE_BUY,
                type=trading_pb2.ORDER_TYPE_MARKET,
                time_in_force=trading_pb2.TIME_IN_FORCE_DAY,
                quantity=common_pb2.Decimal(value="10"),
            )

            response = await trading_servicer.SubmitOrder(request, grpc_context)

            assert response.order.symbol == "AAPL"
            assert response.order.side == trading_pb2.ORDER_SIDE_BUY
            mock_executor.submit_order.assert_called_once()

    async def test_submit_order_limit_order(self, trading_servicer, grpc_context):
        """Test submitting a limit order."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_order = make_mock_order(order_type="LIMIT", limit_price=Decimal("150.50"))
        mock_executor = create_mock_executor(submit_order_return=mock_order)

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.SubmitOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="AAPL",
                side=trading_pb2.ORDER_SIDE_BUY,
                type=trading_pb2.ORDER_TYPE_LIMIT,
                time_in_force=trading_pb2.TIME_IN_FORCE_GTC,
                quantity=common_pb2.Decimal(value="10"),
                limit_price=common_pb2.Decimal(value="150.50"),
            )

            response = await trading_servicer.SubmitOrder(request, grpc_context)

            assert response.order.type == trading_pb2.ORDER_TYPE_LIMIT

    async def test_submit_order_invalid_argument(self, trading_servicer, grpc_context):
        """Test submitting an order with invalid arguments returns INVALID_ARGUMENT."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_executor = MagicMock()
        mock_executor.submit_order = AsyncMock(side_effect=ValueError("Invalid quantity"))

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.SubmitOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="AAPL",
                side=trading_pb2.ORDER_SIDE_BUY,
                type=trading_pb2.ORDER_TYPE_MARKET,
                quantity=common_pb2.Decimal(value="-10"),
            )

            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await trading_servicer.SubmitOrder(request, grpc_context)

            assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestCancelOrder:
    """Tests for CancelOrder gRPC method."""

    async def test_cancel_order_success(self, trading_servicer, grpc_context):
        """Test successfully cancelling an order."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_order = make_mock_order(status="CANCELLED")
        mock_executor = create_mock_executor(
            cancel_order_return=True,
            get_order_return=mock_order,
        )

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.CancelOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                order_id=str(TEST_ORDER_ID),
            )

            response = await trading_servicer.CancelOrder(request, grpc_context)

            assert response.order.status == trading_pb2.ORDER_STATUS_CANCELLED
            mock_executor.cancel_order.assert_called_once()

    async def test_cancel_order_failed_precondition(self, trading_servicer, grpc_context):
        """Test cancelling an order that cannot be cancelled."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_executor = create_mock_executor(cancel_order_return=False)

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.CancelOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                order_id=str(TEST_ORDER_ID),
            )

            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await trading_servicer.CancelOrder(request, grpc_context)

            assert exc_info.value.code() == grpc.StatusCode.FAILED_PRECONDITION


class TestGetOrder:
    """Tests for GetOrder gRPC method."""

    async def test_get_order_success(self, trading_servicer, grpc_context):
        """Test getting an order by ID."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_order = make_mock_order()
        mock_executor = create_mock_executor(get_order_return=mock_order)

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.GetOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                order_id=str(TEST_ORDER_ID),
            )

            response = await trading_servicer.GetOrder(request, grpc_context)

            assert response.order.id == str(TEST_ORDER_ID)
            assert response.order.symbol == "AAPL"

    async def test_get_order_not_found(self, trading_servicer, grpc_context):
        """Test getting a nonexistent order returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_executor = create_mock_executor(get_order_return=None)

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.GetOrderRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                order_id=str(uuid4()),
            )

            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await trading_servicer.GetOrder(request, grpc_context)

            assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestListOrders:
    """Tests for ListOrders gRPC method."""

    async def test_list_orders_empty(self, trading_servicer, grpc_context):
        """Test listing orders returns empty list when none exist."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_executor = create_mock_executor(list_orders_return=([], 0))

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.ListOrdersRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
            )

            response = await trading_servicer.ListOrders(request, grpc_context)

            assert len(response.orders) == 0
            assert response.pagination.total_items == 0

    async def test_list_orders_with_data(self, trading_servicer, grpc_context):
        """Test listing orders with data."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_orders = [
            make_mock_order(id=uuid4(), symbol="AAPL"),
            make_mock_order(id=uuid4(), symbol="GOOGL"),
        ]
        mock_executor = create_mock_executor(list_orders_return=(mock_orders, 2))

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.ListOrdersRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
            )

            response = await trading_servicer.ListOrders(request, grpc_context)

            assert len(response.orders) == 2
            assert response.pagination.total_items == 2

    async def test_list_orders_with_status_filter(self, trading_servicer, grpc_context):
        """Test filtering orders by status."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_orders = [make_mock_order(status="FILLED")]
        mock_executor = create_mock_executor(list_orders_return=(mock_orders, 1))

        with patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor):
            request = trading_pb2.ListOrdersRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                statuses=[trading_pb2.ORDER_STATUS_FILLED],
            )

            response = await trading_servicer.ListOrders(request, grpc_context)

            assert len(response.orders) == 1
            assert response.orders[0].status == trading_pb2.ORDER_STATUS_FILLED


class TestGetPosition:
    """Tests for GetPosition gRPC method."""

    async def test_get_position_success(self, trading_servicer, grpc_context):
        """Test getting a position by symbol."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_position = make_mock_position()
        mock_service = create_mock_position_service(get_position_return=mock_position)

        with patch("src.services.position_service.get_position_service", new=lambda: mock_service):
            request = trading_pb2.GetPositionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="AAPL",
            )

            response = await trading_servicer.GetPosition(request, grpc_context)

            assert response.position.symbol == "AAPL"
            assert response.position.side == trading_pb2.POSITION_SIDE_LONG

    async def test_get_position_not_found(self, trading_servicer, grpc_context):
        """Test getting a nonexistent position returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_service = create_mock_position_service(get_position_return=None)

        with patch("src.services.position_service.get_position_service", new=lambda: mock_service):
            request = trading_pb2.GetPositionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="INVALID",
            )

            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await trading_servicer.GetPosition(request, grpc_context)

            assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestListPositions:
    """Tests for ListPositions gRPC method."""

    async def test_list_positions_empty(self, trading_servicer, grpc_context):
        """Test listing positions returns empty list when none exist."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_service = create_mock_position_service(list_positions_return=[])

        with patch("src.services.position_service.get_position_service", new=lambda: mock_service):
            request = trading_pb2.ListPositionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
            )

            response = await trading_servicer.ListPositions(request, grpc_context)

            assert len(response.positions) == 0

    async def test_list_positions_with_data(self, trading_servicer, grpc_context):
        """Test listing positions with data."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_positions = [
            make_mock_position(symbol="AAPL"),
            make_mock_position(symbol="GOOGL", side="short"),
        ]
        mock_service = create_mock_position_service(list_positions_return=mock_positions)

        with patch("src.services.position_service.get_position_service", new=lambda: mock_service):
            request = trading_pb2.ListPositionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
            )

            response = await trading_servicer.ListPositions(request, grpc_context)

            assert len(response.positions) == 2
            assert response.positions[0].symbol == "AAPL"
            assert response.positions[1].symbol == "GOOGL"


class TestClosePosition:
    """Tests for ClosePosition gRPC method."""

    async def test_close_position_success(self, trading_servicer, grpc_context):
        """Test closing a position successfully."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_position = make_mock_position()
        mock_order = make_mock_order(side="SELL")
        mock_executor = create_mock_executor(submit_order_return=mock_order)
        mock_service = create_mock_position_service(get_position_return=mock_position)

        with (
            patch("src.grpc.servicer.get_order_executor", new=lambda: mock_executor),
            patch("src.services.position_service.get_position_service", new=lambda: mock_service),
        ):
            request = trading_pb2.ClosePositionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="AAPL",
            )

            response = await trading_servicer.ClosePosition(request, grpc_context)

            assert response.order.side == trading_pb2.ORDER_SIDE_SELL

    async def test_close_position_not_found(self, trading_servicer, grpc_context):
        """Test closing a nonexistent position returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, trading_pb2

        mock_service = create_mock_position_service(get_position_return=None)

        with patch("src.services.position_service.get_position_service", new=lambda: mock_service):
            request = trading_pb2.ClosePositionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                session_id=str(TEST_SESSION_ID),
                symbol="INVALID",
            )

            with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                await trading_servicer.ClosePosition(request, grpc_context)

            assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestStreamOrderUpdates:
    """Tests for StreamOrderUpdates gRPC method."""

    async def test_stream_order_updates_starts(self, trading_servicer, grpc_context):
        """Test that order updates stream can be started."""
        import asyncio

        from llamatrade.v1 import common_pb2, trading_pb2

        # Set context to cancelled after a short time
        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            grpc_context._cancelled = True

        request = trading_pb2.StreamOrderUpdatesRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            session_id=str(TEST_SESSION_ID),
        )

        # Start the cancellation task
        cancel_task = asyncio.create_task(cancel_after_delay())

        # The stream should exit when context is cancelled
        await trading_servicer.StreamOrderUpdates(request, grpc_context)

        await cancel_task


class TestStreamPositionUpdates:
    """Tests for StreamPositionUpdates gRPC method."""

    async def test_stream_position_updates_starts(self, trading_servicer, grpc_context):
        """Test that position updates stream can be started."""
        import asyncio

        from llamatrade.v1 import common_pb2, trading_pb2

        # Set context to cancelled after a short time
        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            grpc_context._cancelled = True

        request = trading_pb2.StreamPositionUpdatesRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            session_id=str(TEST_SESSION_ID),
        )

        # Start the cancellation task
        cancel_task = asyncio.create_task(cancel_after_delay())

        # The stream should exit when context is cancelled
        await trading_servicer.StreamPositionUpdates(request, grpc_context)

        await cancel_task
