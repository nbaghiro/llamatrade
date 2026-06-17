"""Trading event publisher for real-time updates via Redis Streams.

Publishes order/position UI events and ledger fill/lifecycle payloads onto
durable Redis Streams (via the shared ``EventBus``). UI events fan out to live
tail-readers (each gets the full stream + reconnect replay); ledger payloads are
consumed by the portfolio service's durable consumer group.

Order/position UI events carry the proto ``trading_pb2.OrderUpdate`` /
``trading_pb2.PositionUpdate`` directly (the same message the gRPC edge streams),
wrapped in an event envelope by ``OrderEvents`` / ``PositionEvents``.
"""

import logging
import os
from datetime import UTC, datetime
from uuid import UUID

from llamatrade_events import EventBus as EventsBus
from llamatrade_events import (
    FillEvents,
    LedgerFill,
    LedgerReservation,
    OrderEvents,
    PositionEvents,
    RedisStreamsTransport,
)
from llamatrade_proto.generated import common_pb2, trading_pb2

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Status string → proto OrderStatus enum.
_ORDER_STATUS: dict[str, trading_pb2.OrderStatus.ValueType] = {
    "submitted": trading_pb2.ORDER_STATUS_SUBMITTED,
    "pending": trading_pb2.ORDER_STATUS_PENDING,
    "accepted": trading_pb2.ORDER_STATUS_ACCEPTED,
    "partial": trading_pb2.ORDER_STATUS_PARTIAL,
    "filled": trading_pb2.ORDER_STATUS_FILLED,
    "cancelled": trading_pb2.ORDER_STATUS_CANCELLED,
    "rejected": trading_pb2.ORDER_STATUS_REJECTED,
    "expired": trading_pb2.ORDER_STATUS_EXPIRED,
}

# Side string → proto OrderSide enum.
_ORDER_SIDE: dict[str, trading_pb2.OrderSide.ValueType] = {
    "buy": trading_pb2.ORDER_SIDE_BUY,
    "sell": trading_pb2.ORDER_SIDE_SELL,
}

# Order type string → proto OrderType enum.
_ORDER_TYPE: dict[str, trading_pb2.OrderType.ValueType] = {
    "market": trading_pb2.ORDER_TYPE_MARKET,
    "limit": trading_pb2.ORDER_TYPE_LIMIT,
    "stop": trading_pb2.ORDER_TYPE_STOP,
    "stop_limit": trading_pb2.ORDER_TYPE_STOP_LIMIT,
    "trailing_stop": trading_pb2.ORDER_TYPE_TRAILING_STOP,
}


def _now_timestamp() -> common_pb2.Timestamp:
    """Current time as a proto Timestamp (whole seconds)."""
    return common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp()))


def _build_order_update(
    *,
    session_id: str,
    order_id: str,
    alpaca_order_id: str | None,
    symbol: str,
    side: str,
    qty: float,
    order_type: str,
    status: str,
    event_type: str,
    filled_qty: float = 0.0,
    filled_avg_price: float | None = None,
) -> trading_pb2.OrderUpdate:
    """Build a proto ``OrderUpdate`` (embedded Order + event_type + timestamp).

    Enum strings are mapped to their proto int values; numeric fields are wrapped
    in ``common_pb2.Decimal``. ``event_type`` drives the bus's semantic EventType
    mapping ("submitted"/"filled"/"cancelled"/"rejected"/"partial_fill").
    """
    order = trading_pb2.Order(
        id=order_id,
        client_order_id=alpaca_order_id or "",
        session_id=session_id,
        symbol=symbol,
        side=_ORDER_SIDE.get(side.lower(), trading_pb2.ORDER_SIDE_BUY),
        type=_ORDER_TYPE.get(order_type.lower(), trading_pb2.ORDER_TYPE_MARKET),
        status=_ORDER_STATUS.get(status.lower(), trading_pb2.ORDER_STATUS_SUBMITTED),
        quantity=common_pb2.Decimal(value=str(qty)),
    )
    if filled_qty > 0:
        order.filled_quantity.CopyFrom(common_pb2.Decimal(value=str(filled_qty)))
    if filled_avg_price is not None:
        order.average_fill_price.CopyFrom(common_pb2.Decimal(value=str(filled_avg_price)))

    return trading_pb2.OrderUpdate(
        order=order,
        event_type=event_type,
        timestamp=_now_timestamp(),
    )


def _build_position_update(
    *,
    session_id: str,
    symbol: str,
    qty: float,
    side: str,
    cost_basis: float,
    market_value: float,
    unrealized_pnl: float,
    unrealized_pnl_percent: float,
    current_price: float,
    event_type: str,
) -> trading_pb2.PositionUpdate:
    """Build a proto ``PositionUpdate`` (embedded Position + event_type + timestamp).

    ``event_type`` drives the bus's semantic EventType mapping
    ("opened"/"closed"/"updated").
    """
    side_enum = (
        trading_pb2.POSITION_SIDE_LONG
        if side.lower() == "long"
        else trading_pb2.POSITION_SIDE_SHORT
    )
    position = trading_pb2.Position(
        session_id=session_id,
        symbol=symbol,
        side=side_enum,
        quantity=common_pb2.Decimal(value=str(qty)),
    )
    if cost_basis:
        position.cost_basis.CopyFrom(common_pb2.Decimal(value=str(cost_basis)))
    if qty > 0 and cost_basis:
        position.average_entry_price.CopyFrom(common_pb2.Decimal(value=str(cost_basis / qty)))
    if current_price:
        position.current_price.CopyFrom(common_pb2.Decimal(value=str(current_price)))
    if market_value:
        position.market_value.CopyFrom(common_pb2.Decimal(value=str(market_value)))
    if unrealized_pnl:
        position.unrealized_pnl.CopyFrom(common_pb2.Decimal(value=str(unrealized_pnl)))
    if unrealized_pnl_percent:
        position.unrealized_pnl_percent.CopyFrom(
            common_pb2.Decimal(value=str(unrealized_pnl_percent))
        )

    return trading_pb2.PositionUpdate(
        position=position,
        event_type=event_type,
        timestamp=_now_timestamp(),
    )


class TradingEventPublisher:
    """Publishes trading events (orders, positions, ledger fills) to Redis Streams.

    Each session has its own UI streams for orders and positions; ledger
    fill/lifecycle payloads go to one global stream.

    Streams:
        - lt:trading:orders:{session_id}    - order UI updates (tail)
        - lt:trading:positions:{session_id} - position UI updates (tail)
        - lt:ledger:fills                   - ledger fill/lifecycle (consumer group)
    """

    def __init__(
        self,
        redis_url: str | None = None,
        orders_events: OrderEvents | None = None,
        positions_events: PositionEvents | None = None,
        fills: FillEvents | None = None,
    ):
        """Initialize the publisher.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
            orders_events: Order UI-stream channel (injected in tests; lazily
                created otherwise).
            positions_events: Position UI-stream channel (injected in tests;
                lazily created otherwise).
            fills: Ledger fill/reservation publisher (injected in tests; lazily
                created otherwise). Proto wire onto ``lt:ledger:fills``.
        """
        self.redis_url = redis_url or REDIS_URL
        self._bus: EventsBus | None = None
        self._orders_events: OrderEvents | None = orders_events
        self._positions_events: PositionEvents | None = positions_events
        self._fills: FillEvents | None = fills

    def _get_bus(self) -> EventsBus:
        """Get or create the shared events bus (Redis Streams transport)."""
        if self._bus is None:
            self._bus = EventsBus(RedisStreamsTransport(self.redis_url))
        return self._bus

    def _get_orders_events(self) -> OrderEvents:
        """Get or create the order UI-stream channel."""
        if self._orders_events is None:
            self._orders_events = OrderEvents(bus=self._get_bus())
        return self._orders_events

    def _get_positions_events(self) -> PositionEvents:
        """Get or create the position UI-stream channel."""
        if self._positions_events is None:
            self._positions_events = PositionEvents(bus=self._get_bus())
        return self._positions_events

    def _get_fills(self) -> FillEvents:
        """Get or create the ledger fill/reservation publisher (proto wire)."""
        if self._fills is None:
            self._fills = FillEvents(bus=self._get_bus())
        return self._fills

    async def publish_order_update(
        self,
        session_id: UUID | str,
        update: trading_pb2.OrderUpdate,
    ) -> str:
        """Publish an order update to the session's order stream.

        Returns the assigned stream entry cursor.
        """
        cursor = await self._get_orders_events().publish(str(session_id), update)
        logger.debug(
            "Published order update",
            extra={
                "order_id": update.order.id,
                "event_type": update.event_type,
                "cursor": cursor,
            },
        )
        return cursor

    async def publish_position_update(
        self,
        session_id: UUID | str,
        update: trading_pb2.PositionUpdate,
    ) -> str:
        """Publish a position update to the session's position stream.

        Returns the assigned stream entry cursor.
        """
        cursor = await self._get_positions_events().publish(str(session_id), update)
        logger.debug(
            "Published position update",
            extra={
                "symbol": update.position.symbol,
                "event_type": update.event_type,
                "cursor": cursor,
            },
        )
        return cursor

    async def publish_order_submitted(
        self,
        session_id: UUID | str,
        order_id: UUID | str,
        alpaca_order_id: str | None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
    ) -> str:
        """Convenience method for publishing order submitted event."""
        update = _build_order_update(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="submitted",
            event_type="submitted",
        )
        return await self.publish_order_update(session_id, update)

    async def publish_order_filled(
        self,
        session_id: UUID | str,
        order_id: UUID | str,
        alpaca_order_id: str | None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        filled_qty: float,
        filled_avg_price: float,
    ) -> str:
        """Convenience method for publishing order filled event."""
        update = _build_order_update(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="filled",
            event_type="filled",
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
        )
        return await self.publish_order_update(session_id, update)

    async def publish_order_cancelled(
        self,
        session_id: UUID | str,
        order_id: UUID | str,
        alpaca_order_id: str | None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        filled_qty: float = 0.0,
    ) -> str:
        """Convenience method for publishing order cancelled event."""
        update = _build_order_update(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="cancelled",
            event_type="cancelled",
            filled_qty=filled_qty,
        )
        return await self.publish_order_update(session_id, update)

    async def publish_position_opened(
        self,
        session_id: UUID | str,
        symbol: str,
        qty: float,
        side: str,
        entry_price: float,
    ) -> str:
        """Convenience method for publishing position opened event."""
        cost_basis = qty * entry_price
        update = _build_position_update(
            session_id=str(session_id),
            symbol=symbol,
            qty=qty,
            side=side,
            cost_basis=cost_basis,
            market_value=cost_basis,  # Initially same as cost
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
            current_price=entry_price,
            event_type="opened",
        )
        return await self.publish_position_update(session_id, update)

    async def publish_position_closed(
        self,
        session_id: UUID | str,
        symbol: str,
        side: str,
        exit_price: float,
        realized_pnl: float,
    ) -> str:
        """Convenience method for publishing position closed event."""
        update = _build_position_update(
            session_id=str(session_id),
            symbol=symbol,
            qty=0.0,
            side=side,
            cost_basis=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
            current_price=exit_price,
            event_type="closed",
        )
        return await self.publish_position_update(session_id, update)

    async def publish_ledger_fill(
        self,
        message: LedgerFill | LedgerReservation,
    ) -> str:
        """Publish a ledger proto message to the global ``ledger:fills`` stream.

        The portfolio service's fill consumer group ingests these into the
        double-entry ledger (see .docs/planning/CONTRACTS.md §1/§4). Messages are
        built by ``src.ledger_events`` — ``LedgerFill`` and ``LedgerReservation``
        share this stream, discriminated by their EventType. Idempotency seeds
        (``client_order_id`` / ``client_order_id:event_type``) are set by
        ``FillEvents``. Returns the stream entry id.
        """
        from src.metrics import record_ledger_publish

        is_reservation = isinstance(message, LedgerReservation)
        kind = message.event_type if is_reservation else "order_filled"
        try:
            fills = self._get_fills()
            entry_id = (
                await fills.publish_reservation(message)
                if is_reservation
                else await fills.publish_fill(message)
            )
        except Exception:
            record_ledger_publish(kind, "failure")
            raise
        record_ledger_publish(kind, "success")
        logger.debug(
            "Published ledger event",
            extra={
                "client_order_id": message.client_order_id,
                "event_type": kind,
                "entry_id": entry_id,
            },
        )
        return entry_id

    async def close(self) -> None:
        """Close the orders/positions/ledger channels and the shared bus."""
        if self._orders_events is not None:
            await self._orders_events.close()
            self._orders_events = None
        if self._positions_events is not None:
            await self._positions_events.close()
            self._positions_events = None
        if self._fills is not None:
            await self._fills.close()
            self._fills = None
        if self._bus is not None:
            await self._bus.close()
            self._bus = None


# Singleton instance
_publisher: TradingEventPublisher | None = None


def get_trading_event_publisher(redis_url: str | None = None) -> TradingEventPublisher:
    """Get the trading event publisher instance.

    Args:
        redis_url: Optional Redis URL. Only used on first call.

    Returns:
        TradingEventPublisher instance.
    """
    global _publisher
    if _publisher is None:
        _publisher = TradingEventPublisher(redis_url)
    return _publisher
