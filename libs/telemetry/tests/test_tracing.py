from __future__ import annotations

import pytest

from llamatrade_telemetry import tracing
from llamatrade_telemetry.config import TelemetrySettings
from llamatrade_telemetry.tracing import _build_sampler


def test_span_reraises_and_records() -> None:
    with pytest.raises(ValueError):
        with tracing.span("boom", attributes={"tenant_id": "t1", "symbol": "AAPL"}):
            raise ValueError("nope")


def test_inject_extract_round_trip() -> None:
    carrier: dict[str, str] = {}
    with tracing.span("parent"):
        tracing.inject_context(carrier)
    assert "traceparent" in carrier
    ctx = tracing.extract_context(carrier)
    assert ctx is not None


def test_build_sampler_variants() -> None:
    always = _build_sampler(TelemetrySettings(OTEL_TRACES_SAMPLER="always_on"))
    parent = _build_sampler(
        TelemetrySettings(
            OTEL_TRACES_SAMPLER="parentbased_traceidratio", OTEL_TRACES_SAMPLER_ARG=0.5
        )
    )
    ratio = _build_sampler(TelemetrySettings(OTEL_TRACES_SAMPLER="traceidratio"))
    assert always.get_description()
    assert parent.get_description()
    assert ratio.get_description()


def test_export_traces_property() -> None:
    off = TelemetrySettings()
    assert off.export_traces is False
    on = TelemetrySettings(OTEL_EXPORTER_OTLP_ENDPOINT="http://collector:4318")
    assert on.export_traces is True


def test_get_tracer_returns_tracer() -> None:
    tracer = tracing.get_tracer("x")
    assert tracer is not None
