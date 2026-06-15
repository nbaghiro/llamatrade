"""``init_telemetry`` — the single entry point every service/worker calls.

Wires structured logging, the OTel MeterProvider + Prometheus ``/metrics``
endpoint, the TracerProvider, the RED middleware, and (optionally) the DB pool
observer. Idempotent and safe to call at import time.
"""

from __future__ import annotations

from collections.abc import Callable

from opentelemetry.sdk.resources import Resource
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from llamatrade_telemetry import tracing
from llamatrade_telemetry.config import TelemetrySettings, load_settings
from llamatrade_telemetry.instrumentation.db import PoolStatsLike, register_pool_observer
from llamatrade_telemetry.instrumentation.http import TelemetryMiddleware
from llamatrade_telemetry.logging import configure_logging, get_logger
from llamatrade_telemetry.registry import configure_metrics, get_metrics
from llamatrade_telemetry.tracing import configure_tracing

logger = get_logger(__name__)


async def _metrics_endpoint(request: Request) -> Response:
    return Response(content=get_metrics(), media_type="text/plain; charset=utf-8")


def _wire_app(app: Starlette, service: str) -> None:
    # Idempotent: some services call both setup_observability and
    # enable_db_pool_metrics, which both route here.
    already = any(getattr(m, "cls", None) is TelemetryMiddleware for m in app.user_middleware)
    if not already:
        app.add_middleware(TelemetryMiddleware, service_name=service)
    has_metrics = any(getattr(route, "path", None) == "/metrics" for route in app.routes)
    if not has_metrics:
        app.add_route("/metrics", _metrics_endpoint, methods=["GET"], include_in_schema=False)


def init_telemetry(
    app: Starlette | None = None,
    *,
    service: str,
    version: str = "0.0.0",
    pool_stats_provider: Callable[[], PoolStatsLike | None] | None = None,
    settings: TelemetrySettings | None = None,
) -> None:
    """Initialise telemetry for a service or worker.

    Args:
        app: the FastAPI/Starlette app to instrument (omit for workers).
        service: service name → ``service.name`` resource attribute + span tag.
        version: service version → ``service.version``.
        pool_stats_provider: pass ``llamatrade_db.get_pool_stats`` to export
            connection-pool gauges.
        settings: override env-derived settings (mainly for tests).
    """
    resolved = settings or load_settings()
    resource = Resource.create(
        {
            "service.name": service,
            "service.version": version or resolved.service_version or "0.0.0",
            "deployment.environment": resolved.environment,
        }
    )

    configure_logging(service, resolved.log_level, resolved.json_logs)
    configure_metrics(resource, enabled=resolved.metrics_enabled)
    configure_tracing(resource, resolved)

    if pool_stats_provider is not None:
        register_pool_observer(pool_stats_provider)

    if app is not None:
        _wire_app(app, service)

    logger.info(
        "telemetry initialised: service=%s version=%s env=%s traces=%s",
        service,
        version,
        resolved.environment,
        resolved.export_traces,
    )


def shutdown() -> None:
    """Flush exporters on process shutdown (call from a lifespan handler)."""
    tracing.shutdown()
