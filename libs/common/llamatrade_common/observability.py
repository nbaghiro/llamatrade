"""Observability middleware and utilities for FastAPI services.

This module provides a unified setup for logging, metrics, and tracing.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from llamatrade_common.logging import (
    clear_request_context,
    configure_logging,
    get_logger,
    set_request_context,
)
from llamatrade_common.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    get_metrics,
    init_service_info,
)

logger = get_logger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware that adds logging, metrics, and request tracing.

    Features:
    - Assigns request ID to each request
    - Records request/response metrics
    - Sets up logging context
    - Adds timing headers

    Example:
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            service_name="auth",
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        service_name: str = "llamatrade",
    ) -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request with observability instrumentation."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Extract tenant info from headers (set by gateway or middleware)
        tenant_id = request.headers.get("X-Tenant-ID")
        user_id = request.headers.get("X-User-ID")

        # Set logging context
        set_request_context(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Get normalized endpoint for metrics
        endpoint = self._get_endpoint(request)
        method = request.method

        # Track in-progress requests
        HTTP_REQUESTS_IN_PROGRESS.labels(
            service=self.service_name,
            method=method,
            endpoint=endpoint,
        ).inc()

        start_time = time.perf_counter()
        status_code = 500  # Default to error, will be overwritten on success

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.exception("Unhandled exception in request: %s", e)
            raise
        finally:
            # Record metrics
            duration = time.perf_counter() - start_time

            HTTP_REQUESTS_TOTAL.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            HTTP_REQUESTS_IN_PROGRESS.labels(
                service=self.service_name,
                method=method,
                endpoint=endpoint,
            ).dec()

            # Log request
            logger.info(
                "HTTP %s %s %d %.3fs",
                method,
                request.url.path,
                status_code,
                duration,
            )

            # Clear logging context
            clear_request_context()

        # Add headers to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response

    def _get_endpoint(self, request: Request) -> str:
        """Get normalized endpoint path for metrics.

        Replaces path parameters with placeholders to avoid
        high-cardinality metrics.
        """
        # Try to get the matched route
        if hasattr(request, "scope") and "route" in request.scope:
            route = request.scope["route"]
            if hasattr(route, "path"):
                return str(route.path)

        # Fallback to raw path (may have high cardinality)
        return str(request.url.path)


def setup_observability(
    app: FastAPI,
    service_name: str,
    version: str = "0.0.0",
    environment: str = "development",
    log_level: str = "INFO",
    json_logs: bool = True,
) -> None:
    """Set up full observability stack for a FastAPI app.

    This function:
    - Configures structured logging
    - Adds observability middleware
    - Adds /metrics endpoint
    - Initializes service info metric

    Args:
        app: FastAPI application
        service_name: Name of the service
        version: Service version
        environment: Deployment environment
        log_level: Log level
        json_logs: Whether to output JSON logs

    Example:
        app = FastAPI()
        setup_observability(
            app,
            service_name="auth",
            version="1.0.0",
            environment=os.getenv("ENVIRONMENT", "development"),
        )
    """
    # Configure logging
    configure_logging(
        service_name=service_name,
        level=log_level,
        json_output=json_logs,
    )

    # Initialize service info metric
    init_service_info(service_name, version, environment)

    # Add observability middleware
    app.add_middleware(
        ObservabilityMiddleware,
        service_name=service_name,
    )

    # Add metrics endpoint
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint."""
        return Response(
            content=get_metrics(),
            media_type="text/plain; charset=utf-8",
        )

    _ = metrics_endpoint  # Registered via decorator

    logger.info(
        "Observability configured: service=%s version=%s env=%s",
        service_name,
        version,
        environment,
    )
