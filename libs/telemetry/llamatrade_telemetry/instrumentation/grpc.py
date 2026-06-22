"""gRPC metric instruments + recorders for native ``grpc.aio`` inter-service calls.

The actual ``grpc.aio`` interceptors live in ``llamatrade_proto.interceptors.telemetry``
(next to the other interceptors, where the server/client chains are wired); they
call these recorders plus ``llamatrade_telemetry``'s trace inject/extract helpers.
Connect RPCs (mounted under ``/``) are captured by the HTTP middleware instead.
"""

from __future__ import annotations

from llamatrade_telemetry import registry

GRPC_REQUESTS_TOTAL = registry.counter(
    "llamatrade_grpc_requests_total",
    ["method", "status"],
    "Total gRPC requests",
)
GRPC_STREAM_ACTIVE = registry.up_down_counter(
    "llamatrade_grpc_stream_active",
    ["method"],
    "Active server-streaming RPCs",
)
GRPC_STREAM_MESSAGES_TOTAL = registry.counter(
    "llamatrade_grpc_stream_messages_total",
    ["method", "direction"],
    "Messages sent/received over streaming RPCs",
)
GRPC_STREAM_DURATION = registry.histogram(
    "llamatrade_grpc_stream_duration_seconds",
    ["method"],
    "Streaming RPC lifetime",
)


def record_grpc_request(method: str, status: str) -> None:
    GRPC_REQUESTS_TOTAL.labels(method=method, status=status).inc()


def record_stream_message(method: str, direction: str) -> None:
    GRPC_STREAM_MESSAGES_TOTAL.labels(method=method, direction=direction).inc()
