"""Unified telemetry for LlamaTrade: metrics + structured logs + traces.

One call wires everything::

    from llamatrade_telemetry import init_telemetry, get_logger, metrics

    init_telemetry(app, service="trading", version="0.1.0")
    log = get_logger(__name__)
    metrics.trading.order_submitted(side="buy", type="market", status="accepted")

See ``.docs/telemetry.md`` for the full catalog and conventions.
"""

from __future__ import annotations

from llamatrade_telemetry import conventions
from llamatrade_telemetry.domain import metrics
from llamatrade_telemetry.logging import (
    LogContext,
    clear_request_context,
    configure_logging,
    get_logger,
    set_request_context,
)
from llamatrade_telemetry.registry import (
    Counter,
    Gauge,
    Histogram,
    UpDownCounter,
    counter,
    gauge,
    get_metrics,
    histogram,
    observable_gauge,
    up_down_counter,
)
from llamatrade_telemetry.setup import init_telemetry, shutdown
from llamatrade_telemetry.tracing import (
    extract_context,
    get_tracer,
    inject_context,
    span,
)

__all__ = [
    # setup
    "init_telemetry",
    "shutdown",
    # metrics
    "metrics",
    "get_metrics",
    "counter",
    "histogram",
    "gauge",
    "up_down_counter",
    "observable_gauge",
    "Counter",
    "Histogram",
    "Gauge",
    "UpDownCounter",
    # logging
    "get_logger",
    "configure_logging",
    "set_request_context",
    "clear_request_context",
    "LogContext",
    # tracing
    "span",
    "get_tracer",
    "inject_context",
    "extract_context",
    # conventions
    "conventions",
]
