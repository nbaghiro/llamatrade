"""Tests for the Redis-backed fixed-window rate limiter."""

from __future__ import annotations

from llamatrade_common.ratelimit import RateLimiter


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRedis:
    """Dict-backed async Redis stand-in for INCR/EXPIRE (with optional errors)."""

    def __init__(self, *, error: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.error = error

    async def incr(self, key: str) -> int:
        if self.error:
            raise ConnectionError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, ttl: int) -> None:
        if self.error:
            raise ConnectionError("redis down")
        self.ttls[key] = ttl


class TestCheckAndCount:
    async def test_allowed_until_limit_then_blocked(self) -> None:
        limiter = RateLimiter(FakeRedis(), clock=FakeClock())

        for _ in range(3):
            assert await limiter.check_and_count("login:1.2.3.4", 3, 60) is True
        assert await limiter.check_and_count("login:1.2.3.4", 3, 60) is False
        assert await limiter.check_and_count("login:1.2.3.4", 3, 60) is False

    async def test_window_reset_allows_again(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(FakeRedis(), clock=clock)

        for _ in range(3):
            await limiter.check_and_count("k", 3, 60)
        assert await limiter.check_and_count("k", 3, 60) is False

        clock.advance(60)
        assert await limiter.check_and_count("k", 3, 60) is True

    async def test_keys_are_independent(self) -> None:
        limiter = RateLimiter(FakeRedis(), clock=FakeClock())

        assert await limiter.check_and_count("a", 1, 60) is True
        assert await limiter.check_and_count("a", 1, 60) is False
        assert await limiter.check_and_count("b", 1, 60) is True

    async def test_windows_are_independent(self) -> None:
        limiter = RateLimiter(FakeRedis(), clock=FakeClock())

        assert await limiter.check_and_count("k", 1, 60) is True
        assert await limiter.check_and_count("k", 1, 60) is False
        # A wider window over the same logical key counts separately.
        assert await limiter.check_and_count("k", 5, 900) is True

    async def test_expiry_set_on_first_hit(self) -> None:
        redis = FakeRedis()
        limiter = RateLimiter(redis, clock=FakeClock())

        await limiter.check_and_count("k", 3, 60)
        await limiter.check_and_count("k", 3, 60)

        assert list(redis.ttls.values()) == [60]

    async def test_fails_open_on_redis_error(self) -> None:
        limiter = RateLimiter(FakeRedis(error=True), clock=FakeClock())
        assert await limiter.check_and_count("k", 1, 60) is True
        assert await limiter.check_and_count("k", 1, 60) is True

    async def test_fails_closed_when_opted_in(self) -> None:
        limiter = RateLimiter(FakeRedis(error=True), clock=FakeClock(), fail_closed=True)
        assert await limiter.check_and_count("k", 1, 60) is False
        assert await limiter.check_and_count("k", 1, 60) is False

    async def test_fail_closed_option_does_not_affect_healthy_path(self) -> None:
        limiter = RateLimiter(FakeRedis(), clock=FakeClock(), fail_closed=True)
        assert await limiter.check_and_count("k", 1, 60) is True
        assert await limiter.check_and_count("k", 1, 60) is False
