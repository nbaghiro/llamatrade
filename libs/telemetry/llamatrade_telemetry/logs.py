"""OTLP log export: the structured record for the log backend.

stdout carries whatever ``LOG_FORMAT`` renders (a console line locally, Cloud
Logging JSON in GKE); this pipeline carries the same records to the collector,
which forwards them to Loki. That is what lets the console stay readable
without giving up field queries or the trace-to-logs pivot in Grafana.

Export is off unless an OTLP endpoint is configured, so local runs and tests
need no setup.
"""

from __future__ import annotations

import logging

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from llamatrade_telemetry.config import TelemetrySettings
from llamatrade_telemetry.logging import ContextFilter, resolve_level

_provider: LoggerProvider | None = None
_handler: LoggingHandler | None = None


class _ExcludeExporterLogs(logging.Filter):
    """Keep the exporter's own failures out of the pipeline they would retry into.

    Without this, one unreachable collector turns every export error into a
    record that is itself queued for export, and the failure feeds itself.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry.exporter")


def configure_log_export(resource: Resource, settings: TelemetrySettings) -> None:
    """Attach an OTLP log handler to the root logger. Idempotent."""
    global _provider, _handler
    if not settings.export_logs or settings.otlp_endpoint is None:
        return

    root = logging.getLogger()
    if _handler is not None:
        # configure_logging clears root handlers, so a re-init drops ours; the
        # provider is still live, so re-attach rather than build a second one.
        if _handler not in root.handlers:
            root.addHandler(_handler)
        return

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{settings.otlp_endpoint.rstrip('/')}/v1/logs")
        )
    )
    handler = LoggingHandler(level=resolve_level(settings.log_level), logger_provider=provider)
    handler.addFilter(ContextFilter())
    handler.addFilter(_ExcludeExporterLogs())
    root.addHandler(handler)
    _provider = provider
    _handler = handler


def shutdown() -> None:
    """Flush and detach the log pipeline (called from ``telemetry.shutdown``)."""
    global _provider, _handler
    if _handler is not None:
        logging.getLogger().removeHandler(_handler)
        _handler = None
    if _provider is not None:
        _provider.shutdown()
        _provider = None
