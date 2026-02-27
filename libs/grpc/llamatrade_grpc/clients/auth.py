"""Auth gRPC client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from llamatrade_grpc.clients.base import BaseGRPCClient

if TYPE_CHECKING:
    from llamatrade.v1 import auth_pb2_grpc

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """Tenant and user context from validated token."""

    tenant_id: str
    user_id: str
    roles: list[str]


@dataclass
class User:
    """User information."""

    id: str
    tenant_id: str
    email: str
    first_name: str
    last_name: str
    roles: list[str]
    is_active: bool
    created_at: datetime | None = None
    last_login: datetime | None = None


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


@dataclass
class RegisterResult:
    """Result of user registration."""

    user: User
    tenant_id: str


@dataclass
class LoginResult:
    """Result of user login."""

    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    user: User


@dataclass
class RefreshResult:
    """Result of token refresh."""

    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class AuthClient(BaseGRPCClient):
    """Client for the Auth gRPC service.

    This client is used by other services to validate tokens and API keys.
    It should be configured with connection pooling for high-frequency calls.

    Example:
        auth_client = AuthClient("auth:8810")

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
        target: str = "auth:8810",
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
                from llamatrade.v1 import auth_pb2_grpc

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
        from llamatrade.v1 import auth_pb2

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
        from llamatrade.v1 import auth_pb2

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
        from llamatrade.v1 import auth_pb2, common_pb2

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

    async def register(
        self,
        email: str,
        password: str,
        tenant_name: str,
        first_name: str = "",
        last_name: str = "",
    ) -> RegisterResult:
        """Register a new user and tenant.

        Args:
            email: User email address
            password: User password
            tenant_name: Name for the new tenant
            first_name: User's first name (optional)
            last_name: User's last name (optional)

        Returns:
            RegisterResult with user and tenant_id

        Raises:
            Exception: If registration fails
        """
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.RegisterRequest(
            email=email,
            password=password,
            tenant_name=tenant_name,
            first_name=first_name,
            last_name=last_name,
        )

        response = await self.stub.Register(request)

        user = User(
            id=response.user.id,
            tenant_id=response.user.tenant_id,
            email=response.user.email,
            first_name=response.user.first_name,
            last_name=response.user.last_name,
            roles=list(response.user.roles),
            is_active=response.user.is_active,
            created_at=datetime.fromtimestamp(response.user.created_at.seconds)
            if response.user.HasField("created_at")
            else None,
            last_login=datetime.fromtimestamp(response.user.last_login.seconds)
            if response.user.HasField("last_login")
            else None,
        )

        return RegisterResult(user=user, tenant_id=response.tenant_id)

    async def login(self, email: str, password: str) -> LoginResult:
        """Login with email and password.

        Args:
            email: User email address
            password: User password

        Returns:
            LoginResult with tokens and user info

        Raises:
            Exception: If login fails (invalid credentials)
        """
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.LoginRequest(email=email, password=password)

        response = await self.stub.Login(request)

        user = User(
            id=response.user.id,
            tenant_id=response.user.tenant_id,
            email=response.user.email,
            first_name=response.user.first_name,
            last_name=response.user.last_name,
            roles=list(response.user.roles),
            is_active=response.user.is_active,
            created_at=datetime.fromtimestamp(response.user.created_at.seconds)
            if response.user.HasField("created_at")
            else None,
            last_login=datetime.fromtimestamp(response.user.last_login.seconds)
            if response.user.HasField("last_login")
            else None,
        )

        return LoginResult(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            access_token_expires_at=datetime.fromtimestamp(
                response.access_token_expires_at.seconds
            ),
            refresh_token_expires_at=datetime.fromtimestamp(
                response.refresh_token_expires_at.seconds
            ),
            user=user,
        )

    async def refresh_token(self, refresh_token: str) -> RefreshResult:
        """Refresh an access token.

        Args:
            refresh_token: The refresh token

        Returns:
            RefreshResult with new tokens

        Raises:
            Exception: If refresh fails (invalid/expired token)
        """
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)

        response = await self.stub.RefreshToken(request)

        return RefreshResult(
            access_token=response.access_token,
            refresh_token=response.refresh_token,
            access_token_expires_at=datetime.fromtimestamp(
                response.access_token_expires_at.seconds
            ),
            refresh_token_expires_at=datetime.fromtimestamp(
                response.refresh_token_expires_at.seconds
            ),
        )

    async def change_password(
        self,
        token: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change user password.

        Args:
            token: The user's access token (passed via metadata)
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            True if password was changed successfully

        Raises:
            Exception: If password change fails
        """
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.ChangePasswordRequest(
            current_password=current_password,
            new_password=new_password,
        )

        # Pass token via metadata
        metadata = [("authorization", f"Bearer {token}")]
        response = await self.stub.ChangePassword(request, metadata=metadata)
        return response.success

    async def get_current_user(self, token: str) -> User:
        """Get the current user from an access token.

        Args:
            token: The user's access token (passed via metadata)

        Returns:
            User object with user information

        Raises:
            Exception: If token is invalid or user not found
        """
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.GetCurrentUserRequest()

        # Pass token via metadata
        metadata = [("authorization", f"Bearer {token}")]
        response = await self.stub.GetCurrentUser(request, metadata=metadata)

        return User(
            id=response.user.id,
            tenant_id=response.user.tenant_id,
            email=response.user.email,
            first_name=response.user.first_name,
            last_name=response.user.last_name,
            roles=list(response.user.roles),
            is_active=response.user.is_active,
            created_at=datetime.fromtimestamp(response.user.created_at.seconds)
            if response.user.HasField("created_at")
            else None,
            last_login=datetime.fromtimestamp(response.user.last_login.seconds)
            if response.user.HasField("last_login")
            else None,
        )
