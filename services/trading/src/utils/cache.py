"""Async TTL cache utilities.

This module provides async-compatible caching decorators with time-to-live
(TTL) support for caching expensive computations.
"""

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar, cast

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class CacheEntry:
    """A single cache entry with value and expiration time."""

    value: Any
    expires_at: float


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class AsyncTTLCache:
    """Thread-safe async TTL cache.

    This cache is designed for async functions and provides:
    - Configurable TTL per entry
    - Thread-safe concurrent access via asyncio locks
    - Automatic cleanup of expired entries
    - Manual invalidation support
    - Statistics tracking

    Usage:
        cache = AsyncTTLCache(default_ttl=60)

        @cache.cached()
        async def expensive_operation(key: str) -> dict:
            return await fetch_from_db(key)

        # Manual invalidation
        cache.invalidate("expensive_operation:key123")

        # Clear all entries
        cache.clear()
    """

    def __init__(
        self,
        default_ttl: float = 60.0,
        max_size: int | None = None,
        cleanup_interval: float = 60.0,
    ):
        """Initialize the cache.

        Args:
            default_ttl: Default time-to-live in seconds.
            max_size: Maximum number of entries (None for unlimited).
            cleanup_interval: Interval for automatic cleanup of expired entries.
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval

        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._stats = CacheStats()
        self._cleanup_task: asyncio.Task[None] | None = None

    def cached(
        self,
        ttl: float | None = None,
        key_builder: Callable[..., str] | None = None,
    ) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
        """Decorator for caching async function results.

        Args:
            ttl: Time-to-live in seconds. Uses default if not specified.
            key_builder: Custom function to build cache key from arguments.
                Signature: key_builder(*args, **kwargs) -> str

        Returns:
            Decorated function.

        Usage:
            @cache.cached(ttl=120)
            async def get_user(user_id: str) -> User:
                return await db.get_user(user_id)

            @cache.cached(key_builder=lambda tenant_id, session_id: f"{tenant_id}:{session_id}")
            async def get_config(tenant_id: UUID, session_id: UUID) -> Config:
                return await db.get_config(tenant_id, session_id)
        """
        entry_ttl = ttl if ttl is not None else self.default_ttl

        def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                # Build cache key
                if key_builder:
                    key = f"{func.__name__}:{key_builder(*args, **kwargs)}"
                else:
                    key = self.build_key(func.__name__, args, kwargs)

                # Try to get from cache
                cached_value = await self.get(key)
                if cached_value is not None:
                    return cast(T, cached_value)

                # Cache miss - compute value
                result = await func(*args, **kwargs)

                # Store in cache
                await self.set(key, result, entry_ttl)

                return result

            # Attach cache reference for direct access
            setattr(wrapper, "cache", self)

            def _default_key_builder(*a: Any, **kw: Any) -> str:
                return self.build_key(func.__name__, a, kw)

            setattr(wrapper, "cache_key_builder", key_builder or _default_key_builder)

            return wrapper

        return decorator

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if time.time() > entry.expires_at:
                # Entry expired
                del self._cache[key]
                self._stats.misses += 1
                self._stats.evictions += 1
                return None

            self._stats.hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time-to-live in seconds. Uses default if not specified.
        """
        entry_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + entry_ttl

        async with self._lock:
            # Evict oldest entries if at max size
            if self.max_size and len(self._cache) >= self.max_size:
                await self._evict_oldest_locked()

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def invalidate(self, key: str) -> bool:
        """Invalidate a specific cache entry.

        Args:
            key: Cache key to invalidate.

        Returns:
            True if the key was found and removed, False otherwise.
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.evictions += 1
                return True
            return False

    async def invalidate_pattern(self, prefix: str) -> int:
        """Invalidate all entries matching a key prefix.

        Args:
            prefix: Key prefix to match.

        Returns:
            Number of entries invalidated.
        """
        async with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
            self._stats.evictions += len(keys_to_remove)
            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries synchronously."""
        self._cache.clear()
        self._stats = CacheStats()

    async def clear_async(self) -> None:
        """Clear all cache entries asynchronously."""
        async with self._lock:
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

    async def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self._cache.items() if v.expires_at < now]
            for key in expired_keys:
                del self._cache[key]
            self._stats.evictions += len(expired_keys)
            return len(expired_keys)

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for expired entries."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        """Background loop to clean up expired entries."""
        while True:
            await asyncio.sleep(self.cleanup_interval)
            try:
                count = await self.cleanup_expired()
                if count > 0:
                    logger.debug(f"Cache cleanup removed {count} expired entries")
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")

    async def _evict_oldest_locked(self) -> None:
        """Evict the oldest entry. Must be called with lock held."""
        if not self._cache:
            return

        # Find the entry with the earliest expiration time
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].expires_at)
        del self._cache[oldest_key]
        self._stats.evictions += 1

    def build_key(self, func_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        """Build a cache key from function name and arguments.

        Args:
            func_name: Name of the function.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Cache key string.
        """
        # Convert args and kwargs to a hashable representation
        key_parts = [func_name]

        for arg in args:
            key_parts.append(self._serialize_arg(arg))

        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={self._serialize_arg(v)}")

        key_string = ":".join(key_parts)

        # If key is too long, hash it
        if len(key_string) > 200:
            hash_digest = hashlib.sha256(key_string.encode()).hexdigest()[:32]
            return f"{func_name}:{hash_digest}"

        return key_string

    def _serialize_arg(self, arg: Any) -> str:
        """Serialize an argument to a string for cache key generation.

        Args:
            arg: Argument to serialize.

        Returns:
            String representation.
        """
        if arg is None:
            return "None"
        if isinstance(arg, (str, int, float, bool)):
            return str(arg)
        if hasattr(arg, "__str__"):
            # UUIDs, enums, etc.
            return str(arg)
        try:
            # Try JSON serialization for complex types
            return json.dumps(arg, sort_keys=True, default=str)
        except TypeError, ValueError:
            # Fallback to repr
            return repr(arg)


def async_ttl_cache(
    ttl_seconds: float = 60.0,
    key_builder: Callable[..., str] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for caching async function results with TTL.

    This is a simpler alternative to AsyncTTLCache for single-function use.

    Args:
        ttl_seconds: Time-to-live in seconds.
        key_builder: Custom function to build cache key from arguments.

    Returns:
        Decorated function.

    Usage:
        @async_ttl_cache(ttl_seconds=60)
        async def get_config(tenant_id: UUID, session_id: UUID) -> Config:
            return await db.get_config(tenant_id, session_id)

        # Clear cache for this function
        get_config.cache_clear()

        # Invalidate specific key
        get_config.cache_invalidate(tenant_id=uuid, session_id=session_uuid)
    """
    # Create a per-function cache
    func_cache = AsyncTTLCache(default_ttl=ttl_seconds)

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Build cache key
            if key_builder:
                key = f"{func.__name__}:{key_builder(*args, **kwargs)}"
            else:
                key = func_cache.build_key(func.__name__, args, kwargs)

            # Try to get from cache
            cached_value = await func_cache.get(key)
            if cached_value is not None:
                return cast(T, cached_value)

            # Cache miss - compute value
            result = await func(*args, **kwargs)

            # Store in cache
            await func_cache.set(key, result, ttl_seconds)

            return result

        def cache_clear() -> None:
            """Clear all cached entries for this function."""
            func_cache.clear()

        async def cache_invalidate(*args: Any, **kwargs: Any) -> bool:
            """Invalidate a specific cache entry."""
            if key_builder:
                key = f"{func.__name__}:{key_builder(*args, **kwargs)}"
            else:
                key = func_cache.build_key(func.__name__, args, kwargs)
            return await func_cache.invalidate(key)

        setattr(wrapper, "cache_clear", cache_clear)
        setattr(wrapper, "cache_invalidate", cache_invalidate)
        setattr(wrapper, "cache", func_cache)

        return wrapper

    return decorator


# Global shared cache instance
_shared_cache: AsyncTTLCache | None = None


def get_shared_cache(ttl: float = 60.0) -> AsyncTTLCache:
    """Get the shared cache instance.

    Args:
        ttl: Default TTL for the cache (only used on first call).

    Returns:
        Shared AsyncTTLCache instance.
    """
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = AsyncTTLCache(default_ttl=ttl)
    return _shared_cache
