"""Tests for the async TTL cache backing the risk-config lookup."""

import asyncio

import pytest

from src.utils.cache import AsyncTTLCache


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

    async def test_clear(self, cache: AsyncTTLCache) -> None:
        """Test clearing all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert cache.size == 0

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
