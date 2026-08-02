"""Tests for resilience module."""

import asyncio
import logging
import time
from unittest.mock import MagicMock

import httpx
import pytest

from llamatrade_alpaca import (
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)
from llamatrade_alpaca.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    RedisRateLimiter,
    RetryConfig,
    create_market_data_resilience,
    create_trading_resilience,
    parse_alpaca_error,
    retry_with_backoff,
    select_rate_limiter,
)


class TestRateLimiter:
    """Tests for RateLimiter."""

    async def test_acquire_within_capacity(self) -> None:
        """Test acquiring tokens within capacity."""
        limiter = RateLimiter(capacity=10, refill_rate=1.0)
        for _ in range(10):
            assert await limiter.acquire() is True

    async def test_acquire_with_timeout(self) -> None:
        """Test acquire times out when no tokens available."""
        limiter = RateLimiter(capacity=1, refill_rate=0.1)
        await limiter.acquire()  # Use the only token
        # Should timeout since refill is slow
        result = await limiter.acquire(timeout=0.05)
        assert result is False

    async def test_available_tokens(self) -> None:
        """Test available_tokens property."""
        limiter = RateLimiter(capacity=5, refill_rate=1.0)
        assert limiter.available_tokens == 5.0
        await limiter.acquire()
        assert limiter.available_tokens == 4.0


class TestRateLimiterTiming:
    """Time-based RateLimiter behavior (fake clock via _last_refill rewind)."""

    async def test_refill_over_elapsed_time(self) -> None:
        limiter = RateLimiter(capacity=10, refill_rate=2.0)
        for _ in range(10):
            assert await limiter.acquire() is True
        assert limiter.available_tokens < 1

        limiter._last_refill -= 2.5  # simulate 2.5s elapsed -> 5 tokens back
        assert await limiter.acquire() is True
        assert limiter.available_tokens == pytest.approx(4.0, abs=0.1)

    async def test_refill_caps_at_capacity(self) -> None:
        limiter = RateLimiter(capacity=10, refill_rate=2.0)
        await limiter.acquire()

        limiter._last_refill -= 1000.0
        assert await limiter.acquire() is True
        assert limiter.available_tokens == pytest.approx(9.0, abs=0.1)

    async def test_concurrent_acquires_block_until_refill(self) -> None:
        limiter = RateLimiter(capacity=2, refill_rate=100.0)
        for _ in range(2):
            assert await limiter.acquire() is True

        start = time.monotonic()
        results = await asyncio.gather(
            limiter.acquire(timeout=2.0),
            limiter.acquire(timeout=2.0),
        )
        elapsed = time.monotonic() - start

        assert results == [True, True]
        # Two extra tokens at 100/s means the waiters really blocked (~20ms).
        assert elapsed >= 0.015
        assert limiter.available_tokens < 1

    async def test_acquire_timeout_returns_false_without_blocking(self) -> None:
        limiter = RateLimiter(capacity=1, refill_rate=0.001)
        assert await limiter.acquire() is True

        start = time.monotonic()
        assert await limiter.acquire(timeout=0.05) is False
        # The needed wait (~1000s) exceeds the timeout, so it returns immediately.
        assert time.monotonic() - start < 0.05


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    async def test_initial_state_closed(self) -> None:
        """Test circuit starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_open is False

    async def test_opens_after_threshold_failures(self) -> None:
        """Test circuit opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=2)

        async def failing_func() -> None:
            raise AlpacaServerError("error")

        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    async def test_open_circuit_raises_error(self) -> None:
        """Test open circuit raises CircuitOpenError."""
        cb = CircuitBreaker(failure_threshold=1)

        async def failing_func() -> None:
            raise AlpacaServerError("error")

        with pytest.raises(AlpacaServerError):
            await cb.call(failing_func)

        with pytest.raises(CircuitOpenError):
            await cb.call(failing_func)

    async def test_successful_call_resets_failures(self) -> None:
        """Test successful call resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)

        async def failing_func() -> None:
            raise AlpacaServerError("error")

        async def success_func() -> str:
            return "ok"

        # Two failures
        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await cb.call(failing_func)

        # Success resets count
        result = await cb.call(success_func)
        assert result == "ok"

        # Can fail twice more before opening
        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await cb.call(failing_func)

        assert cb.state == CircuitState.CLOSED

    async def test_reset(self) -> None:
        """Test manual reset."""
        cb = CircuitBreaker(failure_threshold=1)

        async def failing_func() -> None:
            raise AlpacaServerError("error")

        with pytest.raises(AlpacaServerError):
            await cb.call(failing_func)

        assert cb.is_open is True

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_open is False


async def _fail() -> None:
    raise AlpacaServerError("boom")


async def _ok() -> str:
    return "ok"


class TestCircuitBreakerHalfOpen:
    """OPEN -> HALF_OPEN -> CLOSED/OPEN transitions with an injected clock."""

    async def _open(self, cb: CircuitBreaker) -> None:
        for _ in range(cb.failure_threshold):
            with pytest.raises(AlpacaServerError):
                await cb.call(_fail)
        assert cb.state == CircuitState.OPEN

    async def test_open_transitions_to_half_open_after_reset_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)
        await self._open(cb)

        with pytest.raises(CircuitOpenError):
            await cb.call(_ok)

        cb._last_failure_time -= 60.0  # rewind: reset_timeout has now elapsed
        states_during_probe: list[CircuitState] = []

        async def probe() -> str:
            states_during_probe.append(cb.state)
            return "ok"

        assert await cb.call(probe) == "ok"
        assert states_during_probe == [CircuitState.HALF_OPEN]

    async def test_half_open_success_closes_and_resets_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=30.0)
        await self._open(cb)

        cb._last_failure_time -= 30.0
        assert await cb.call(_ok) == "ok"
        assert cb.state == CircuitState.CLOSED

        # Failure count was reset: one failure does not re-open a threshold-2 breaker.
        with pytest.raises(AlpacaServerError):
            await cb.call(_fail)
        assert cb.state == CircuitState.CLOSED

    async def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=30.0)
        await self._open(cb)

        cb._last_failure_time -= 30.0
        with pytest.raises(AlpacaServerError):
            await cb.call(_fail)

        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await cb.call(_ok)


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_calculate_delay_without_jitter(self) -> None:
        """Test delay calculation without jitter."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert config.calculate_delay(0) == 1.0
        assert config.calculate_delay(1) == 2.0
        assert config.calculate_delay(2) == 4.0

    def test_calculate_delay_respects_max(self) -> None:
        """Test delay respects max_delay."""
        config = RetryConfig(base_delay=10.0, max_delay=15.0, jitter=False)
        assert config.calculate_delay(0) == 10.0
        assert config.calculate_delay(1) == 15.0  # Capped at max
        assert config.calculate_delay(2) == 15.0  # Still capped


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    async def test_no_retry_on_success(self) -> None:
        """Test no retry needed on success."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def success_func() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await success_func()
        assert result == "ok"
        assert call_count == 1

    async def test_retry_on_retryable_exception(self) -> None:
        """Test retries on retryable exceptions."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def flaky_func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise AlpacaServerError("temporary error")
            return "ok"

        result = await flaky_func()
        assert result == "ok"
        assert call_count == 3

    async def test_no_retry_on_non_retryable_exception(self) -> None:
        """Test no retry on non-retryable exceptions."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def invalid_request_func() -> str:
            nonlocal call_count
            call_count += 1
            raise InvalidRequestError("bad request")

        with pytest.raises(InvalidRequestError):
            await invalid_request_func()

        assert call_count == 1

    async def test_exhausts_retries(self) -> None:
        """Test exception raised after all retries exhausted."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise AlpacaServerError("persistent error")

        with pytest.raises(AlpacaServerError):
            await always_fails()

        assert call_count == 3  # Initial + 2 retries


class TestParseAlpacaError:
    """Tests for parse_alpaca_error function."""

    def test_parse_400_error(self) -> None:
        """Test parsing 400 Bad Request."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.json.return_value = {"message": "Invalid symbol"}

        error = parse_alpaca_error(response)
        assert isinstance(error, InvalidRequestError)
        assert error.message == "Invalid symbol"

    def test_parse_404_error(self) -> None:
        """Test parsing 404 Not Found."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 404
        response.url = "https://data.alpaca.markets/v2/stocks/INVALID/bars"
        response.json.return_value = {"message": "not found"}

        error = parse_alpaca_error(response)
        assert isinstance(error, SymbolNotFoundError)
        assert error.symbol == "INVALID"

    def test_parse_429_error(self) -> None:
        """Test parsing 429 Rate Limit."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.headers = {"Retry-After": "60"}
        response.json.return_value = {"message": "rate limited"}

        error = parse_alpaca_error(response)
        assert isinstance(error, AlpacaRateLimitError)
        assert error.retry_after == 60

    def test_parse_500_error(self) -> None:
        """Test parsing 500 Server Error."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        response.json.return_value = {"message": "internal error"}

        error = parse_alpaca_error(response)
        assert isinstance(error, AlpacaServerError)
        assert error.status_code == 500


class TestFactoryFunctions:
    """Tests for resilience factory functions."""

    def test_create_market_data_resilience(self) -> None:
        """Test market data resilience factory."""
        rate_limiter, circuit_breaker = create_market_data_resilience()

        assert isinstance(rate_limiter, RateLimiter)
        assert rate_limiter.capacity == 200

        assert isinstance(circuit_breaker, CircuitBreaker)
        assert circuit_breaker.failure_threshold == 5
        assert circuit_breaker.reset_timeout == 60.0

    def test_create_trading_resilience(self) -> None:
        """Test trading resilience factory."""
        rate_limiter, circuit_breaker = create_trading_resilience()

        assert isinstance(rate_limiter, RateLimiter)
        assert rate_limiter.capacity == 200

        assert isinstance(circuit_breaker, CircuitBreaker)
        assert circuit_breaker.failure_threshold == 3  # Stricter for trading
        assert circuit_breaker.reset_timeout == 30.0  # Faster recovery


# === Shared (Redis) Rate Limiter ===


class FakeRedis:
    """In-memory INCR/EXPIRE fake matching the RedisClientLike protocol."""

    def __init__(self, fail: bool = False) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail

    async def incr(self, name: str) -> int:
        if self.fail:
            raise ConnectionError("redis down")
        self.counts[name] = self.counts.get(name, 0) + 1
        return self.counts[name]

    async def expire(self, name: str, seconds: int) -> bool:
        if self.fail:
            raise ConnectionError("redis down")
        self.ttls[name] = seconds
        return True


class FakeClock:
    """Wall clock + sleep pair where sleeping advances the clock (no real waits)."""

    def __init__(self, now: float = 1200.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def _shared_limiter(
    redis: FakeRedis, clock: FakeClock, limit: int = 3, fallback: RateLimiter | None = None
) -> RedisRateLimiter:
    return RedisRateLimiter(
        redis=redis,
        fallback=fallback or RateLimiter(capacity=5, refill_rate=1.0),
        limit=limit,
        window_s=60,
        scope="cred1",
        time_fn=clock.time,
        sleep=clock.sleep,
    )


class TestRedisRateLimiter:
    """Cluster-wide fixed-window limiter behavior."""

    async def test_enforces_window_limit(self) -> None:
        redis = FakeRedis()
        clock = FakeClock(now=1200.0)
        limiter = _shared_limiter(redis, clock, limit=3)

        for _ in range(3):
            assert await limiter.acquire(timeout=0.0) is True
        assert await limiter.acquire(timeout=1.0) is False
        assert clock.sleeps == []  # over-timeout waits return immediately

    async def test_sets_expiry_on_first_increment_of_window(self) -> None:
        redis = FakeRedis()
        clock = FakeClock(now=1200.0)
        limiter = _shared_limiter(redis, clock, limit=3)

        await limiter.acquire()
        key = "alpaca:ratelimit:cred1:20"
        assert redis.counts == {key: 1}
        assert redis.ttls == {key: 120}

    async def test_waits_into_next_window_when_allowed(self) -> None:
        redis = FakeRedis()
        clock = FakeClock(now=1200.0)
        limiter = _shared_limiter(redis, clock, limit=3)

        for _ in range(3):
            await limiter.acquire()
        assert await limiter.acquire(timeout=90.0) is True

        # Slept exactly to the window boundary, then counted in the new window.
        assert clock.sleeps == [pytest.approx(60.0)]
        assert redis.counts["alpaca:ratelimit:cred1:21"] == 1

    async def test_windows_are_scoped_per_credential(self) -> None:
        redis = FakeRedis()
        clock = FakeClock(now=1200.0)
        a = _shared_limiter(redis, clock, limit=1)
        b = RedisRateLimiter(
            redis=redis,
            fallback=RateLimiter(capacity=5, refill_rate=1.0),
            limit=1,
            window_s=60,
            scope="cred2",
            time_fn=clock.time,
            sleep=clock.sleep,
        )

        assert await a.acquire(timeout=0.0) is True
        assert await b.acquire(timeout=0.0) is True  # separate budget
        assert await a.acquire(timeout=0.0) is False

    async def test_redis_error_fails_open_to_local_bucket(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fallback = RateLimiter(capacity=5, refill_rate=1.0)
        limiter = _shared_limiter(FakeRedis(fail=True), FakeClock(), fallback=fallback)

        with caplog.at_level(logging.WARNING, logger="llamatrade_alpaca.resilience"):
            assert await limiter.acquire() is True

        assert "failing open" in caplog.text
        assert fallback.available_tokens == pytest.approx(4.0, abs=0.1)

    async def test_fail_open_respects_remaining_timeout(self) -> None:
        fallback = RateLimiter(capacity=1, refill_rate=0.001)
        await fallback.acquire()  # drain the local bucket
        limiter = _shared_limiter(FakeRedis(fail=True), FakeClock(), fallback=fallback)

        start = time.monotonic()
        assert await limiter.acquire(timeout=0.05) is False
        assert time.monotonic() - start < 0.05


class TestSharedLimiterSelection:
    """Env-driven selection between the local bucket and the shared limiter."""

    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("ALPACA_RATE_LIMIT_REDIS_URL", "ALPACA_SHARED_RATE_LIMIT", "REDIS_URL"):
            monkeypatch.delenv(var, raising=False)

    def test_defaults_to_local_bucket(self) -> None:
        local = RateLimiter(capacity=200)
        assert select_rate_limiter(local, scope="s") is local

    def test_dedicated_url_selects_shared_limiter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPACA_RATE_LIMIT_REDIS_URL", "redis://localhost:6399/0")
        local = RateLimiter(capacity=200)

        limiter = select_rate_limiter(local, scope="cred-hash")

        assert isinstance(limiter, RedisRateLimiter)
        assert limiter.limit == 200
        assert limiter.scope == "cred-hash"

    def test_redis_url_with_flag_selects_shared_limiter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6399/0")
        monkeypatch.setenv("ALPACA_SHARED_RATE_LIMIT", "true")

        limiter = select_rate_limiter(RateLimiter(capacity=200), scope="s")
        assert isinstance(limiter, RedisRateLimiter)

    def test_redis_url_without_flag_stays_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6399/0")
        local = RateLimiter(capacity=200)
        assert select_rate_limiter(local, scope="s") is local

    def test_flag_without_url_stays_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPACA_SHARED_RATE_LIMIT", "true")
        local = RateLimiter(capacity=200)
        assert select_rate_limiter(local, scope="s") is local

    async def test_client_base_uses_shared_limiter_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamatrade_alpaca import MarketDataClient

        monkeypatch.setenv("ALPACA_RATE_LIMIT_REDIS_URL", "redis://localhost:6399/0")
        client = MarketDataClient(api_key="key-a", api_secret="secret")
        try:
            assert isinstance(client._rate_limiter, RedisRateLimiter)
            assert client._rate_limiter.scope != "key-a"  # hashed, not the raw key
        finally:
            await client.close()

    async def test_client_base_defaults_to_local_bucket(self) -> None:
        from llamatrade_alpaca import MarketDataClient

        client = MarketDataClient(api_key="key-a", api_secret="secret")
        try:
            assert isinstance(client._rate_limiter, RateLimiter)
        finally:
            await client.close()
