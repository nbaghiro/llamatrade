"""Auth gRPC client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from llamatrade_grpc.clients.base import BaseGRPCClient

if TYPE_CHECKING:
    from llamatrade_grpc.generated.llamatrade.v1 import auth_pb2_grpc

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """Tenant and user context from validated token."""

    tenant_id: str
    user_id: str
    roles: list[str]


@dataclass
class TokenValidationResult:
    """Result of token validation."""

    valid: bool
    context: TenantContext | None
    expires_at: datetime | None
    token_type: str | None


@dataclass
class APIKeyValidationResult:
    """Result of API key validation."""

    valid: bool
    context: TenantContext | None
    granted_scopes: list[str]


class AuthClient(BaseGRPCClient):
    """Client for the Auth gRPC service.

    This client is used by other services to validate tokens and API keys.
    It should be configured with connection pooling for high-frequency calls.

    Example:
        auth_client = AuthClient("auth:50051")

        # Validate a JWT token
        result = await auth_client.validate_token(token)
        if result.valid:
            print(f"User: {result.context.user_id}")
            print(f"Tenant: {result.context.tenant_id}")

        # Validate an API key
        result = await auth_client.validate_api_key(api_key, required_scopes=["read:orders"])
        if result.valid:
            print(f"Scopes: {result.granted_scopes}")
    """

    def __init__(
        self,
        target: str = "auth:50051",
        *,
        secure: bool = False,
        credentials: object | None = None,
        interceptors: list[object] | None = None,
        options: list[tuple[str, str | int | bool]] | None = None,
    ) -> None:
        """Initialize the Auth client.

        Args:
            target: The gRPC server address
            secure: Whether to use TLS
            credentials: Optional channel credentials
            interceptors: Optional client interceptors
            options: Optional channel options
        """
        super().__init__(
            target,
            secure=secure,
            credentials=credentials,  # type: ignore[arg-type]
            interceptors=interceptors,  # type: ignore[arg-type]
            options=options,
        )
        self._stub: auth_pb2_grpc.AuthServiceStub | None = None

    @property
    def stub(self) -> auth_pb2_grpc.AuthServiceStub:
        """Get the gRPC stub (lazy initialization)."""
        if self._stub is None:
            try:
                from llamatrade_grpc.generated.llamatrade.v1 import auth_pb2_grpc

                self._stub = auth_pb2_grpc.AuthServiceStub(self.channel)
            except ImportError:
                raise RuntimeError(
                    "Generated gRPC code not found. Run 'make generate' in libs/proto"
                )
        return self._stub

    async def validate_token(self, token: str) -> TokenValidationResult:
        """Validate a JWT token.

        This is a high-frequency call used by all services to validate
        incoming requests. Consider using caching.

        Args:
            token: The JWT token to validate

        Returns:
            TokenValidationResult with validation status and context
        """
        from llamatrade_grpc.generated.llamatrade.v1 import auth_pb2

        request = auth_pb2.ValidateTokenRequest(token=token)

        try:
            response = await self.stub.ValidateToken(request)

            context = None
            if response.valid and response.HasField("context"):
                context = TenantContext(
                    tenant_id=response.context.tenant_id,
                    user_id=response.context.user_id,
                    roles=list(response.context.roles),
                )

            expires_at = None
            if response.HasField("expires_at"):
                expires_at = datetime.fromtimestamp(response.expires_at.seconds)

            return TokenValidationResult(
                valid=response.valid,
                context=context,
                expires_at=expires_at,
                token_type=response.token_type if response.token_type else None,
            )
        except Exception as e:
            logger.error("Token validation failed: %s", e)
            return TokenValidationResult(
                valid=False,
                context=None,
                expires_at=None,
                token_type=None,
            )

    async def validate_api_key(
        self,
        api_key: str,
        required_scopes: list[str] | None = None,
    ) -> APIKeyValidationResult:
        """Validate an API key.

        Args:
            api_key: The API key to validate
            required_scopes: Optional list of required scopes

        Returns:
            APIKeyValidationResult with validation status and granted scopes
        """
        from llamatrade_grpc.generated.llamatrade.v1 import auth_pb2

        request = auth_pb2.ValidateAPIKeyRequest(
            api_key=api_key,
            required_scopes=required_scopes or [],
        )

        try:
            response = await self.stub.ValidateAPIKey(request)

            context = None
            if response.valid and response.HasField("context"):
                context = TenantContext(
                    tenant_id=response.context.tenant_id,
                    user_id=response.context.user_id,
                    roles=list(response.context.roles),
                )

            return APIKeyValidationResult(
                valid=response.valid,
                context=context,
                granted_scopes=list(response.granted_scopes),
            )
        except Exception as e:
            logger.error("API key validation failed: %s", e)
            return APIKeyValidationResult(
                valid=False,
                context=None,
                granted_scopes=[],
            )

    async def check_permission(
        self,
        context: TenantContext,
        resource: str,
        action: str,
    ) -> tuple[bool, str | None]:
        """Check if a user has permission for an action.

        Args:
            context: The tenant context
            resource: The resource to check (e.g., "strategies")
            action: The action to check (e.g., "create")

        Returns:
            Tuple of (allowed, reason)
        """
        from llamatrade_grpc.generated.llamatrade.v1 import auth_pb2, common_pb2

        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            resource=resource,
            action=action,
        )

        try:
            response = await self.stub.CheckPermission(request)
            return response.allowed, response.reason if response.reason else None
        except Exception as e:
            logger.error("Permission check failed: %s", e)
            return False, str(e)
