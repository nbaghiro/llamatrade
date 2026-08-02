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
