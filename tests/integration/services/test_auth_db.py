"""Auth service gRPC integration tests with real database.

These tests verify auth functionality using the gRPC servicer:
1. User registration creates tenant and user
2. Login returns valid tokens
3. Token refresh works correctly
4. Password change works
5. GetCurrentUser returns user info

Uses testcontainers for real PostgreSQL database.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import grpc.aio
import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self) -> None:
        self._metadata: list[tuple[str, str]] = []
        self._aborted = False
        self._abort_code: grpc.StatusCode | None = None
        self._abort_details: str | None = None

    def invocation_metadata(self) -> list[tuple[str, str]]:
        return self._metadata

    def set_metadata(self, metadata: list[tuple[str, str]]) -> None:
        self._metadata = metadata

    async def abort(self, code: grpc.StatusCode, details: str) -> None:
        self._aborted = True
        self._abort_code = code
        self._abort_details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    @property
    def aborted(self) -> bool:
        return self._aborted


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def auth_servicer(db_session: AsyncSession):
    """Create an auth servicer with test database session."""
    import sys
    from pathlib import Path

    # Add auth service to path
    auth_path = Path(__file__).parents[3] / "services" / "auth"
    auth_path_str = str(auth_path)
    if auth_path_str not in sys.path:
        sys.path.insert(0, auth_path_str)

    # Clear any cached src modules
    modules_to_remove = [
        k for k in list(sys.modules.keys())
        if k == "src" or k.startswith("src.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    from src.grpc.servicer import AuthServicer

    servicer = AuthServicer()

    # Mock the session factory to return our test session
    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db

    return servicer


class TestUserRegistration:
    """User registration tests with real database."""

    async def test_register_creates_tenant_and_user(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test registration creates both tenant and user in database."""
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.RegisterRequest(
            tenant_name="Test Company",
            email="newuser@example.com",
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )

        response = await auth_servicer.Register(request, grpc_context)

        # Verify response
        assert response.user.email == "newuser@example.com"
        assert response.user.first_name == "Test"
        assert response.user.last_name == "User"
        assert "admin" in response.user.roles
        assert response.user.is_active is True
        assert response.user.id
        assert response.user.tenant_id
        assert response.tenant.id
        assert response.tenant.name == "Test Company"

        # Verify user exists in database
        from uuid import UUID

        from llamatrade_db.models import User
        from sqlalchemy import select

        user_result = await db_session.execute(
            select(User).where(User.email == "newuser@example.com")
        )
        user = user_result.scalar_one_or_none()
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.role == "admin"
        assert user.is_active is True

        # Verify tenant exists
        from llamatrade_db.models import Tenant

        tenant_result = await db_session.execute(
            select(Tenant).where(Tenant.id == UUID(response.tenant.id))
        )
        tenant = tenant_result.scalar_one_or_none()
        assert tenant is not None
        assert tenant.name == "Test Company"
        assert tenant.is_active is True

    async def test_register_duplicate_email_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        test_user,
    ):
        """Test registration fails if email already exists."""
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.RegisterRequest(
            tenant_name="Another Company",
            email=test_user.email,  # Already exists
            password="SecurePassword123!",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.Register(request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.ALREADY_EXISTS
        assert "already registered" in exc_info.value.details().lower()


class TestUserLogin:
    """User login tests with real database."""

    async def test_login_returns_valid_tokens(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test login with correct credentials returns tokens."""
        from llamatrade.v1 import auth_pb2

        # First register a user
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Login Test Co",
            email="logintest@example.com",
            password="TestPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        # Then login
        login_request = auth_pb2.LoginRequest(
            email="logintest@example.com",
            password="TestPassword123!",
        )
        response = await auth_servicer.Login(login_request, grpc_context)

        assert response.access_token
        assert response.refresh_token
        assert response.user.email == "logintest@example.com"
        assert response.access_token_expires_at.seconds > 0
        assert response.refresh_token_expires_at.seconds > 0

    async def test_login_wrong_password_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test login with wrong password returns UNAUTHENTICATED."""
        from llamatrade.v1 import auth_pb2

        # First register a user
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Wrong Pass Co",
            email="wrongpass@example.com",
            password="CorrectPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        # Try to login with wrong password
        login_request = auth_pb2.LoginRequest(
            email="wrongpass@example.com",
            password="WrongPassword123!",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.Login(login_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "invalid" in exc_info.value.details().lower()

    async def test_login_nonexistent_user_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test login with nonexistent email returns UNAUTHENTICATED."""
        from llamatrade.v1 import auth_pb2

        login_request = auth_pb2.LoginRequest(
            email="doesnotexist@example.com",
            password="AnyPassword123!",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.Login(login_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


class TestTokenRefresh:
    """Token refresh tests."""

    async def test_refresh_token_returns_new_tokens(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test refresh token returns new access and refresh tokens."""
        from llamatrade.v1 import auth_pb2

        # Register and login to get tokens
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Refresh Test Co",
            email="refreshtest@example.com",
            password="TestPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(
            email="refreshtest@example.com",
            password="TestPassword123!",
        )
        login_response = await auth_servicer.Login(login_request, grpc_context)

        # Wait a bit so new token has different iat
        await asyncio.sleep(1.1)

        # Refresh the token
        refresh_request = auth_pb2.RefreshTokenRequest(
            refresh_token=login_response.refresh_token,
        )
        response = await auth_servicer.RefreshToken(refresh_request, grpc_context)

        assert response.access_token
        assert response.refresh_token
        # New tokens should be different (different iat)
        assert response.access_token != login_response.access_token

    async def test_refresh_with_invalid_token_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test refresh with invalid token returns UNAUTHENTICATED."""
        from llamatrade.v1 import auth_pb2

        refresh_request = auth_pb2.RefreshTokenRequest(
            refresh_token="invalid.refresh.token",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.RefreshToken(refresh_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED

    async def test_refresh_with_access_token_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test refresh using an access token (instead of refresh) fails."""
        from llamatrade.v1 import auth_pb2

        # Register and login to get tokens
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Access Token Test Co",
            email="accesstokentest@example.com",
            password="TestPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(
            email="accesstokentest@example.com",
            password="TestPassword123!",
        )
        login_response = await auth_servicer.Login(login_request, grpc_context)

        # Try to use access_token as refresh_token
        refresh_request = auth_pb2.RefreshTokenRequest(
            refresh_token=login_response.access_token,  # Wrong token type
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.RefreshToken(refresh_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestGetCurrentUser:
    """Current user endpoint tests."""

    async def test_get_current_user_returns_user_info(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test GetCurrentUser returns current user information."""
        from llamatrade.v1 import auth_pb2

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Me Test Co",
            email="metest@example.com",
            password="TestPassword123!",
            first_name="Test",
            last_name="User",
        )
        await auth_servicer.Register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(
            email="metest@example.com",
            password="TestPassword123!",
        )
        login_response = await auth_servicer.Login(login_request, grpc_context)

        # Set token in metadata
        grpc_context.set_metadata([
            ("authorization", f"Bearer {login_response.access_token}"),
        ])

        # Get current user
        get_user_request = auth_pb2.GetCurrentUserRequest()
        response = await auth_servicer.GetCurrentUser(get_user_request, grpc_context)

        assert response.user.email == "metest@example.com"
        assert response.user.first_name == "Test"
        assert response.user.last_name == "User"
        assert response.user.id
        assert response.user.tenant_id
        assert response.tenant.id
        assert response.tenant.name == "Me Test Co"

    async def test_get_current_user_without_token_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test GetCurrentUser without token returns UNAUTHENTICATED."""
        from llamatrade.v1 import auth_pb2

        # No metadata set
        get_user_request = auth_pb2.GetCurrentUserRequest()

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.GetCurrentUser(get_user_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED

    async def test_get_current_user_with_invalid_token_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test GetCurrentUser with invalid token returns UNAUTHENTICATED."""
        from llamatrade.v1 import auth_pb2

        grpc_context.set_metadata([
            ("authorization", "Bearer invalid.token.here"),
        ])

        get_user_request = auth_pb2.GetCurrentUserRequest()

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.GetCurrentUser(get_user_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


class TestPasswordChange:
    """Password change tests."""

    async def test_change_password_success(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test changing password with correct current password."""
        from llamatrade.v1 import auth_pb2

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Password Change Co",
            email="passchange@example.com",
            password="OldPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(
            email="passchange@example.com",
            password="OldPassword123!",
        )
        login_response = await auth_servicer.Login(login_request, grpc_context)

        # Set token in metadata
        grpc_context.set_metadata([
            ("authorization", f"Bearer {login_response.access_token}"),
        ])

        # Change password
        change_request = auth_pb2.ChangePasswordRequest(
            current_password="OldPassword123!",
            new_password="NewPassword456!",
        )
        response = await auth_servicer.ChangePassword(change_request, grpc_context)

        assert response.success is True

        # Verify can login with new password
        new_login_request = auth_pb2.LoginRequest(
            email="passchange@example.com",
            password="NewPassword456!",
        )
        new_context = MockServicerContext()
        new_response = await auth_servicer.Login(new_login_request, new_context)
        assert new_response.access_token

        # Verify old password no longer works
        old_login_request = auth_pb2.LoginRequest(
            email="passchange@example.com",
            password="OldPassword123!",
        )
        old_context = MockServicerContext()
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.Login(old_login_request, old_context)
        assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED

    async def test_change_password_wrong_current_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test changing password with wrong current password fails."""
        from llamatrade.v1 import auth_pb2

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Wrong Current Co",
            email="wrongcurrent@example.com",
            password="RealPassword123!",
        )
        await auth_servicer.Register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(
            email="wrongcurrent@example.com",
            password="RealPassword123!",
        )
        login_response = await auth_servicer.Login(login_request, grpc_context)

        # Set token in metadata
        grpc_context.set_metadata([
            ("authorization", f"Bearer {login_response.access_token}"),
        ])

        # Try to change with wrong current password
        change_request = auth_pb2.ChangePasswordRequest(
            current_password="WrongPassword123!",
            new_password="NewPassword456!",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await auth_servicer.ChangePassword(change_request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
