"""Integration tests: the cache module lifecycle against a real Redis container."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from src.cache import TTL_SNAPSHOT, MarketDataCache, close_cache, get_cache, init_cache

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def clean_cache_singleton(
    redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[None]:
    """Point REDIS_URL at the container and reset the module singleton per test."""
    monkeypatch.setenv("REDIS_URL", redis_url)
    await close_cache()
    try:
        yield
    finally:
        await close_cache()


class TestInitCloseLifecycle:
    async def test_init_connects_and_is_idempotent(self) -> None:
        cache = await init_cache()
        assert isinstance(cache, MarketDataCache)
        assert get_cache() is cache
        assert await init_cache() is cache  # second init returns the singleton

    async def test_close_clears_the_singleton_and_reinit_reconnects(self) -> None:
        first = await init_cache()
        assert first is not None
        await close_cache()
        assert get_cache() is None

        second = await init_cache()
        assert second is not None
        assert second is not first
        assert await second.health_check() is True

    async def test_init_returns_none_when_redis_unreachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        assert await init_cache() is None
        assert get_cache() is None


class TestRoundTrips:
    async def test_set_get_delete_round_trip(self) -> None:
        cache = await init_cache()
        assert cache is not None

        assert await cache.set("itest:key", "value-1", ttl=60) is True
        assert await cache.get("itest:key") == "value-1"
        assert await cache.delete("itest:key") is True
        assert await cache.get("itest:key") is None

    async def test_set_applies_the_ttl(self) -> None:
        cache = await init_cache()
        assert cache is not None

        await cache.set("itest:ttl", "v", ttl=TTL_SNAPSHOT)
        ttl = await cache.redis.ttl("itest:ttl")
        assert 0 < ttl <= TTL_SNAPSHOT

    async def test_mget_mixes_hits_and_misses_in_one_round_trip(self) -> None:
        cache = await init_cache()
        assert cache is not None

        await cache.set("itest:a", "A", ttl=60)
        await cache.set("itest:c", "C", ttl=60)
        result = await cache.mget(["itest:a", "itest:b", "itest:c"])
        assert result == {"itest:a": "A", "itest:b": None, "itest:c": "C"}

    async def test_mget_empty_keys_is_a_noop(self) -> None:
        cache = await init_cache()
        assert cache is not None
        assert await cache.mget([]) == {}

    async def test_health_check_true_on_live_connection(self) -> None:
        cache = await init_cache()
        assert cache is not None
        assert await cache.health_check() is True
