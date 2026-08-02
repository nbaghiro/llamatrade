"""Database metrics: query timing, connection-pool gauges, RLS-bypass count.

The pool gauges are sampled at scrape time from a provider callback (the model
``llamatrade_db.get_pool_stats`` already supports), so they always reflect live
counts without a background sampler. ``DB_RLS_BYPASS`` is incremented by
``llamatrade_db.session`` alongside its audit log line; the per-use detail
(caller, reason, tenant scope) stays on the log, never on a metric label.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from opentelemetry.metrics import CallbackOptions, Observation

from llamatrade_telemetry import registry

DB_QUERY_DURATION = registry.histogram(
    "llamatrade_db_query_duration_seconds",
    ["operation", "table"],
    "Database query duration",
)
DB_POOL_EXHAUSTED = registry.counter(
    "llamatrade_db_pool_exhausted_total",
    (),
    "Times a connection could not be acquired before timeout",
)
DB_RLS_BYPASS = registry.counter(
    "llamatrade_db_rls_bypass_total",
    ["operation"],
    "RLS system-bypass activations by entry point",
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
