"""Trading gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NoReturn
from uuid import UUID

import grpc.aio

from llamatrade_common import AuthError, resolve_identity
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

# Map the transport-neutral AuthError codes to gRPC status codes (1A).
_AUTH_CODE_TO_GRPC = {
    "unauthenticated": grpc.StatusCode.UNAUTHENTICATED,
    "permission_denied": grpc.StatusCode.PERMISSION_DENIED,
    "invalid_argument": grpc.StatusCode.INVALID_ARGUMENT,
}


def _identity(request_context: Any) -> tuple[UUID, UUID]:
    """Verified (tenant_id, user_id) for the call.

    Derives identity from the authenticated principal (the JWT, via the
    AuthMiddleware contextvar) rather than trusting the wire ``context``, and
    rejects a request whose wire tenant doesn't match the token (1A).
    """
    return resolve_identity(
        request_context.tenant_id or None,
        request_context.user_id or None,
    )


async def _abort_auth(context: grpc.aio.ServicerContext[Any, Any], err: AuthError) -> NoReturn:
    """Abort with the gRPC status code for an auth failure (``context.abort`` never returns)."""
    await context.abort(
        _AUTH_CODE_TO_GRPC.get(err.code, grpc.StatusCode.UNAUTHENTICATED), err.message
    )


async def _aclose(obj: object | None) -> None:
    """Best-effort release of a request-scoped service's resources (13A).

    Tolerates test mocks (whose ``aclose`` returns a non-awaitable).
    """
    if obj is None:
        return
    closer = getattr(obj, "aclose", None)
    if closer is None:
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.debug("aclose failed", exc_info=True)


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

        service = None
        try:
            tenant_id, user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.start_session(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=UUID(request.strategy_id),
                strategy_version=request.strategy_version or None,
                name=request.name or "Trading Session",
                mode=request.mode or EXECUTION_MODE_PAPER,
                credentials_id=UUID(request.credentials_id),
                symbols=list(request.symbols) or None,
                execution_id=UUID(request.execution_id) if request.execution_id else None,
            )
            return trading_pb2.StartTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("StartSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to start session")
        finally:
            await _aclose(service)

    async def StopSession(
        self,
        request: trading_pb2.StopTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.StopTradingSessionResponse:
        """Stop a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.stop_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.StopTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("StopSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to stop session")
        finally:
            await _aclose(service)

    async def PauseSession(
        self,
        request: trading_pb2.PauseTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.PauseTradingSessionResponse:
        """Pause a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.pause_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.PauseTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("PauseSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to pause session")
        finally:
            await _aclose(service)

    async def ResumeSession(
        self,
        request: trading_pb2.ResumeTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ResumeTradingSessionResponse:
        """Resume a paused trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.resume_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.ResumeTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("ResumeSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to resume session")
        finally:
            await _aclose(service)

    async def GetSession(
        self,
        request: trading_pb2.GetTradingSessionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetTradingSessionResponse:
        """Get a trading session with P&L."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.get_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Session not found")
            return trading_pb2.GetTradingSessionResponse(session=self._to_proto_session(session))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("GetSession error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to get session")
        finally:
            await _aclose(service)

    async def ListSessions(
        self,
        request: trading_pb2.ListTradingSessionsRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListTradingSessionsResponse:
        """List trading sessions for the tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            service = await create_live_session_service(tenant_id)
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20
            sessions, total = await service.list_sessions(
                tenant_id=tenant_id,
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
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("ListSessions error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to list sessions")
        finally:
            await _aclose(service)

    async def SubmitOrder(
        self,
        request: trading_pb2.SubmitOrderRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.SubmitOrderResponse:
        """Submit a new order."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, user_id = _identity(request.context)
            session_id = UUID(request.session_id)

            # The executor's Alpaca client is built from this session's own
            # per-tenant credentials, never the platform default (2A).
            executor = await create_order_executor(session_id=session_id, tenant_id=tenant_id)

            # Ledger attribution, fixed at origination (CONTRACTS.md §5)
            sleeve_id, account_id = await self._resolve_order_attribution(
                db=executor.db,
                tenant_id=tenant_id,
                user_id=str(user_id),
                session_id=session_id,
                requested_sleeve_id=request.sleeve_id,
            )

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

            order = await executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order_create,
            )
            return trading_pb2.SubmitOrderResponse(order=self._to_proto_order(order))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("SubmitOrder error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to submit order")
        finally:
            await _aclose(executor)

    async def CancelOrder(
        self,
        request: trading_pb2.CancelOrderRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.CancelOrderResponse:
        """Cancel an order."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, _user_id = _identity(request.context)
            order_id = UUID(request.order_id)

            executor = await create_order_executor(tenant_id=tenant_id)
            success = await executor.cancel_order(order_id=order_id, tenant_id=tenant_id)
            if not success:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot cancel order")

            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Order not found: {order_id}")

            return trading_pb2.CancelOrderResponse(order=self._to_proto_order(order))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("CancelOrder error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to cancel order")
        finally:
            await _aclose(executor)

    async def GetOrder(
        self,
        request: trading_pb2.GetOrderRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetOrderResponse:
        """Get an order by ID."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, _user_id = _identity(request.context)
            order_id = UUID(request.order_id)

            executor = await create_order_executor(tenant_id=tenant_id)
            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Order not found: {order_id}")

            return trading_pb2.GetOrderResponse(order=self._to_proto_order(order))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("GetOrder error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to get order")
        finally:
            await _aclose(executor)

    async def ListOrders(
        self,
        request: trading_pb2.ListOrdersRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListOrdersResponse:
        """List orders for a tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        executor = None
        try:
            tenant_id, _user_id = _identity(request.context)
            session_id = UUID(request.session_id) if request.session_id else None
            status = request.statuses[0] if request.statuses else None

            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            executor = await create_order_executor(tenant_id=tenant_id)
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
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("ListOrders error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to list orders")
        finally:
            await _aclose(executor)

    async def GetPosition(
        self,
        request: trading_pb2.GetPositionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.GetPositionResponse:
        """Get a position by symbol."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            service = await create_position_service(tenant_id)
            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )
            if not position:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Position not found for symbol: {symbol}"
                )

            return trading_pb2.GetPositionResponse(position=self._to_proto_position(position))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("GetPosition error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to get position")
        finally:
            await _aclose(service)

    async def ListPositions(
        self,
        request: trading_pb2.ListPositionsRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ListPositionsResponse:
        """List positions for a session."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            session_id = UUID(request.session_id)

            service = await create_position_service(tenant_id)
            positions = await service.list_open_positions(
                tenant_id=tenant_id,
                session_id=session_id,
            )

            proto_positions = [self._to_proto_position(p) for p in positions]
            return trading_pb2.ListPositionsResponse(positions=proto_positions)
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except Exception as e:
            logger.error("ListPositions error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to list positions")
        finally:
            await _aclose(service)

    async def ClosePosition(
        self,
        request: trading_pb2.ClosePositionRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> trading_pb2.ClosePositionResponse:
        """Close a position."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        executor = None
        service = None
        try:
            tenant_id, _user_id = _identity(request.context)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            service = await create_position_service(tenant_id)
            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )
            if not position:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"No position for symbol: {symbol}")

            quantity = (
                Decimal(request.quantity.value)
                if request.HasField("quantity") and Decimal(request.quantity.value) > 0
                else Decimal(str(position.qty))
            )
            side = ORDER_SIDE_SELL if position.side == "long" else ORDER_SIDE_BUY

            order_create = OrderCreate(
                symbol=symbol,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                time_in_force=TIME_IN_FORCE_DAY,
                qty=float(quantity),
            )

            # Closing order hits the session's own brokerage account (2A).
            executor = await create_order_executor(session_id=session_id, tenant_id=tenant_id)
            order = await executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order_create,
            )

            return trading_pb2.ClosePositionResponse(order=self._to_proto_order(order))
        except grpc.aio.AioRpcError:
            raise
        except AuthError as e:
            await _abort_auth(context, e)
        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("ClosePosition error: %s", e, exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to close position")
        finally:
            await _aclose(executor)
            await _aclose(service)

    async def StreamOrderUpdates(
        self,
        request: trading_pb2.StreamOrderUpdatesRequest,
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> AsyncGenerator[trading_pb2.OrderUpdate]:
        """Stream real-time order updates via Redis Streams (tail-read)."""
        # Require a valid principal before streaming (1A).
        try:
            _identity(request.context)
        except AuthError as e:
            await _abort_auth(context, e)
            return
        session_id = request.session_id
        logger.info("Starting order updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
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
        try:
            _identity(request.context)
        except AuthError as e:
            await _abort_auth(context, e)
            return
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
            # The deterministic client_order_id (idempotency key), NOT the broker id.
            client_order_id=order.client_order_id or "",
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
