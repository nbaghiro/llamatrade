"""Tests for resilience module."""

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
    RetryConfig,
    create_market_data_resilience,
    create_trading_resilience,
    parse_alpaca_error,
    retry_with_backoff,
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
