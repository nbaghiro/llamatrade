"""Back-compat shim → :mod:`llamatrade_telemetry`.

Metrics moved to the unified, OTel-backed telemetry library (exported in
Prometheus format by ``init_telemetry``). This module re-exports the handful of
symbols existing services still import. Prefer ``llamatrade_telemetry`` directly
in new code.
"""

from __future__ import annotations

from collections.abc import Callable

from llamatrade_telemetry.instrumentation.db import PoolStatsLike, register_pool_observer
from llamatrade_telemetry.registry import get_metrics

__all__ = ["PoolStatsLike", "get_metrics", "init_service_info", "register_db_pool_observer"]


def init_service_info(service_name: str, version: str, environment: str) -> None:
    """Deprecated no-op.

    Service identity is now an OpenTelemetry resource attribute set by
    ``init_telemetry`` (``service.name`` / ``service.version`` /
    ``deployment.environment``), surfaced on Prometheus ``target_info``.
    """
    return None


def register_db_pool_observer(
    service_name: str,
    provider: Callable[[], PoolStatsLike | None],
) -> None:
    """Deprecated alias → :func:`llamatrade_telemetry...register_pool_observer`.

    The per-service dimension is now the Prometheus scrape ``job`` label, so the
    ``service_name`` argument is accepted for compatibility but unused.
    """
    register_pool_observer(provider)
