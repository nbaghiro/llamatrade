"""Authentication interceptor for gRPC servers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import grpc
import grpc.aio

if TYPE_CHECKING:
    from llamatrade_grpc.clients.auth import AuthClient

logger = logging.getLogger(__name__)


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Server-side authentication interceptor.

    This interceptor validates JWT tokens on incoming requests and injects
    the tenant context into the request metadata.

    Example:
        from llamatrade_grpc import AuthClient, AuthInterceptor

        auth_client = AuthClient("auth:50051")
        interceptor = AuthInterceptor(
            auth_client,
            skip_methods=["/llamatrade.v1.AuthService/Login"]
        )

        server = grpc.aio.server(interceptors=[interceptor])
    """

    def __init__(
        self,
        auth_client: AuthClient,
        skip_methods: list[str] | None = None,
    ) -> None:
        """Initialize the interceptor.

        Args:
            auth_client: The AuthClient to use for token validation
            skip_methods: List of method names to skip authentication for
        """
        self._auth_client = auth_client
        self._skip_methods = set(skip_methods or [])

    async def intercept_service(
        self,
        continuation: Callable[[grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler | None]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        """Intercept incoming requests and validate authentication.

        Args:
            continuation: The next handler in the chain
            handler_call_details: Details about the incoming call

        Returns:
            The response from the continuation handler
        """
        method = handler_call_details.method

        # Skip authentication for whitelisted methods
        if method in self._skip_methods:
            return await continuation(handler_call_details)

        # Extract token from metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        auth_header = metadata.get("authorization", "")

        if not auth_header:
            logger.warning("Missing authorization header for method: %s", method)
            return self._unauthenticated_handler()

        # Extract bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = auth_header

        # Validate token
        result = await self._auth_client.validate_token(token)

        if not result.valid:
            logger.warning("Invalid token for method: %s", method)
            return self._unauthenticated_handler()

        # Token is valid, continue with the request
        # The tenant context is available in result.context
        logger.debug(
            "Authenticated request: method=%s, tenant=%s, user=%s",
            method,
            result.context.tenant_id if result.context else "unknown",
            result.context.user_id if result.context else "unknown",
        )

        return await continuation(handler_call_details)

    def _unauthenticated_handler(self) -> grpc.RpcMethodHandler:
        """Return a handler that always returns UNAUTHENTICATED."""

        async def _abort(request: object, context: grpc.aio.ServicerContext) -> None:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or missing authentication token",
            )

        return grpc.unary_unary_rpc_method_handler(_abort)


class ClientAuthInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Client-side interceptor that adds authentication token to requests.

    Example:
        token = "eyJ..."
        interceptor = ClientAuthInterceptor(token)
        channel = grpc.aio.insecure_channel(
            "localhost:50051",
            interceptors=[interceptor]
        )
    """

    def __init__(self, token: str | Callable[[], str]) -> None:
        """Initialize the interceptor.

        Args:
            token: The token string or a callable that returns the token
        """
        self._token = token

    async def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        """Add authentication header to outgoing requests."""
        token = self._token() if callable(self._token) else self._token

        # Add authorization metadata
        metadata = list(client_call_details.metadata or [])
        metadata.append(("authorization", f"Bearer {token}"))

        new_details = grpc.aio.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )

        return await continuation(new_details, request)
