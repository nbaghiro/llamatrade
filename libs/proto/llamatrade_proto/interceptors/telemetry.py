"""Client-side telemetry interceptor: W3C trace propagation + metrics for ``grpc.aio``.

The client injects the current ``traceparent`` into outgoing metadata, opens a
CLIENT span, and records ``llamatrade_grpc_requests_total`` via the shared
telemetry recorder. There is no server-side interceptor: inbound extraction is
the HTTP middleware's job, since every service serves Connect under ASGI.

Unary-unary is wrapped (the dominant peer shape); streaming calls pass through.
"""

from __future__ import annotations

import grpc
import grpc.aio
from opentelemetry.trace import SpanKind, Status, StatusCode

from llamatrade_telemetry import get_tracer, inject_context
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
