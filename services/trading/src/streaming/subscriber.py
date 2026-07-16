"""Trading event subscriber for real-time updates via Redis Streams.

Tail-reads a session's order/position streams: each caller gets its own full
copy of the stream and a reconnecting client replays the gap from its last-seen
cursor (the durability pub/sub never had). The yielded items are the proto
``trading_pb2.OrderUpdate`` / ``trading_pb2.PositionUpdate`` messages the bus
carries directly.
"""

import logging
import os
from collections.abc import AsyncIterator
from uuid import UUID

from llamatrade_events import CURSOR_NEW, OrderEvents, PositionEvents, RedisStreamsTransport
from llamatrade_events import EventBus as EventsBus
from llamatrade_proto.generated import trading_pb2

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class TradingEventSubscriber:
    """Tail-reads trading events (orders, positions) from Redis Streams.

    Usage:
        subscriber = TradingEventSubscriber()

        async for cursor, update in subscriber.tail_orders(session_id):
            print(f"Order {update.order.id}: {update.order.status}")

        await subscriber.close()
    """

    def __init__(
        self,
        redis_url: str | None = None,
        orders_events: OrderEvents | None = None,
        positions_events: PositionEvents | None = None,
    ):
        """Initialize the subscriber.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
            orders_events: Order UI-stream channel (injected in tests; lazily
                created otherwise).
            positions_events: Position UI-stream channel (injected in tests;
                lazily created otherwise).
        """
        self.redis_url = redis_url or REDIS_URL
        self._bus: EventsBus | None = None
        self._orders_events: OrderEvents | None = orders_events
        self._positions_events: PositionEvents | None = positions_events

    def _get_bus(self) -> EventsBus:
        if self._bus is None:
            self._bus = EventsBus(RedisStreamsTransport(self.redis_url))
        return self._bus

    def _get_orders_events(self) -> OrderEvents:
        if self._orders_events is None:
            self._orders_events = OrderEvents(bus=self._get_bus())
        return self._orders_events

    def _get_positions_events(self) -> PositionEvents:
        if self._positions_events is None:
            self._positions_events = PositionEvents(bus=self._get_bus())
        return self._positions_events

    async def tail_orders(
        self,
        session_id: UUID | str,
        *,
        last_seen_id: str = "",
    ) -> AsyncIterator[tuple[str, trading_pb2.OrderUpdate]]:
        """Tail the session's order stream.

        Yields ``(stream_cursor, update)``. Each caller gets its own full copy;
        a reconnecting client passes its last-seen cursor back and the gap is
        replayed. An empty cursor starts live (``CURSOR_NEW``).
        """
        async for cursor, update in self._get_orders_events().tail(
            session_id, from_cursor=last_seen_id or CURSOR_NEW
        ):
            yield cursor, update

    async def tail_positions(
        self,
        session_id: UUID | str,
        *,
        last_seen_id: str = "",
    ) -> AsyncIterator[tuple[str, trading_pb2.PositionUpdate]]:
        """Tail the session's position stream; see :meth:`tail_orders`."""
        async for cursor, update in self._get_positions_events().tail(
            session_id, from_cursor=last_seen_id or CURSOR_NEW
        ):
            yield cursor, update

    async def close(self) -> None:
        """Close the orders/positions channels and the shared bus, if created."""
        if self._orders_events is not None:
            await self._orders_events.close()
            self._orders_events = None
        if self._positions_events is not None:
            await self._positions_events.close()
            self._positions_events = None
        if self._bus is not None:
            await self._bus.close()
            self._bus = None


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
