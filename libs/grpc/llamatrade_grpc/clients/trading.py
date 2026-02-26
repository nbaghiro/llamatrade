"""Trading gRPC client."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from llamatrade_grpc.clients.auth import TenantContext
from llamatrade_grpc.clients.base import BaseGRPCClient

if TYPE_CHECKING:
    from llamatrade_grpc.generated.llamatrade.v1 import trading_pb2, trading_pb2_grpc

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(Enum):
    """Order status."""

    NEW = "new"
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(Enum):
    """Time in force."""

    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


@dataclass
class Order:
    """Order data."""

    id: str
    client_order_id: str | None
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    average_fill_price: Decimal | None
    time_in_force: TimeInForce
    created_at: datetime
    filled_at: datetime | None


@dataclass
class Position:
    """Position data."""

    symbol: str
    quantity: Decimal
    side: str
    cost_basis: Decimal
    average_entry_price: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_percent: Decimal | None


@dataclass
class OrderUpdate:
    """Order update event."""

    order: Order
    event_type: str
    timestamp: datetime


class TradingClient(BaseGRPCClient):
    """Client for the Trading gRPC service.

    Example:
        async with TradingClient("trading:50055") as client:
            # Submit an order
            order = await client.submit_order(
                context=context,
                session_id="session-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                order_type=OrderType.MARKET,
            )

            # Stream order updates
            async for update in client.stream_order_updates(context, session_id):
                print(f"Order {update.order.id}: {update.event_type}")
    """

    def __init__(
        self,
        target: str = "trading:50055",
        *,
        secure: bool = False,
        credentials: object | None = None,
        interceptors: list[object] | None = None,
        options: list[tuple[str, str | int | bool]] | None = None,
    ) -> None:
        """Initialize the Trading client.

        Args:
            target: The gRPC server address
            secure: Whether to use TLS
            credentials: Optional channel credentials
            interceptors: Optional client interceptors
            options: Optional channel options
        """
        super().__init__(
            target,
            secure=secure,
            credentials=credentials,  # type: ignore[arg-type]
            interceptors=interceptors,  # type: ignore[arg-type]
            options=options,
        )
        self._stub: trading_pb2_grpc.TradingServiceStub | None = None

    @property
    def stub(self) -> trading_pb2_grpc.TradingServiceStub:
        """Get the gRPC stub (lazy initialization)."""
        if self._stub is None:
            try:
                from llamatrade_grpc.generated.llamatrade.v1 import trading_pb2_grpc

                self._stub = trading_pb2_grpc.TradingServiceStub(self.channel)
            except ImportError:
                raise RuntimeError(
                    "Generated gRPC code not found. Run 'make generate' in libs/proto"
                )
        return self._stub

    async def submit_order(
        self,
        context: TenantContext,
        session_id: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """Submit a new order.

        Args:
            context: Tenant context
            session_id: Trading session ID
            symbol: Ticker symbol
            side: Order side (buy/sell)
            quantity: Order quantity
            order_type: Order type
            time_in_force: Time in force
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            client_order_id: Optional client-specified order ID

        Returns:
            The submitted Order
        """
        from llamatrade_grpc.generated.llamatrade.v1 import common_pb2, trading_pb2

        # Map enums
        side_map = {
            OrderSide.BUY: trading_pb2.ORDER_SIDE_BUY,
            OrderSide.SELL: trading_pb2.ORDER_SIDE_SELL,
        }
        type_map = {
            OrderType.MARKET: trading_pb2.ORDER_TYPE_MARKET,
            OrderType.LIMIT: trading_pb2.ORDER_TYPE_LIMIT,
            OrderType.STOP: trading_pb2.ORDER_TYPE_STOP,
            OrderType.STOP_LIMIT: trading_pb2.ORDER_TYPE_STOP_LIMIT,
            OrderType.TRAILING_STOP: trading_pb2.ORDER_TYPE_TRAILING_STOP,
        }
        tif_map = {
            TimeInForce.DAY: trading_pb2.TIME_IN_FORCE_DAY,
            TimeInForce.GTC: trading_pb2.TIME_IN_FORCE_GTC,
            TimeInForce.IOC: trading_pb2.TIME_IN_FORCE_IOC,
            TimeInForce.FOK: trading_pb2.TIME_IN_FORCE_FOK,
        }

        request = trading_pb2.SubmitOrderRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            session_id=session_id,
            symbol=symbol,
            side=side_map[side],
            type=type_map[order_type],
            time_in_force=tif_map[time_in_force],
            quantity=common_pb2.Decimal(value=str(quantity)),
        )

        if client_order_id:
            request.client_order_id = client_order_id
        if limit_price is not None:
            request.limit_price.CopyFrom(common_pb2.Decimal(value=str(limit_price)))
        if stop_price is not None:
            request.stop_price.CopyFrom(common_pb2.Decimal(value=str(stop_price)))

        response = await self.stub.SubmitOrder(request)
        return self._proto_to_order(response.order)

    async def cancel_order(self, context: TenantContext, order_id: str) -> Order:
        """Cancel an order.

        Args:
            context: Tenant context
            order_id: The order ID to cancel

        Returns:
            The cancelled Order
        """
        from llamatrade_grpc.generated.llamatrade.v1 import common_pb2, trading_pb2

        request = trading_pb2.CancelOrderRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            order_id=order_id,
        )

        response = await self.stub.CancelOrder(request)
        return self._proto_to_order(response.order)

    async def get_positions(self, context: TenantContext, session_id: str) -> list[Position]:
        """Get all positions for a session.

        Args:
            context: Tenant context
            session_id: Trading session ID

        Returns:
            List of Position objects
        """
        from llamatrade_grpc.generated.llamatrade.v1 import common_pb2, trading_pb2

        request = trading_pb2.ListPositionsRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            session_id=session_id,
        )

        response = await self.stub.ListPositions(request)
        return [self._proto_to_position(pos) for pos in response.positions]

    async def stream_order_updates(
        self,
        context: TenantContext,
        session_id: str,
    ) -> AsyncIterator[OrderUpdate]:
        """Stream real-time order updates.

        Args:
            context: Tenant context
            session_id: Trading session ID

        Yields:
            OrderUpdate events
        """
        from llamatrade_grpc.generated.llamatrade.v1 import common_pb2, trading_pb2

        request = trading_pb2.StreamOrderUpdatesRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            session_id=session_id,
        )

        async for update in self.stub.StreamOrderUpdates(request):
            yield OrderUpdate(
                order=self._proto_to_order(update.order),
                event_type=update.event_type,
                timestamp=datetime.fromtimestamp(update.timestamp.seconds),
            )

    def _proto_to_order(self, proto: trading_pb2.Order) -> Order:
        """Convert protobuf Order to dataclass."""
        from llamatrade_grpc.generated.llamatrade.v1 import trading_pb2

        status_map = {
            trading_pb2.ORDER_STATUS_NEW: OrderStatus.NEW,
            trading_pb2.ORDER_STATUS_PENDING: OrderStatus.PENDING,
            trading_pb2.ORDER_STATUS_ACCEPTED: OrderStatus.ACCEPTED,
            trading_pb2.ORDER_STATUS_PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            trading_pb2.ORDER_STATUS_FILLED: OrderStatus.FILLED,
            trading_pb2.ORDER_STATUS_CANCELLED: OrderStatus.CANCELLED,
            trading_pb2.ORDER_STATUS_REJECTED: OrderStatus.REJECTED,
            trading_pb2.ORDER_STATUS_EXPIRED: OrderStatus.EXPIRED,
        }
        side_map = {
            trading_pb2.ORDER_SIDE_BUY: OrderSide.BUY,
            trading_pb2.ORDER_SIDE_SELL: OrderSide.SELL,
        }
        type_map = {
            trading_pb2.ORDER_TYPE_MARKET: OrderType.MARKET,
            trading_pb2.ORDER_TYPE_LIMIT: OrderType.LIMIT,
            trading_pb2.ORDER_TYPE_STOP: OrderType.STOP,
            trading_pb2.ORDER_TYPE_STOP_LIMIT: OrderType.STOP_LIMIT,
            trading_pb2.ORDER_TYPE_TRAILING_STOP: OrderType.TRAILING_STOP,
        }
        tif_map = {
            trading_pb2.TIME_IN_FORCE_DAY: TimeInForce.DAY,
            trading_pb2.TIME_IN_FORCE_GTC: TimeInForce.GTC,
            trading_pb2.TIME_IN_FORCE_IOC: TimeInForce.IOC,
            trading_pb2.TIME_IN_FORCE_FOK: TimeInForce.FOK,
        }

        return Order(
            id=proto.id,
            client_order_id=proto.client_order_id if proto.client_order_id else None,
            symbol=proto.symbol,
            side=side_map.get(proto.side, OrderSide.BUY),
            type=type_map.get(proto.type, OrderType.MARKET),
            status=status_map.get(proto.status, OrderStatus.NEW),
            quantity=Decimal(proto.quantity.value) if proto.HasField("quantity") else Decimal(0),
            filled_quantity=(
                Decimal(proto.filled_quantity.value)
                if proto.HasField("filled_quantity")
                else Decimal(0)
            ),
            limit_price=(
                Decimal(proto.limit_price.value) if proto.HasField("limit_price") else None
            ),
            stop_price=Decimal(proto.stop_price.value) if proto.HasField("stop_price") else None,
            average_fill_price=(
                Decimal(proto.average_fill_price.value)
                if proto.HasField("average_fill_price")
                else None
            ),
            time_in_force=tif_map.get(proto.time_in_force, TimeInForce.DAY),
            created_at=datetime.fromtimestamp(proto.created_at.seconds),
            filled_at=(
                datetime.fromtimestamp(proto.filled_at.seconds)
                if proto.HasField("filled_at")
                else None
            ),
        )

    def _proto_to_position(self, proto: trading_pb2.Position) -> Position:
        """Convert protobuf Position to dataclass."""
        return Position(
            symbol=proto.symbol,
            quantity=Decimal(proto.quantity.value) if proto.HasField("quantity") else Decimal(0),
            side="long" if proto.side == 1 else "short",
            cost_basis=(
                Decimal(proto.cost_basis.value) if proto.HasField("cost_basis") else Decimal(0)
            ),
            average_entry_price=(
                Decimal(proto.average_entry_price.value)
                if proto.HasField("average_entry_price")
                else Decimal(0)
            ),
            current_price=(
                Decimal(proto.current_price.value) if proto.HasField("current_price") else None
            ),
            market_value=(
                Decimal(proto.market_value.value) if proto.HasField("market_value") else None
            ),
            unrealized_pnl=(
                Decimal(proto.unrealized_pnl.value) if proto.HasField("unrealized_pnl") else None
            ),
            unrealized_pnl_percent=(
                Decimal(proto.unrealized_pnl_percent.value)
                if proto.HasField("unrealized_pnl_percent")
                else None
            ),
        )
