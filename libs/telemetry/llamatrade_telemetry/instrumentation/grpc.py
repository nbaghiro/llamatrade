"""gRPC metric instruments + recorder for native ``grpc.aio`` inter-service calls.

The client-side interceptor (``llamatrade_proto.interceptors.telemetry
.TelemetryClientInterceptor``) calls this recorder plus ``llamatrade_telemetry``'s
trace inject/extract helpers; there is no server-side interceptor. Connect RPCs
(mounted under ``/``) are captured by the HTTP middleware instead.
"""

from __future__ import annotations

from llamatrade_telemetry import registry

GRPC_REQUESTS_TOTAL = registry.counter(
    "llamatrade_grpc_requests_total",
    ["method", "status"],
    "Total gRPC requests",
)


def record_grpc_request(method: str, status: str) -> None:
    GRPC_REQUESTS_TOTAL.labels(method=method, status=status).inc()
