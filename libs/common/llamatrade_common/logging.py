"""Back-compat shim → :mod:`llamatrade_telemetry.logging`.

Structured logging moved to the unified telemetry library. Import from
``llamatrade_telemetry`` in new code; this module re-exports for existing call
sites.
"""

from __future__ import annotations

from llamatrade_telemetry.logging import (
    JSONFormatter,
    LogContext,
    clear_request_context,
    configure_logging,
    get_logger,
    set_request_context,
)

__all__ = [
    "JSONFormatter",
    "LogContext",
    "clear_request_context",
    "configure_logging",
    "get_logger",
    "set_request_context",
]
