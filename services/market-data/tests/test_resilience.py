"""Tests for resilience patterns."""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest
from src.models import (
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)
from src.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    RetryConfig,
    parse_alpaca_error,
    reset_resilience,
    retry_with_backoff,
)


class TestRateLimiter:
    """Tests for token bucket rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Create a rate limiter with small capacity for testing."""
        return RateLimiter(capacity=3, refill_rate=1.0)

    @pytest.mark.asyncio
    async def test_acquire_within_capacity(self, limiter):
        """Test acquiring tokens within capacity."""
        for _ in range(3):
            result = await limiter.acquire(timeout=0.1)
            assert result is True

    @pytest.mark.asyncio
    async def test_acquire_exceeds_capacity_times_out(self, limiter):
        """Test that exceeding capacity with timeout returns False."""
        # Drain all tokens
        for _ in range(3):
            await limiter.acquire()

        # Next acquire should timeout
        result = await limiter.acquire(timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_waits_for_refill(self, limiter):
        """Test that acquire waits for token refill."""
        # Drain all tokens
        for _ in range(3):
            await limiter.acquire()

        # Wait for refill (1 token/second)
        await asyncio.sleep(1.1)

        # Should now succeed
        result = await limiter.acquire(timeout=0.1)
        assert result is True

    @pytest.mark.asyncio
    async def test_available_tokens_property(self, limiter):
        """Test available_tokens reflects token count."""
        initial = limiter.available_tokens
        assert initial == 3.0

        await limiter.acquire()
        assert limiter.available_tokens < initial

    @pytest.mark.asyncio
    async def test_refill_does_not_exceed_capacity(self, limiter):
        """Test that refill doesn't exceed capacity."""
        # Wait for potential over-refill
        await asyncio.sleep(0.5)

        assert limiter.available_tokens <= limiter.capacity


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    @pytest.fixture
    def breaker(self):
        """Create a circuit breaker with low thresholds for testing."""
        return CircuitBreaker(failure_threshold=2, reset_timeout=0.5)

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, breaker):
        """Test circuit starts in closed state."""
        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open

    @pytest.mark.asyncio
    async def test_successful_call_keeps_circuit_closed(self, breaker):
        """Test successful calls keep circuit closed."""

        async def success():
            return "ok"

        result = await breaker.call(success)

        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self, breaker):
        """Test consecutive failures open the circuit."""

        async def failure():
            raise AlpacaServerError("error")

        # First failure
        with pytest.raises(AlpacaServerError):
            await breaker.call(failure)
        assert breaker.state == CircuitState.CLOSED

        # Second failure - should open circuit
        with pytest.raises(AlpacaServerError):
            await breaker.call(failure)
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self, breaker):
        """Test open circuit rejects calls with CircuitOpenError."""

        async def failure():
            raise AlpacaServerError("error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await breaker.call(failure)

        # Next call should be rejected
        with pytest.raises(CircuitOpenError):
            await breaker.call(failure)

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, breaker):
        """Test circuit transitions to half-open after reset timeout."""

        async def failure():
            raise AlpacaServerError("error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await breaker.call(failure)

        assert breaker.state == CircuitState.OPEN

        # Wait for reset timeout
        await asyncio.sleep(0.6)

        # Next call should be allowed (half-open)
        with pytest.raises(AlpacaServerError):
            await breaker.call(failure)

        # Should be back to open after failure in half-open
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes_circuit(self, breaker):
        """Test successful call in half-open state closes circuit."""
        call_count = 0

        async def sometimes_fail():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise AlpacaServerError("error")
            return "ok"

        # Open the circuit
        for _ in range(2):
            with pytest.raises(AlpacaServerError):
                await breaker.call(sometimes_fail)

        # Wait for reset timeout
        await asyncio.sleep(0.6)

        # This should succeed and close the circuit
        result = await breaker.call(sometimes_fail)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self, breaker):
        """Test successful call resets failure count."""

        async def success():
            return "ok"

        async def failure():
            raise AlpacaServerError("error")

        # One failure
        with pytest.raises(AlpacaServerError):
            await breaker.call(failure)

        # One success - should reset
        await breaker.call(success)

        # One more failure - should not open (count reset)
        with pytest.raises(AlpacaServerError):
            await breaker.call(failure)

        assert breaker.state == CircuitState.CLOSED

    def test_reset_method(self, breaker):
        """Test manual reset of circuit breaker."""
        breaker._state = CircuitState.OPEN
        breaker._failure_count = 5

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0


class TestRetryConfig:
    """Tests for retry configuration."""

    def test_default_values(self):
        """Test default retry config values."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.exponential_base == 2.0

    def test_calculate_delay_exponential(self):
        """Test exponential delay calculation."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

        assert config.calculate_delay(0) == 1.0
        assert config.calculate_delay(1) == 2.0
        assert config.calculate_delay(2) == 4.0
        assert config.calculate_delay(3) == 8.0

    def test_calculate_delay_respects_max(self):
        """Test delay respects maximum."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)

        # 2^10 would be 1024, but should cap at 5
        assert config.calculate_delay(10) == 5.0

    def test_calculate_delay_with_jitter(self):
        """Test jitter adds randomness to delay."""
        config = RetryConfig(base_delay=1.0, jitter=True)

        delays = [config.calculate_delay(0) for _ in range(10)]

        # All delays should be different (with high probability)
        assert len(set(delays)) > 1
        # All should be within expected range (0.5 to 1.5 of base)
        assert all(0.5 <= d <= 1.5 for d in delays)


class TestRetryWithBackoff:
    """Tests for retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_succeeds_without_retry(self):
        """Test successful call returns immediately."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await success()

        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_exception(self):
        """Test retries on retryable exceptions."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise AlpacaServerError("error")
            return "ok"

        result = await fail_then_succeed()

        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Test raises exception after max retries."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise AlpacaServerError("error")

        with pytest.raises(AlpacaServerError):
            await always_fail()

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable(self):
        """Test does not retry non-retryable exceptions."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def invalid_request():
            nonlocal call_count
            call_count += 1
            raise InvalidRequestError("bad request")

        with pytest.raises(InvalidRequestError):
            await invalid_request()

        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_does_not_retry_symbol_not_found(self):
        """Test does not retry SymbolNotFoundError."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def not_found():
            nonlocal call_count
            call_count += 1
            raise SymbolNotFoundError("INVALID")

        with pytest.raises(SymbolNotFoundError):
            await not_found()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_does_not_retry_circuit_open(self):
        """Test does not retry CircuitOpenError."""
        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        async def circuit_open():
            nonlocal call_count
            call_count += 1
            raise CircuitOpenError()

        with pytest.raises(CircuitOpenError):
            await circuit_open()

        assert call_count == 1


class TestParseAlpacaError:
    """Tests for parse_alpaca_error function."""

    def _make_response(
        self, status_code: int, json_data: dict | None = None, text: str = ""
    ) -> httpx.Response:
        """Create a mock response."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.text = text
        response.url = "https://data.alpaca.markets/v2/stocks/AAPL/bars"
        response.headers = {}

        if json_data:
            response.json.return_value = json_data
        else:
            response.json.side_effect = ValueError("No JSON")

        return response

    def test_parse_400_returns_invalid_request(self):
        """Test 400 returns InvalidRequestError."""
        response = self._make_response(400, {"message": "Invalid timeframe"})

        error = parse_alpaca_error(response)

        assert isinstance(error, InvalidRequestError)
        assert "Invalid timeframe" in str(error)

    def test_parse_404_returns_symbol_not_found(self):
        """Test 404 returns SymbolNotFoundError."""
        response = self._make_response(404, {"message": "Symbol not found"})

        error = parse_alpaca_error(response)

        assert isinstance(error, SymbolNotFoundError)
        assert error.symbol == "AAPL"

    def test_parse_422_returns_symbol_not_found(self):
        """Test 422 returns SymbolNotFoundError."""
        response = self._make_response(422, {"message": "Invalid symbol"})

        error = parse_alpaca_error(response)

        assert isinstance(error, SymbolNotFoundError)

    def test_parse_429_returns_rate_limit(self):
        """Test 429 returns AlpacaRateLimitError."""
        response = self._make_response(429, {"message": "Rate limit exceeded"})
        response.headers = {"Retry-After": "60"}

        error = parse_alpaca_error(response)

        assert isinstance(error, AlpacaRateLimitError)
        assert error.retry_after == 60

    def test_parse_500_returns_server_error(self):
        """Test 500 returns AlpacaServerError."""
        response = self._make_response(500, {"message": "Internal error"})

        error = parse_alpaca_error(response)

        assert isinstance(error, AlpacaServerError)
        assert error.status_code == 500

    def test_parse_502_returns_server_error(self):
        """Test 502 returns AlpacaServerError."""
        response = self._make_response(502, text="Bad Gateway")

        error = parse_alpaca_error(response)

        assert isinstance(error, AlpacaServerError)
        assert error.status_code == 502

    def test_parse_503_returns_server_error(self):
        """Test 503 returns AlpacaServerError."""
        response = self._make_response(503, {"message": "Service unavailable"})

        error = parse_alpaca_error(response)

        assert isinstance(error, AlpacaServerError)
        assert error.status_code == 503


class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_alpaca_rate_limit_error(self):
        """Test AlpacaRateLimitError properties."""
        error = AlpacaRateLimitError("Rate limited", retry_after=30)

        assert error.status_code == 429
        assert error.retry_after == 30
        assert "Rate limited" in str(error)

    def test_alpaca_server_error(self):
        """Test AlpacaServerError properties."""
        error = AlpacaServerError("Server error", status_code=502)

        assert error.status_code == 502
        assert "Server error" in str(error)

    def test_symbol_not_found_error(self):
        """Test SymbolNotFoundError properties."""
        error = SymbolNotFoundError("INVALID")

        assert error.symbol == "INVALID"
        assert error.status_code == 404
        assert "INVALID" in str(error)

    def test_invalid_request_error(self):
        """Test InvalidRequestError properties."""
        error = InvalidRequestError("Bad params")

        assert error.status_code == 400
        assert "Bad params" in str(error)

    def test_circuit_open_error(self):
        """Test CircuitOpenError properties."""
        error = CircuitOpenError("Circuit is open")

        assert "Circuit is open" in str(error)


class TestGlobalInstances:
    """Tests for global resilience instances."""

    def test_reset_resilience_clears_instances(self):
        """Test reset_resilience clears global instances."""
        from src.resilience import (
            get_circuit_breaker,
            get_rate_limiter,
        )

        # Create instances
        limiter1 = get_rate_limiter()
        breaker1 = get_circuit_breaker()

        # Reset
        reset_resilience()

        # Get new instances
        limiter2 = get_rate_limiter()
        breaker2 = get_circuit_breaker()

        # Should be different instances
        assert limiter1 is not limiter2
        assert breaker1 is not breaker2
