"""Metrics for Alpaca API calls → unified telemetry dependency metrics.

Alpaca is the single owner of Alpaca-call metrics for the whole platform. Calls
are recorded as outbound-dependency metrics (``llamatrade_dependency_requests_total``
/ ``llamatrade_dependency_duration_seconds`` with ``target="alpaca"`` and
``operation=<endpoint>``) via the shared telemetry library — so the same concept
is no longer defined separately in the trading and market-data services.

Resilience metrics (``llamatrade_alpaca_*``) make incidents visible directly:
circuit breaker transitions, rate limiter throttles/waits, and retry attempts,
recorded by ``resilience.py`` on the shared exposition.

Usage:
    from llamatrade_alpaca.metrics import time_alpaca_call

    async with time_alpaca_call("submit_order"):
        result = await client.post("/orders", ...)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from llamatrade_telemetry import registry
from llamatrade_telemetry.instrumentation.dependency import record_dependency, time_dependency

_TARGET = "alpaca"

CIRCUIT_TRANSITIONS_TOTAL = registry.counter(
    "llamatrade_alpaca_circuit_transitions_total",
    ["state"],
    "Alpaca circuit breaker state transitions, labeled by the state entered",
)
RATE_LIMIT_THROTTLE_TOTAL = registry.counter(
    "llamatrade_alpaca_rate_limit_throttle_total",
    ["mode", "outcome"],
    "Alpaca rate limiter throttle events (calls that waited or were refused)",
)
RATE_LIMIT_WAIT_SECONDS = registry.histogram(
    "llamatrade_alpaca_rate_limit_wait_seconds",
    ["mode"],
    "Time Alpaca calls spent waiting on the rate limiter",
)
RETRY_ATTEMPTS_TOTAL = registry.counter(
    "llamatrade_alpaca_retry_attempts_total",
    ["reason"],
    "Alpaca call retry attempts by retryable-error classification",
)


def record_circuit_transition(state: str) -> None:
    """Record a circuit breaker transition into ``state`` (open / half_open / closed)."""
    CIRCUIT_TRANSITIONS_TOTAL.labels(state=state).inc()


def record_rate_limit_throttle(mode: str, outcome: str, wait_seconds: float | None = None) -> None:
    """Record a throttle event; ``wait_seconds``, when known, also feeds the wait histogram.

    ``mode`` is ``local`` (in-process bucket) or ``shared`` (Redis window);
    ``outcome`` is ``waited`` or ``refused``.
    """
    RATE_LIMIT_THROTTLE_TOTAL.labels(mode=mode, outcome=outcome).inc()
    if wait_seconds is not None:
        RATE_LIMIT_WAIT_SECONDS.labels(mode=mode).observe(wait_seconds)


def record_retry_attempt(reason: str) -> None:
    """Record one scheduled retry, labeled with a bounded error classification."""
    RETRY_ATTEMPTS_TOTAL.labels(reason=reason).inc()


@asynccontextmanager
async def time_alpaca_call(endpoint: str) -> AsyncGenerator[None]:
    """Time an Alpaca API call and record it as a dependency metric.

    Records duration + status (``success`` / ``error`` / ``timeout``) under
    ``target="alpaca"``, ``operation=endpoint``.
    """
    with time_dependency(_TARGET, endpoint):
        yield


def record_api_call(endpoint: str, status: str, duration: float) -> None:
    """Record an Alpaca API call with explicit values (non-context-manager path)."""
    record_dependency(_TARGET, endpoint, status, duration)
