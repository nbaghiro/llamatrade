"""Async TTL cache backing the risk manager's config reads."""

import asyncio
import time
from dataclasses import dataclass


@dataclass
class CacheEntry[T]:
    """A single cache entry with value and expiration time."""

    value: T
    expires_at: float


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0


class AsyncTTLCache[T]:
    """Async TTL cache with lock-guarded access and size-bounded eviction."""

    def __init__(
        self,
        default_ttl: float = 60.0,
        max_size: int | None = None,
    ):
        """Initialize the cache.

        Args:
            default_ttl: Default time-to-live in seconds.
            max_size: Maximum number of entries (None for unlimited).
        """
        self.default_ttl = default_ttl
        self.max_size = max_size

        self._cache: dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._stats = CacheStats()

    async def get(self, key: str) -> T | None:
        """Get a value from the cache, or None when absent or expired."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if time.time() > entry.expires_at:
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                return None

            self._stats.hits += 1
            return entry.value

    async def set(self, key: str, value: T, ttl: float | None = None) -> None:
        """Set a value in the cache; ``ttl`` overrides the default TTL."""
        entry_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + entry_ttl

        async with self._lock:
            if self.max_size and len(self._cache) >= self.max_size:
                self._evict_oldest_locked()

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def invalidate(self, key: str) -> bool:
        """Remove a specific entry; True when it existed."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.evictions += 1
                return True
            return False

    def clear(self) -> None:
        """Clear all cache entries and reset statistics."""
        self._cache.clear()
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Get current number of entries in cache."""
        return len(self._cache)

    def _evict_oldest_locked(self) -> None:
        """Evict the entry expiring soonest. Must be called with the lock held."""
        if not self._cache:
            return
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].expires_at)
        del self._cache[oldest_key]
        self._stats.evictions += 1
