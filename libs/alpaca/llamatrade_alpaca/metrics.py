"""Prometheus metrics for Alpaca API calls.

This module provides metrics with graceful degradation - if prometheus_client
is not installed, metrics are no-ops.

Usage:
    from llamatrade_alpaca.metrics import time_alpaca_call

    async with time_alpaca_call("submit_order"):
        result = await client.post("/orders", ...)
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol, runtime_checkable

# Type checking imports
if TYPE_CHECKING:
    from prometheus_client import Counter, Histogram


@runtime_checkable
class MetricProtocol(Protocol):
    """Protocol for metric objects (Counter, Histogram, etc.)."""

    def labels(self, **kwargs: str) -> MetricProtocol:
        """Return labeled metric."""
        ...


class NoOpMetric:
    """No-op metric for when prometheus_client is not installed."""

    def labels(self, **kwargs: str) -> NoOpMetric:
        """Return self (no-op)."""
        return self

    def inc(self, amount: float = 1) -> None:
        """No-op increment."""
        pass

    def observe(self, value: float) -> None:
        """No-op observe."""
        pass


def _create_metrics() -> tuple[Counter | NoOpMetric, Histogram | NoOpMetric, bool]:
    """Create metrics, returning no-ops if prometheus_client is not installed."""
    try:
        from prometheus_client import Counter, Histogram

        counter: Counter | NoOpMetric = Counter(
            "alpaca_api_calls_total",
            "Total Alpaca API calls",
            ["endpoint", "status"],
        )
        histogram: Histogram | NoOpMetric = Histogram(
            "alpaca_api_duration_seconds",
            "Alpaca API call duration",
            ["endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        return counter, histogram, True
    except ImportError:
        return NoOpMetric(), NoOpMetric(), False


# Create metrics at module load time
ALPACA_API_CALLS_TOTAL, ALPACA_API_DURATION_SECONDS, HAS_PROMETHEUS = _create_metrics()


@asynccontextmanager
async def time_alpaca_call(endpoint: str) -> AsyncIterator[None]:
    """Context manager to time Alpaca API calls and record metrics.

    Records both duration (histogram) and call count (counter with status label).
    Gracefully degrades to no-op if prometheus_client is not installed.

    Usage:
        async with time_alpaca_call("submit_order"):
            result = await client.post("/orders", ...)

    Args:
        endpoint: Name of the API endpoint being called

    Yields:
        None
    """
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except TimeoutError:
        status = "timeout"
        raise
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        ALPACA_API_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration)
        ALPACA_API_CALLS_TOTAL.labels(endpoint=endpoint, status=status).inc()


def record_api_call(endpoint: str, status: str, duration: float) -> None:
    """Record an API call with explicit values.

    Use this when you can't use the context manager (e.g., in non-async code).

    Args:
        endpoint: Name of the API endpoint
        status: Result status ("success", "error", "timeout")
        duration: Duration in seconds
    """
    ALPACA_API_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration)
    ALPACA_API_CALLS_TOTAL.labels(endpoint=endpoint, status=status).inc()
