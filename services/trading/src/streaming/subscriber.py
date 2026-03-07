"""Trading event subscriber for real-time updates via Redis pub/sub.

This module provides the subscriber side of the streaming infrastructure,
allowing clients to receive real-time order and position updates.
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import SupportsFloat, cast
from uuid import UUID

import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from src.streaming.publisher import OrderUpdate, PositionUpdate

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class TradingEventSubscriber:
    """Subscribes to trading events (orders, positions) from Redis pub/sub.

    This subscriber enables clients to receive real-time streaming updates
    for orders and positions from a trading session.

    Usage:
        subscriber = TradingEventSubscriber()

        # Subscribe to order updates
        async for update in subscriber.subscribe_orders(session_id):
            print(f"Order {update.order_id}: {update.status}")

        # Subscribe to position updates
        async for update in subscriber.subscribe_positions(session_id):
            print(f"Position {update.symbol}: {update.qty}")

        # Clean up
        await subscriber.close()
    """

    def __init__(self, redis_url: str | None = None):
        """Initialize the subscriber.

        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
        """
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None  # type: ignore[type-arg]
        self._pubsub: PubSub | None = None

    async def _get_redis(self) -> aioredis.Redis:  # type: ignore[type-arg]
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)  # type: ignore[no-untyped-call]
        return self._redis

    async def subscribe_orders(
        self,
        session_id: UUID | str,
        timeout: float | None = None,
    ) -> AsyncIterator[OrderUpdate]:
        """Subscribe to order updates for a session.

        Yields OrderUpdate objects as they are published.

        Args:
            session_id: Trading session ID.
            timeout: Optional timeout in seconds between messages.
                If no message received within timeout, stops iteration.

        Yields:
            OrderUpdate objects.
        """
        redis = await self._get_redis()
        pubsub: PubSub = redis.pubsub()  # type: ignore[no-untyped-call]
        channel = f"trading:orders:{session_id}"

        await pubsub.subscribe(channel)  # type: ignore[no-untyped-call]
        logger.debug(f"Subscribed to {channel}")

        try:
            while True:
                message = await pubsub.get_message(  # type: ignore[no-untyped-call]
                    ignore_subscribe_messages=True,
                    timeout=timeout,
                )

                if message is None:
                    if timeout is not None:
                        # Timeout reached with no message
                        break
                    continue

                msg = cast(dict[str, object], message)
                if msg["type"] == "message":
                    raw_data = cast(str | bytes, msg["data"])
                    data = cast(dict[str, object], json.loads(raw_data))
                    yield self._parse_order_update(data)
        finally:
            await pubsub.unsubscribe(channel)  # type: ignore[no-untyped-call]
            await pubsub.close()
            logger.debug(f"Unsubscribed from {channel}")

    async def subscribe_positions(
        self,
        session_id: UUID | str,
        timeout: float | None = None,
    ) -> AsyncIterator[PositionUpdate]:
        """Subscribe to position updates for a session.

        Yields PositionUpdate objects as they are published.

        Args:
            session_id: Trading session ID.
            timeout: Optional timeout in seconds between messages.
                If no message received within timeout, stops iteration.

        Yields:
            PositionUpdate objects.
        """
        redis = await self._get_redis()
        pubsub: PubSub = redis.pubsub()  # type: ignore[no-untyped-call]
        channel = f"trading:positions:{session_id}"

        await pubsub.subscribe(channel)  # type: ignore[no-untyped-call]
        logger.debug(f"Subscribed to {channel}")

        try:
            while True:
                message = await pubsub.get_message(  # type: ignore[no-untyped-call]
                    ignore_subscribe_messages=True,
                    timeout=timeout,
                )

                if message is None:
                    if timeout is not None:
                        # Timeout reached with no message
                        break
                    continue

                msg = cast(dict[str, object], message)
                if msg["type"] == "message":
                    raw_data = cast(str | bytes, msg["data"])
                    data = cast(dict[str, object], json.loads(raw_data))
                    yield self._parse_position_update(data)
        finally:
            await pubsub.unsubscribe(channel)  # type: ignore[no-untyped-call]
            await pubsub.close()
            logger.debug(f"Unsubscribed from {channel}")

    async def subscribe_all(
        self,
        session_id: UUID | str,
        timeout: float | None = None,
    ) -> AsyncIterator[OrderUpdate | PositionUpdate]:
        """Subscribe to all trading events (orders and positions) for a session.

        Yields OrderUpdate or PositionUpdate objects as they are published.

        Args:
            session_id: Trading session ID.
            timeout: Optional timeout in seconds between messages.

        Yields:
            OrderUpdate or PositionUpdate objects.
        """
        redis = await self._get_redis()
        pubsub: PubSub = redis.pubsub()  # type: ignore[no-untyped-call]
        order_channel = f"trading:orders:{session_id}"
        position_channel = f"trading:positions:{session_id}"

        await pubsub.subscribe(order_channel, position_channel)  # type: ignore[no-untyped-call]
        logger.debug(f"Subscribed to {order_channel} and {position_channel}")

        try:
            while True:
                message = await pubsub.get_message(  # type: ignore[no-untyped-call]
                    ignore_subscribe_messages=True,
                    timeout=timeout,
                )

                if message is None:
                    if timeout is not None:
                        break
                    continue

                msg = cast(dict[str, object], message)
                if msg["type"] == "message":
                    channel = cast(bytes | str, msg["channel"])
                    channel_str = channel.decode() if isinstance(channel, bytes) else channel
                    raw_data = cast(str | bytes, msg["data"])
                    data = cast(dict[str, object], json.loads(raw_data))

                    if "orders" in channel_str:
                        yield self._parse_order_update(data)
                    else:
                        yield self._parse_position_update(data)
        finally:
            await pubsub.unsubscribe(order_channel, position_channel)  # type: ignore[no-untyped-call]
            await pubsub.close()
            logger.debug("Unsubscribed from all channels")

    def _parse_order_update(self, data: dict[str, object]) -> OrderUpdate:
        """Parse order update from JSON data."""
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

    def _parse_position_update(self, data: dict[str, object]) -> PositionUpdate:
        """Parse position update from JSON data."""
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
        """Close the Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None


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
