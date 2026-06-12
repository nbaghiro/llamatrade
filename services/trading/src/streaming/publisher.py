"""Trading event publisher for real-time updates via Redis pub/sub.

This module provides the publisher side of the streaming infrastructure,
allowing order and position updates to be broadcast to subscribers.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis

from llamatrade_common.eventbus import (
    EventBus,
    streams_ledger_fills_enabled,
    streams_trading_enabled,
)

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# One global durable stream for ledger fill/lifecycle payloads (bus-namespaced
# to lt:ledger:fills). Single stream — not per-account — because XREADGROUP has
# no pattern-subscribe, global order preserves per-account FIFO, and payloads
# already carry account_id. See CONTRACTS.md §1.
LEDGER_FILLS_STREAM = "ledger:fills"
LEDGER_FILLS_MAXLEN = 10_000

# Per-session UI event streams (STREAMS_TRADING): tail-read fan-out so each
# browser/gRPC stream gets its own full copy and a reconnect replays the gap
# from the client's last-seen cursor. Entries carry the same JSON body as the
# pub/sub message, in a single "payload" field.
TRADING_ORDERS_STREAM_PREFIX = "trading:orders"
TRADING_POSITIONS_STREAM_PREFIX = "trading:positions"
TRADING_UI_MAXLEN = 1_000


def orders_stream(session_id: UUID | str) -> str:
    return f"{TRADING_ORDERS_STREAM_PREFIX}:{session_id}"


def positions_stream(session_id: UUID | str) -> str:
    return f"{TRADING_POSITIONS_STREAM_PREFIX}:{session_id}"


def _serialize_uuid(obj: Any) -> str:
    """JSON serializer for UUID objects."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


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


class TradingEventPublisher:
    """Publishes trading events (orders, positions) to Redis pub/sub.

    This publisher enables real-time streaming of trading updates to
    connected clients. Each session has its own channels for orders
    and positions.

    Channels:
        - trading:orders:{session_id} - Order updates
        - trading:positions:{session_id} - Position updates

    Usage:
        publisher = TradingEventPublisher()

        # Publish order update
        await publisher.publish_order_update(
            session_id=session_id,
            order=OrderUpdate(...)
        )

        # Publish position update
        await publisher.publish_position_update(
            session_id=session_id,
            position=PositionUpdate(...)
        )

        # Clean up
        await publisher.close()
    """

    def __init__(self, redis_url: str | None = None, event_bus: EventBus | None = None):
        """Initialize the publisher.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
            event_bus: Streams transport (injected in tests; lazily created
                otherwise) for the durable dual-write paths.
        """
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None
        self._bus: EventBus | None = event_bus

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    def _get_bus(self) -> EventBus:
        """Get or create the Streams bus (same Redis, namespaced keys)."""
        if self._bus is None:
            self._bus = EventBus(self.redis_url)
        return self._bus

    async def publish_order_update(
        self,
        session_id: UUID | str,
        order: OrderUpdate,
    ) -> int:
        """Publish an order update.

        Args:
            session_id: Trading session ID.
            order: Order update data.

        Returns:
            Number of subscribers that received the message.
        """
        message = json.dumps(order.to_dict(), default=_serialize_uuid)
        await self._dual_write_ui_stream(orders_stream(session_id), message)
        redis = await self._get_redis()
        channel = f"trading:orders:{session_id}"
        result: int = await redis.publish(channel, message)
        logger.debug(
            f"Published order update to {channel}",
            extra={"order_id": order.order_id, "status": order.status, "subscribers": result},
        )
        return result

    async def publish_position_update(
        self,
        session_id: UUID | str,
        position: PositionUpdate,
    ) -> int:
        """Publish a position update.

        Args:
            session_id: Trading session ID.
            position: Position update data.

        Returns:
            Number of subscribers that received the message.
        """
        message = json.dumps(position.to_dict(), default=_serialize_uuid)
        await self._dual_write_ui_stream(positions_stream(session_id), message)
        redis = await self._get_redis()
        channel = f"trading:positions:{session_id}"
        result: int = await redis.publish(channel, message)
        logger.debug(
            f"Published position update to {channel}",
            extra={"symbol": position.symbol, "qty": position.qty, "subscribers": result},
        )
        return result

    async def _dual_write_ui_stream(self, stream: str, message: str) -> None:
        """Best-effort XADD of a UI event under STREAMS_TRADING (dual-write).

        Pub/sub stays primary during the soak; a stream failure logs and
        never blocks the pub/sub delivery.
        """
        if not streams_trading_enabled():
            return
        try:
            await self._get_bus().publish(stream, {"payload": message}, maxlen=TRADING_UI_MAXLEN)
        except Exception:
            logger.exception("Failed to XADD UI event to stream %s", stream)

    async def publish_order_submitted(
        self,
        session_id: UUID | str,
        order_id: UUID | str,
        alpaca_order_id: str | None,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
    ) -> int:
        """Convenience method for publishing order submitted event.

        Args:
            session_id: Trading session ID.
            order_id: Internal order ID.
            alpaca_order_id: Alpaca order ID (if available).
            symbol: Stock symbol.
            side: Order side (buy/sell).
            qty: Order quantity.
            order_type: Order type (market/limit/etc).

        Returns:
            Number of subscribers.
        """
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
    ) -> int:
        """Convenience method for publishing order filled event.

        Args:
            session_id: Trading session ID.
            order_id: Internal order ID.
            alpaca_order_id: Alpaca order ID.
            symbol: Stock symbol.
            side: Order side.
            qty: Original order quantity.
            order_type: Order type.
            filled_qty: Filled quantity.
            filled_avg_price: Average fill price.

        Returns:
            Number of subscribers.
        """
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
    ) -> int:
        """Convenience method for publishing order cancelled event.

        Args:
            session_id: Trading session ID.
            order_id: Internal order ID.
            alpaca_order_id: Alpaca order ID.
            symbol: Stock symbol.
            side: Order side.
            qty: Original order quantity.
            order_type: Order type.
            filled_qty: Partially filled quantity.

        Returns:
            Number of subscribers.
        """
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
    ) -> int:
        """Convenience method for publishing position opened event.

        Args:
            session_id: Trading session ID.
            symbol: Stock symbol.
            qty: Position quantity.
            side: Position side (long/short).
            entry_price: Entry price.

        Returns:
            Number of subscribers.
        """
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
    ) -> int:
        """Convenience method for publishing position closed event.

        Args:
            session_id: Trading session ID.
            symbol: Stock symbol.
            side: Position side (long/short).
            exit_price: Exit price.
            realized_pnl: Realized P&L.

        Returns:
            Number of subscribers.
        """
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
    ) -> int:
        """Publish a ledger event payload to ``ledger:fills:{account_id}``.

        The portfolio service's fill consumer ingests these into the
        double-entry ledger (see .docs/planning/CONTRACTS.md §1/§4). Payloads
        are built by ``src.ledger_events`` — fills and order lifecycle
        (reservation) events share this channel.

        Returns:
            Number of subscribers that received the message.
        """
        from src.metrics import record_ledger_publish

        kind = payload.get("event_type", "order_filled")

        # Durable dual-write (STREAMS_LEDGER_FILLS): one global stream consumed
        # by the portfolio's "portfolio-ledger" group. Best-effort while pub/sub
        # remains primary during the soak — a stream failure logs + counts but
        # never blocks the pub/sub delivery.
        if streams_ledger_fills_enabled():
            try:
                await self._get_bus().publish(
                    LEDGER_FILLS_STREAM, payload, maxlen=LEDGER_FILLS_MAXLEN
                )
                record_ledger_publish(kind, "stream_success")
            except Exception:
                record_ledger_publish(kind, "stream_failure")
                logger.exception(
                    "Failed to XADD ledger event to stream",
                    extra={"client_order_id": payload.get("client_order_id")},
                )

        try:
            redis = await self._get_redis()
            channel = f"ledger:fills:{account_id}"
            result: int = await redis.publish(channel, json.dumps(payload))
        except Exception:
            record_ledger_publish(kind, "failure")
            raise
        record_ledger_publish(kind, "success")
        logger.debug(
            f"Published ledger event to {channel}",
            extra={
                "client_order_id": payload.get("client_order_id"),
                "event_type": kind,
                "subscribers": result,
            },
        )
        return result

    async def close(self) -> None:
        """Close the Redis connection (and the Streams bus, if created)."""
        if self._redis:
            await self._redis.close()
            self._redis = None
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
