from __future__ import annotations

import logging

import pytest
from opentelemetry.sdk.resources import Resource

from llamatrade_telemetry import logs as log_export
from llamatrade_telemetry.config import TelemetrySettings


@pytest.fixture(autouse=True)
def _reset_export() -> object:
    log_export.shutdown()
    yield
    log_export.shutdown()


def _resource() -> Resource:
    return Resource.create({"service.name": "svc"})


def test_export_is_off_without_an_endpoint() -> None:
    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT=None)
    assert settings.export_logs is False
    log_export.configure_log_export(_resource(), settings)
    assert log_export._provider is None


def test_export_is_off_when_disabled() -> None:
    settings = TelemetrySettings(
        OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318",
        TELEMETRY_LOGS_ENABLED=False,
    )
    assert settings.export_logs is False
    log_export.configure_log_export(_resource(), settings)
    assert log_export._provider is None


def test_export_attaches_a_root_handler_when_configured() -> None:
    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    assert settings.export_logs is True
    before = len(logging.getLogger().handlers)
    log_export.configure_log_export(_resource(), settings)
    assert log_export._provider is not None
    assert len(logging.getLogger().handlers) == before + 1


def test_export_is_idempotent() -> None:
    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    log_export.configure_log_export(_resource(), settings)
    handlers = len(logging.getLogger().handlers)
    log_export.configure_log_export(_resource(), settings)
    assert len(logging.getLogger().handlers) == handlers


def test_reattaches_after_configure_logging_clears_root_handlers() -> None:
    """init_telemetry runs configure_logging first, which wipes root handlers."""
    from llamatrade_telemetry.logging import configure_logging

    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    log_export.configure_log_export(_resource(), settings)
    attached = log_export._handler
    assert attached is not None

    configure_logging("svc", "INFO", fmt="json")
    assert attached not in logging.getLogger().handlers

    log_export.configure_log_export(_resource(), settings)
    assert attached in logging.getLogger().handlers
    assert log_export._handler is attached


def test_exporter_failures_are_kept_off_their_own_pipeline() -> None:
    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    log_export.configure_log_export(_resource(), settings)
    handler = log_export._handler
    assert handler is not None

    exporter_record = logging.LogRecord(
        "opentelemetry.exporter.otlp.proto.http._log_exporter",
        logging.ERROR,
        __file__,
        1,
        "Failed to export logs batch",
        None,
        None,
    )
    app_record = logging.LogRecord("src.runner", logging.ERROR, __file__, 1, "real", None, None)
    assert all(f.filter(exporter_record) for f in handler.filters) is False
    assert all(f.filter(app_record) for f in handler.filters) is True


def test_shutdown_detaches_the_handler() -> None:
    settings = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    before = len(logging.getLogger().handlers)
    log_export.configure_log_export(_resource(), settings)
    log_export.shutdown()
    assert log_export._provider is None
    assert len(logging.getLogger().handlers) == before
