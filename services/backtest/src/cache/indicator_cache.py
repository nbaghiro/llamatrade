"""Redis cache for computed indicators.

Caches indicator values to speed up repeated backtests with the same indicators.
Since indicators on historical data don't change, we can cache them effectively.
"""

import hashlib
import logging
import os
import zlib
from collections.abc import Callable
from datetime import date
from typing import TypedDict, cast

import numpy as np
import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = 24 * 60 * 60  # 24 hours


class CacheStats(TypedDict):
    """Cache statistics."""

    hits: int
    misses: int
    hit_rate: float


class IndicatorCache:
    """Redis cache for computed indicator values.

    Key format: bt:ind:{symbol}:{indicator}:{params_hash}:{start}:{end}

    Values are stored as compressed numpy arrays for efficiency.
    """

    KEY_PREFIX = "bt:ind"

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int = DEFAULT_TTL,
    ):
        """Initialize the indicator cache.

        Args:
            redis_url: Redis connection URL
            ttl: Cache TTL in seconds (default 24 hours)
        """
        self.redis_url = redis_url or REDIS_URL
        self.ttl = ttl
        self._redis: redis.Redis | None = None
        self._hits = 0
        self._misses = 0

    def _get_redis(self) -> redis.Redis:
        """Get Redis client (lazy initialization)."""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        return self._redis

    def _build_key(
        self,
        symbol: str,
        indicator: str,
        params: tuple,
        start_date: date,
        end_date: date,
    ) -> str:
        """Build cache key for an indicator.

        Args:
            symbol: Symbol name
            indicator: Indicator type (e.g., "sma", "rsi")
            params: Indicator parameters tuple
            start_date: Data start date
            end_date: Data end date

        Returns:
            Cache key string
        """
        # Hash params to keep key length reasonable
        params_str = str(params)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]

        return (
            f"{self.KEY_PREFIX}:{symbol}:{indicator}:{params_hash}:"
            f"{start_date.isoformat()}:{end_date.isoformat()}"
        )

    def _serialize(self, values: np.ndarray) -> bytes:
        """Serialize numpy array to compressed bytes.

        Args:
            values: Numpy array to serialize

        Returns:
            Compressed bytes
        """
        # Convert to bytes and compress
        array_bytes = values.tobytes()
        compressed = zlib.compress(array_bytes, level=6)
        # Store dtype and shape metadata
        dtype_str = str(values.dtype)
        shape_str = ",".join(map(str, values.shape))
        header = f"{dtype_str}|{shape_str}|".encode()
        return header + compressed

    def _deserialize(self, data: bytes) -> np.ndarray:
        """Deserialize compressed bytes to numpy array.

        Args:
            data: Compressed bytes with header

        Returns:
            Numpy array
        """
        # Parse header
        header_end = data.index(b"|", data.index(b"|") + 1) + 1
        header = data[:header_end].decode()
        dtype_str, shape_str, _ = header.split("|")

        # Decompress
        compressed = data[header_end:]
        array_bytes = zlib.decompress(compressed)

        # Reconstruct array
        dtype = np.dtype(dtype_str)
        shape = tuple(map(int, shape_str.split(",")))
        return np.frombuffer(array_bytes, dtype=dtype).reshape(shape)

    def get(
        self,
        symbol: str,
        indicator: str,
        params: tuple,
        start_date: date,
        end_date: date,
    ) -> np.ndarray | None:
        """Get cached indicator values.

        Args:
            symbol: Symbol name
            indicator: Indicator type
            params: Indicator parameters
            start_date: Data start date
            end_date: Data end date

        Returns:
            Cached numpy array or None if not found
        """
        key = self._build_key(symbol, indicator, params, start_date, end_date)

        try:
            r = self._get_redis()
            data = r.get(key)

            if data is not None:
                self._hits += 1
                logger.debug(f"Cache hit: {key}")
                # Redis sync client returns bytes directly; cast to satisfy type checker
                return self._deserialize(cast(bytes, data))
            else:
                self._misses += 1
                logger.debug(f"Cache miss: {key}")
                return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            self._misses += 1
            return None

    def set(
        self,
        symbol: str,
        indicator: str,
        params: tuple,
        start_date: date,
        end_date: date,
        values: np.ndarray,
        ttl: int | None = None,
    ) -> bool:
        """Set cached indicator values.

        Args:
            symbol: Symbol name
            indicator: Indicator type
            params: Indicator parameters
            start_date: Data start date
            end_date: Data end date
            values: Computed indicator values
            ttl: Optional TTL override

        Returns:
            True if successful
        """
        key = self._build_key(symbol, indicator, params, start_date, end_date)

        try:
            r = self._get_redis()
            data = self._serialize(values)
            r.setex(key, ttl or self.ttl, data)
            logger.debug(f"Cache set: {key} ({len(data)} bytes)")
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    def get_or_compute(
        self,
        symbol: str,
        indicator: str,
        params: tuple[int | float, ...],
        start_date: date,
        end_date: date,
        compute_fn: Callable[[], np.ndarray],
    ) -> np.ndarray:
        """Get from cache or compute and cache.

        Args:
            symbol: Symbol name
            indicator: Indicator type
            params: Indicator parameters
            start_date: Data start date
            end_date: Data end date
            compute_fn: Function to compute values if not cached

        Returns:
            Indicator values (from cache or computed)
        """
        # Try cache first
        cached = self.get(symbol, indicator, params, start_date, end_date)
        if cached is not None:
            return cached

        # Compute
        values = compute_fn()

        # Cache result
        self.set(symbol, indicator, params, start_date, end_date, values)

        return values

    def invalidate(
        self,
        symbol: str | None = None,
        indicator: str | None = None,
    ) -> int:
        """Invalidate cached entries.

        Args:
            symbol: Optional symbol to invalidate
            indicator: Optional indicator type to invalidate

        Returns:
            Number of keys deleted
        """
        try:
            r = self._get_redis()

            if symbol and indicator:
                pattern = f"{self.KEY_PREFIX}:{symbol}:{indicator}:*"
            elif symbol:
                pattern = f"{self.KEY_PREFIX}:{symbol}:*"
            elif indicator:
                pattern = f"{self.KEY_PREFIX}:*:{indicator}:*"
            else:
                pattern = f"{self.KEY_PREFIX}:*"

            keys = list(r.scan_iter(match=pattern))
            if keys:
                deleted = r.delete(*keys)
                # Redis sync client returns int directly; cast to satisfy type checker
                return cast(int, deleted) if deleted else 0
            return 0

        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")
            return 0

    def get_stats(self) -> CacheStats:
        """Get cache hit/miss statistics.

        Returns:
            CacheStats with hits, misses, and hit rate
        """
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }

    def reset_stats(self) -> None:
        """Reset hit/miss statistics."""
        self._hits = 0
        self._misses = 0

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            self._redis.close()
            self._redis = None


# Global cache instance (singleton pattern)
_cache_instance: IndicatorCache | None = None


def get_indicator_cache() -> IndicatorCache:
    """Get the global indicator cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = IndicatorCache()
    return _cache_instance
