"""Trading Connect servicer implementation."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from llamatrade_common import pagination_response, resolve_pagination
from llamatrade_common.connect import resolve_identity_connect
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_UNSPECIFIED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
    OrderStatus,
)
from llamatrade_proto.timestamps import to_proto_timestamp

from src import proto_mappers
from src.executor.order_executor import create_order_executor
from src.models import OrderCreate, SessionResponse, order_side_to_str
from src.streaming import get_trading_event_subscriber

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from llamatrade_proto.clients.ledger import LedgerClient
    from llamatrade_proto.generated import trading_pb2

logger = logging.getLogger(__name__)

# Status values a client may filter on; UNSPECIFIED is the "no filter" sentinel (never a filter value), and a value outside the enum has no database label to bind to.
_ORDER_STATUS_FILTERS = frozenset(OrderStatus.values()) - {ORDER_STATUS_UNSPECIFIED}
# Sessions carry a narrower set than ExecutionStatus: there is no PENDING session label.
_SESSION_STATUS_FILTERS = frozenset(
    {
        EXECUTION_STATUS_RUNNING,
        EXECUTION_STATUS_PAUSED,
        EXECUTION_STATUS_STOPPED,
        EXECUTION_STATUS_ERROR,
    }
)


def _status_filter(values: Sequence[int], allowed: frozenset[int], field: str) -> int | None:
    """The status filter a request carries, or None when the field is unset.

    Every value is checked, so an explicit UNSPECIFIED or an int outside the enum is
    reported as INVALID_ARGUMENT instead of failing later on the database enum bridge.
    Only the first value is applied — the service layer filters on one status.
    """
    for value in values:
        if value not in allowed:
            raise ConnectError(
                Code.INVALID_ARGUMENT,
                f"{field}: {value} is not a valid filter value (expected one of {sorted(allowed)})",
            )
    return values[0] if values else None


async def _aclose(obj: object | None) -> None:
    """Best-effort release of a request-scoped service's resources.

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
    """Connect servicer for the Trading service.

    Implements the TradingService Protocol defined in trading_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._ledger_client: LedgerClient | None = None

    def _get_ledger(self) -> LedgerClient:
        """Lazy LedgerClient to the portfolio service (sleeve resolution)."""
        if self._ledger_client is None:
            from src.attribution import get_ledger_client

            self._ledger_client = get_ledger_client()
        return self._ledger_client

    async def _resolve_order_attribution(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: str,
        session_id: UUID,
        requested_sleeve_id: str,
        symbol: str,
        side: str,
    ) -> tuple[UUID | None, UUID | None]:
        """(sleeve_id, account_id) for an order, fixed at origination.

        Delegates to the shared resolver (``src.attribution``); a resolution
        failure raises so the SubmitOrder RPC fails rather than silently booking
        the order as an unattributed manual trade (hardening 7A). ``symbol``/``side``
        drive Unmanaged sell-routing: a manual sell of a holding the Manual sleeve
        does not carry books against Unmanaged instead of freezing the book.
        """
        from src.attribution import resolve_order_attribution

        return await resolve_order_attribution(
            db=db,
            ledger=self._get_ledger(),
            tenant_id=tenant_id,
            session_id=session_id,
            requested_sleeve_id=requested_sleeve_id,
            user_id=user_id,
            symbol=symbol,
            side=side,
        )

    async def start_session(
        self,
        request: trading_pb2.StartTradingSessionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.StartTradingSessionResponse:
        """Start a trading session (preflight checks + runner launch)."""
        from llamatrade_proto.generated import trading_pb2
        from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, user_id = resolve_identity_connect(request.context)
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
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("start_session error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to start session")
        finally:
            await _aclose(service)

    async def stop_session(
        self,
        request: trading_pb2.StopTradingSessionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.StopTradingSessionResponse:
        """Stop a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.stop_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                raise ConnectError(Code.NOT_FOUND, "Session not found")
            return trading_pb2.StopTradingSessionResponse(session=self._to_proto_session(session))
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("stop_session error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to stop session")
        finally:
            await _aclose(service)

    async def pause_session(
        self,
        request: trading_pb2.PauseTradingSessionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.PauseTradingSessionResponse:
        """Pause a trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.pause_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                raise ConnectError(Code.NOT_FOUND, "Session not found")
            return trading_pb2.PauseTradingSessionResponse(session=self._to_proto_session(session))
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("pause_session error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to pause session")
        finally:
            await _aclose(service)

    async def resume_session(
        self,
        request: trading_pb2.ResumeTradingSessionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.ResumeTradingSessionResponse:
        """Resume a paused trading session and its runner."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.resume_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                raise ConnectError(Code.NOT_FOUND, "Session not found")
            return trading_pb2.ResumeTradingSessionResponse(session=self._to_proto_session(session))
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))
        except Exception as e:
            logger.error("resume_session error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to resume session")
        finally:
            await _aclose(service)

    async def get_session(
        self,
        request: trading_pb2.GetTradingSessionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.GetTradingSessionResponse:
        """Get a trading session with P&L."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            service = await create_live_session_service(tenant_id)
            session = await service.get_session(
                session_id=UUID(request.session_id),
                tenant_id=tenant_id,
            )
            if session is None:
                raise ConnectError(Code.NOT_FOUND, "Session not found")
            return trading_pb2.GetTradingSessionResponse(session=self._to_proto_session(session))
        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_session error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to get session")
        finally:
            await _aclose(service)

    async def list_sessions(
        self,
        request: trading_pb2.ListTradingSessionsRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.ListTradingSessionsResponse:
        """List trading sessions for the tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        from src.services.live_session_service import create_live_session_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            service = await create_live_session_service(tenant_id)
            page, page_size = resolve_pagination(
                request.pagination if request.HasField("pagination") else None
            )
            # Singular proto3 enum: an unset filter and an explicit UNSPECIFIED share the same wire value, so 0 keeps its documented "all statuses" meaning.
            status = _status_filter(
                (request.status,) if request.status else (), _SESSION_STATUS_FILTERS, "status"
            )
            sessions, total = await service.list_sessions(
                tenant_id=tenant_id,
                status=status,
                strategy_id=UUID(request.strategy_id) if request.strategy_id else None,
                page=page,
                page_size=page_size,
            )
            return trading_pb2.ListTradingSessionsResponse(
                sessions=[self._to_proto_session(s) for s in sessions],
                pagination=common_pb2.PaginationResponse(
                    **pagination_response(total, page, page_size)
                ),
            )
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("list_sessions error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to list sessions")
        finally:
            await _aclose(service)

    async def submit_order(
        self,
        request: trading_pb2.SubmitOrderRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.SubmitOrderResponse:
        """Submit a new order."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, user_id = resolve_identity_connect(request.context)
            session_id = UUID(request.session_id)

            # The executor's Alpaca client is built from this session's own per-tenant credentials, never the platform default.
            executor = await create_order_executor(session_id=session_id, tenant_id=tenant_id)

            # Ledger attribution, fixed at origination (portfolio-ledger.md); symbol/side let a manual sell of an Unmanaged-only holding route there.
            sleeve_id, account_id = await self._resolve_order_attribution(
                db=executor.db,
                tenant_id=tenant_id,
                user_id=str(user_id),
                session_id=session_id,
                requested_sleeve_id=request.sleeve_id,
                symbol=request.symbol,
                side=order_side_to_str(request.side or ORDER_SIDE_BUY),
            )

            order_create = OrderCreate(
                symbol=request.symbol,
                side=request.side or ORDER_SIDE_BUY,
                order_type=request.type or ORDER_TYPE_MARKET,
                time_in_force=request.time_in_force or TIME_IN_FORCE_DAY,
                qty=Decimal(request.quantity.value)
                if request.HasField("quantity")
                else Decimal("0"),
                limit_price=Decimal(request.limit_price.value)
                if request.HasField("limit_price")
                else None,
                stop_price=Decimal(request.stop_price.value)
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
            return trading_pb2.SubmitOrderResponse(order=proto_mappers.order_to_proto(order))
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("submit_order error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to submit order")
        finally:
            await _aclose(executor)

    async def cancel_order(
        self,
        request: trading_pb2.CancelOrderRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.CancelOrderResponse:
        """Cancel an order."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            order_id = UUID(request.order_id)

            # Resolve the order's owning session first so the cancel hits the tenant's OWN Alpaca account via that session's per-tenant credentials, never the platform/env account (GAP 10); the lookup needs no broker client, so a tenant-only executor suffices.
            probe = await create_order_executor(tenant_id=tenant_id)
            try:
                session_id = await probe.get_order_session_id(order_id, tenant_id)
            finally:
                await _aclose(probe)
            if session_id is None:
                raise ConnectError(Code.NOT_FOUND, f"Order not found: {order_id}")

            executor = await create_order_executor(session_id=session_id, tenant_id=tenant_id)
            success = await executor.cancel_order(order_id=order_id, tenant_id=tenant_id)
            if not success:
                raise ConnectError(Code.FAILED_PRECONDITION, "Cannot cancel order")

            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                raise ConnectError(Code.NOT_FOUND, f"Order not found: {order_id}")

            return trading_pb2.CancelOrderResponse(order=proto_mappers.order_to_proto(order))
        except ConnectError:
            raise
        except Exception as e:
            logger.error("cancel_order error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to cancel order")
        finally:
            await _aclose(executor)

    async def get_order(
        self,
        request: trading_pb2.GetOrderRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.GetOrderResponse:
        """Get an order by ID."""
        from llamatrade_proto.generated import trading_pb2

        executor = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            order_id = UUID(request.order_id)

            executor = await create_order_executor(tenant_id=tenant_id)
            order = await executor.get_order(order_id=order_id, tenant_id=tenant_id)
            if not order:
                raise ConnectError(Code.NOT_FOUND, f"Order not found: {order_id}")

            return trading_pb2.GetOrderResponse(order=proto_mappers.order_to_proto(order))
        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_order error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to get order")
        finally:
            await _aclose(executor)

    async def list_orders(
        self,
        request: trading_pb2.ListOrdersRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.ListOrdersResponse:
        """List orders for a tenant."""
        from llamatrade_proto.generated import common_pb2, trading_pb2

        executor = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            session_id = UUID(request.session_id) if request.session_id else None
            status = _status_filter(request.statuses, _ORDER_STATUS_FILTERS, "statuses")

            page, page_size = resolve_pagination(
                request.pagination if request.HasField("pagination") else None
            )

            executor = await create_order_executor(tenant_id=tenant_id)
            orders, total = await executor.list_orders(
                tenant_id=tenant_id,
                session_id=session_id,
                status=status,
                page=page,
                page_size=page_size,
            )

            proto_orders = [proto_mappers.order_to_proto(o) for o in orders]

            return trading_pb2.ListOrdersResponse(
                orders=proto_orders,
                pagination=common_pb2.PaginationResponse(
                    **pagination_response(total, page, page_size)
                ),
            )
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("list_orders error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to list orders")
        finally:
            await _aclose(executor)

    async def get_position(
        self,
        request: trading_pb2.GetPositionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.GetPositionResponse:
        """Get a position by symbol."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            service = await create_position_service(tenant_id)
            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )
            if not position:
                raise ConnectError(Code.NOT_FOUND, f"Position not found for symbol: {symbol}")

            return trading_pb2.GetPositionResponse(
                position=proto_mappers.position_to_proto(position)
            )
        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_position error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to get position")
        finally:
            await _aclose(service)

    async def list_positions(
        self,
        request: trading_pb2.ListPositionsRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.ListPositionsResponse:
        """List positions for a session."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            session_id = UUID(request.session_id)

            service = await create_position_service(tenant_id)
            positions = await service.list_open_positions(
                tenant_id=tenant_id,
                session_id=session_id,
            )

            proto_positions = [proto_mappers.position_to_proto(p) for p in positions]
            return trading_pb2.ListPositionsResponse(positions=proto_positions)
        except ConnectError:
            raise
        except Exception as e:
            logger.error("list_positions error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to list positions")
        finally:
            await _aclose(service)

    async def close_position(
        self,
        request: trading_pb2.ClosePositionRequest,
        ctx: RequestContext[object, object],
    ) -> trading_pb2.ClosePositionResponse:
        """Close a position."""
        from llamatrade_proto.generated import trading_pb2

        from src.services.position_service import create_position_service

        executor = None
        service = None
        try:
            tenant_id, _user_id = resolve_identity_connect(request.context)
            session_id = UUID(request.session_id)
            symbol = request.symbol

            service = await create_position_service(tenant_id)
            position = await service.get_position(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
            )
            if not position:
                raise ConnectError(Code.NOT_FOUND, f"No position for symbol: {symbol}")

            quantity = (
                Decimal(request.quantity.value)
                if request.HasField("quantity") and Decimal(request.quantity.value) > 0
                else position.qty
            )
            # position.side is the proto PositionSide int (DB row), not a string.
            side = (
                ORDER_SIDE_SELL
                if position.side == trading_pb2.POSITION_SIDE_LONG
                else ORDER_SIDE_BUY
            )

            order_create = OrderCreate(
                symbol=symbol,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                time_in_force=TIME_IN_FORCE_DAY,
                qty=quantity,
            )

            # Closing order hits the session's own brokerage account.
            executor = await create_order_executor(session_id=session_id, tenant_id=tenant_id)
            order = await executor.submit_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order_create,
            )

            return trading_pb2.ClosePositionResponse(order=proto_mappers.order_to_proto(order))
        except ConnectError:
            raise
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("close_position error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, "Failed to close position")
        finally:
            await _aclose(executor)
            await _aclose(service)

    async def stream_order_updates(
        self,
        request: trading_pb2.StreamOrderUpdatesRequest,
        ctx: RequestContext[object, object],
    ) -> AsyncGenerator[trading_pb2.OrderUpdate]:
        """Stream real-time order updates via Redis Streams (tail-read)."""
        # Require a valid principal before streaming (raises ConnectError on failure).
        resolve_identity_connect(request.context)
        session_id = request.session_id
        logger.info("Starting order updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            async for cursor, update in subscriber.tail_orders(
                session_id, last_seen_id=request.last_seen_id
            ):
                update.stream_cursor = cursor
                yield update

        except asyncio.CancelledError:
            logger.info("Order updates stream cancelled for session: %s", session_id)
        except Exception as e:
            logger.error("Order stream error for session %s: %s", session_id, e, exc_info=True)
            raise
        finally:
            await subscriber.close()

    async def stream_position_updates(
        self,
        request: trading_pb2.StreamPositionUpdatesRequest,
        ctx: RequestContext[object, object],
    ) -> AsyncGenerator[trading_pb2.PositionUpdate]:
        """Stream real-time position updates via Redis Streams (tail-read)."""
        resolve_identity_connect(request.context)
        session_id = request.session_id
        logger.info("Starting position updates stream for session: %s", session_id)

        subscriber = get_trading_event_subscriber()
        try:
            async for cursor, update in subscriber.tail_positions(
                session_id, last_seen_id=request.last_seen_id
            ):
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
            started_at=to_proto_timestamp(session.started_at),
            sleeve_id=str(session.sleeve_id) if session.sleeve_id else "",
            account_id=str(session.account_id) if session.account_id else "",
        )
        if session.stopped_at:
            proto.ended_at.CopyFrom(to_proto_timestamp(session.stopped_at))
        return proto
