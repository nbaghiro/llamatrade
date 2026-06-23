"""Telemetry interceptors: W3C trace propagation + metrics for ``grpc.aio`` calls.

These close the cross-service tracing gap for native gRPC peer calls (Connect
RPCs are handled by the HTTP middleware). The client injects the current
``traceparent`` into outgoing metadata and opens a CLIENT span; the server
extracts it and opens a SERVER span as its child — so a single trace follows a
request across the ``signal → order → fill → ledger`` path. Both record
``llamatrade_grpc_requests_total`` via the shared telemetry recorder.

Unary-unary is wrapped (the dominant peer shape); streaming handlers pass through.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import grpc
import grpc.aio
from opentelemetry import context as _otel_context
from opentelemetry.trace import SpanKind, Status, StatusCode

from llamatrade_telemetry import extract_context, get_tracer, inject_context
from llamatrade_telemetry.instrumentation.grpc import record_grpc_request


def _method_str(method: object) -> str:
    return method.decode() if isinstance(method, bytes) else str(method)


class TelemetryClientInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Inject trace context + record metrics on outgoing unary gRPC calls."""

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        method = _method_str(client_call_details.method)
        tracer = get_tracer("llamatrade.grpc.client")
        with tracer.start_as_current_span(f"GRPC {method}", kind=SpanKind.CLIENT) as span:
            carrier: dict[str, str] = {}
            inject_context(carrier)
            metadata = list(client_call_details.metadata or [])
            metadata.extend(carrier.items())
            details = grpc.aio.ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=grpc.aio.Metadata(*metadata),
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
            )
            call = await continuation(details, request)
            code = await call.code()
            record_grpc_request(method, code.name)
            if code is not grpc.StatusCode.OK:
                span.set_status(Status(StatusCode.ERROR))
            return call


class TelemetryServerInterceptor(grpc.aio.ServerInterceptor):
    """Extract trace context + record metrics on incoming unary gRPC calls."""

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler | None]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        handler = await continuation(handler_call_details)
        behavior = getattr(handler, "unary_unary", None)
        if handler is None or behavior is None:
            return handler  # streaming / unknown handler — pass through

        method = _method_str(handler_call_details.method)
        carrier = {
            _method_str(k): _method_str(v)
            for k, v in (handler_call_details.invocation_metadata or [])
        }
        parent = extract_context(carrier)

        async def traced(request, context):
            token = _otel_context.attach(parent)
            tracer = get_tracer("llamatrade.grpc.server")
            try:
                with tracer.start_as_current_span(f"GRPC {method}", kind=SpanKind.SERVER) as span:
                    try:
                        response = await behavior(request, context)
                        record_grpc_request(method, "OK")
                        return response
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        record_grpc_request(method, "ERROR")
                        raise
            finally:
                _otel_context.detach(token)

        return grpc.unary_unary_rpc_method_handler(
            traced,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
