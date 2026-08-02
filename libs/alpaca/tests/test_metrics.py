"""Tests for Alpaca metrics → unified telemetry dependency + resilience metrics."""

from __future__ import annotations

import re

import pytest

from llamatrade_alpaca.errors import AlpacaRateLimitError, AlpacaServerError
from llamatrade_alpaca.metrics import record_api_call, time_alpaca_call
from llamatrade_alpaca.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    RedisRateLimiter,
    RetryConfig,
    retry_with_backoff,
)
from llamatrade_telemetry.registry import get_metrics

from .test_resilience import FakeClock, FakeRedis

CIRCUIT = "llamatrade_alpaca_circuit_transitions_total"
THROTTLE = "llamatrade_alpaca_rate_limit_throttle_total"
WAIT_COUNT = "llamatrade_alpaca_rate_limit_wait_seconds_count"
RETRIES = "llamatrade_alpaca_retry_attempts_total"


def _scrape() -> str:
    return get_metrics().decode()


def _sample(name: str, **labels: str) -> float:
    """Value of the ``name`` sample whose labels contain ``labels`` (0.0 if absent).

    Matches on label containment, not equality: the OTel Prometheus exporter
    appends ``otel_scope_*`` labels whose presence varies by exporter version.
    """
    for line in _scrape().splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        match = re.match(rf"{re.escape(name)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line)
        if match is None:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in labels.items()):
            return float(match.group("value"))
    return 0.0


def test_record_api_call_emits_dependency_metric() -> None:
    record_api_call("unit_record", "success", 0.5)
    out = _scrape()
    assert (
        'llamatrade_dependency_requests_total{operation="unit_record",status="success",target="alpaca"}'
        in out
    )


async def test_time_alpaca_call_success() -> None:
    async with time_alpaca_call("unit_success"):
        pass
    out = _scrape()
    assert (
        'llamatrade_dependency_requests_total{operation="unit_success",status="success",target="alpaca"}'
        in out
    )


async def test_time_alpaca_call_error_records_error_status() -> None:
    with pytest.raises(ValueError):
        async with time_alpaca_call("unit_error"):
            raise ValueError("boom")
    out = _scrape()
    assert (
        'llamatrade_dependency_requests_total{operation="unit_error",status="error",target="alpaca"}'
        in out
    )


async def test_time_alpaca_call_timeout_records_timeout_status() -> None:
    with pytest.raises(TimeoutError):
        async with time_alpaca_call("unit_timeout"):
            raise TimeoutError("slow")
    out = _scrape()
    assert (
        'llamatrade_dependency_requests_total{operation="unit_timeout",status="timeout",target="alpaca"}'
        in out
    )


async def _boom() -> None:
    raise RuntimeError("down")


async def _ok() -> str:
    return "ok"


async def test_circuit_breaker_open_transition_increments_counter() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)
    before = _sample(CIRCUIT, state="open")

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)

    assert breaker.state is CircuitState.OPEN
    assert _sample(CIRCUIT, state="open") == before + 1.0


async def test_circuit_breaker_half_open_and_closed_transitions() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    before_half = _sample(CIRCUIT, state="half_open")
    before_closed = _sample(CIRCUIT, state="closed")

    breaker._last_failure_time -= 60.0  # rewind: reset_timeout has now elapsed
    assert await breaker.call(_ok) == "ok"

    assert breaker.state is CircuitState.CLOSED
    assert _sample(CIRCUIT, state="half_open") == before_half + 1.0
    assert _sample(CIRCUIT, state="closed") == before_closed + 1.0


async def test_circuit_breaker_failure_while_already_open_not_double_counted() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)
    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    before = _sample(CIRCUIT, state="open")

    await breaker._on_failure(RuntimeError("straggler from an in-flight call"))

    assert breaker.state is CircuitState.OPEN
    assert _sample(CIRCUIT, state="open") == before


async def test_rate_limiter_wait_records_throttle_and_wait_time() -> None:
    limiter = RateLimiter(capacity=1, refill_rate=100.0)
    assert await limiter.acquire() is True
    before = _sample(THROTTLE, mode="local", outcome="waited")
    before_wait = _sample(WAIT_COUNT, mode="local")

    assert await limiter.acquire() is True

    assert _sample(THROTTLE, mode="local", outcome="waited") == before + 1.0
    assert _sample(WAIT_COUNT, mode="local") == before_wait + 1.0


async def test_rate_limiter_unthrottled_acquire_records_nothing() -> None:
    limiter = RateLimiter(capacity=2, refill_rate=1.0)
    before = _sample(THROTTLE, mode="local", outcome="waited")
    before_wait = _sample(WAIT_COUNT, mode="local")

    assert await limiter.acquire() is True

    assert _sample(THROTTLE, mode="local", outcome="waited") == before
    assert _sample(WAIT_COUNT, mode="local") == before_wait


async def test_rate_limiter_timeout_records_refused() -> None:
    limiter = RateLimiter(capacity=1, refill_rate=0.1)
    assert await limiter.acquire() is True
    before = _sample(THROTTLE, mode="local", outcome="refused")

    assert await limiter.acquire(timeout=0.05) is False

    assert _sample(THROTTLE, mode="local", outcome="refused") == before + 1.0


async def test_shared_rate_limiter_records_waited_and_refused() -> None:
    clock = FakeClock(now=1200.0)
    limiter = RedisRateLimiter(
        redis=FakeRedis(),
        fallback=RateLimiter(capacity=5, refill_rate=1.0),
        limit=1,
        window_s=60,
        scope="metrics_test",
        time_fn=clock.time,
        sleep=clock.sleep,
    )
    assert await limiter.acquire() is True
    before_waited = _sample(THROTTLE, mode="shared", outcome="waited")
    before_wait = _sample(WAIT_COUNT, mode="shared")

    assert await limiter.acquire() is True

    assert _sample(THROTTLE, mode="shared", outcome="waited") == before_waited + 1.0
    assert _sample(WAIT_COUNT, mode="shared") == before_wait + 1.0

    before_refused = _sample(THROTTLE, mode="shared", outcome="refused")
    assert await limiter.acquire(timeout=1.0) is False
    assert _sample(THROTTLE, mode="shared", outcome="refused") == before_refused + 1.0


async def test_retry_attempts_increment_with_server_error_reason() -> None:
    before = _sample(RETRIES, reason="server_error")
    config = RetryConfig(max_retries=2, base_delay=0.001, max_delay=0.002, jitter=False)
    calls = 0

    @retry_with_backoff(config)
    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise AlpacaServerError("boom", status_code=503)
        return "ok"

    assert await flaky() == "ok"
    assert _sample(RETRIES, reason="server_error") == before + 2.0


async def test_retry_rate_limit_error_classified_as_rate_limit() -> None:
    before = _sample(RETRIES, reason="rate_limit")
    config = RetryConfig(max_retries=1, base_delay=0.001, max_delay=0.001, jitter=False)
    calls = 0

    @retry_with_backoff(config)
    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AlpacaRateLimitError("slow down")
        return "ok"

    assert await flaky() == "ok"
    assert _sample(RETRIES, reason="rate_limit") == before + 1.0


async def test_retry_exhaustion_counts_only_scheduled_retries() -> None:
    before = _sample(RETRIES, reason="server_error")
    config = RetryConfig(max_retries=2, base_delay=0.001, max_delay=0.001, jitter=False)

    @retry_with_backoff(config)
    async def always_down() -> str:
        raise AlpacaServerError("down", status_code=500)

    with pytest.raises(AlpacaServerError):
        await always_down()

    assert _sample(RETRIES, reason="server_error") == before + 2.0
