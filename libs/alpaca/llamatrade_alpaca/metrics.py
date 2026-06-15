"""Metrics for Alpaca API calls → unified telemetry dependency metrics.

Alpaca is the single owner of Alpaca-call metrics for the whole platform. Calls
are recorded as outbound-dependency metrics (``llamatrade_dependency_requests_total``
/ ``llamatrade_dependency_duration_seconds`` with ``target="alpaca"`` and
``operation=<endpoint>``) via the shared telemetry library — so the same concept
is no longer defined separately in the trading and market-data services.

Usage:
    from llamatrade_alpaca.metrics import time_alpaca_call

    async with time_alpaca_call("submit_order"):
        result = await client.post("/orders", ...)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from llamatrade_telemetry.instrumentation.dependency import record_dependency, time_dependency

_TARGET = "alpaca"


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
