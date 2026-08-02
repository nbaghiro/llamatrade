"""Resilience patterns for Alpaca API calls.

Provides rate limiting, retry with exponential backoff, and circuit breaker patterns.
"""

import asyncio
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from typing import ParamSpec, Protocol, TypeVar, cast

import httpx

from .errors import (
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)
from .metrics import record_circuit_transition, record_rate_limit_throttle, record_retry_attempt

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# === Rate Limiter (Token Bucket) ===


class RateLimiter:
    """Token bucket rate limiter for API calls.

    Default configuration matches Alpaca free tier: 200 requests/minute.
    """

    def __init__(
        self,
        capacity: int = 200,
        refill_rate: float = 200 / 60,  # tokens per second
    ):
        """Initialize rate limiter.

        Args:
            capacity: Maximum number of tokens (requests)
            refill_rate: Tokens added per second
        """
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
        waited = False

        async with self._lock:
            while True:
                self._refill()

                if self._tokens >= 1:
                    self._tokens -= 1
                    if waited:
                        record_rate_limit_throttle("local", "waited", time.monotonic() - start_time)
                    return True

                # Calculate wait time until next token
                wait_time = (1 - self._tokens) / self.refill_rate

                # Check timeout
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    if elapsed + wait_time > timeout:
                        record_rate_limit_throttle("local", "refused")
                        return False

                waited = True
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


# === Shared (Cluster-Wide) Rate Limiter ===


class RateLimiterLike(Protocol):
    """Anything a client can rate-limit through (local bucket or shared limiter)."""

    async def acquire(self, timeout: float | None = None) -> bool: ...


class RedisClientLike(Protocol):
    """Minimal async Redis surface the shared limiter needs."""

    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, seconds: int) -> bool: ...


class RedisRateLimiter:
    """Cluster-wide fixed-window rate limiter over Redis (INCR + EXPIRE).

    Trade-off: one atomic INCR per acquire, but a fixed window can admit up to
    2x the limit across a window boundary — accepted for simplicity over a
    sliding-window Lua script.

    Fails OPEN to the local in-process bucket on any Redis error.
    """

    def __init__(
        self,
        redis: RedisClientLike,
        fallback: RateLimiter,
        limit: int = 200,
        window_s: int = 60,
        scope: str = "default",
        key_prefix: str = "alpaca:ratelimit",
        time_fn: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self.scope = scope
        self._redis = redis
        self._fallback = fallback
        self._key_prefix = key_prefix
        self._time = time_fn
        self._sleep = sleep

    def _key(self, window: int) -> str:
        return f"{self._key_prefix}:{self.scope}:{window}"

    async def acquire(self, timeout: float | None = None) -> bool:
        """Acquire a slot in the shared window, waiting for the next window if full.

        Returns:
            True if a slot was acquired, False if the wait would exceed ``timeout``.
        """
        start = self._time()
        waited = False
        while True:
            now = self._time()
            window = int(now // self.window_s)
            try:
                count = await self._redis.incr(self._key(window))
                if count == 1:
                    await self._redis.expire(self._key(window), self.window_s * 2)
            except Exception:
                logger.warning(
                    "Shared rate limiter Redis error; failing open to local bucket",
                    exc_info=True,
                )
                remaining = None if timeout is None else max(0.0, timeout - (now - start))
                return await self._fallback.acquire(timeout=remaining)

            if count <= self.limit:
                if waited:
                    record_rate_limit_throttle("shared", "waited", now - start)
                return True

            wait = (window + 1) * self.window_s - now
            if timeout is not None and (now - start) + wait > timeout:
                record_rate_limit_throttle("shared", "refused")
                return False
            waited = True
            await self._sleep(wait)


def _shared_limiter_url() -> str | None:
    url = os.getenv("ALPACA_RATE_LIMIT_REDIS_URL")
    if url:
        return url
    if os.getenv("ALPACA_SHARED_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return os.getenv("REDIS_URL") or None
    return None


def select_rate_limiter(local: RateLimiter, scope: str) -> RateLimiterLike:
    """The cluster-shared limiter when configured via env, else the local bucket.

    N replicas each holding a full in-process bucket multiply the Alpaca
    budget; the shared limiter enforces one budget per credential scope. Falls
    back to ``local`` when Redis is unconfigured or the client cannot be built.
    """
    url = _shared_limiter_url()
    if url is None:
        return local
    try:
        import redis.asyncio as redis_asyncio

        client = cast(RedisClientLike, redis_asyncio.Redis.from_url(url))
    except Exception:
        logger.warning("Shared rate limiter unavailable; using in-process bucket", exc_info=True)
        return local
    return RedisRateLimiter(redis=client, fallback=local, limit=local.capacity, scope=scope)


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
                record_circuit_transition(CircuitState.HALF_OPEN.value)

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker closing (service recovered)")
                self._state = CircuitState.CLOSED
                record_circuit_transition(CircuitState.CLOSED.value)
            self._failure_count = 0

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("Circuit breaker opening (half-open test failed)")
                self._state = CircuitState.OPEN
                record_circuit_transition(CircuitState.OPEN.value)

            elif (
                self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold
            ):
                logger.warning(f"Circuit breaker opening after {self._failure_count} failures")
                self._state = CircuitState.OPEN
                record_circuit_transition(CircuitState.OPEN.value)

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


def _retry_reason(error: Exception) -> str:
    """Bounded classification of a retryable error for the retry-attempt metric."""
    if isinstance(error, AlpacaRateLimitError):
        return "rate_limit"
    if isinstance(error, AlpacaServerError):
        return "server_error"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "connect"
    return "other"


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
                        record_retry_attempt(_retry_reason(e))
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


# === Factory Functions ===


def create_market_data_resilience() -> tuple[RateLimiter, CircuitBreaker]:
    """Create resilience components configured for market data API.

    Returns:
        Tuple of (RateLimiter, CircuitBreaker) with market data settings
    """
    return (
        RateLimiter(capacity=200, refill_rate=200 / 60),
        CircuitBreaker(failure_threshold=5, reset_timeout=60.0),
    )


def create_trading_resilience() -> tuple[RateLimiter, CircuitBreaker]:
    """Create resilience components configured for trading API.

    Trading uses stricter settings since order failures are more critical.

    Returns:
        Tuple of (RateLimiter, CircuitBreaker) with trading settings
    """
    return (
        RateLimiter(capacity=200, refill_rate=200 / 60),
        CircuitBreaker(failure_threshold=3, reset_timeout=30.0),
    )
