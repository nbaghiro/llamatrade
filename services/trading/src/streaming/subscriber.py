"""Trading event subscriber for real-time updates via Redis Streams.

Tail-reads a session's order/position streams: each caller gets its own full
copy of the stream and a reconnecting client replays the gap from its last-seen
cursor (the durability pub/sub never had).
"""

import logging
import os
from collections.abc import AsyncIterator, Mapping
from typing import SupportsFloat, cast
from uuid import UUID

from llamatrade_common.events import Event, EventBus

from src.streaming.publisher import (
    OrderUpdate,
    PositionUpdate,
    orders_stream,
    positions_stream,
)

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class TradingEventSubscriber:
    """Tail-reads trading events (orders, positions) from Redis Streams.

    Usage:
        subscriber = TradingEventSubscriber()

        async for cursor, update in subscriber.tail_orders(session_id):
            print(f"Order {update.order_id}: {update.status}")

        await subscriber.close()
    """

    def __init__(self, redis_url: str | None = None, event_bus: EventBus | None = None):
        """Initialize the subscriber.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
            event_bus: Streams transport (injected in tests; lazily created
                otherwise).
        """
        self.redis_url = redis_url or REDIS_URL
        self._bus: EventBus | None = event_bus

    def _get_bus(self) -> EventBus:
        if self._bus is None:
            self._bus = EventBus(self.redis_url)
        return self._bus

    async def tail_orders(
        self,
        session_id: UUID | str,
        *,
        last_seen_id: str = "",
    ) -> AsyncIterator[tuple[str, OrderUpdate]]:
        """Tail the session's order stream.

        Yields ``(stream_cursor, update)``. Each caller gets its own full copy;
        a reconnecting client passes its last-seen cursor back and the gap is
        replayed. An empty cursor starts live ("$").
        """
        async for entry_id, fields in self._get_bus().tail(
            orders_stream(session_id), last_id=last_seen_id or "$"
        ):
            event = Event.from_redis_stream(fields)
            yield entry_id, self._parse_order_update(event.data)

    async def tail_positions(
        self,
        session_id: UUID | str,
        *,
        last_seen_id: str = "",
    ) -> AsyncIterator[tuple[str, PositionUpdate]]:
        """Tail the session's position stream; see :meth:`tail_orders`."""
        async for entry_id, fields in self._get_bus().tail(
            positions_stream(session_id), last_id=last_seen_id or "$"
        ):
            event = Event.from_redis_stream(fields)
            yield entry_id, self._parse_position_update(event.data)

    def _parse_order_update(self, data: Mapping[str, object]) -> OrderUpdate:
        """Parse an order update from the Event.data body."""
        return OrderUpdate(
            session_id=str(data["session_id"]),
            order_id=str(data["order_id"]),
            alpaca_order_id=str(data["alpaca_order_id"]) if data.get("alpaca_order_id") else None,
            symbol=str(data["symbol"]),
            side=str(data["side"]),
            qty=float(cast(SupportsFloat, data.get("qty", 0))),
            order_type=str(data["order_type"]),
            status=str(data["status"]),
            filled_qty=float(cast(SupportsFloat, data.get("filled_qty", 0))),
            filled_avg_price=(
                float(cast(SupportsFloat, data["filled_avg_price"]))
                if data.get("filled_avg_price") is not None
                else None
            ),
            submitted_at=str(data["submitted_at"]) if data.get("submitted_at") else None,
            filled_at=str(data["filled_at"]) if data.get("filled_at") else None,
            update_type=str(data.get("update_type", "status_change")),
            timestamp=str(data.get("timestamp", "")),
        )

    def _parse_position_update(self, data: Mapping[str, object]) -> PositionUpdate:
        """Parse a position update from the Event.data body."""
        return PositionUpdate(
            session_id=str(data["session_id"]),
            symbol=str(data["symbol"]),
            qty=float(cast(SupportsFloat, data.get("qty", 0))),
            side=str(data["side"]),
            cost_basis=float(cast(SupportsFloat, data.get("cost_basis", 0))),
            market_value=float(cast(SupportsFloat, data.get("market_value", 0))),
            unrealized_pnl=float(cast(SupportsFloat, data.get("unrealized_pnl", 0))),
            unrealized_pnl_percent=float(
                cast(SupportsFloat, data.get("unrealized_pnl_percent", 0))
            ),
            current_price=float(cast(SupportsFloat, data.get("current_price", 0))),
            update_type=str(data.get("update_type", "change")),
            timestamp=str(data.get("timestamp", "")),
        )

    async def close(self) -> None:
        """Close the Streams bus, if created."""
        if self._bus is not None:
            await self._bus.close()
            self._bus = None


# Factory function for easy instantiation
def get_trading_event_subscriber(redis_url: str | None = None) -> TradingEventSubscriber:
    """Create a trading event subscriber.

    Unlike the publisher, subscribers are not singletons since each
    subscription needs its own connection.

    Args:
        redis_url: Optional Redis URL.

    Returns:
        New TradingEventSubscriber instance.
    """
    return TradingEventSubscriber(redis_url)
