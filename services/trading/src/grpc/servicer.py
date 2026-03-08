"""Trading gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import grpc.aio

from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import create_order_executor
from src.models import OrderCreate, OrderResponse, PositionResponse
from src.streaming import (
    OrderUpdate,
    PositionUpdate,
    get_trading_event_subscriber,
)

if TYPE_CHECKING:
    from llamatrade_proto.generated import trading_pb2

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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.SubmitOrderResponse:
        """Submit a new order."""
        from llamatrade_proto.generated import trading_pb2

        try:
            executor = await create_order_executor()

            # Extract tenant context
            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)

            # Proto enum values are same as our int constants - use directly
            # Create order request
            order_create = OrderCreate(
                symbol=request.symbol,
                side=request.side or ORDER_SIDE_BUY,
                order_type=request.type or ORDER_TYPE_MARKET,
                time_in_force=request.time_in_force or TIME_IN_FORCE_DAY,
                qty=float(request.quantity.value) if request.HasField("quantity") else 0.0,
                limit_price=float(request.limit_price.value)
                if request.HasField("limit_price")
                else None,
                stop_price=float(request.stop_price.value)
                if request.HasField("stop_price")
                else None,
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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.CancelOrderResponse:
        """Cancel an order."""
        from llamatrade_proto.generated import trading_pb2

        try:
            executor = await create_order_executor()

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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetOrderResponse:
        """Get an order by ID."""
        from llamatrade_proto.generated import trading_pb2

        try:
            executor = await create_order_executor()

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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListOrdersResponse:
        """List orders for a tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        try:
            executor = await create_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id) if request.session_id else None

            # Use first status filter if provided (proto int values pass through directly)
            status = request.statuses[0] if request.statuses else None

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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetPositionResponse:
        """Get a position by symbol."""
        from llamatrade_proto.generated import trading_pb2

        try:
            from src.services.position_service import create_position_service

            service = await create_position_service()

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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListPositionsResponse:
        """List positions for a session."""
        from llamatrade_proto.generated import trading_pb2

        try:
            from src.services.position_service import create_position_service

            service = await create_position_service()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)

            positions = await service.list_open_positions(
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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ClosePositionResponse:
        """Close a position."""
        from llamatrade_proto.generated import trading_pb2

        try:
            executor = await create_order_executor()

            tenant_id = UUID(request.context.tenant_id)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            # Get current position
            from src.services.position_service import create_position_service

            service = await create_position_service()
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
            quantity = (
                Decimal(request.quantity.value)
                if request.HasField("quantity") and Decimal(request.quantity.value) > 0
                else Decimal(str(position.qty))
            )
            side = ORDER_SIDE_SELL if position.side == "long" else ORDER_SIDE_BUY

            # Create close order
            order_create = OrderCreate(
                symbol=symbol,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                time_in_force=TIME_IN_FORCE_DAY,
                qty=float(quantity),
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
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> AsyncGenerator[trading_pb2.OrderUpdate]:
        """Stream real-time order updates via Redis pub/sub."""
        _tenant_id = request.context.tenant_id  # Reserved for future use
        session_id = request.session_id
        logger.info("Starting order updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            async for update in subscriber.subscribe_orders(session_id):
                if context.cancelled():
                    break
                proto_update = self._to_proto_order_update(update)
                yield proto_update

        except asyncio.CancelledError:
            logger.info("Order updates stream cancelled for session: %s", session_id)
        except Exception as e:
            logger.error("Order stream error for session %s: %s", session_id, e, exc_info=True)
            raise
        finally:
            await subscriber.close()

    async def StreamPositionUpdates(
        self,
        request: trading_pb2.StreamPositionUpdatesRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> AsyncGenerator[trading_pb2.PositionUpdate]:
        """Stream real-time position updates via Redis pub/sub."""
        _tenant_id = request.context.tenant_id  # Reserved for future use
        session_id = request.session_id
        logger.info("Starting position updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            async for update in subscriber.subscribe_positions(session_id):
                if context.cancelled():
                    break
                proto_update = self._to_proto_position_update(update)
                yield proto_update

        except asyncio.CancelledError:
            logger.info("Position updates stream cancelled for session: %s", session_id)
        except Exception as e:
            logger.error("Position stream error for session %s: %s", session_id, e, exc_info=True)
            raise
        finally:
            await subscriber.close()

    def _to_proto_order(self, order: OrderResponse) -> trading_pb2.Order:
        """Convert internal order to proto Order.

        OrderResponse now uses proto ValueType directly, so no casting needed.
        """
        from llamatrade_proto.generated import common_pb2, trading_pb2

        proto_order = trading_pb2.Order(
            id=str(order.id),
            client_order_id=order.alpaca_order_id or "",
            tenant_id="",  # Not stored in OrderResponse
            session_id="",  # Not stored in OrderResponse
            symbol=order.symbol,
            side=order.side,
            type=order.order_type,
            status=order.status,
            quantity=common_pb2.Decimal(value=str(order.qty)),
        )

        if order.filled_qty:
            proto_order.filled_quantity.CopyFrom(common_pb2.Decimal(value=str(order.filled_qty)))
        if order.limit_price:
            proto_order.limit_price.CopyFrom(common_pb2.Decimal(value=str(order.limit_price)))
        if order.stop_price:
            proto_order.stop_price.CopyFrom(common_pb2.Decimal(value=str(order.stop_price)))
        if order.filled_avg_price:
            proto_order.average_fill_price.CopyFrom(
                common_pb2.Decimal(value=str(order.filled_avg_price))
            )
        if order.submitted_at:
            proto_order.created_at.CopyFrom(
                common_pb2.Timestamp(seconds=int(order.submitted_at.timestamp()))
            )

        return proto_order

    def _to_proto_position(self, position: PositionResponse) -> trading_pb2.Position:
        """Convert internal position to proto Position."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        side = (
            trading_pb2.POSITION_SIDE_LONG
            if position.side == "long"
            else trading_pb2.POSITION_SIDE_SHORT
        )

        proto_position = trading_pb2.Position(
            id="",  # PositionResponse doesn't have id
            symbol=position.symbol,
            side=side,
            quantity=common_pb2.Decimal(value=str(position.qty)),
        )

        if position.cost_basis:
            proto_position.cost_basis.CopyFrom(common_pb2.Decimal(value=str(position.cost_basis)))
        # PositionResponse doesn't have average_entry_price, use cost_basis / qty
        if position.qty > 0:
            avg_entry = position.cost_basis / position.qty
            proto_position.average_entry_price.CopyFrom(common_pb2.Decimal(value=str(avg_entry)))
        if position.current_price:
            proto_position.current_price.CopyFrom(
                common_pb2.Decimal(value=str(position.current_price))
            )
        if position.market_value:
            proto_position.market_value.CopyFrom(
                common_pb2.Decimal(value=str(position.market_value))
            )
        if position.unrealized_pnl:
            proto_position.unrealized_pnl.CopyFrom(
                common_pb2.Decimal(value=str(position.unrealized_pnl))
            )

        return proto_position

    def _to_proto_order_update(self, update: OrderUpdate) -> trading_pb2.OrderUpdate:
        """Convert streaming OrderUpdate to proto OrderUpdate.

        Proto OrderUpdate structure (from trading.proto):
        - Order order = 1;  // embedded full Order message
        - Fill latest_fill = 2;  // optional
        - string event_type = 3;  // "new", "fill", "partial_fill", "cancelled", "rejected"
        - Timestamp timestamp = 4;
        """
        from llamatrade_proto.generated import common_pb2, trading_pb2

        # Map status string to proto enum
        status_map = {
            "submitted": trading_pb2.ORDER_STATUS_SUBMITTED,
            "pending": trading_pb2.ORDER_STATUS_PENDING,
            "accepted": trading_pb2.ORDER_STATUS_ACCEPTED,
            "partial": trading_pb2.ORDER_STATUS_PARTIAL,
            "filled": trading_pb2.ORDER_STATUS_FILLED,
            "cancelled": trading_pb2.ORDER_STATUS_CANCELLED,
            "rejected": trading_pb2.ORDER_STATUS_REJECTED,
            "expired": trading_pb2.ORDER_STATUS_EXPIRED,
        }

        # Map side string to proto enum
        side_map = {
            "buy": trading_pb2.ORDER_SIDE_BUY,
            "sell": trading_pb2.ORDER_SIDE_SELL,
        }

        # Map order type string to proto enum
        type_map = {
            "market": trading_pb2.ORDER_TYPE_MARKET,
            "limit": trading_pb2.ORDER_TYPE_LIMIT,
            "stop": trading_pb2.ORDER_TYPE_STOP,
            "stop_limit": trading_pb2.ORDER_TYPE_STOP_LIMIT,
            "trailing_stop": trading_pb2.ORDER_TYPE_TRAILING_STOP,
        }

        # Build embedded Order message
        order = trading_pb2.Order(
            id=update.order_id,
            client_order_id=update.alpaca_order_id or "",
            session_id=update.session_id,
            symbol=update.symbol,
            side=side_map.get(update.side.lower(), trading_pb2.ORDER_SIDE_BUY),
            type=type_map.get(update.order_type.lower(), trading_pb2.ORDER_TYPE_MARKET),
            status=status_map.get(update.status.lower(), trading_pb2.ORDER_STATUS_SUBMITTED),
            quantity=common_pb2.Decimal(value=str(update.qty)),
        )

        if update.filled_qty > 0:
            order.filled_quantity.CopyFrom(common_pb2.Decimal(value=str(update.filled_qty)))
        if update.filled_avg_price is not None:
            order.average_fill_price.CopyFrom(
                common_pb2.Decimal(value=str(update.filled_avg_price))
            )

        # Map update_type to event_type
        event_type_map = {
            "submitted": "new",
            "filled": "fill",
            "partial": "partial_fill",
            "cancelled": "cancelled",
            "rejected": "rejected",
            "status_change": "status_change",
        }
        event_type = event_type_map.get(update.update_type, update.update_type)

        # Build OrderUpdate with embedded Order
        proto_update = trading_pb2.OrderUpdate(
            order=order,
            event_type=event_type,
        )

        # Add timestamp if available
        if update.timestamp:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(update.timestamp.replace("Z", "+00:00"))
                proto_update.timestamp.CopyFrom(common_pb2.Timestamp(seconds=int(dt.timestamp())))
            except ValueError, AttributeError:
                pass

        return proto_update

    def _to_proto_position_update(self, update: PositionUpdate) -> trading_pb2.PositionUpdate:
        """Convert streaming PositionUpdate to proto PositionUpdate.

        Proto PositionUpdate structure (from trading.proto):
        - Position position = 1;  // embedded full Position message
        - string event_type = 2;  // "opened", "updated", "closed"
        - Timestamp timestamp = 3;
        """
        from llamatrade_proto.generated import common_pb2, trading_pb2

        side = (
            trading_pb2.POSITION_SIDE_LONG
            if update.side.lower() == "long"
            else trading_pb2.POSITION_SIDE_SHORT
        )

        # Build embedded Position message
        position = trading_pb2.Position(
            session_id=update.session_id,
            symbol=update.symbol,
            side=side,
            quantity=common_pb2.Decimal(value=str(update.qty)),
        )

        if update.cost_basis:
            position.cost_basis.CopyFrom(common_pb2.Decimal(value=str(update.cost_basis)))
        if update.qty > 0 and update.cost_basis:
            avg_entry = update.cost_basis / update.qty
            position.average_entry_price.CopyFrom(common_pb2.Decimal(value=str(avg_entry)))
        if update.current_price:
            position.current_price.CopyFrom(common_pb2.Decimal(value=str(update.current_price)))
        if update.market_value:
            position.market_value.CopyFrom(common_pb2.Decimal(value=str(update.market_value)))
        if update.unrealized_pnl:
            position.unrealized_pnl.CopyFrom(common_pb2.Decimal(value=str(update.unrealized_pnl)))
        if update.unrealized_pnl_percent:
            position.unrealized_pnl_percent.CopyFrom(
                common_pb2.Decimal(value=str(update.unrealized_pnl_percent))
            )

        # Build PositionUpdate with embedded Position
        proto_update = trading_pb2.PositionUpdate(
            position=position,
            event_type=update.update_type,
        )

        # Add timestamp if available
        if update.timestamp:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(update.timestamp.replace("Z", "+00:00"))
                proto_update.timestamp.CopyFrom(common_pb2.Timestamp(seconds=int(dt.timestamp())))
            except ValueError, AttributeError:
                pass

        return proto_update
