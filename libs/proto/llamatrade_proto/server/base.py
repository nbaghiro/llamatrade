"""Base gRPC server utilities."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import grpc.aio

logger = logging.getLogger(__name__)


class GRPCServer:
    """Async gRPC server to run alongside FastAPI.

    This server manages the lifecycle of a gRPC server, supporting
    interceptors, servicer registration, and graceful shutdown.

    Example:
        from llamatrade_proto.server import GRPCServer
        from llamatrade_proto.interceptors import LoggingInterceptor
        from llamatrade_proto.generated import market_data_pb2_grpc
        from src.grpc.servicer import MarketDataServicer

        # Create server
        grpc_server = GRPCServer(
            port=8840,
            interceptors=[LoggingInterceptor()],
        )

        # Register servicer
        servicer = MarketDataServicer()
        grpc_server.add_servicer(
            lambda s: market_data_pb2_grpc.add_MarketDataServiceServicer_to_server(servicer, s)
        )

        # Start in lifespan
        await grpc_server.start()

        yield  # FastAPI lifespan

        await grpc_server.stop()
    """

    def __init__(
        self,
        port: int,
        *,
        host: str = "0.0.0.0",
        interceptors: list[grpc.aio.ServerInterceptor] | None = None,
        options: list[tuple[str, int]] | None = None,
    ) -> None:
        """Initialize the gRPC server.

        Args:
            port: The port to listen on
            host: The host address (default: 0.0.0.0 for all IPv4 interfaces)
            interceptors: Optional list of server interceptors
            options: Optional channel options
        """
        self._port = port
        self._host = host
        self._interceptors = interceptors or []
        self._options = options or [
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
        ]
        self._server: grpc.aio.Server | None = None
        self._servicer_registrations: list[Callable[[grpc.aio.Server], None]] = []

    @property
    def port(self) -> int:
        """Get the server port."""
        return self._port

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None

    def add_servicer(
        self,
        register_fn: Callable[[grpc.aio.Server], None],
    ) -> None:
        """Register a servicer to be added on start.

        The register_fn should call the generated add_*Servicer_to_server function.

        Args:
            register_fn: A function that takes a server and registers a servicer

        Example:
            server.add_servicer(
                lambda s: auth_pb2_grpc.add_AuthServiceServicer_to_server(
                    AuthServicer(), s
                )
            )
        """
        self._servicer_registrations.append(register_fn)

    async def start(self) -> None:
        """Start the gRPC server.

        Creates the server, registers all servicers, and starts listening.
        """
        if self._server is not None:
            logger.warning("gRPC server already running on port %d", self._port)
            return

        self._server = grpc.aio.server(
            interceptors=self._interceptors,
            options=self._options,
        )

        # Register all servicers
        for register_fn in self._servicer_registrations:
            register_fn(self._server)

        # Add listening port
        listen_addr = f"{self._host}:{self._port}"
        self._server.add_insecure_port(listen_addr)

        await self._server.start()
        logger.info("gRPC server started on port %d", self._port)

    async def start_secure(
        self,
        credentials: grpc.ServerCredentials,
    ) -> None:
        """Start the gRPC server with TLS.

        Args:
            credentials: Server credentials for TLS
        """
        if self._server is not None:
            logger.warning("gRPC server already running on port %d", self._port)
            return

        self._server = grpc.aio.server(
            interceptors=self._interceptors,
            options=self._options,
        )

        for register_fn in self._servicer_registrations:
            register_fn(self._server)

        listen_addr = f"{self._host}:{self._port}"
        self._server.add_secure_port(listen_addr, credentials)

        await self._server.start()
        logger.info("gRPC server (TLS) started on port %d", self._port)

    async def stop(self, grace: float = 5.0) -> None:
        """Stop the gRPC server gracefully.

        Args:
            grace: Grace period in seconds for pending RPCs to complete
        """
        if self._server is None:
            return

        await self._server.stop(grace)
        self._server = None
        logger.info("gRPC server stopped")

    async def wait_for_termination(self, timeout: float | None = None) -> None:
        """Block until the server terminates.

        Args:
            timeout: Maximum time to wait (None for infinite)
        """
        if self._server is None:
            return

        if timeout is not None:
            try:
                await asyncio.wait_for(
                    self._server.wait_for_termination(),
                    timeout=timeout,
                )
            except TimeoutError:
                logger.warning("gRPC server wait_for_termination timed out")
        else:
            await self._server.wait_for_termination()
