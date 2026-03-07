"""Tests for llamatrade_proto.clients.auth module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.auth import (
    APIKeyValidationResult,
    AuthClient,
    LoginResult,
    RefreshResult,
    RegisterResult,
    TenantContext,
    TokenValidationResult,
    User,
)


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_create_tenant_context(self) -> None:
        """Test creating TenantContext."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            user_id="user-456",
            roles=["admin", "trader"],
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.user_id == "user-456"
        assert ctx.roles == ["admin", "trader"]

    def test_tenant_context_empty_roles(self) -> None:
        """Test TenantContext with empty roles."""
        ctx = TenantContext(
            tenant_id="tenant-123",
            user_id="user-456",
            roles=[],
        )

        assert ctx.roles == []


class TestUser:
    """Tests for User dataclass."""

    def test_create_user_minimal(self) -> None:
        """Test creating User with required fields."""
        user = User(
            id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            roles=["user"],
            is_active=True,
        )

        assert user.id == "user-123"
        assert user.tenant_id == "tenant-456"
        assert user.email == "test@example.com"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.roles == ["user"]
        assert user.is_active is True
        assert user.created_at is None
        assert user.last_login is None

    def test_create_user_with_timestamps(self) -> None:
        """Test creating User with optional timestamps."""
        created = datetime(2024, 1, 1, 10, 0, 0)
        last_login = datetime(2024, 1, 15, 14, 30, 0)

        user = User(
            id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            roles=["user"],
            is_active=True,
            created_at=created,
            last_login=last_login,
        )

        assert user.created_at == created
        assert user.last_login == last_login


class TestTokenValidationResult:
    """Tests for TokenValidationResult dataclass."""

    def test_create_valid_result(self) -> None:
        """Test creating valid TokenValidationResult."""
        ctx = TenantContext("tenant-123", "user-456", ["admin"])
        expires = datetime(2024, 1, 15, 12, 0, 0)

        result = TokenValidationResult(
            valid=True,
            context=ctx,
            expires_at=expires,
            token_type="access",
        )

        assert result.valid is True
        assert result.context is ctx
        assert result.expires_at == expires
        assert result.token_type == "access"

    def test_create_invalid_result(self) -> None:
        """Test creating invalid TokenValidationResult."""
        result = TokenValidationResult(
            valid=False,
            context=None,
            expires_at=None,
            token_type=None,
        )

        assert result.valid is False
        assert result.context is None


class TestAPIKeyValidationResult:
    """Tests for APIKeyValidationResult dataclass."""

    def test_create_valid_api_key_result(self) -> None:
        """Test creating valid APIKeyValidationResult."""
        ctx = TenantContext("tenant-123", "user-456", ["api"])

        result = APIKeyValidationResult(
            valid=True,
            context=ctx,
            granted_scopes=["read:orders", "write:orders"],
        )

        assert result.valid is True
        assert result.context is ctx
        assert result.granted_scopes == ["read:orders", "write:orders"]

    def test_create_invalid_api_key_result(self) -> None:
        """Test creating invalid APIKeyValidationResult."""
        result = APIKeyValidationResult(
            valid=False,
            context=None,
            granted_scopes=[],
        )

        assert result.valid is False
        assert result.granted_scopes == []


class TestRegisterResult:
    """Tests for RegisterResult dataclass."""

    def test_create_register_result(self) -> None:
        """Test creating RegisterResult."""
        user = User(
            id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            roles=["user"],
            is_active=True,
        )

        result = RegisterResult(user=user, tenant_id="tenant-456")

        assert result.user is user
        assert result.tenant_id == "tenant-456"


class TestLoginResult:
    """Tests for LoginResult dataclass."""

    def test_create_login_result(self) -> None:
        """Test creating LoginResult."""
        user = User(
            id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            roles=["user"],
            is_active=True,
        )
        access_expires = datetime(2024, 1, 15, 12, 0, 0)
        refresh_expires = datetime(2024, 1, 22, 12, 0, 0)

        result = LoginResult(
            access_token="access-token-123",
            refresh_token="refresh-token-456",
            access_token_expires_at=access_expires,
            refresh_token_expires_at=refresh_expires,
            user=user,
        )

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        assert result.access_token_expires_at == access_expires
        assert result.refresh_token_expires_at == refresh_expires
        assert result.user is user


class TestRefreshResult:
    """Tests for RefreshResult dataclass."""

    def test_create_refresh_result(self) -> None:
        """Test creating RefreshResult."""
        access_expires = datetime(2024, 1, 15, 12, 0, 0)
        refresh_expires = datetime(2024, 1, 22, 12, 0, 0)

        result = RefreshResult(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            access_token_expires_at=access_expires,
            refresh_token_expires_at=refresh_expires,
        )

        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"
        assert result.access_token_expires_at == access_expires
        assert result.refresh_token_expires_at == refresh_expires


class TestAuthClientInit:
    """Tests for AuthClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test AuthClient initialization with defaults."""
        client = AuthClient()

        assert client._target == "auth:8810"
        assert client._secure is False
        assert client._stub is None

    def test_init_with_custom_target(self) -> None:
        """Test AuthClient initialization with custom target."""
        client = AuthClient("localhost:9000")

        assert client._target == "localhost:9000"

    def test_init_with_secure(self) -> None:
        """Test AuthClient initialization with secure=True."""
        client = AuthClient(secure=True)

        assert client._secure is True


class TestAuthClientStub:
    """Tests for AuthClient stub property."""

    def test_stub_raises_on_missing_generated_code(self) -> None:
        """Test stub raises RuntimeError when generated code is missing."""
        client = AuthClient()

        with patch("grpc.aio.insecure_channel"):
            with patch.dict("sys.modules", {"llamatrade_proto.generated": None}):
                # This will try to import and fail
                with pytest.raises((RuntimeError, ImportError)):
                    _ = client.stub


class TestAuthClientValidateToken:
    """Tests for AuthClient.validate_token method."""

    @pytest.mark.asyncio
    async def test_validate_token_returns_invalid_on_exception(self) -> None:
        """Test validate_token returns invalid result on exception."""
        client = AuthClient()

        # Mock the stub to raise an exception
        mock_stub = MagicMock()
        mock_stub.ValidateToken = AsyncMock(side_effect=Exception("Connection failed"))
        client._stub = mock_stub

        # Must also patch the generated module import
        mock_auth_pb2 = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.auth_pb2": mock_auth_pb2,
            },
        ):
            result = await client.validate_token("invalid-token")

        assert result.valid is False
        assert result.context is None
        assert result.expires_at is None
        assert result.token_type is None


class TestAuthClientValidateAPIKey:
    """Tests for AuthClient.validate_api_key method."""

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_invalid_on_exception(self) -> None:
        """Test validate_api_key returns invalid result on exception."""
        client = AuthClient()

        mock_stub = MagicMock()
        mock_stub.ValidateAPIKey = AsyncMock(side_effect=Exception("Connection failed"))
        client._stub = mock_stub

        # Must also patch the generated module import
        mock_auth_pb2 = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.auth_pb2": mock_auth_pb2,
            },
        ):
            result = await client.validate_api_key("invalid-key")

        assert result.valid is False
        assert result.context is None
        assert result.granted_scopes == []


class TestAuthClientCheckPermission:
    """Tests for AuthClient.check_permission method."""

    @pytest.mark.asyncio
    async def test_check_permission_returns_false_on_exception(self) -> None:
        """Test check_permission returns (False, error) on exception."""
        client = AuthClient()
        ctx = TenantContext("tenant-123", "user-456", ["admin"])

        mock_stub = MagicMock()
        mock_stub.CheckPermission = AsyncMock(side_effect=Exception("Connection failed"))
        client._stub = mock_stub

        # Must also patch the generated module import
        mock_auth_pb2 = MagicMock()
        mock_common_pb2 = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.auth_pb2": mock_auth_pb2,
                "llamatrade_proto.generated.common_pb2": mock_common_pb2,
            },
        ):
            allowed, reason = await client.check_permission(ctx, "strategies", "create")

        assert allowed is False
        assert reason is not None and "Connection failed" in reason

    @pytest.mark.asyncio
    async def test_check_permission_success(self) -> None:
        """Test check_permission returns allowed on success."""
        client = AuthClient()
        ctx = TenantContext("tenant-123", "user-456", ["admin"])

        mock_response = MagicMock()
        mock_response.allowed = True
        mock_response.reason = ""

        mock_stub = MagicMock()
        mock_stub.CheckPermission = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        # Must also patch the generated module import
        mock_auth_pb2 = MagicMock()
        mock_common_pb2 = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.auth_pb2": mock_auth_pb2,
                "llamatrade_proto.generated.common_pb2": mock_common_pb2,
            },
        ):
            allowed, reason = await client.check_permission(ctx, "strategies", "create")

        assert allowed is True
        assert reason is None


class TestAuthClientValidateTokenSuccess:
    """Tests for AuthClient.validate_token success cases."""

    @pytest.mark.asyncio
    async def test_validate_token_valid_with_context(self) -> None:
        """Test validate_token returns valid result with context."""
        client = AuthClient()

        # Create mock response
        mock_context = MagicMock()
        mock_context.tenant_id = "tenant-123"
        mock_context.user_id = "user-456"
        mock_context.roles = ["admin", "trader"]

        mock_expires_at = MagicMock()
        mock_expires_at.seconds = 1705320000  # Some timestamp

        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.HasField = lambda field: field in ["context", "expires_at"]
        mock_response.context = mock_context
        mock_response.expires_at = mock_expires_at
        mock_response.token_type = "access"

        mock_stub = MagicMock()
        mock_stub.ValidateToken = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        # Mock the generated module import
        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            with patch("llamatrade_proto.clients.auth.logger"):
                result = await client.validate_token("valid-token")

        assert result.valid is True
        assert result.context is not None
        assert result.context.tenant_id == "tenant-123"
        assert result.context.user_id == "user-456"
        assert result.context.roles == ["admin", "trader"]
        assert result.token_type == "access"

    @pytest.mark.asyncio
    async def test_validate_token_valid_without_context(self) -> None:
        """Test validate_token with valid=True but no context."""
        client = AuthClient()

        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.HasField = lambda field: False
        mock_response.token_type = ""

        mock_stub = MagicMock()
        mock_stub.ValidateToken = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.validate_token("token")

        assert result.valid is True
        assert result.context is None
        assert result.expires_at is None
        assert result.token_type is None


class TestAuthClientValidateAPIKeySuccess:
    """Tests for AuthClient.validate_api_key success cases."""

    @pytest.mark.asyncio
    async def test_validate_api_key_valid_with_context(self) -> None:
        """Test validate_api_key returns valid result with context."""
        client = AuthClient()

        mock_context = MagicMock()
        mock_context.tenant_id = "tenant-123"
        mock_context.user_id = "user-456"
        mock_context.roles = ["api"]

        mock_response = MagicMock()
        mock_response.valid = True
        mock_response.HasField = lambda field: field == "context"
        mock_response.context = mock_context
        mock_response.granted_scopes = ["read:orders", "write:orders"]

        mock_stub = MagicMock()
        mock_stub.ValidateAPIKey = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.validate_api_key("valid-api-key", ["read:orders"])

        assert result.valid is True
        assert result.context is not None
        assert result.context.tenant_id == "tenant-123"
        assert result.granted_scopes == ["read:orders", "write:orders"]


class TestAuthClientRegister:
    """Tests for AuthClient.register method."""

    @pytest.mark.asyncio
    async def test_register_success(self) -> None:
        """Test register returns RegisterResult on success."""
        client = AuthClient()

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.tenant_id = "tenant-456"
        mock_user.email = "test@example.com"
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.roles = ["user"]
        mock_user.is_active = True
        mock_user.HasField = lambda field: field == "created_at"
        mock_user.created_at = mock_created_at
        mock_user.last_login = None

        mock_response = MagicMock()
        mock_response.user = mock_user
        mock_response.tenant_id = "tenant-456"

        mock_stub = MagicMock()
        mock_stub.Register = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.register(
                email="test@example.com",
                password="password123",
                tenant_name="Test Tenant",
                first_name="John",
                last_name="Doe",
            )

        assert result.tenant_id == "tenant-456"
        assert result.user.id == "user-123"
        assert result.user.email == "test@example.com"


class TestAuthClientLogin:
    """Tests for AuthClient.login method."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """Test login returns LoginResult on success."""
        client = AuthClient()

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.tenant_id = "tenant-456"
        mock_user.email = "test@example.com"
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.roles = ["user"]
        mock_user.is_active = True
        mock_user.HasField = lambda field: field == "created_at"
        mock_user.created_at = mock_created_at

        mock_access_expires = MagicMock()
        mock_access_expires.seconds = 1705323600

        mock_refresh_expires = MagicMock()
        mock_refresh_expires.seconds = 1705924800

        mock_response = MagicMock()
        mock_response.access_token = "access-token-123"
        mock_response.refresh_token = "refresh-token-456"
        mock_response.access_token_expires_at = mock_access_expires
        mock_response.refresh_token_expires_at = mock_refresh_expires
        mock_response.user = mock_user

        mock_stub = MagicMock()
        mock_stub.Login = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.login("test@example.com", "password123")

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        assert result.user.id == "user-123"


class TestAuthClientRefreshToken:
    """Tests for AuthClient.refresh_token method."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self) -> None:
        """Test refresh_token returns RefreshResult on success."""
        client = AuthClient()

        mock_access_expires = MagicMock()
        mock_access_expires.seconds = 1705323600

        mock_refresh_expires = MagicMock()
        mock_refresh_expires.seconds = 1705924800

        mock_response = MagicMock()
        mock_response.access_token = "new-access-token"
        mock_response.refresh_token = "new-refresh-token"
        mock_response.access_token_expires_at = mock_access_expires
        mock_response.refresh_token_expires_at = mock_refresh_expires

        mock_stub = MagicMock()
        mock_stub.RefreshToken = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.refresh_token("old-refresh-token")

        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"


class TestAuthClientChangePassword:
    """Tests for AuthClient.change_password method."""

    @pytest.mark.asyncio
    async def test_change_password_success(self) -> None:
        """Test change_password returns True on success."""
        client = AuthClient()

        mock_response = MagicMock()
        mock_response.success = True

        mock_stub = MagicMock()
        mock_stub.ChangePassword = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.change_password(
                token="access-token",
                current_password="old-password",
                new_password="new-password",
            )

        assert result is True
        # Verify metadata was passed
        call_args = mock_stub.ChangePassword.call_args
        assert call_args.kwargs["metadata"] == [("authorization", "Bearer access-token")]


class TestAuthClientGetCurrentUser:
    """Tests for AuthClient.get_current_user method."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self) -> None:
        """Test get_current_user returns User on success."""
        client = AuthClient()

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_last_login = MagicMock()
        mock_last_login.seconds = 1705400000

        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.tenant_id = "tenant-456"
        mock_user.email = "test@example.com"
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.roles = ["user", "admin"]
        mock_user.is_active = True
        mock_user.HasField = lambda field: field in ["created_at", "last_login"]
        mock_user.created_at = mock_created_at
        mock_user.last_login = mock_last_login

        mock_response = MagicMock()
        mock_response.user = mock_user

        mock_stub = MagicMock()
        mock_stub.GetCurrentUser = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        with patch.dict("sys.modules", {"llamatrade_proto.generated": MagicMock()}):
            result = await client.get_current_user("access-token")

        assert result.id == "user-123"
        assert result.email == "test@example.com"
        assert result.roles == ["user", "admin"]
        # Verify metadata was passed
        call_args = mock_stub.GetCurrentUser.call_args
        assert call_args.kwargs["metadata"] == [("authorization", "Bearer access-token")]
