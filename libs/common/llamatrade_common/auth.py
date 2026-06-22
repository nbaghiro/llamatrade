"""Shared authentication for LlamaTrade Connect/ASGI services.

A single mechanism, adopted platform-wide (see the planning doc
`.docs/planning/trading-hardening-plan.md` and memory `platform-connect-auth-gap`).

The pieces:

- ``TenantContext`` — the request-scoped, verified identity, held in a
  ``ContextVar`` so a servicer running in the same task can read it.
- ``AuthMiddleware`` — pure-ASGI middleware that verifies the inbound credential
  on every non-public request and stashes the ``TenantContext``. It accepts
  either a *user* access JWT or an internal *service* token, and is **fail-closed**
  (HTTP 401) otherwise. Pure ASGI (not ``BaseHTTPMiddleware``) so the ContextVar
  set here propagates to the downstream handler task.
- ``resolve_identity`` — turns the verified context plus the wire
  ``TenantContext`` into a trusted ``(tenant_id, user_id)``, rejecting
  cross-tenant requests.
- ``mint_service_token`` — issues the internal service JWT that inter-service
  gRPC clients attach so they pass the fail-closed edge. The grpc client
  interceptor that uses it lives in ``llamatrade_proto`` (it needs grpc); this
  module stays grpc-free.

Tokens are HS256 over ``JWT_SECRET`` (the same secret the auth service signs
with). User access tokens carry ``type=access`` + ``tenant_id``/``sub``; service
tokens carry ``type=service``.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field

_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")
_DEFAULT_SECRET = "dev-secret-change-in-production"
_DEFAULT_ALGORITHM = "HS256"
_SERVICE_SUBJECT = "llamatrade-service"

# ASGI scope/message aliases (kept loose — ASGI dicts are heterogeneous).
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class TenantContext(BaseModel):
    """Verified request identity (the in-process auth context).

    For a *user* token, ``tenant_id``/``user_id`` are the authoritative principal.
    For a *service* token, ``is_service`` is True and the principal is carried on
    the wire by the calling service (which already authenticated the user).
    """

    tenant_id: UUID
    user_id: UUID
    email: str = ""
    roles: list[str] = Field(default_factory=list)
    is_service: bool = False

    model_config = ConfigDict(frozen=True)


_context: ContextVar[TenantContext | None] = ContextVar("llamatrade_tenant_context", default=None)


def current_context() -> TenantContext | None:
    """Return the verified context for this request, or None if unauthenticated."""
    return _context.get()


def set_context(ctx: TenantContext | None) -> Token[TenantContext | None]:
    """Set the verified context; returns a token for ``reset_context``."""
    return _context.set(ctx)


def reset_context(token: Token[TenantContext | None]) -> None:
    """Restore the context to its prior value (use in a ``finally``)."""
    _context.reset(token)


class AuthError(Exception):
    """Auth/authorization failure with a transport-neutral code.

    ``code`` is one of ``unauthenticated`` | ``permission_denied`` |
    ``invalid_argument`` so each servicer can map it to its own error type
    (grpc StatusCode or connectrpc Code) without this module depending on either.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def mint_service_token(
    *,
    service_name: str = "internal",
    secret: str | None = None,
    algorithm: str = _DEFAULT_ALGORITHM,
    ttl_seconds: int = 300,
) -> str:
    """Mint an internal service JWT (``type=service``) for inter-service calls."""
    secret = secret or os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    now = int(time.time())
    payload = {
        "sub": _SERVICE_SUBJECT,
        "type": "service",
        "svc": service_name,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_credential(
    token: str,
    *,
    secret: str | None = None,
    algorithm: str = _DEFAULT_ALGORITHM,
) -> TenantContext | None:
    """Verify a bearer token and return its ``TenantContext``, or None if invalid.

    Accepts user access tokens (``type=access``) and internal service tokens
    (``type=service``). Refresh tokens and malformed/expired tokens return None.
    """
    secret = secret or os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.InvalidTokenError:
        return None

    token_type = payload.get("type", "access")
    if token_type == "service":
        return TenantContext(tenant_id=_NIL_UUID, user_id=_NIL_UUID, is_service=True)
    if token_type != "access":
        # Refresh (or any non-access) token cannot authenticate an API call.
        return None

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("sub")
    if not tenant_id or not user_id:
        return None
    try:
        return TenantContext(
            tenant_id=UUID(str(tenant_id)),
            user_id=UUID(str(user_id)),
            email=str(payload.get("email", "") or ""),
            roles=list(payload.get("roles", []) or []),
        )
    except ValueError, TypeError:
        return None


def resolve_identity(
    wire_tenant_id: str | None,
    wire_user_id: str | None,
) -> tuple[UUID, UUID]:
    """Trusted ``(tenant_id, user_id)`` for a servicer call.

    - **user** context → the token identity is authoritative; if the wire
      ``tenant_id`` is present and differs, reject (cross-tenant guard).
    - **service** context → trust the wire identity (the caller already
      authenticated the user and forwards the tenant).
    - **no** context → trust the wire identity. In production the fail-closed
      ``AuthMiddleware`` guarantees a context exists, so this branch is only hit
      by unit tests that call servicers directly.

    Raises ``AuthError`` on a missing/mismatched/invalid context.
    """
    ctx = _context.get()
    if ctx is not None and not ctx.is_service:
        if wire_tenant_id:
            try:
                wire_tid = UUID(str(wire_tenant_id))
            except (ValueError, TypeError, AttributeError) as e:
                raise AuthError("invalid_argument", f"invalid tenant_id in context: {e}") from e
            if wire_tid != ctx.tenant_id:
                raise AuthError(
                    "permission_denied",
                    "tenant_id in request does not match the authenticated principal",
                )
        return ctx.tenant_id, ctx.user_id

    # Service context, or no middleware (unit tests): trust the wire identity.
    if not wire_tenant_id or not wire_user_id:
        raise AuthError("unauthenticated", "valid tenant context is required")
    try:
        tenant_id = UUID(str(wire_tenant_id))
        user_id = UUID(str(wire_user_id))
    except (ValueError, TypeError, AttributeError) as e:
        raise AuthError("invalid_argument", f"invalid UUID in context: {e}") from e
    if tenant_id == _NIL_UUID or user_id == _NIL_UUID:
        raise AuthError(
            "unauthenticated", "valid tenant context is required (nil UUID not allowed)"
        )
    return tenant_id, user_id


class AuthMiddleware:
    """Pure-ASGI middleware: verify the inbound credential, set the context.

    Fail-closed for protected paths — a request with no valid user or service
    token gets a 401 before reaching the handler. Public paths (health, metrics,
    CORS preflight, and any configured RPC suffixes such as the auth service's
    ``/Login``) pass through untouched.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        jwt_secret: str | None = None,
        jwt_algorithm: str = _DEFAULT_ALGORITHM,
        public_paths: list[str] | None = None,
        public_suffixes: list[str] | None = None,
    ) -> None:
        self.app = app
        self._secret = jwt_secret or os.getenv("JWT_SECRET", _DEFAULT_SECRET)
        self._algorithm = jwt_algorithm
        self._public_paths = set(public_paths or ["/health", "/metrics", "/docs", "/openapi.json"])
        self._public_suffixes = tuple(public_suffixes or ())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        # CORS preflight carries no Authorization header; let it through.
        if method == "OPTIONS" or self._is_public(path):
            await self.app(scope, receive, send)
            return

        token = self._bearer_token(scope)
        ctx = (
            verify_credential(token, secret=self._secret, algorithm=self._algorithm)
            if token
            else None
        )
        if ctx is None:
            await self._reject(send)
            return

        reset = _context.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            _context.reset(reset)

    def _is_public(self, path: str) -> bool:
        if path in self._public_paths:
            return True
        return bool(self._public_suffixes) and path.endswith(self._public_suffixes)

    @staticmethod
    def _bearer_token(scope: Scope) -> str | None:
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                header = value.decode("latin-1").strip()
                if header.lower().startswith("bearer "):
                    return header[7:].strip()
                return header or None
        return None

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"code":"unauthenticated","message":"missing or invalid authentication token"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
