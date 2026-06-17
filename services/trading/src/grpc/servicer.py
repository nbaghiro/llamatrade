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
from src.models import OrderCreate, OrderResponse, PositionResponse, SessionResponse
from src.streaming import get_trading_event_subscriber

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from llamatrade_proto.clients.ledger import LedgerClient
    from llamatrade_proto.generated import trading_pb2

logger = logging.getLogger(__name__)


class TradingServicer:
    """gRPC servicer for the Trading service.

    Implements the TradingService defined in trading.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._ledger_client: LedgerClient | None = None

    def _get_ledger(self) -> LedgerClient:
        """Lazy LedgerClient to the portfolio service (sleeve resolution)."""
        if self._ledger_client is None:
            import os

            from llamatrade_proto.clients.ledger import LedgerClient

            self._ledger_client = LedgerClient(os.getenv("PORTFOLIO_GRPC_TARGET", "portfolio:8860"))
        return self._ledger_client

    async def _resolve_order_attribution(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: str,
        session_id: UUID,
        requested_sleeve_id: str,
    ) -> tuple[UUID | None, UUID | None]:
        """(sleeve_id, account_id) for an order, fixed at origination.

        Resolution order (CONTRACTS.md §5): explicit request sleeve → the
        session's strategy sleeve → the account's Manual sleeve (an
        unattributed order is a manual trade). Resolution failures log and fall
        back to unattributed — reconciliation will classify the effects as
        external rather than blocking the order.
        """
        from sqlalchemy import select

        from llamatrade_db.models.trading import TradingSession
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_TYPE_MANUAL

        try:
            session = await db.scalar(
                select(TradingSession).where(
                    TradingSession.tenant_id == tenant_id,
                    TradingSession.id == session_id,
                )
            )
            if requested_sleeve_id:
                sleeve_id = UUID(requested_sleeve_id)
                if session is not None and session.account_id is not None:
                    return sleeve_id, session.account_id
                detail = await self._get_ledger().get_sleeve(
                    str(tenant_id), user_id, requested_sleeve_id
                )
                return sleeve_id, UUID(detail.sleeve.account_id)

            if session is not None and session.sleeve_id is not None:
                return session.sleeve_id, session.account_id

            if session is not None:
                bootstrap = await self._get_ledger().get_or_create_account(
                    str(tenant_id), user_id, str(session.credentials_id)
                )
                manual = next(
                    (s for s in bootstrap.base_sleeves if s.type == SLEEVE_TYPE_MANUAL), None
                )
                if manual is not None:
                    return UUID(manual.id), UUID(bootstrap.account.id)
        except Exception as e:
            logger.warning("Order attribution resolution failed (session=%s): %s", session_id, e)
        return None, None

    async def StartSession(
        self,
        request: trading_pb2.StartTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.StartTradingSessionResponse:
        """Start a trading session (preflight checks + runner launch)."""
        from llamatrade_proto.generated import trading_pb2
        from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            session = await service.start_session(
                tenant_id=UUID(request.context.tenant_id),
                user_id=UUID(request.context.user_id),
                strategy_id=UUID(request.strategy_id),
                strategy_version=request.strategy_version or None,
                name=request.name or "Trading Session",
                mode=request.mode or EXECUTION_MODE_PAPER,
                credentials_id=UUID(request.credentials_id),
                symbols=list(request.symbols) or None,
                execution_id=UUID(request.execution_id) if request.execution_id else None,
            )
            return trading_pb2.StartTradingSessionResponse(session=self._to_proto_session(session))
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("StartSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to start session: {e}")

    async def StopSession(
        self,
        request: trading_pb2.StopTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.StopTradingSessionResponse:
        """Stop a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            session = await service.stop_session(
                session_id=UUID(request.session_id),
                tenant_id=UUID(request.context.tenant_id),
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.StopTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("StopSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to stop session: {e}")

    async def PauseSession(
        self,
        request: trading_pb2.PauseTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.PauseTradingSessionResponse:
        """Pause a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            session = await service.pause_session(
                session_id=UUID(request.session_id),
                tenant_id=UUID(request.context.tenant_id),
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.PauseTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("PauseSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to pause session: {e}")

    async def ResumeSession(
        self,
        request: trading_pb2.ResumeTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ResumeTradingSessionResponse:
        """Resume a paused trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            session = await service.resume_session(
                session_id=UUID(request.session_id),
                tenant_id=UUID(request.context.tenant_id),
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.ResumeTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("ResumeSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to resume session: {e}")

    async def GetSession(
        self,
        request: trading_pb2.GetTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetTradingSessionResponse:
        """Get a trading session with P&L."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            session = await service.get_session(
                session_id=UUID(request.session_id),
                tenant_id=UUID(request.context.tenant_id),
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.GetTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("GetSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to get session: {e}")

    async def ListSessions(
        self,
        request: trading_pb2.ListTradingSessionsRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListTradingSessionsResponse:
        """List trading sessions for the tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        from src.services.live_session_service import create_live_session_service

        try:
            service = await create_live_session_service()
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20
            sessions, total = await service.list_sessions(
                tenant_id=UUID(request.context.tenant_id),
                status=request.status or None,
                strategy_id=UUID(request.strategy_id) if request.strategy_id else None,
                page=max(page, 1),
                page_size=max(page_size, 1),
            )
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            return trading_pb2.ListTradingSessionsResponse(
                sessions=[self._to_proto_session(s) for s in sessions],
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
            logger.error("ListSessions error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Failed to list sessions: {e}")

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

            # Ledger attribution, fixed at origination (CONTRACTS.md §5)
            sleeve_id, account_id = await self._resolve_order_attribution(
                db=executor.db,
                tenant_id=tenant_id,
                user_id=request.context.user_id,
                session_id=session_id,
                requested_sleeve_id=request.sleeve_id,
            )

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
                sleeve_id=sleeve_id,
                account_id=account_id,
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
        """Stream real-time order updates via Redis Streams (tail-read)."""
        _tenant_id = request.context.tenant_id  # Reserved for future use
        session_id = request.session_id
        logger.info("Starting order updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            # Tail-read delivery: reconnect replays the gap from the client's
            # last-seen cursor (carried back via stream_cursor).
            async for cursor, update in subscriber.tail_orders(
                session_id, last_seen_id=request.last_seen_id
            ):
                if context.cancelled():
                    break
                update.stream_cursor = cursor
                yield update

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
        """Stream real-time position updates via Redis Streams (tail-read)."""
        _tenant_id = request.context.tenant_id  # Reserved for future use
        session_id = request.session_id
        logger.info("Starting position updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            async for cursor, update in subscriber.tail_positions(
                session_id, last_seen_id=request.last_seen_id
            ):
                if context.cancelled():
                    break
                update.stream_cursor = cursor
                yield update

        except asyncio.CancelledError:
            logger.info("Position updates stream cancelled for session: %s", session_id)
        except Exception as e:
            logger.error("Position stream error for session %s: %s", session_id, e, exc_info=True)
            raise
        finally:
            await subscriber.close()

    def _to_proto_session(self, session: SessionResponse) -> trading_pb2.TradingSession:
        """Convert internal session response to proto TradingSession."""
        from llamatrade_proto.generated import common_pb2, trading_pb2
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_RUNNING

        proto = trading_pb2.TradingSession(
            id=str(session.id),
            tenant_id=str(session.tenant_id),
            strategy_id=str(session.strategy_id),
            name=session.name,
            mode=session.mode,
            is_active=session.status == EXECUTION_STATUS_RUNNING,
            total_pnl=common_pb2.Decimal(value=str(session.pnl)),
            total_trades=session.trades_count,
            started_at=common_pb2.Timestamp(seconds=int(session.started_at.timestamp())),
            sleeve_id=str(session.sleeve_id) if session.sleeve_id else "",
            account_id=str(session.account_id) if session.account_id else "",
        )
        if session.stopped_at:
            proto.ended_at.CopyFrom(
                common_pb2.Timestamp(seconds=int(session.stopped_at.timestamp()))
            )
        return proto

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
