"""Tests for llamatrade_proto.clients.auth against real generated messages."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.auth import (
    APIKeyValidationResult,
    AuthClient,
    TenantContext,
    TokenValidationResult,
)
from llamatrade_proto.generated import auth_pb2, common_pb2

# 2024-01-15T12:00:00Z, +1h, +7d. Decoded values must be UTC-aware instants,
# independent of the host timezone.
CREATED_AT = common_pb2.Timestamp(seconds=1705320000)
LAST_LOGIN = common_pb2.Timestamp(seconds=1705400000)
ACCESS_EXPIRES = common_pb2.Timestamp(seconds=1705323600)
REFRESH_EXPIRES = common_pb2.Timestamp(seconds=1705924800)

CREATED_AT_DT = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
LAST_LOGIN_DT = datetime(2024, 1, 16, 10, 13, 20, tzinfo=UTC)
ACCESS_EXPIRES_DT = datetime(2024, 1, 15, 13, 0, tzinfo=UTC)
REFRESH_EXPIRES_DT = datetime(2024, 1, 22, 12, 0, tzinfo=UTC)


def _pb_user(
    created_at: common_pb2.Timestamp | None = None,
    last_login: common_pb2.Timestamp | None = None,
) -> auth_pb2.User:
    return auth_pb2.User(
        id="user-123",
        tenant_id="tenant-456",
        email="test@example.com",
        first_name="John",
        last_name="Doe",
        roles=["user"],
        is_active=True,
        created_at=created_at,
        last_login=last_login,
    )


def _client_with_stub(**rpc: AsyncMock) -> tuple[AuthClient, MagicMock]:
    client = AuthClient()
    stub = MagicMock()
    for name, mock in rpc.items():
        setattr(stub, name, mock)
    client._stub = stub
    return client, stub


class TestAuthClientInit:
    """Tests for AuthClient initialization."""

    def test_init_with_defaults(self) -> None:
        client = AuthClient()

        assert client._target == "auth:8810"
        assert client._secure is False
        assert client._stub is None

    def test_init_with_custom_target(self) -> None:
        client = AuthClient("localhost:9000")

        assert client._target == "localhost:9000"

    def test_init_with_secure(self) -> None:
        client = AuthClient(secure=True)

        assert client._secure is True


class TestAuthClientStub:
    """Tests for AuthClient stub property."""

    def test_stub_raises_on_missing_generated_code(self) -> None:
        client = AuthClient()

        with patch.dict("sys.modules", {"llamatrade_proto.generated": None}):
            with pytest.raises(RuntimeError, match="Generated gRPC code not found"):
                _ = client.stub


class TestValidateToken:
    """Tests for AuthClient.validate_token."""

    async def test_valid_with_context_decodes_utc_expiry(self) -> None:
        response = auth_pb2.ValidateTokenResponse(
            valid=True,
            context=common_pb2.TenantContext(
                tenant_id="tenant-123", user_id="user-456", roles=["admin", "trader"]
            ),
            expires_at=ACCESS_EXPIRES,
            token_type="access",
        )
        client, stub = _client_with_stub(ValidateToken=AsyncMock(return_value=response))

        result = await client.validate_token("valid-token")

        assert result.valid is True
        assert result.context == TenantContext("tenant-123", "user-456", ["admin", "trader"])
        assert result.expires_at is not None
        assert result.expires_at == ACCESS_EXPIRES_DT
        assert result.expires_at.tzinfo is UTC
        assert result.token_type == "access"
        request = stub.ValidateToken.call_args[0][0]
        assert request.token == "valid-token"
        assert stub.ValidateToken.call_args.kwargs["timeout"] == 5.0

    async def test_valid_without_context(self) -> None:
        response = auth_pb2.ValidateTokenResponse(valid=True)
        client, _ = _client_with_stub(ValidateToken=AsyncMock(return_value=response))

        result = await client.validate_token("token")

        assert result.valid is True
        assert result.context is None
        assert result.expires_at is None
        assert result.token_type is None

    async def test_invalid_token_never_carries_context(self) -> None:
        response = auth_pb2.ValidateTokenResponse(
            valid=False,
            context=common_pb2.TenantContext(tenant_id="tenant-123", user_id="user-456"),
        )
        client, _ = _client_with_stub(ValidateToken=AsyncMock(return_value=response))

        result = await client.validate_token("expired-token")

        assert result.valid is False
        assert result.context is None

    async def test_rpc_error_returns_invalid(self) -> None:
        client, _ = _client_with_stub(
            ValidateToken=AsyncMock(side_effect=RuntimeError("connection failed"))
        )

        result = await client.validate_token("token")

        assert result == TokenValidationResult(
            valid=False, context=None, expires_at=None, token_type=None
        )


class TestValidateAPIKey:
    """Tests for AuthClient.validate_api_key."""

    async def test_valid_with_context_and_scopes(self) -> None:
        response = auth_pb2.ValidateAPIKeyResponse(
            valid=True,
            context=common_pb2.TenantContext(
                tenant_id="tenant-123", user_id="user-456", roles=["api"]
            ),
            granted_scopes=["read:orders", "write:orders"],
        )
        client, stub = _client_with_stub(ValidateAPIKey=AsyncMock(return_value=response))

        result = await client.validate_api_key("valid-api-key", ["read:orders"])

        assert result.valid is True
        assert result.context == TenantContext("tenant-123", "user-456", ["api"])
        assert result.granted_scopes == ["read:orders", "write:orders"]
        request = stub.ValidateAPIKey.call_args[0][0]
        assert request.api_key == "valid-api-key"
        assert list(request.required_scopes) == ["read:orders"]

    async def test_defaults_to_no_required_scopes(self) -> None:
        response = auth_pb2.ValidateAPIKeyResponse(valid=True)
        client, stub = _client_with_stub(ValidateAPIKey=AsyncMock(return_value=response))

        result = await client.validate_api_key("key")

        assert result.valid is True
        assert result.context is None
        assert list(stub.ValidateAPIKey.call_args[0][0].required_scopes) == []

    async def test_rpc_error_returns_invalid(self) -> None:
        client, _ = _client_with_stub(
            ValidateAPIKey=AsyncMock(side_effect=RuntimeError("connection failed"))
        )

        result = await client.validate_api_key("key")

        assert result == APIKeyValidationResult(valid=False, context=None, granted_scopes=[])


class TestCheckPermission:
    """Tests for AuthClient.check_permission."""

    async def test_allowed_maps_empty_reason_to_none(self) -> None:
        response = auth_pb2.CheckPermissionResponse(allowed=True)
        client, stub = _client_with_stub(CheckPermission=AsyncMock(return_value=response))
        ctx = TenantContext("tenant-123", "user-456", ["admin"])

        allowed, reason = await client.check_permission(ctx, "strategies", "create")

        assert allowed is True
        assert reason is None
        request = stub.CheckPermission.call_args[0][0]
        assert request.context.tenant_id == "tenant-123"
        assert request.context.user_id == "user-456"
        assert list(request.context.roles) == ["admin"]
        assert request.resource == "strategies"
        assert request.action == "create"

    async def test_denied_carries_reason(self) -> None:
        response = auth_pb2.CheckPermissionResponse(allowed=False, reason="missing role")
        client, _ = _client_with_stub(CheckPermission=AsyncMock(return_value=response))
        ctx = TenantContext("tenant-123", "user-456", [])

        allowed, reason = await client.check_permission(ctx, "strategies", "delete")

        assert allowed is False
        assert reason == "missing role"

    async def test_rpc_error_returns_denied_with_message(self) -> None:
        client, _ = _client_with_stub(
            CheckPermission=AsyncMock(side_effect=RuntimeError("connection failed"))
        )
        ctx = TenantContext("tenant-123", "user-456", ["admin"])

        allowed, reason = await client.check_permission(ctx, "strategies", "create")

        assert allowed is False
        assert reason is not None and "connection failed" in reason


class TestRegister:
    """Tests for AuthClient.register."""

    async def test_register_decodes_user_with_utc_created_at(self) -> None:
        response = auth_pb2.RegisterResponse(
            user=_pb_user(created_at=CREATED_AT),
            tenant=auth_pb2.Tenant(id="tenant-456", name="Test Tenant"),
        )
        client, stub = _client_with_stub(Register=AsyncMock(return_value=response))

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
        assert result.user.created_at == CREATED_AT_DT
        assert result.user.created_at is not None and result.user.created_at.tzinfo is UTC
        assert result.user.last_login is None
        request = stub.Register.call_args[0][0]
        assert request.email == "test@example.com"
        assert request.password == "password123"
        assert request.tenant_name == "Test Tenant"


class TestLogin:
    """Tests for AuthClient.login."""

    async def test_login_decodes_utc_token_expiries(self) -> None:
        response = auth_pb2.LoginResponse(
            access_token="access-token-123",
            refresh_token="refresh-token-456",
            user=_pb_user(created_at=CREATED_AT, last_login=LAST_LOGIN),
            access_token_expires_at=ACCESS_EXPIRES,
            refresh_token_expires_at=REFRESH_EXPIRES,
        )
        client, stub = _client_with_stub(Login=AsyncMock(return_value=response))

        result = await client.login("test@example.com", "password123")

        assert result.access_token == "access-token-123"
        assert result.refresh_token == "refresh-token-456"
        assert result.access_token_expires_at == ACCESS_EXPIRES_DT
        assert result.access_token_expires_at.tzinfo is UTC
        assert result.refresh_token_expires_at == REFRESH_EXPIRES_DT
        assert result.refresh_token_expires_at.tzinfo is UTC
        assert result.user.id == "user-123"
        assert result.user.last_login == LAST_LOGIN_DT
        request = stub.Login.call_args[0][0]
        assert request.email == "test@example.com"
        assert request.password == "password123"

    async def test_login_error_propagates(self) -> None:
        client, _ = _client_with_stub(
            Login=AsyncMock(side_effect=RuntimeError("invalid credentials"))
        )

        with pytest.raises(RuntimeError, match="invalid credentials"):
            await client.login("test@example.com", "wrong")


class TestRefreshToken:
    """Tests for AuthClient.refresh_token."""

    async def test_refresh_decodes_utc_token_expiries(self) -> None:
        response = auth_pb2.RefreshTokenResponse(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            access_token_expires_at=ACCESS_EXPIRES,
            refresh_token_expires_at=REFRESH_EXPIRES,
        )
        client, stub = _client_with_stub(RefreshToken=AsyncMock(return_value=response))

        result = await client.refresh_token("old-refresh-token")

        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"
        assert result.access_token_expires_at == ACCESS_EXPIRES_DT
        assert result.access_token_expires_at.tzinfo is UTC
        assert result.refresh_token_expires_at == REFRESH_EXPIRES_DT
        assert result.refresh_token_expires_at.tzinfo is UTC
        assert stub.RefreshToken.call_args[0][0].refresh_token == "old-refresh-token"


class TestChangePassword:
    """Tests for AuthClient.change_password."""

    async def test_change_password_sends_bearer_metadata(self) -> None:
        response = auth_pb2.ChangePasswordResponse(success=True)
        client, stub = _client_with_stub(ChangePassword=AsyncMock(return_value=response))

        result = await client.change_password(
            token="access-token",
            current_password="old-password",
            new_password="new-password",
        )

        assert result is True
        call_args = stub.ChangePassword.call_args
        assert call_args.kwargs["metadata"] == [("authorization", "Bearer access-token")]
        request = call_args[0][0]
        assert request.current_password == "old-password"
        assert request.new_password == "new-password"


class TestGetCurrentUser:
    """Tests for AuthClient.get_current_user."""

    async def test_get_current_user_decodes_utc_timestamps(self) -> None:
        response = auth_pb2.GetCurrentUserResponse(
            user=_pb_user(created_at=CREATED_AT, last_login=LAST_LOGIN)
        )
        client, stub = _client_with_stub(GetCurrentUser=AsyncMock(return_value=response))

        result = await client.get_current_user("access-token")

        assert result.id == "user-123"
        assert result.email == "test@example.com"
        assert result.roles == ["user"]
        assert result.created_at == CREATED_AT_DT
        assert result.created_at is not None and result.created_at.tzinfo is UTC
        assert result.last_login == LAST_LOGIN_DT
        assert result.last_login is not None and result.last_login.tzinfo is UTC
        call_args = stub.GetCurrentUser.call_args
        assert call_args.kwargs["metadata"] == [("authorization", "Bearer access-token")]
