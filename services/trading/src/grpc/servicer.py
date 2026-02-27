"""Trading gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from uuid import UUID

import grpc.aio

from src.executor.order_executor import get_order_executor
from src.models import OrderCreate, OrderSide, OrderType, TimeInForce

logger = logging.getLogger(__name__)


class TradingServicer:
    """gRPC servicer for the Trading service.

    Implements the TradingService defined in trading.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        pass

    async def SubmitOrder(
        self,
        request: trading_pb2.SubmitOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.SubmitOrderResponse:
        """Submit a new order."""
        from llamatrade.v1 import trading_pb2

        try:
            executor = get_order_executor()

            # Extract tenant context
            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)

            # Map proto enums to internal enums
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

            # Create order request
            order_create = OrderCreate(
                symbol=request.symbol,
                side=side_map.get(request.side, OrderSide.BUY),
                order_type=type_map.get(request.type, OrderType.MARKET),
                time_in_force=tif_map.get(request.time_in_force, TimeInForce.DAY),
                quantity=Decimal(request.quantity.value) if request.HasField("quantity") else Decimal("0"),
                limit_price=Decimal(request.limit_price.value) if request.HasField("limit_price") else None,
                stop_price=Decimal(request.stop_price.value) if request.HasField("stop_price") else None,
                client_order_id=request.client_order_id if request.client_order_id else None,
            )

            # Submit the order
            order = await executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order_create,
            )

            return trading_pb2.SubmitOrderResponse(
                order=self._to_proto_order(order),
            )

        except ValueError as e:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                str(e),
            )
        except Exception as e:
            logger.error("SubmitOrder error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to submit order: {e}",
            )

    async def CancelOrder(
        self,
        request: trading_pb2.CancelOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.CancelOrderResponse:
        """Cancel an order."""
        from llamatrade.v1 import trading_pb2

        try:
            executor = get_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            order_id = UUID(request.order_id)

            success = await executor.cancel_order(
                order_id=order_id,
                tenant_id=tenant_id,
            )

            if not success:
                await context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "Cannot cancel order",
                )

            # Get updated order
            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Order not found: {order_id}",
                )

            return trading_pb2.CancelOrderResponse(
                order=self._to_proto_order(order),
            )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("CancelOrder error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to cancel order: {e}",
            )

    async def GetOrder(
        self,
        request: trading_pb2.GetOrderRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.GetOrderResponse:
        """Get an order by ID."""
        from llamatrade.v1 import trading_pb2

        try:
            executor = get_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            order_id = UUID(request.order_id)

            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Order not found: {order_id}",
                )

            return trading_pb2.GetOrderResponse(
                order=self._to_proto_order(order),
            )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("GetOrder error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get order: {e}",
            )

    async def ListOrders(
        self,
        request: trading_pb2.ListOrdersRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.ListOrdersResponse:
        """List orders for a tenant."""
        from llamatrade.v1 import common_pb2, trading_pb2

        try:
            executor = get_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id) if request.session_id else None

            # Map status filters
            status = None
            if request.statuses:
                # Use first status for now
                from src.models import OrderStatus as InternalOrderStatus

                status_map = {
                    trading_pb2.ORDER_STATUS_NEW: InternalOrderStatus.NEW,
                    trading_pb2.ORDER_STATUS_PENDING: InternalOrderStatus.PENDING,
                    trading_pb2.ORDER_STATUS_FILLED: InternalOrderStatus.FILLED,
                    trading_pb2.ORDER_STATUS_CANCELLED: InternalOrderStatus.CANCELLED,
                }
                if request.statuses[0] in status_map:
                    status = status_map[request.statuses[0]]

            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            orders, total = await executor.list_orders(
                tenant_id=tenant_id,
                session_id=session_id,
                status=status,
                page=page,
                page_size=page_size,
            )

            proto_orders = [self._to_proto_order(o) for o in orders]
            total_pages = (total + page_size - 1) // page_size

            return trading_pb2.ListOrdersResponse(
                orders=proto_orders,
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

        except Exception as e:
            logger.error("ListOrders error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list orders: {e}",
            )

    async def GetPosition(
        self,
        request: trading_pb2.GetPositionRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.GetPositionResponse:
        """Get a position by symbol."""
        from llamatrade.v1 import trading_pb2

        try:
            from src.services.position_service import get_position_service

            service = get_position_service()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )

            if not position:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Position not found for symbol: {symbol}",
                )

            return trading_pb2.GetPositionResponse(
                position=self._to_proto_position(position),
            )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("GetPosition error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get position: {e}",
            )

    async def ListPositions(
        self,
        request: trading_pb2.ListPositionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.ListPositionsResponse:
        """List positions for a session."""
        from llamatrade.v1 import trading_pb2

        try:
            from src.services.position_service import get_position_service

            service = get_position_service()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)

            positions = await service.list_positions(
                tenant_id=tenant_id,
                session_id=session_id,
            )

            proto_positions = [self._to_proto_position(p) for p in positions]

            return trading_pb2.ListPositionsResponse(positions=proto_positions)

        except Exception as e:
            logger.error("ListPositions error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list positions: {e}",
            )

    async def ClosePosition(
        self,
        request: trading_pb2.ClosePositionRequest,
        context: grpc.aio.ServicerContext,
    ) -> trading_pb2.ClosePositionResponse:
        """Close a position."""
        from llamatrade.v1 import trading_pb2

        try:
            executor = get_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            # Get current position
            from src.services.position_service import get_position_service

            service = get_position_service()
            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )

            if not position:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"No position for symbol: {symbol}",
                )

            # Determine quantity and side
            quantity = Decimal(request.quantity.value) if request.HasField("quantity") and Decimal(request.quantity.value) > 0 else position.quantity
            side = OrderSide.SELL if position.side == "long" else OrderSide.BUY

            # Create close order
            order_create = OrderCreate(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                quantity=quantity,
            )

            order = await executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order_create,
            )

            return trading_pb2.ClosePositionResponse(
                order=self._to_proto_order(order),
            )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("ClosePosition error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to close position: {e}",
            )

    async def StreamOrderUpdates(
        self,
        request: trading_pb2.StreamOrderUpdatesRequest,
        context: grpc.aio.ServicerContext,
    ):
        """Stream real-time order updates."""

        tenant_id = request.context.tenant_id
        session_id = request.session_id
        logger.info("Starting order updates stream for session: %s", session_id)

        try:
            while not context.cancelled():
                # In production, would integrate with a message queue
                # For now, poll or wait
                await asyncio.sleep(30.0)

        except asyncio.CancelledError:
            logger.info("Order updates stream cancelled for session: %s", session_id)

    async def StreamPositionUpdates(
        self,
        request: trading_pb2.StreamPositionUpdatesRequest,
        context: grpc.aio.ServicerContext,
    ):
        """Stream real-time position updates."""

        tenant_id = request.context.tenant_id
        session_id = request.session_id
        logger.info("Starting position updates stream for session: %s", session_id)

        try:
            while not context.cancelled():
                await asyncio.sleep(30.0)

        except asyncio.CancelledError:
            logger.info("Position updates stream cancelled for session: %s", session_id)

    def _to_proto_order(self, order: OrderResponse) -> trading_pb2.Order:
        """Convert internal order to proto Order."""
        from llamatrade.v1 import common_pb2, trading_pb2

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
        from src.models import OrderStatus as InternalOrderStatus

        status_map = {
            InternalOrderStatus.NEW: trading_pb2.ORDER_STATUS_NEW,
            InternalOrderStatus.PENDING: trading_pb2.ORDER_STATUS_PENDING,
            InternalOrderStatus.FILLED: trading_pb2.ORDER_STATUS_FILLED,
            InternalOrderStatus.CANCELLED: trading_pb2.ORDER_STATUS_CANCELLED,
            InternalOrderStatus.REJECTED: trading_pb2.ORDER_STATUS_REJECTED,
        }

        proto_order = trading_pb2.Order(
            id=str(order.id),
            client_order_id=order.client_order_id or "",
            tenant_id=str(order.tenant_id) if hasattr(order, "tenant_id") else "",
            session_id=str(order.session_id) if hasattr(order, "session_id") else "",
            symbol=order.symbol,
            side=side_map.get(order.side, trading_pb2.ORDER_SIDE_BUY),
            type=type_map.get(order.order_type, trading_pb2.ORDER_TYPE_MARKET),
            status=status_map.get(order.status, trading_pb2.ORDER_STATUS_NEW),
            quantity=common_pb2.Decimal(value=str(order.quantity)),
        )

        if order.filled_quantity:
            proto_order.filled_quantity.CopyFrom(common_pb2.Decimal(value=str(order.filled_quantity)))
        if order.limit_price:
            proto_order.limit_price.CopyFrom(common_pb2.Decimal(value=str(order.limit_price)))
        if order.stop_price:
            proto_order.stop_price.CopyFrom(common_pb2.Decimal(value=str(order.stop_price)))
        if order.average_fill_price:
            proto_order.average_fill_price.CopyFrom(common_pb2.Decimal(value=str(order.average_fill_price)))
        if order.created_at:
            proto_order.created_at.CopyFrom(common_pb2.Timestamp(seconds=int(order.created_at.timestamp())))

        return proto_order

    def _to_proto_position(self, position: PositionResponse) -> trading_pb2.Position:
        """Convert internal position to proto Position."""
        from llamatrade.v1 import common_pb2, trading_pb2

        side = trading_pb2.POSITION_SIDE_LONG if position.side == "long" else trading_pb2.POSITION_SIDE_SHORT

        proto_position = trading_pb2.Position(
            id=str(position.id) if hasattr(position, "id") else "",
            symbol=position.symbol,
            side=side,
            quantity=common_pb2.Decimal(value=str(position.quantity)),
        )

        if hasattr(position, "cost_basis") and position.cost_basis:
            proto_position.cost_basis.CopyFrom(common_pb2.Decimal(value=str(position.cost_basis)))
        if hasattr(position, "average_entry_price") and position.average_entry_price:
            proto_position.average_entry_price.CopyFrom(common_pb2.Decimal(value=str(position.average_entry_price)))
        if hasattr(position, "current_price") and position.current_price:
            proto_position.current_price.CopyFrom(common_pb2.Decimal(value=str(position.current_price)))
        if hasattr(position, "market_value") and position.market_value:
            proto_position.market_value.CopyFrom(common_pb2.Decimal(value=str(position.market_value)))
        if hasattr(position, "unrealized_pnl") and position.unrealized_pnl:
            proto_position.unrealized_pnl.CopyFrom(common_pb2.Decimal(value=str(position.unrealized_pnl)))

        return proto_position
