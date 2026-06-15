"""HTTP/Connect RED middleware + standard request metrics.

A **pure ASGI** middleware (not ``BaseHTTPMiddleware``) so it never buffers the
response body — critical because several services serve long-lived streaming
RPCs (market-data bars, trading order/position updates, backtest progress).
Connect RPCs mount under ``/`` and pass through here too; their route label is
the bounded RPC path. Each request opens a SERVER span as a child of any inbound
``traceparent``.
"""

from __future__ import annotations

import uuid
from time import perf_counter

from opentelemetry import context as otel_context
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from llamatrade_telemetry import registry
from llamatrade_telemetry.logging import clear_request_context, get_logger, set_request_context
from llamatrade_telemetry.runtime import ensure_runtime_monitor
from llamatrade_telemetry.tracing import extract_context, get_tracer

logger = get_logger(__name__)

HTTP_REQUESTS_TOTAL = registry.counter(
    "llamatrade_http_requests_total",
    ["transport", "method", "route", "status_code", "status_class"],
    "Total inbound HTTP/Connect requests",
)
HTTP_REQUEST_DURATION = registry.histogram(
    "llamatrade_http_request_duration_seconds",
    ["transport", "method", "route"],
    "Inbound request duration",
)
HTTP_REQUESTS_IN_PROGRESS = registry.up_down_counter(
    "llamatrade_http_requests_in_progress",
    ["transport", "method", "route"],
    "Inbound requests currently being processed",
)


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}


# Operational endpoints excluded from RED metrics + spans: Prometheus scrapes
# `/metrics` every ~15s and k8s probes `/health` constantly — instrumenting them
# would swamp request-rate panels and trace volume with self-noise.
_SKIP_ROUTES = frozenset({"/metrics", "/health"})


def _transport(headers: dict[str, str], path: str) -> str:
    content_type = headers.get("content-type", "")
    if content_type.startswith("application/grpc"):
        return "grpc"
    if content_type.startswith("application/connect") or content_type.startswith(
        "application/proto"
    ):
        return "connect"
    # Connect unary also uses application/json on /Pkg.Service/Method paths.
    if path.count("/") == 2 and "." in path.split("/")[1]:
        return "connect"
    return "http"


class TelemetryMiddleware:
    """Pure-ASGI RED metrics + request context + SERVER span."""

    def __init__(self, app: ASGIApp, service_name: str = "llamatrade") -> None:
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ensure_runtime_monitor()

        path = scope.get("path", "")
        if path in _SKIP_ROUTES:
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        set_request_context(
            request_id=request_id,
            tenant_id=headers.get("x-tenant-id"),
            user_id=headers.get("x-user-id"),
        )

        method = scope.get("method", "GET")
        transport = _transport(headers, path)
        route = path  # Connect/REST paths here are bounded by the proto/routes.
        labels = {"transport": transport, "method": method, "route": route}

        HTTP_REQUESTS_IN_PROGRESS.labels(**labels).inc()
        start = perf_counter()
        status_code = 500
        is_streaming = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, is_streaming
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(raw=message.setdefault("headers", []))
                response_headers["X-Request-ID"] = request_id
                response_headers["X-Response-Time"] = f"{perf_counter() - start:.3f}s"
            elif message["type"] == "http.response.body" and message.get("more_body"):
                # Multi-chunk body => a streaming RPC. Its lifetime is unbounded,
                # so it must not pollute the unary latency histogram.
                is_streaming = True
            await send(message)

        parent = extract_context(headers)
        token = otel_context.attach(parent)
        tracer = get_tracer("llamatrade.http")
        try:
            with tracer.start_as_current_span(
                f"{transport.upper()} {route}", kind=SpanKind.SERVER
            ) as span_obj:
                span_obj.set_attribute("http.request.method", method)
                span_obj.set_attribute("url.path", path)
                span_obj.set_attribute("llamatrade.service", self.service_name)
                try:
                    await self.app(scope, receive, send_wrapper)
                    span_obj.set_attribute("http.response.status_code", status_code)
                    if status_code >= 500:
                        span_obj.set_status(Status(StatusCode.ERROR))
                except Exception as exc:
                    span_obj.record_exception(exc)
                    span_obj.set_status(Status(StatusCode.ERROR, str(exc)))
                    logger.exception("Unhandled exception in request: %s", exc)
                    raise
        finally:
            duration = perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(
                status_code=str(status_code),
                status_class=f"{status_code // 100}xx",
                **labels,
            ).inc()
            # Skip the unary latency histogram for streaming RPCs (full-stream
            # duration would otherwise land in +Inf and skew p99).
            if not is_streaming:
                HTTP_REQUEST_DURATION.labels(**labels).observe(duration)
            HTTP_REQUESTS_IN_PROGRESS.labels(**labels).dec()
            logger.info("HTTP %s %s %d %.3fs", method, path, status_code, duration)
            clear_request_context()
            otel_context.detach(token)
