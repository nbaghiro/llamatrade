"""Tests for async TTL cache utilities."""

import asyncio
from uuid import uuid4

import pytest

from src.utils.cache import (
    AsyncTTLCache,
    async_ttl_cache,
    get_shared_cache,
)


@pytest.fixture
def cache() -> AsyncTTLCache:
    """Create a fresh cache instance."""
    return AsyncTTLCache(default_ttl=1.0)


class TestAsyncTTLCache:
    """Tests for AsyncTTLCache class."""

    async def test_set_and_get(self, cache: AsyncTTLCache) -> None:
        """Test basic set and get operations."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_missing_key(self, cache: AsyncTTLCache) -> None:
        """Test getting a non-existent key."""
        result = await cache.get("nonexistent")
        assert result is None

    async def test_ttl_expiration(self) -> None:
        """Test that entries expire after TTL."""
        cache = AsyncTTLCache(default_ttl=0.1)
        await cache.set("key1", "value1")

        # Should be available immediately
        assert await cache.get("key1") == "value1"

        # Wait for expiration
        await asyncio.sleep(0.15)

        # Should be expired
        assert await cache.get("key1") is None

    async def test_custom_ttl_per_entry(self, cache: AsyncTTLCache) -> None:
        """Test custom TTL for individual entries."""
        await cache.set("short", "value", ttl=0.1)
        await cache.set("long", "value", ttl=10.0)

        await asyncio.sleep(0.15)

        # Short TTL should expire
        assert await cache.get("short") is None
        # Long TTL should still exist
        assert await cache.get("long") == "value"

    async def test_invalidate(self, cache: AsyncTTLCache) -> None:
        """Test manual invalidation."""
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

        result = await cache.invalidate("key1")
        assert result is True

        assert await cache.get("key1") is None

    async def test_invalidate_nonexistent(self, cache: AsyncTTLCache) -> None:
        """Test invalidating a non-existent key."""
        result = await cache.invalidate("nonexistent")
        assert result is False

    async def test_invalidate_pattern(self, cache: AsyncTTLCache) -> None:
        """Test pattern-based invalidation."""
        await cache.set("user:1:profile", "data1")
        await cache.set("user:1:settings", "data2")
        await cache.set("user:2:profile", "data3")
        await cache.set("other:key", "data4")

        count = await cache.invalidate_pattern("user:1:")
        assert count == 2

        # user:1 entries should be gone
        assert await cache.get("user:1:profile") is None
        assert await cache.get("user:1:settings") is None

        # Other entries should remain
        assert await cache.get("user:2:profile") == "data3"
        assert await cache.get("other:key") == "data4"

    async def test_clear(self, cache: AsyncTTLCache) -> None:
        """Test clearing all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert cache.size == 0

    async def test_clear_async(self, cache: AsyncTTLCache) -> None:
        """Test async clear."""
        await cache.set("key1", "value1")
        await cache.clear_async()
        assert cache.size == 0

    async def test_stats_tracking(self, cache: AsyncTTLCache) -> None:
        """Test cache statistics."""
        await cache.set("key1", "value1")

        # First access - hit
        await cache.get("key1")
        assert cache.stats.hits == 1
        assert cache.stats.misses == 0

        # Miss
        await cache.get("nonexistent")
        assert cache.stats.hits == 1
        assert cache.stats.misses == 1

        assert cache.stats.hit_rate == 0.5

    async def test_max_size_eviction(self) -> None:
        """Test that oldest entries are evicted when at max size."""
        cache = AsyncTTLCache(default_ttl=60.0, max_size=3)

        await cache.set("key1", "value1")
        await asyncio.sleep(0.01)
        await cache.set("key2", "value2")
        await asyncio.sleep(0.01)
        await cache.set("key3", "value3")

        assert cache.size == 3

        # Adding fourth entry should evict oldest
        await cache.set("key4", "value4")

        assert cache.size == 3
        assert await cache.get("key1") is None  # Evicted
        assert await cache.get("key4") == "value4"

    async def test_cleanup_expired(self, cache: AsyncTTLCache) -> None:
        """Test manual cleanup of expired entries."""
        await cache.set("short", "value1", ttl=0.1)
        await cache.set("long", "value2", ttl=10.0)

        await asyncio.sleep(0.15)

        count = await cache.cleanup_expired()
        assert count == 1
        assert cache.size == 1


class TestCachedDecorator:
    """Tests for the cached() decorator."""

    async def test_basic_caching(self, cache: AsyncTTLCache) -> None:
        """Test that decorated function results are cached."""
        call_count = 0

        @cache.cached()
        async def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should execute function
        result1 = await expensive_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should return cached result
        result2 = await expensive_func(5)
        assert result2 == 10
        assert call_count == 1  # No additional call

        # Different argument - should execute function
        result3 = await expensive_func(10)
        assert result3 == 20
        assert call_count == 2

    async def test_custom_key_builder(self, cache: AsyncTTLCache) -> None:
        """Test custom key builder function."""
        call_count = 0

        @cache.cached(key_builder=lambda tenant_id, session_id: f"{tenant_id}:{session_id}")
        async def get_config(tenant_id: str, session_id: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"tenant": tenant_id, "session": session_id}

        tenant1 = str(uuid4())
        session1 = str(uuid4())

        result1 = await get_config(tenant1, session1)
        assert result1["tenant"] == tenant1
        assert call_count == 1

        # Same arguments - cached
        result2 = await get_config(tenant1, session1)
        assert result2 == result1
        assert call_count == 1

    async def test_cached_with_kwargs(self, cache: AsyncTTLCache) -> None:
        """Test caching with keyword arguments."""
        call_count = 0

        @cache.cached()
        async def func_with_kwargs(a: int, b: int = 10) -> int:
            nonlocal call_count
            call_count += 1
            return a + b

        result1 = await func_with_kwargs(5, b=20)
        assert result1 == 25
        assert call_count == 1

        # Same args - cached
        result2 = await func_with_kwargs(5, b=20)
        assert result2 == 25
        assert call_count == 1

        # Different kwargs - not cached
        result3 = await func_with_kwargs(5, b=30)
        assert result3 == 35
        assert call_count == 2


class TestAsyncTTLCacheDecorator:
    """Tests for the standalone async_ttl_cache decorator."""

    async def test_basic_usage(self) -> None:
        """Test basic decorator usage."""
        call_count = 0

        @async_ttl_cache(ttl_seconds=1.0)
        async def cached_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = await cached_func(5)
        assert result1 == 10
        assert call_count == 1

        # Cached call
        result2 = await cached_func(5)
        assert result2 == 10
        assert call_count == 1

    async def test_cache_clear(self) -> None:
        """Test cache_clear method."""
        call_count = 0

        @async_ttl_cache(ttl_seconds=60.0)
        async def cached_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        await cached_func(5)
        assert call_count == 1

        # Clear cache
        cached_func.cache_clear()  # type: ignore

        # Should call function again
        await cached_func(5)
        assert call_count == 2

    async def test_cache_invalidate(self) -> None:
        """Test cache_invalidate method."""
        call_count = 0

        @async_ttl_cache(ttl_seconds=60.0)
        async def cached_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        await cached_func(5)
        assert call_count == 1

        # Invalidate specific entry
        result = await cached_func.cache_invalidate(5)  # type: ignore
        assert result is True

        # Should call function again
        await cached_func(5)
        assert call_count == 2

    async def test_ttl_expiration_with_decorator(self) -> None:
        """Test TTL expiration with decorator."""
        call_count = 0

        @async_ttl_cache(ttl_seconds=0.1)
        async def cached_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        await cached_func(5)
        assert call_count == 1

        # Wait for expiration
        await asyncio.sleep(0.15)

        # Should call function again
        await cached_func(5)
        assert call_count == 2


class TestConcurrentAccess:
    """Tests for concurrent access safety."""

    async def test_concurrent_reads(self, cache: AsyncTTLCache) -> None:
        """Test concurrent read operations."""
        await cache.set("key1", "value1")

        async def read_key() -> str | None:
            return await cache.get("key1")

        # Run many concurrent reads
        tasks = [read_key() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        assert all(r == "value1" for r in results)

    async def test_concurrent_writes(self, cache: AsyncTTLCache) -> None:
        """Test concurrent write operations."""

        async def write_key(i: int) -> None:
            await cache.set(f"key{i}", f"value{i}")

        # Run many concurrent writes
        tasks = [write_key(i) for i in range(100)]
        await asyncio.gather(*tasks)

        # Verify all writes succeeded
        for i in range(100):
            assert await cache.get(f"key{i}") == f"value{i}"

    async def test_concurrent_cached_function(self) -> None:
        """Test concurrent access to cached function returns correct results."""
        call_count = 0
        lock = asyncio.Lock()

        @async_ttl_cache(ttl_seconds=60.0)
        async def slow_func(x: int) -> int:
            nonlocal call_count
            async with lock:
                call_count += 1
            await asyncio.sleep(0.01)  # Simulate slow operation
            return x * 2

        # Run many concurrent calls with same argument
        tasks = [slow_func(5) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All should get the same result
        assert all(r == 10 for r in results)

        # Note: Without lock coalescing, concurrent misses will all
        # trigger the function. This is expected for a simple cache.
        # After initial calls complete and cache, subsequent calls will hit.
        assert call_count >= 1

        # Now test that subsequent calls are cached
        call_count = 0
        tasks = [slow_func(5) for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should be cached now
        assert all(r == 10 for r in results)
        assert call_count == 0  # All hits


class TestKeyGeneration:
    """Tests for cache key generation."""

    async def test_key_with_uuid(self, cache: AsyncTTLCache) -> None:
        """Test key generation with UUID arguments."""
        call_count = 0

        @cache.cached()
        async def func_with_uuid(tenant_id, session_id) -> str:
            nonlocal call_count
            call_count += 1
            return f"{tenant_id}:{session_id}"

        tenant = uuid4()
        session = uuid4()

        await func_with_uuid(tenant, session)
        await func_with_uuid(tenant, session)

        assert call_count == 1

    async def test_key_with_complex_types(self, cache: AsyncTTLCache) -> None:
        """Test key generation with complex types."""
        call_count = 0

        @cache.cached()
        async def func_with_dict(config: dict[str, int]) -> int:
            nonlocal call_count
            call_count += 1
            return sum(config.values())

        await func_with_dict({"a": 1, "b": 2})
        await func_with_dict({"a": 1, "b": 2})

        assert call_count == 1

        # Different dict - different key
        await func_with_dict({"a": 1, "c": 3})
        assert call_count == 2


class TestSharedCache:
    """Tests for shared cache instance."""

    def test_get_shared_cache_singleton(self) -> None:
        """Test that shared cache returns same instance."""
        cache1 = get_shared_cache()
        cache2 = get_shared_cache()
        assert cache1 is cache2

    async def test_shared_cache_usage(self) -> None:
        """Test using shared cache."""
        cache = get_shared_cache()
        await cache.set("shared_key", "shared_value")
        assert await cache.get("shared_key") == "shared_value"
