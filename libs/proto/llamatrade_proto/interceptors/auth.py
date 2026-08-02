"""Service-to-service authentication for outgoing gRPC client calls."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable

import grpc
import grpc.aio


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
