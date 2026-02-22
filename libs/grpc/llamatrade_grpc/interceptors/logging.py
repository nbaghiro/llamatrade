"""Logging interceptor for gRPC calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import grpc
import grpc.aio

logger = logging.getLogger(__name__)


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    """Server-side logging interceptor.

    Logs all incoming gRPC requests with timing information and error details.

    Example:
        interceptor = LoggingInterceptor(log_level=logging.INFO)
        server = grpc.aio.server(interceptors=[interceptor])
    """

    def __init__(
        self,
        log_level: int = logging.DEBUG,
        log_request_metadata: bool = False,
    ) -> None:
        """Initialize the interceptor.

        Args:
            log_level: The logging level to use
            log_request_metadata: Whether to log request metadata
        """
        self._log_level = log_level
        self._log_request_metadata = log_request_metadata

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Any],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Any:
        """Intercept and log incoming requests.

        Args:
            continuation: The next handler in the chain
            handler_call_details: Details about the incoming call

        Returns:
            The response from the continuation handler
        """
        method = handler_call_details.method
        start_time = time.perf_counter()

        # Log request
        log_msg = f"gRPC request: {method}"
        if self._log_request_metadata:
            metadata = dict(handler_call_details.invocation_metadata or [])
            # Filter sensitive headers
            safe_metadata = {
                k: v if k.lower() not in ("authorization", "x-api-key") else "[REDACTED]"
                for k, v in metadata.items()
            }
            log_msg += f" metadata={safe_metadata}"

        logger.log(self._log_level, log_msg)

        try:
            response = await continuation(handler_call_details)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.log(
                self._log_level,
                "gRPC response: %s status=OK duration=%.2fms",
                method,
                duration_ms,
            )

            return response

        except grpc.aio.AioRpcError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.warning(
                "gRPC error: %s status=%s details=%s duration=%.2fms",
                method,
                e.code().name,
                e.details(),
                duration_ms,
            )
            raise

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "gRPC exception: %s error=%s duration=%.2fms",
                method,
                str(e),
                duration_ms,
                exc_info=True,
            )
            raise


class ClientLoggingInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Client-side logging interceptor.

    Logs all outgoing gRPC requests with timing information.

    Example:
        interceptor = ClientLoggingInterceptor()
        channel = grpc.aio.insecure_channel(
            "localhost:50051",
            interceptors=[interceptor]
        )
    """

    def __init__(self, log_level: int = logging.DEBUG) -> None:
        """Initialize the interceptor.

        Args:
            log_level: The logging level to use
        """
        self._log_level = log_level

    async def intercept_unary_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: Any,
    ) -> Any:
        """Log outgoing requests and responses."""
        method = client_call_details.method
        start_time = time.perf_counter()

        logger.log(self._log_level, "gRPC client call: %s", method)

        try:
            response = await continuation(client_call_details, request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.log(
                self._log_level,
                "gRPC client response: %s status=OK duration=%.2fms",
                method,
                duration_ms,
            )

            return response

        except grpc.aio.AioRpcError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.warning(
                "gRPC client error: %s status=%s details=%s duration=%.2fms",
                method,
                e.code().name,
                e.details(),
                duration_ms,
            )
            raise
