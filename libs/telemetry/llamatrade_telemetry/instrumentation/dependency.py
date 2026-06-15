"""Uniform outbound-dependency metrics (Alpaca, Stripe, peer services, …).

One schema for every external call so dashboards compare like-for-like:
``target`` is the dependency (``alpaca``, ``stripe``, ``market-data``), and
``operation`` the logical call (``submit_order``, ``get_bars``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from llamatrade_telemetry import registry

DEPENDENCY_REQUESTS_TOTAL = registry.counter(
    "llamatrade_dependency_requests_total",
    ["target", "operation", "status"],
    "Outbound dependency calls by result",
)
DEPENDENCY_DURATION = registry.histogram(
    "llamatrade_dependency_duration_seconds",
    ["target", "operation"],
    "Outbound dependency call duration",
)


def record_dependency(target: str, operation: str, status: str, duration: float) -> None:
    DEPENDENCY_REQUESTS_TOTAL.labels(target=target, operation=operation, status=status).inc()
    DEPENDENCY_DURATION.labels(target=target, operation=operation).observe(duration)


@contextmanager
def time_dependency(target: str, operation: str) -> Iterator[None]:
    """Time a dependency call; records status success/error/timeout on exit."""
    start = perf_counter()
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
        record_dependency(target, operation, status, perf_counter() - start)
