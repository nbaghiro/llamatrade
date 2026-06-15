"""gRPC metrics for native HTTP/2 inter-service calls.

Connect RPCs (mounted under ``/``) are already captured by the HTTP middleware;
these instruments cover server/client interceptors for raw ``grpcio`` paths and
streaming RPCs when those are wired.
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
