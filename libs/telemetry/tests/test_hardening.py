"""Tests for production-hardening paths (Phase 1 review fixes)."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from llamatrade_telemetry import init_telemetry, registry, runtime, tracing
from llamatrade_telemetry.config import TelemetrySettings
from llamatrade_telemetry.logging import JSONFormatter, configure_logging
from llamatrade_telemetry.setup import _build_resource
from tests.conftest import scrape


# --------------------------------------------------------------------------- #
# Lenient vs strict labels (a mislabel must never crash a prod request)
# --------------------------------------------------------------------------- #
def test_strict_labels_raise() -> None:
    ctr = registry.counter("llamatrade_test_strict_total", ["result"], "x")
    with pytest.raises(registry.conventions.LabelError):
        ctr.labels(wrong="x")


def test_lenient_labels_drop_without_raising() -> None:
    ctr = registry.counter("llamatrade_test_lenient_total", ["result"], "x")
    original = registry._strict_labels
    registry._strict_labels = False
    try:
        # bad labels: dropped, no raise, no series created
        ctr.labels(wrong="x").inc()
        # good labels still record
        ctr.labels(result="ok").inc()
    finally:
        registry._strict_labels = original
    out = scrape()
    assert 'llamatrade_test_lenient_total{result="ok"} 1.0' in out
    assert "wrong=" not in out


def test_settings_strict_labels_by_environment() -> None:
    assert TelemetrySettings(ENVIRONMENT="development").strict_labels is True
    assert TelemetrySettings(ENVIRONMENT="production").strict_labels is False
    assert TelemetrySettings(ENVIRONMENT="staging").strict_labels is False
    assert (
        TelemetrySettings(ENVIRONMENT="production", TELEMETRY_STRICT_LABELS=True).strict_labels
        is True
    )


# --------------------------------------------------------------------------- #
# Invalid LOG_LEVEL must not crash startup
# --------------------------------------------------------------------------- #
def test_invalid_log_level_defaults_to_info() -> None:
    configure_logging("svc", "definitely-not-a-level", json_output=True)
    assert logging.getLogger().level == logging.INFO
    # restore a sane default for the rest of the session
    configure_logging("svc", "INFO", json_output=True)


def test_valid_log_level_applied() -> None:
    configure_logging("svc", "warning", json_output=True)
    assert logging.getLogger().level == logging.WARNING
    configure_logging("svc", "INFO", json_output=True)


# --------------------------------------------------------------------------- #
# Resource identity (git_sha + instance id on target_info)
# --------------------------------------------------------------------------- #
def test_build_resource_includes_git_sha_and_instance() -> None:
    resource = _build_resource("trading", "1.2.3", TelemetrySettings(GIT_SHA="abc123"))
    attrs = resource.attributes
    assert attrs["service.name"] == "trading"
    assert attrs["service.version"] == "1.2.3"
    assert attrs["service.git_sha"] == "abc123"
    assert attrs["service.instance.id"]


def test_build_resource_omits_git_sha_when_unset() -> None:
    resource = _build_resource("trading", "1.0.0", TelemetrySettings())
    assert "service.git_sha" not in resource.attributes


# --------------------------------------------------------------------------- #
# OTLP trace export wiring (the export branch was previously untested)
# --------------------------------------------------------------------------- #
def test_configure_tracing_wires_otlp_exporter() -> None:
    saved_provider, saved_configured = tracing._provider, tracing._configured
    tracing._provider, tracing._configured = None, False
    try:
        settings = TelemetrySettings(
            OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318",
            OTEL_TRACES_SAMPLER="always_on",
        )
        assert settings.export_traces is True
        tracing.configure_tracing(Resource.create({"service.name": "t"}), settings)
        assert tracing._provider is not None
        with tracing.span("exported"):
            pass
    finally:
        if tracing._provider is not None and tracing._provider is not saved_provider:
            tracing._provider.shutdown()
        tracing._provider, tracing._configured = saved_provider, saved_configured


# --------------------------------------------------------------------------- #
# Error responses mark the span ERROR (not just the 5xx counter)
# --------------------------------------------------------------------------- #
async def test_error_response_marks_span_error() -> None:
    exporter = InMemorySpanExporter()
    provider = tracing._provider
    assert provider is not None
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    app = FastAPI()

    @app.get("/explode")
    async def explode() -> dict[str, bool]:
        raise ValueError("boom")

    init_telemetry(app, service="err", version="0.0.0")
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        assert (await client.get("/explode")).status_code == 500

    server = [s for s in exporter.get_finished_spans() if s.name == "HTTP /explode"]
    assert server, "server span for /explode not captured"
    assert server[0].status.status_code == StatusCode.ERROR


# --------------------------------------------------------------------------- #
# Runtime monitor actually records a tick (loop body was untested)
# --------------------------------------------------------------------------- #
async def test_runtime_monitor_records_a_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime.stop_runtime_monitor()
    monkeypatch.setattr(runtime, "_MONITOR_INTERVAL_SECONDS", 0.01)
    runtime.ensure_runtime_monitor()
    await asyncio.sleep(0.05)
    runtime.stop_runtime_monitor()
    out = scrape()
    assert "llamatrade_runtime_event_loop_lag_seconds_count" in out
    assert "llamatrade_runtime_asyncio_tasks" in out


# --------------------------------------------------------------------------- #
# JSON log line carries trace ids during a request (formatter sanity)
# --------------------------------------------------------------------------- #
def test_json_formatter_emits_valid_json() -> None:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "hi %s", ("x",), None)
    parsed = json.loads(JSONFormatter("svc").format(rec))
    assert parsed["message"] == "hi x"
    assert parsed["service"] == "svc"
