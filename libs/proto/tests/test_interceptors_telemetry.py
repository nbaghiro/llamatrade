"""End-to-end trace propagation + metrics for the gRPC telemetry interceptors.

A real in-process ``grpc.aio`` server with a generic byte-echo handler proves a
trace crosses the client→server boundary (no generated protobufs needed).
"""

from __future__ import annotations

from collections.abc import Iterator

import grpc
import grpc.aio
import pytest
from opentelemetry import trace

from llamatrade_proto.interceptors.telemetry import (
    TelemetryClientInterceptor,
    TelemetryServerInterceptor,
)
from llamatrade_telemetry import get_metrics, init_telemetry, registry, tracing
from llamatrade_telemetry.config import TelemetrySettings


@pytest.fixture(scope="module", autouse=True)
def _telemetry() -> Iterator[None]:
    registry.reset_for_testing()
    tracing.reset_for_testing()
    init_telemetry(
        service="proto-test",
        settings=TelemetrySettings(ENVIRONMENT="test", OTEL_TRACES_SAMPLER="always_on"),
    )
    yield


def _identity(value: bytes) -> bytes:
    return value


async def _serve(service: str, method: str, handler_fn):
    handler = grpc.unary_unary_rpc_method_handler(handler_fn)
    generic = grpc.method_handlers_generic_handler(service, {method: handler})
    server = grpc.aio.server(interceptors=[TelemetryServerInterceptor()])
    server.add_generic_rpc_handlers((generic,))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    return server, port


@pytest.mark.asyncio
async def test_trace_propagates_client_to_server() -> None:
    captured: dict[str, int] = {}

    async def echo(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        captured["trace_id"] = trace.get_current_span().get_span_context().trace_id
        return request

    server, port = await _serve("test.Svc", "Echo", echo)
    try:
        channel = grpc.aio.insecure_channel(
            f"127.0.0.1:{port}", interceptors=[TelemetryClientInterceptor()]
        )
        with tracing.span("client.root") as client_span:
            client_trace_id = client_span.get_span_context().trace_id
            call = channel.unary_unary(
                "/test.Svc/Echo", request_serializer=_identity, response_deserializer=_identity
            )
            response = await call(b"hello")
        await channel.close()
    finally:
        await server.stop(None)

    assert response == b"hello"
    assert captured["trace_id"] == client_trace_id


@pytest.mark.asyncio
async def test_grpc_metrics_recorded() -> None:
    async def ping(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        return request

    server, port = await _serve("metric.Svc", "Ping", ping)
    try:
        channel = grpc.aio.insecure_channel(
            f"127.0.0.1:{port}", interceptors=[TelemetryClientInterceptor()]
        )
        call = channel.unary_unary(
            "/metric.Svc/Ping", request_serializer=_identity, response_deserializer=_identity
        )
        await call(b"x")
        await channel.close()
    finally:
        await server.stop(None)

    assert (
        'llamatrade_grpc_requests_total{method="/metric.Svc/Ping",status="OK"}'
        in get_metrics().decode()
    )
