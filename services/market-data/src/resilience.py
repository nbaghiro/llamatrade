"""Resilience patterns for external API calls.

Provides rate limiting, retry with exponential backoff, and circuit breaker patterns
for the Alpaca API client.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from typing import ParamSpec, TypeVar

import httpx

from src.models import (
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# === Rate Limiter (Token Bucket) ===


class RateLimiter:
    """Token bucket rate limiter for API calls.

    Alpaca free tier limit: 200 requests/minute.
    """

    def __init__(
        self,
        capacity: int = 200,
        refill_rate: float = 200 / 60,  # tokens per second
    ):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float | None = None) -> bool:
        """Acquire a token, waiting if necessary.

        Args:
            timeout: Maximum time to wait for a token (None = wait indefinitely)

        Returns:
            True if token acquired, False if timeout
        """
        start_time = time.monotonic()

        async with self._lock:
            while True:
                self._refill()

                if self._tokens >= 1:
                    self._tokens -= 1
                    return True

                # Calculate wait time until next token
                wait_time = (1 - self._tokens) / self.refill_rate

                # Check timeout
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if elapsed + wait_time > timeout:
                        return False

                # Release lock while waiting
                self._lock.release()
                try:
                    await asyncio.sleep(min(wait_time, 0.1))  # Check periodically
                finally:
                    await self._lock.acquire()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Get current available tokens (approximate)."""
        return self._tokens


# === Circuit Breaker ===


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker for external service calls.

    Prevents cascading failures by stopping requests to a failing service.
    """

    failure_threshold: int = 5  # Consecutive failures before opening
    reset_timeout: float = 60.0  # Seconds before trying half-open

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
        """
        async with self._lock:
            await self._check_state()

            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(f"Circuit is open, will retry after {self.reset_timeout}s")

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure(e)
            raise

    async def _check_state(self) -> None:
        """Check and potentially transition circuit state."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.reset_timeout:
                logger.info("Circuit breaker transitioning to half-open")
                self._state = CircuitState.HALF_OPEN

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker closing (service recovered)")
                self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker opening (half-open test failed)")
                self._state = CircuitState.OPEN

            elif self._failure_count >= self.failure_threshold:
                logger.warning(f"Circuit breaker opening after {self._failure_count} failures")
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0


# === Retry Configuration ===


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True

    # HTTP status codes to retry
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)

    # Exception types to retry
    retryable_exceptions: tuple[type[Exception], ...] = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        AlpacaRateLimitError,
        AlpacaServerError,
    )

    # Exception types that should NOT be retried
    non_retryable_exceptions: tuple[type[Exception], ...] = (
        InvalidRequestError,
        SymbolNotFoundError,
        CircuitOpenError,
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number (0-indexed)."""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add random jitter (0.5 to 1.5 of delay)
            delay = delay * (0.5 + random.random())

        return delay


def retry_with_backoff(
    config: RetryConfig | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for retrying async functions with exponential backoff.

    Args:
        config: Retry configuration (defaults to RetryConfig())

    Returns:
        Decorated function with retry behavior
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except config.non_retryable_exceptions:
                    # Don't retry these
                    raise

                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Retrying {func.__name__} after {delay:.2f}s "
                            f"(attempt {attempt + 1}/{config.max_retries + 1}): {e}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries ({config.max_retries}) exceeded for {func.__name__}: {e}"
                        )

                except Exception:
                    # Unexpected exception - don't retry
                    raise

            # Should not reach here, but raise last exception if we do
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry loop completed without success or exception")

        return wrapper

    return decorator


# === Error Parsing ===


def parse_alpaca_error(response: httpx.Response) -> Exception:
    """Parse Alpaca API error response into typed exception.

    Args:
        response: HTTP response from Alpaca API

    Returns:
        Appropriate exception type based on status code
    """
    status_code = response.status_code

    # Try to extract error message from response body
    try:
        data = response.json()
        message = data.get("message", data.get("error", str(data)))
    except Exception:
        message = response.text or f"HTTP {status_code}"

    if status_code == 400:
        return InvalidRequestError(message)

    elif status_code in (404, 422):
        # Try to extract symbol from request URL
        symbol = "unknown"
        if "/stocks/" in str(response.url):
            parts = str(response.url).split("/stocks/")
            if len(parts) > 1:
                symbol = parts[1].split("/")[0].upper()
        return SymbolNotFoundError(symbol, message)

    elif status_code == 429:
        retry_after = response.headers.get("Retry-After")
        retry_seconds = int(retry_after) if retry_after else None
        return AlpacaRateLimitError(message, retry_after=retry_seconds)

    elif status_code >= 500:
        return AlpacaServerError(message, status_code=status_code)

    else:
        return AlpacaServerError(f"Unexpected error: {message}", status_code=status_code)


# === Global Instances ===

# Global rate limiter for Alpaca API
_rate_limiter: RateLimiter | None = None

# Global circuit breaker
_circuit_breaker: CircuitBreaker | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def reset_resilience() -> None:
    """Reset global resilience instances (for testing)."""
    global _rate_limiter, _circuit_breaker
    _rate_limiter = None
    _circuit_breaker = None
