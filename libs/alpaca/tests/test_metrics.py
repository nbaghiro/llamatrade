"""Tests for Alpaca metrics → unified telemetry dependency metrics."""

from __future__ import annotations

import pytest

from llamatrade_alpaca.metrics import record_api_call, time_alpaca_call
from llamatrade_telemetry.registry import get_metrics


def _scrape() -> str:
    return get_metrics().decode()


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
