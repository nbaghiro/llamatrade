"""Database metrics: query timing + connection-pool gauges.

The pool gauges are sampled at scrape time from a provider callback (the model
``llamatrade_db.get_pool_stats`` already supports), so they always reflect live
counts without a background sampler.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Protocol

from opentelemetry.metrics import CallbackOptions, Observation

from llamatrade_telemetry import registry

DB_QUERY_DURATION = registry.histogram(
    "llamatrade_db_query_duration_seconds",
    ["operation", "table"],
    "Database query duration",
)
DB_POOL_ACQUIRE_WAIT = registry.histogram(
    "llamatrade_db_pool_acquire_wait_seconds",
    (),
    "Time spent waiting to acquire a pooled connection",
)
DB_POOL_EXHAUSTED = registry.counter(
    "llamatrade_db_pool_exhausted_total",
    (),
    "Times a connection could not be acquired before timeout",
)


class PoolStatsLike(Protocol):
    """Structural type for a DB pool snapshot (matches ``llamatrade_db.PoolStats``)."""

    @property
    def checked_out(self) -> int: ...

    @property
    def checked_in(self) -> int: ...

    @property
    def max_connections(self) -> int: ...


_pool_providers: list[Callable[[], PoolStatsLike | None]] = []
_pool_registered = False


def _pool_observe(options: CallbackOptions) -> Iterable[Observation]:
    observations: list[Observation] = []
    for provider in _pool_providers:
        try:
            stats = provider()
        except Exception:
            continue
        if stats is None:
            continue
        observations.append(Observation(stats.checked_out, {"state": "active"}))
        observations.append(Observation(stats.checked_in, {"state": "idle"}))
        observations.append(Observation(stats.max_connections, {"state": "max"}))
    return observations


def register_pool_observer(provider: Callable[[], PoolStatsLike | None]) -> None:
    """Register a pool-stats provider; values are exported on every scrape.

    Pass ``llamatrade_db.get_pool_stats``. Safe to call repeatedly.
    """
    global _pool_registered
    _pool_providers.append(provider)
    if not _pool_registered:
        registry.observable_gauge(
            "llamatrade_db_connections",
            _pool_observe,
            ["state"],
            "Database connections by state (active/idle/max)",
        )
        _pool_registered = True


@contextmanager
def time_query(operation: str, table: str) -> Iterator[None]:
    """Time a DB query and record it under ``operation``/``table``."""
    start = perf_counter()
    try:
        yield
    finally:
        DB_QUERY_DURATION.labels(operation=operation, table=table).observe(perf_counter() - start)
