"""Base gRPC client with common functionality."""

from __future__ import annotations

import logging
from types import TracebackType

import grpc
import grpc.aio

logger = logging.getLogger(__name__)


class BaseGRPCClient:
    """Base class for gRPC clients with connection management."""

    def __init__(
        self,
        target: str,
        *,
        secure: bool = False,
        credentials: grpc.ChannelCredentials | None = None,
        interceptors: list[grpc.aio.ClientInterceptor] | None = None,
        options: list[tuple[str, str | int | bool]] | None = None,
    ) -> None:
        """Initialize the gRPC client.

        Args:
            target: The target address (e.g., "localhost:8810")
            secure: Whether to use TLS
            credentials: Optional channel credentials for secure connections
            interceptors: Optional list of client interceptors
            options: Optional channel options
        """
        self._target = target
        self._secure = secure
        self._credentials = credentials
        self._interceptors = interceptors or []
        self._options = options or [
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50MB
        ]
        self._channel: grpc.aio.Channel | None = None

    @property
    def channel(self) -> grpc.aio.Channel:
        """Get or create the gRPC channel."""
        if self._channel is None:
            self._channel = self._create_channel()
        return self._channel

    def _create_channel(self) -> grpc.aio.Channel:
        """Create a new gRPC channel."""
        if self._secure:
            credentials = self._credentials or grpc.ssl_channel_credentials()
            channel = grpc.aio.secure_channel(
                self._target,
                credentials,
                options=self._options,
                interceptors=self._interceptors,
            )
        else:
            channel = grpc.aio.insecure_channel(
                self._target,
                options=self._options,
                interceptors=self._interceptors,
            )
        logger.debug("Created gRPC channel to %s (secure=%s)", self._target, self._secure)
        return channel

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            logger.debug("Closed gRPC channel to %s", self._target)

    async def __aenter__(self) -> BaseGRPCClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def wait_for_ready(self, timeout: float = 10.0) -> bool:
        """Wait for the channel to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if the channel is ready, False if timeout
        """
        try:
            await self.channel.channel_ready()
            return True
        except grpc.aio.AioRpcError:
            return False
