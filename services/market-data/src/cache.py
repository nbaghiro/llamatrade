"""Redis cache utilities for market data."""

import json
import logging
import os
from collections.abc import Awaitable, Sequence
from datetime import date, datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.models import Timeframe

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# TTL Constants (in seconds)
TTL_HISTORICAL_BARS = 24 * 60 * 60  # 24 hours for immutable historical data
TTL_TODAY_BARS = 5 * 60  # 5 minutes for today's data (still updating)
TTL_LATEST_BAR = 2 * 60  # 2 minutes
TTL_LATEST_QUOTE = 10  # 10 seconds (near real-time)
TTL_SNAPSHOT = 15  # 15 seconds


class MarketDataCache:
    """Redis cache for market data."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    @property
    def redis(self) -> Redis:
        """Get the Redis client."""
        return self._redis

    # === Key Generation ===

    @staticmethod
    def bars_key(
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None,
        limit: int,
    ) -> str:
        """Generate cache key for historical bars."""
        start_str = start.isoformat()
        end_str = end.isoformat() if end else "none"
        return f"market:bars:{symbol}:{timeframe.value}:{start_str}:{end_str}:{limit}"

    @staticmethod
    def latest_bar_key(symbol: str) -> str:
        """Generate cache key for latest bar."""
        return f"market:bar:latest:{symbol}"

    @staticmethod
    def latest_quote_key(symbol: str) -> str:
        """Generate cache key for latest quote."""
        return f"market:quote:{symbol}"

    @staticmethod
    def snapshot_key(symbol: str) -> str:
        """Generate cache key for snapshot."""
        return f"market:snapshot:{symbol}"

    # === TTL Calculation ===

    @staticmethod
    def calculate_bars_ttl(start: datetime, end: datetime | None) -> int:
        """Calculate TTL for bars based on whether data is from today."""
        today = date.today()
        # If end date is today or None (meaning current), use short TTL
        if end is None or end.date() >= today:
            return TTL_TODAY_BARS
        # Historical data (before today) is immutable, use long TTL
        return TTL_HISTORICAL_BARS

    # === Serialization ===

    @staticmethod
    def serialize_model(model: BaseModel) -> str:
        """Serialize a Pydantic model to JSON string."""
        return model.model_dump_json()

    @staticmethod
    def serialize_model_list(models: Sequence[BaseModel]) -> str:
        """Serialize a list of Pydantic models to JSON string."""
        return json.dumps([json.loads(m.model_dump_json()) for m in models])

    @staticmethod
    def serialize_model_dict(models: dict[str, BaseModel]) -> str:
        """Serialize a dict of Pydantic models to JSON string."""
        return json.dumps({k: json.loads(v.model_dump_json()) for k, v in models.items()})

    @staticmethod
    def serialize_bars_dict(bars: dict[str, list[BaseModel]]) -> str:
        """Serialize a dict of symbol -> list of bars to JSON string."""
        return json.dumps(
            {
                symbol: [json.loads(bar.model_dump_json()) for bar in bar_list]
                for symbol, bar_list in bars.items()
            }
        )

    @staticmethod
    def deserialize_model(data: str, model_class: type[T]) -> T:
        """Deserialize a JSON string to a Pydantic model."""
        return model_class.model_validate_json(data)

    @staticmethod
    def deserialize_model_list(data: str, model_class: type[T]) -> list[T]:
        """Deserialize a JSON string to a list of Pydantic models."""
        items = json.loads(data)
        return [model_class.model_validate(item) for item in items]

    @staticmethod
    def deserialize_model_dict(data: str, model_class: type[T]) -> dict[str, T]:
        """Deserialize a JSON string to a dict of Pydantic models."""
        items = json.loads(data)
        return {k: model_class.model_validate(v) for k, v in items.items()}

    @staticmethod
    def deserialize_bars_dict(data: str, bar_class: type[T]) -> dict[str, list[T]]:
        """Deserialize a JSON string to a dict of symbol -> list of bars."""
        items = json.loads(data)
        return {
            symbol: [bar_class.model_validate(bar) for bar in bar_list]
            for symbol, bar_list in items.items()
        }

    # === Cache Operations ===

    async def get(self, key: str) -> str | None:
        """Get a value from cache. Returns None on cache miss or error."""
        try:
            value = await self._redis.get(key)
            if value:
                logger.debug(f"Cache hit: {key}")
                return value.decode("utf-8") if isinstance(value, bytes) else value
            logger.debug(f"Cache miss: {key}")
            return None
        except RedisError as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int) -> bool:
        """Set a value in cache with TTL. Returns False on error."""
        try:
            await self._redis.setex(key, timedelta(seconds=ttl), value)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True
        except RedisError as e:
            logger.warning(f"Cache set failed for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns False on error."""
        try:
            await self._redis.delete(key)
            logger.debug(f"Cache delete: {key}")
            return True
        except RedisError as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            result = self._redis.ping()
            if isinstance(result, Awaitable):
                await result
            return True
        except RedisError:
            return False


# === Lifecycle Functions ===

_cache: MarketDataCache | None = None


async def init_cache() -> MarketDataCache | None:
    """Initialize the Redis cache. Returns None if Redis is unavailable."""
    global _cache
    redis_url = os.getenv("REDIS_URL", "redis://localhost:47379")

    try:
        redis_client = Redis.from_url(redis_url, decode_responses=False)
        # Test connection
        result = redis_client.ping()
        if isinstance(result, Awaitable):
            await result
        _cache = MarketDataCache(redis_client)
        logger.info(f"Redis cache connected: {redis_url}")
        return _cache
    except RedisError as e:
        logger.warning(f"Redis connection failed, caching disabled: {e}")
        return None


async def close_cache() -> None:
    """Close the Redis connection."""
    global _cache
    if _cache is not None:
        try:
            await _cache.redis.aclose()
            logger.info("Redis cache connection closed")
        except RedisError as e:
            logger.warning(f"Error closing Redis connection: {e}")
        finally:
            _cache = None


def get_cache() -> MarketDataCache | None:
    """Get the cache instance (may be None if Redis is unavailable)."""
    return _cache
