"""Trace propagation + metrics for the client-side gRPC telemetry interceptor.

A real in-process ``grpc.aio`` server with a generic byte-echo handler proves the
client injects W3C trace context onto the wire and records the request metric.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator

import grpc
import grpc.aio
import pytest

from llamatrade_proto.interceptors.telemetry import TelemetryClientInterceptor
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


async def _serve(
    service: str,
    method: str,
    handler_fn: Callable[[bytes, grpc.aio.ServicerContext], Awaitable[bytes]],
) -> tuple[grpc.aio.Server, int]:
    handler = grpc.unary_unary_rpc_method_handler(handler_fn)
    generic = grpc.method_handlers_generic_handler(service, {method: handler})
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((generic,))
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    return server, port


@pytest.mark.asyncio
async def test_client_injects_trace_context_onto_wire() -> None:
    captured: dict[str, str] = {}

    async def echo(request: bytes, context: grpc.aio.ServicerContext) -> bytes:
        for key, value in context.invocation_metadata() or ():
            captured[str(key)] = str(value)
        return request

    server, port = await _serve("test.Svc", "Echo", echo)
    try:
        channel = grpc.aio.insecure_channel(
            f"127.0.0.1:{port}", interceptors=[TelemetryClientInterceptor()]
        )
        with tracing.span("client.root"):
            call = channel.unary_unary(
                "/test.Svc/Echo", request_serializer=_identity, response_deserializer=_identity
            )
            response = await call(b"hello")
        await channel.close()
    finally:
        await server.stop(None)

    assert response == b"hello"
    assert "traceparent" in captured


@pytest.mark.asyncio
async def test_grpc_client_metric_recorded() -> None:
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
