"""Trading event publisher for real-time updates via Redis Streams.

Publishes order/position UI events and ledger fill/lifecycle payloads onto
durable Redis Streams (via the shared ``EventBus``). UI events fan out to live
tail-readers (each gets the full stream + reconnect replay); ledger payloads are
consumed by the portfolio service's durable consumer group.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from llamatrade_common.events import Event, EventBus, EventType

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# One global durable stream for ledger fill/lifecycle payloads (bus-namespaced
# to lt:ledger:fills). Single stream — not per-account — because XREADGROUP has
# no pattern-subscribe, global order preserves per-account FIFO, and payloads
# already carry account_id. See CONTRACTS.md §1.
LEDGER_FILLS_STREAM = "ledger:fills"
LEDGER_FILLS_MAXLEN = 10_000

# Per-session UI event streams: tail-read fan-out so each browser/gRPC stream
# gets its own full copy and a reconnect replays the gap from the client's
# last-seen cursor. Entries are the shared `Event` envelope (id/type/timestamp +
# JSON `data` body) via Event.to_redis_stream(), so the wire carries a semantic
# event type instead of an opaque "payload" blob.
TRADING_ORDERS_STREAM_PREFIX = "trading:orders"
TRADING_POSITIONS_STREAM_PREFIX = "trading:positions"
TRADING_UI_MAXLEN = 1_000


def orders_stream(session_id: UUID | str) -> str:
    return f"{TRADING_ORDERS_STREAM_PREFIX}:{session_id}"


def positions_stream(session_id: UUID | str) -> str:
    return f"{TRADING_POSITIONS_STREAM_PREFIX}:{session_id}"


@dataclass
class OrderUpdate:
    """Order update message for streaming."""

    session_id: str
    order_id: str
    alpaca_order_id: str | None
    symbol: str
    side: str
    qty: float
    order_type: str
    status: str
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    submitted_at: str | None = None
    filled_at: str | None = None
    update_type: str = "status_change"  # "submitted", "status_change", "filled", "cancelled"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "order_id": self.order_id,
            "alpaca_order_id": self.alpaca_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "filled_avg_price": self.filled_avg_price,
            "submitted_at": self.submitted_at,
            "filled_at": self.filled_at,
            "update_type": self.update_type,
            "timestamp": self.timestamp,
        }


@dataclass
class PositionUpdate:
    """Position update message for streaming."""

    session_id: str
    symbol: str
    qty: float
    side: str
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float
    update_type: str = "change"  # "opened", "increased", "reduced", "closed", "change"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "qty": self.qty,
            "side": self.side,
            "cost_basis": self.cost_basis,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_percent": self.unrealized_pnl_percent,
            "current_price": self.current_price,
            "update_type": self.update_type,
            "timestamp": self.timestamp,
        }


# Map a domain update_type to a semantic envelope EventType. "status_change"
# (and any unmapped kind) falls back to the generic *_UPDATED member.
_ORDER_EVENT_TYPES: dict[str, EventType] = {
    "submitted": EventType.ORDER_SUBMITTED,
    "filled": EventType.ORDER_FILLED,
    "cancelled": EventType.ORDER_CANCELLED,
    "rejected": EventType.ORDER_REJECTED,
    "status_change": EventType.ORDER_UPDATED,
}
_POSITION_EVENT_TYPES: dict[str, EventType] = {
    "opened": EventType.POSITION_OPENED,
    "closed": EventType.POSITION_CLOSED,
    "increased": EventType.POSITION_UPDATED,
    "reduced": EventType.POSITION_UPDATED,
    "change": EventType.POSITION_UPDATED,
}


def _order_event(order: OrderUpdate) -> Event:
    """Wrap an order update in the canonical Event envelope for the stream."""
    return Event(
        type=_ORDER_EVENT_TYPES.get(order.update_type, EventType.ORDER_UPDATED),
        data=order.to_dict(),
    )


def _position_event(position: PositionUpdate) -> Event:
    """Wrap a position update in the canonical Event envelope for the stream."""
    return Event(
        type=_POSITION_EVENT_TYPES.get(position.update_type, EventType.POSITION_UPDATED),
        data=position.to_dict(),
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

    def __init__(self, redis_url: str | None = None, event_bus: EventBus | None = None):
        """Initialize the publisher.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
            event_bus: Streams transport (injected in tests; lazily created
                otherwise).
        """
        self.redis_url = redis_url or REDIS_URL
        self._bus: EventBus | None = event_bus

    def _get_bus(self) -> EventBus:
        """Get or create the Streams bus (namespaced keys)."""
        if self._bus is None:
            self._bus = EventBus(self.redis_url)
        return self._bus

    async def publish_order_update(
        self,
        session_id: UUID | str,
        order: OrderUpdate,
    ) -> str:
        """Publish an order update to the session's order stream.

        Returns the assigned stream entry id.
        """
        entry_id = await self._get_bus().publish(
            orders_stream(session_id),
            _order_event(order).to_redis_stream(),
            maxlen=TRADING_UI_MAXLEN,
        )
        logger.debug(
            "Published order update",
            extra={"order_id": order.order_id, "status": order.status, "entry_id": entry_id},
        )
        return entry_id

    async def publish_position_update(
        self,
        session_id: UUID | str,
        position: PositionUpdate,
    ) -> str:
        """Publish a position update to the session's position stream.

        Returns the assigned stream entry id.
        """
        entry_id = await self._get_bus().publish(
            positions_stream(session_id),
            _position_event(position).to_redis_stream(),
            maxlen=TRADING_UI_MAXLEN,
        )
        logger.debug(
            "Published position update",
            extra={"symbol": position.symbol, "qty": position.qty, "entry_id": entry_id},
        )
        return entry_id

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
        update = OrderUpdate(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="submitted",
            update_type="submitted",
            submitted_at=datetime.now(UTC).isoformat(),
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
        now = datetime.now(UTC).isoformat()
        update = OrderUpdate(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="filled",
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
            filled_at=now,
            update_type="filled",
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
        update = OrderUpdate(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id=alpaca_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            status="cancelled",
            filled_qty=filled_qty,
            update_type="cancelled",
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
        update = PositionUpdate(
            session_id=str(session_id),
            symbol=symbol,
            qty=qty,
            side=side,
            cost_basis=cost_basis,
            market_value=cost_basis,  # Initially same as cost
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
            current_price=entry_price,
            update_type="opened",
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
        update = PositionUpdate(
            session_id=str(session_id),
            symbol=symbol,
            qty=0.0,
            side=side,
            cost_basis=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
            current_price=exit_price,
            update_type="closed",
        )
        return await self.publish_position_update(session_id, update)

    async def publish_ledger_fill(
        self,
        account_id: UUID | str,
        payload: dict[str, str],
    ) -> str:
        """Publish a ledger event payload to the global ``ledger:fills`` stream.

        The portfolio service's fill consumer group ingests these into the
        double-entry ledger (see .docs/planning/CONTRACTS.md §1/§4). Payloads
        are built by ``src.ledger_events`` — fills and order lifecycle
        (reservation) events share this stream. Returns the stream entry id.
        """
        from src.metrics import record_ledger_publish

        kind = payload.get("event_type", "order_filled")
        try:
            entry_id = await self._get_bus().publish(
                LEDGER_FILLS_STREAM, payload, maxlen=LEDGER_FILLS_MAXLEN
            )
        except Exception:
            record_ledger_publish(kind, "failure")
            raise
        record_ledger_publish(kind, "success")
        logger.debug(
            "Published ledger event",
            extra={
                "client_order_id": payload.get("client_order_id"),
                "event_type": kind,
                "entry_id": entry_id,
            },
        )
        return entry_id

    async def close(self) -> None:
        """Close the Streams bus, if created."""
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
