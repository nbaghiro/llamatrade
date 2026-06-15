"""Back-compat shim → :mod:`llamatrade_telemetry`.

Observability setup moved to the unified ``init_telemetry`` call. These thin
wrappers preserve the old API (used across service ``main.py`` files) and now
wire the full stack: structured logging, OTel metrics + Prometheus ``/metrics``,
distributed tracing, the RED middleware, and DB pool gauges.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.applications import Starlette

from llamatrade_telemetry import init_telemetry
from llamatrade_telemetry.config import TelemetrySettings
from llamatrade_telemetry.instrumentation.db import PoolStatsLike
from llamatrade_telemetry.instrumentation.http import TelemetryMiddleware as ObservabilityMiddleware

__all__ = [
    "ObservabilityMiddleware",
    "PoolStatsLike",
    "enable_db_pool_metrics",
    "setup_observability",
]


def enable_db_pool_metrics(
    app: Starlette,
    service_name: str,
    pool_stats_provider: Callable[[], PoolStatsLike | None],
) -> None:
    """Initialise telemetry for ``app`` and export DB pool gauges.

    Now wires the full telemetry stack (was pool-gauges-only). Idempotent.
    """
    init_telemetry(app, service=service_name, pool_stats_provider=pool_stats_provider)


def setup_observability(
    app: Starlette,
    service_name: str,
    version: str = "0.0.0",
    environment: str = "development",
    log_level: str = "INFO",
    json_logs: bool = True,
) -> None:
    """Initialise the full telemetry stack for ``app`` (idempotent)."""
    settings = TelemetrySettings(
        ENVIRONMENT=environment,
        LOG_LEVEL=log_level,
        LOG_FORMAT="json" if json_logs else "text",
    )
    init_telemetry(app, service=service_name, version=version, settings=settings)
