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

Token signing:

- **User tokens** (``type=access``/``refresh`` + ``tenant_id``/``sub``, minted
  only by the auth service) are RS256 over the ``AUTH_JWT_PRIVATE_KEY`` /
  ``AUTH_JWT_PUBLIC_KEY`` PEM pair when configured — required in
  production/staging, where the auth service fails closed at startup — and fall
  back to HS256 over ``JWT_SECRET`` for zero-config dev/test.
- **Service tokens** (``mint_service_token``; ``type=service`` + ``svc`` +
  ``aud=llamatrade-internal``) stay HS256 over ``JWT_SECRET``: every service
  mints them locally for short-lived S2S calls, so they need the shared secret,
  not the auth service's private key.

Verification pins the algorithm to the configured key material, never to the
token header: with a public key configured, user tokens are accepted only as
RS256 and HS256 is reserved for service tokens (``type`` + ``aud`` checked), so
a service token can never authenticate as a user or vice versa, and
alg-confusion (an HS256 token where RS256 is pinned, or the public key replayed
as an HMAC secret) fails.
"""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable, Collection, Mapping, MutableMapping
from contextvars import ContextVar, Token
from typing import Any
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from llamatrade_common.revocation import RevocationStore
from llamatrade_common.utils import is_production_environment, require_secret
from llamatrade_telemetry import metrics

_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")
_DEFAULT_SECRET = "dev-secret-change-in-production"
_DEFAULT_ALGORITHM = "HS256"
_ASYMMETRIC_ALGORITHM = "RS256"
_SERVICE_SUBJECT = "llamatrade-service"
SERVICE_AUDIENCE = "llamatrade-internal"

# ASGI scope/message aliases (kept loose — ASGI dicts are heterogeneous).
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class TenantContext(BaseModel):
    """Verified request identity (the in-process auth context).

    For a *user* token, ``tenant_id``/``user_id`` are the authoritative principal.
    For a *service* token, ``is_service`` is True, ``svc`` names the minting
    service, and the principal is carried on the wire by the calling service
    (which already authenticated the user).
    """

    tenant_id: UUID
    user_id: UUID
    email: str = ""
    roles: list[str] = Field(default_factory=list)
    is_service: bool = False
    svc: str = ""

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


def user_token_signing_key() -> tuple[str, str]:
    """``(key, algorithm)`` the auth service signs user tokens with.

    RS256 over ``AUTH_JWT_PRIVATE_KEY`` when the PEM pair is configured, HS256
    over ``JWT_SECRET`` otherwise. Production/staging refuse to run without the
    pair, and a half-configured pair is always an error (fail closed).
    """
    private_pem = os.environ.get("AUTH_JWT_PRIVATE_KEY")
    public_pem = os.environ.get("AUTH_JWT_PUBLIC_KEY")
    if bool(private_pem) != bool(public_pem):
        raise RuntimeError(
            "AUTH_JWT_PRIVATE_KEY and AUTH_JWT_PUBLIC_KEY must be configured together"
        )
    if not private_pem and is_production_environment():
        raise RuntimeError(
            "AUTH_JWT_PRIVATE_KEY/AUTH_JWT_PUBLIC_KEY must be set in production/staging; "
            "user tokens must be asymmetrically signed"
        )
    if private_pem:
        return private_pem, _ASYMMETRIC_ALGORITHM
    return require_secret("JWT_SECRET", _DEFAULT_SECRET), _DEFAULT_ALGORITHM


def user_token_verification_key() -> tuple[str, str]:
    """``(key, algorithm)`` for verifying user tokens: the RS256 public key when
    configured, else the shared HS256 secret."""
    public_pem = os.environ.get("AUTH_JWT_PUBLIC_KEY")
    if public_pem:
        return public_pem, _ASYMMETRIC_ALGORITHM
    return require_secret("JWT_SECRET", _DEFAULT_SECRET), _DEFAULT_ALGORITHM


def mint_service_token(
    *,
    service_name: str = "internal",
    secret: str | None = None,
    algorithm: str = _DEFAULT_ALGORITHM,
    ttl_seconds: int = 300,
) -> str:
    """Mint an internal service JWT (``type=service``) for inter-service calls."""
    secret = secret or require_secret("JWT_SECRET", _DEFAULT_SECRET)
    now = int(time.time())
    payload = {
        "sub": _SERVICE_SUBJECT,
        "type": "service",
        "svc": service_name,
        "aud": SERVICE_AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def _decode(token: str, key: str, algorithm: str) -> dict[str, object] | None:
    """``jwt.decode`` pinned to one algorithm; ``aud`` is matrix-checked by the caller."""
    try:
        claims: dict[str, object] = jwt.decode(
            token, key, algorithms=[algorithm], options={"verify_aud": False}
        )
    except jwt.PyJWTError:
        return None
    return claims


def _acceptable_user_claims(claims: Mapping[str, object]) -> bool:
    """A user token is never service-typed and never carries the internal audience."""
    return claims.get("type") != "service" and claims.get("aud") != SERVICE_AUDIENCE


def decode_token_claims(
    token: str,
    *,
    secret: str | None = None,
    algorithm: str | None = None,
    public_key: str | None = None,
) -> dict[str, object] | None:
    """Verified claims of a bearer token (user or internal service), or None.

    The acceptable algorithm is pinned by the configured key material, never by
    the token header. With a public key (``public_key`` param or
    ``AUTH_JWT_PUBLIC_KEY``), user tokens must be RS256 over it; HS256 stays
    accepted only for service tokens (``type=service`` +
    ``aud=llamatrade-internal``) over the shared secret. Without one, everything
    is HS256 over the shared secret and the type/audience matrix still forbids
    cross-acceptance.
    """
    public_pem = public_key or os.environ.get("AUTH_JWT_PUBLIC_KEY") or None
    try:
        header_alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError:
        return None

    if public_pem is not None and header_alg == _ASYMMETRIC_ALGORITHM:
        claims = _decode(token, public_pem, _ASYMMETRIC_ALGORITHM)
        if claims is None or not _acceptable_user_claims(claims):
            return None
        return claims

    hmac_algorithm = algorithm or _DEFAULT_ALGORITHM
    if header_alg != hmac_algorithm:
        return None
    hmac_secret = secret or require_secret("JWT_SECRET", _DEFAULT_SECRET)
    claims = _decode(token, hmac_secret, hmac_algorithm)
    if claims is None:
        return None
    if claims.get("type") == "service":
        return claims if claims.get("aud") == SERVICE_AUDIENCE else None
    if public_pem is not None:
        # User tokens must be asymmetric once a public key is configured.
        return None
    return claims if _acceptable_user_claims(claims) else None


def context_from_claims(payload: Mapping[str, object]) -> TenantContext | None:
    """``TenantContext`` for verified claims, or None if they can't authenticate.

    Accepts user access tokens (``type=access``) and internal service tokens
    (``type=service`` + the internal audience). Refresh (or any other) tokens
    return None.
    """
    token_type = payload.get("type", "access")
    if token_type == "service":
        if payload.get("aud") != SERVICE_AUDIENCE:
            return None
        return TenantContext(
            tenant_id=_NIL_UUID,
            user_id=_NIL_UUID,
            is_service=True,
            svc=str(payload.get("svc", "") or ""),
        )
    if token_type != "access":
        # Refresh (or any non-access) token cannot authenticate an API call.
        return None

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("sub")
    if not tenant_id or not user_id:
        return None
    roles_raw = payload.get("roles") or []
    try:
        return TenantContext(
            tenant_id=UUID(str(tenant_id)),
            user_id=UUID(str(user_id)),
            email=str(payload.get("email", "") or ""),
            roles=[str(role) for role in roles_raw] if isinstance(roles_raw, list) else [],
        )
    except ValueError, TypeError:
        return None


def verify_credential(
    token: str,
    *,
    secret: str | None = None,
    algorithm: str | None = None,
    public_key: str | None = None,
) -> TenantContext | None:
    """Verify a bearer token and return its ``TenantContext``, or None if invalid."""
    claims = decode_token_claims(token, secret=secret, algorithm=algorithm, public_key=public_key)
    return context_from_claims(claims) if claims is not None else None


def _accepted_services_from_env() -> frozenset[str] | None:
    """The ``AUTH_ACCEPTED_SERVICES`` allowlist, or None when unset (accept any)."""
    raw = os.environ.get("AUTH_ACCEPTED_SERVICES")
    if not raw:
        return None
    names = frozenset(name.strip() for name in raw.split(",") if name.strip())
    return names or None


def resolve_identity(
    wire_tenant_id: str | None,
    wire_user_id: str | None,
    *,
    accepted_services: Collection[str] | None = None,
) -> tuple[UUID, UUID]:
    """Trusted ``(tenant_id, user_id)`` for a servicer call.

    - **user** context → the token identity is authoritative; if the wire
      ``tenant_id`` is present and differs, reject (cross-tenant guard).
    - **service** context → trust the wire identity (the caller already
      authenticated the user and forwards the tenant). When an allowlist is
      configured (``accepted_services`` argument, else ``AUTH_ACCEPTED_SERVICES``),
      a service token whose ``svc`` is not listed is rejected; unset accepts any.
    - **no** context → trust the wire identity. In production the fail-closed
      ``AuthMiddleware`` guarantees a context exists, so this branch is only hit
      by unit tests that call servicers directly.

    Raises ``AuthError`` on a missing/mismatched/invalid context.
    """
    ctx = _context.get()
    if ctx is not None and ctx.is_service:
        allowed = (
            accepted_services if accepted_services is not None else _accepted_services_from_env()
        )
        if allowed is not None and ctx.svc not in allowed:
            raise AuthError(
                "permission_denied",
                f"service {ctx.svc or '<unknown>'} is not in the accepted-services allowlist",
            )
    if ctx is not None and not ctx.is_service:
        if wire_tenant_id:
            try:
                wire_tid = UUID(str(wire_tenant_id))
            except (ValueError, TypeError, AttributeError) as e:
                raise AuthError("invalid_argument", f"invalid tenant_id in context: {e}") from e
            if wire_tid != ctx.tenant_id:
                metrics.auth.cross_tenant_access_attempt()
                raise AuthError(
                    "permission_denied",
                    "tenant_id in request does not match the authenticated principal",
                )
        if wire_user_id:
            try:
                wire_uid = UUID(str(wire_user_id))
            except (ValueError, TypeError, AttributeError) as e:
                raise AuthError("invalid_argument", f"invalid user_id in context: {e}") from e
            if wire_uid != ctx.user_id:
                raise AuthError(
                    "permission_denied",
                    "user_id in request does not match the authenticated principal",
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
        jwt_public_key: str | None = None,
        public_paths: list[str] | None = None,
        public_suffixes: list[str] | None = None,
        redis_client: Redis | None = None,
    ) -> None:
        self.app = app
        self._secret = jwt_secret or require_secret("JWT_SECRET", _DEFAULT_SECRET)
        self._algorithm = jwt_algorithm
        # RS256 pin for user tokens; HS256 stays for service tokens (module docstring).
        self._public_key = jwt_public_key or os.environ.get("AUTH_JWT_PUBLIC_KEY") or None
        self._public_paths = set(public_paths or ["/health", "/metrics", "/docs", "/openapi.json"])
        self._public_suffixes = tuple(public_suffixes or ())
        # Revocation checking needs Redis. When a client is not supplied, build one
        # from REDIS_URL so the secure default does not hinge on each call site
        # passing one; only its absence (no client, no URL) disables the check.
        if redis_client is None:
            redis_client = self._default_redis_client()
        self._revocation = RevocationStore(redis_client) if redis_client is not None else None
        if self._revocation is None and is_production_environment():
            raise RuntimeError(
                "token revocation is disabled (no Redis client and REDIS_URL is unset); "
                "refusing to start in production/staging without revocation enforcement"
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type == "websocket":
            # No websocket auth exists here; reject rather than bypass the fail-closed edge.
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope_type != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        # CORS preflight carries no Authorization header; let it through.
        if method == "OPTIONS" or self._is_public(path):
            await self.app(scope, receive, send)
            return

        token = self._bearer_token(scope)
        claims = (
            decode_token_claims(
                token,
                secret=self._secret,
                algorithm=self._algorithm,
                public_key=self._public_key,
            )
            if token
            else None
        )
        ctx = context_from_claims(claims) if claims is not None else None
        if ctx is None:
            await self._reject(send)
            return
        if (
            self._revocation is not None
            and claims is not None
            and not ctx.is_service
            and await self._revocation.is_revoked(claims)
        ):
            await self._reject(send)
            return

        reset = _context.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            _context.reset(reset)

    @staticmethod
    def _default_redis_client() -> Redis | None:
        """Build a Redis client from ``REDIS_URL`` for revocation, or None if unset.

        ``from_url`` is lazy (no connection until the first command), so this is
        safe at construction; a Redis outage still fails open inside ``is_revoked``.
        """
        url = os.environ.get("REDIS_URL")
        if not url:
            return None
        return Redis.from_url(url)

    def _is_public(self, path: str) -> bool:
        if path in self._public_paths or path.startswith("/health/"):
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
