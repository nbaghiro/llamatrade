"""Client-side logging interceptor for gRPC calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

import grpc
import grpc.aio

logger = logging.getLogger(__name__)


class ClientLoggingInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Client-side logging interceptor.

    Logs all outgoing gRPC requests with timing information.

    Example:
        interceptor = ClientLoggingInterceptor()
        channel = grpc.aio.insecure_channel(
            "localhost:8810",
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
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
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
