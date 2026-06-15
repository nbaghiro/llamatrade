"""Cache / Redis operation metrics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from llamatrade_telemetry import registry

CACHE_OPERATIONS_TOTAL = registry.counter(
    "llamatrade_cache_operations_total",
    ["cache", "op", "result"],
    "Cache operations by result (hit/miss/error)",
)
CACHE_OP_DURATION = registry.histogram(
    "llamatrade_cache_op_duration_seconds",
    ["cache", "op"],
    "Cache operation duration",
)


def record_cache_operation(cache: str, op: str, result: str) -> None:
    """Record a cache op. ``result`` is one of hit/miss/error/success."""
    CACHE_OPERATIONS_TOTAL.labels(cache=cache, op=op, result=result).inc()


@contextmanager
def time_cache_op(cache: str, op: str) -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    finally:
        CACHE_OP_DURATION.labels(cache=cache, op=op).observe(perf_counter() - start)
