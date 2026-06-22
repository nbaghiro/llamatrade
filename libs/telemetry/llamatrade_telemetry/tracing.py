"""Distributed tracing: provider, W3C propagation, and span helpers.

Traces export via OTLP/HTTP when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set; with no
endpoint the provider still records spans (so ``trace_id`` shows up in logs) but
exports nothing — zero-config for dev and tests.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ParentBased,
    Sampler,
    TraceIdRatioBased,
)
from opentelemetry.trace import SpanKind, Status, StatusCode

from llamatrade_telemetry.config import TelemetrySettings

_provider: TracerProvider | None = None
_configured = False
_global_tracer_set = False


def _build_sampler(settings: TelemetrySettings) -> Sampler:
    if settings.traces_sampler == "always_on":
        return ALWAYS_ON
    ratio = TraceIdRatioBased(settings.traces_sampler_arg)
    if settings.traces_sampler.startswith("parentbased"):
        return ParentBased(root=ratio)
    return ratio


def configure_tracing(resource: Resource, settings: TelemetrySettings) -> None:
    """Build the TracerProvider and (optionally) an OTLP exporter. Idempotent."""
    global _provider, _configured, _global_tracer_set
    if _configured:
        return
    provider = TracerProvider(resource=resource, sampler=_build_sampler(settings))
    if settings.export_traces and settings.otlp_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    _provider = provider
    if not _global_tracer_set:
        trace.set_tracer_provider(provider)
        _global_tracer_set = True
    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    """Return a tracer; falls back to the global (possibly no-op) provider."""
    if _provider is not None:
        return _provider.get_tracer(name)
    return trace.get_tracer(name)


def shutdown() -> None:
    """Flush and stop span processors (call on process shutdown)."""
    if _provider is not None:
        _provider.shutdown()


def reset_for_testing() -> None:
    """Tear down the tracer provider for test isolation."""
    global _provider, _configured
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    _configured = False


@contextmanager
def span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> Iterator[trace.Span]:
    """Start a span; records exceptions and sets ERROR status on raise.

    High-cardinality attributes (tenant_id, symbol, ids) are fine here — that is
    exactly what traces are for.
    """
    tracer = get_tracer("llamatrade")
    with tracer.start_as_current_span(name, kind=kind) as current:
        if attributes:
            for key, value in attributes.items():
                current.set_attribute(key, value)
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def inject_context(carrier: MutableMapping[str, str]) -> None:
    """Inject the current trace context (W3C ``traceparent``) into ``carrier``.

    Use when calling a downstream service or publishing to the EventBus.
    """
    inject(carrier)


def extract_context(carrier: Mapping[str, str]) -> Context:
    """Extract a trace context from inbound headers / stream metadata."""
    return extract(carrier)
