"""Authentication interceptor for gRPC servers."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import grpc
import grpc.aio

if TYPE_CHECKING:
    from llamatrade_proto.clients.auth import AuthClient

logger = logging.getLogger(__name__)


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Server-side authentication interceptor.

    This interceptor validates JWT tokens on incoming requests and injects
    the tenant context into the request metadata.

    Example:
        from llamatrade_proto.clients import AuthClient
        from llamatrade_proto.interceptors import AuthInterceptor

        auth_client = AuthClient("auth:8810")
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
            "localhost:8810",
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


class _ServiceTokenCache:
    """Caches a minted service token until shortly before it expires."""

    def __init__(self, ttl_seconds: int = 300, refresh_margin: int = 60) -> None:
        self._ttl = ttl_seconds
        self._margin = refresh_margin
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get(self) -> str:
        now = time.time()
        if self._token is None or now >= self._expires_at - self._margin:
            # Lazy import: keeps llamatrade_proto free of a hard llamatrade_common
            # dependency; the helper is always present in a running service.
            from llamatrade_common.auth import mint_service_token

            self._token = mint_service_token(
                service_name=os.getenv("SERVICE_NAME", "internal"),
                ttl_seconds=self._ttl,
            )
            self._expires_at = now + self._ttl
        return self._token


def _with_authorization(
    details: grpc.aio.ClientCallDetails, token: str
) -> grpc.aio.ClientCallDetails:
    """Return call details with an Authorization header, preserving an existing one."""
    metadata = list(details.metadata or [])
    if any(str(key).lower() == "authorization" for key, _ in metadata):
        # A caller-set token (e.g. a forwarded user token) wins.
        return details
    metadata.append(("authorization", f"Bearer {token}"))
    return grpc.aio.ClientCallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=metadata,
        credentials=details.credentials,
        wait_for_ready=details.wait_for_ready,
    )


class ServiceAuthClientInterceptor(
    grpc.aio.UnaryUnaryClientInterceptor,
    grpc.aio.UnaryStreamClientInterceptor,
    grpc.aio.StreamUnaryClientInterceptor,
    grpc.aio.StreamStreamClientInterceptor,
):
    """Attach an internal service JWT to every outgoing inter-service call.

    Lets service-to-service gRPC calls pass the fail-closed ``AuthMiddleware`` at
    the callee (they carry no user token). Does not override an Authorization
    header a caller set explicitly, so a forwarded user token still wins.
    """

    def __init__(self, token_provider: Callable[[], str] | None = None) -> None:
        self._token_provider = token_provider or _ServiceTokenCache().get

    async def intercept_unary_unary(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        return await continuation(
            _with_authorization(client_call_details, self._token_provider()), request
        )

    async def intercept_unary_stream(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request: object,
    ) -> object:
        return await continuation(
            _with_authorization(client_call_details, self._token_provider()), request
        )

    async def intercept_stream_unary(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: object,
    ) -> object:
        return await continuation(
            _with_authorization(client_call_details, self._token_provider()), request_iterator
        )

    async def intercept_stream_stream(
        self,
        continuation: Callable[[grpc.aio.ClientCallDetails, object], Awaitable[object]],
        client_call_details: grpc.aio.ClientCallDetails,
        request_iterator: object,
    ) -> object:
        return await continuation(
            _with_authorization(client_call_details, self._token_provider()), request_iterator
        )
