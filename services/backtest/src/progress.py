"""Progress tracking and publishing for backtests."""

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@dataclass
class ProgressUpdate:
    """Progress update message."""

    backtest_id: str
    progress: float  # 0-100
    message: str
    eta_seconds: int | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "backtest_id": self.backtest_id,
            "progress": self.progress,
            "message": self.message,
            "eta_seconds": self.eta_seconds,
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
        }


class ProgressPublisher:
    """Publishes progress updates to Redis pub/sub."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def publish(
        self,
        backtest_id: str,
        progress: float,
        message: str,
        eta_seconds: int | None = None,
    ) -> None:
        """Publish a progress update."""
        redis = await self._get_redis()
        update = ProgressUpdate(
            backtest_id=backtest_id,
            progress=progress,
            message=message,
            eta_seconds=eta_seconds,
        )
        await redis.publish(
            f"backtest:progress:{backtest_id}",
            json.dumps(update.to_dict()),
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class ProgressSubscriber:
    """Subscribes to progress updates from Redis pub/sub."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def subscribe(self, backtest_id: str) -> AsyncIterator[ProgressUpdate]:
        """Subscribe to progress updates for a backtest.

        Yields ProgressUpdate objects as they come in.
        """
        redis = await self._get_redis()
        self._pubsub = redis.pubsub()
        channel = f"backtest:progress:{backtest_id}"

        await self._pubsub.subscribe(channel)

        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield ProgressUpdate(
                        backtest_id=data["backtest_id"],
                        progress=data["progress"],
                        message=data["message"],
                        eta_seconds=data.get("eta_seconds"),
                        timestamp=data.get("timestamp"),
                    )
                    # Stop if we hit 100%
                    if data["progress"] >= 100:
                        break
        finally:
            await self._pubsub.unsubscribe(channel)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
