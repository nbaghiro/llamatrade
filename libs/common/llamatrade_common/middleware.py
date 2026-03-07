"""Tenant context middleware for FastAPI services."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from llamatrade_common.models import TenantContext

# Context variable to store tenant context per request
_tenant_context: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


def get_tenant_context() -> TenantContext:
    """Get the current tenant context from context variable.

    Raises:
        HTTPException: If no tenant context is set.
    """
    ctx = _tenant_context.get()
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return ctx


def set_tenant_context(ctx: TenantContext | None) -> None:
    """Set the tenant context for the current request."""
    _tenant_context.set(ctx)


class TenantMiddleware:
    """Middleware to extract tenant context from JWT token."""

    def __init__(
        self,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        public_paths: list[str] | None = None,
    ):
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.public_paths = public_paths or ["/health", "/docs", "/openapi.json"]

    async def __call__(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process the request and extract tenant context."""
        # Clear any existing context
        set_tenant_context(None)

        # Check if path is public
        path = request.url.path
        if any(path.startswith(p) for p in self.public_paths):
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # Let the endpoint handle authentication
            return await call_next(request)

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Decode JWT token
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
            )

            # Extract tenant context from payload
            tenant_context = TenantContext(
                tenant_id=UUID(payload["tenant_id"]),
                user_id=UUID(payload["sub"]),
                email=payload["email"],
                roles=payload.get("roles", []),
            )

            # Set context for this request
            set_tenant_context(tenant_context)

        except jwt.ExpiredSignatureError:
            # Token expired - let endpoint handle it
            pass
        except jwt.InvalidTokenError:
            # Invalid token - let endpoint handle it
            pass
        except KeyError, ValueError, ValidationError:
            # Missing or invalid claims - let endpoint handle it
            pass

        response = await call_next(request)
        return response


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TenantContext:
    """Dependency to require authentication.

    Use this in route dependencies to require a valid JWT token.
    """
    ctx = _tenant_context.get()
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


def require_roles(
    *required_roles: str,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """Dependency factory to require specific roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_roles("admin"))])
        async def admin_endpoint(): ...
    """

    async def check_roles(ctx: TenantContext = Depends(require_auth)) -> TenantContext:
        if not any(role in ctx.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(required_roles)}",
            )
        return ctx

    return check_roles


class ServiceClient:
    """Base client for inter-service communication."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        """Get headers including tenant context for service-to-service calls."""
        ctx = _tenant_context.get()
        headers = {"Content-Type": "application/json"}

        if ctx:
            # For service-to-service calls, we could use a service token
            # or propagate the user's token
            headers["X-Tenant-ID"] = str(ctx.tenant_id)
            headers["X-User-ID"] = str(ctx.user_id)

        return headers
