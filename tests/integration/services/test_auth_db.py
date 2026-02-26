"""Auth service integration tests with real database.

These tests verify that the auth service works correctly with PostgreSQL,
including user registration, login, token management, and email uniqueness.

Note: These tests require the auth service package to be installed:
    pip install -e services/auth
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Tenant, User

# Import auth service app - must be done after environment is set up
pytestmark = pytest.mark.integration

# Check if auth service is installed
try:
    from src.main import app as _auth_app
    AUTH_SERVICE_AVAILABLE = True
except ImportError:
    AUTH_SERVICE_AVAILABLE = False
    _auth_app = None


@pytest.fixture
def auth_app():
    """Get the auth service FastAPI app."""
    if not AUTH_SERVICE_AVAILABLE:
        pytest.skip("Auth service not installed. Run: pip install -e services/auth")
    return _auth_app


@pytest.fixture
async def integration_client(
    auth_app,
    db_session: AsyncSession,
) -> AsyncClient:
    """Create async client with real database session for integration testing.

    This client uses the actual auth service app but with the test database.
    """
    from llamatrade_db import get_db

    async def override_get_db():
        yield db_session

    auth_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    auth_app.dependency_overrides.clear()


class TestHealthCheck:
    """Health endpoint tests."""

    async def test_health_returns_healthy(self, integration_client: AsyncClient):
        """Test health endpoint returns healthy status."""
        response = await integration_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "auth"


class TestUserRegistration:
    """User registration tests with real database."""

    async def test_register_creates_tenant_and_user(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test registration creates both tenant and user in database."""
        response = await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "admin"
        assert "id" in data
        assert "tenant_id" in data

        # Verify user exists in database
        user_result = await db_session.execute(
            select(User).where(User.email == "newuser@example.com")
        )
        user = user_result.scalar_one_or_none()
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.role == "admin"
        assert user.is_active is True

        # Verify tenant exists in database
        tenant_result = await db_session.execute(
            select(Tenant).where(Tenant.id == user.tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        assert tenant is not None
        assert tenant.is_active is True

    async def test_register_duplicate_email_fails(
        self,
        integration_client: AsyncClient,
        test_user: User,
    ):
        """Test registration fails if email already exists."""
        response = await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Another Company",
                "email": test_user.email,  # Already exists
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    async def test_register_invalid_email_fails(
        self,
        integration_client: AsyncClient,
    ):
        """Test registration fails with invalid email format."""
        response = await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "not-an-email",
                "password": "SecurePassword123!",
            },
        )

        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """User login tests with real database."""

    async def test_login_returns_valid_tokens(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test login with correct credentials returns tokens."""
        # First register a user
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Login Test Co",
                "email": "logintest@example.com",
                "password": "TestPassword123!",
            },
        )

        # Then login
        response = await integration_client.post(
            "/auth/login",
            json={
                "email": "logintest@example.com",
                "password": "TestPassword123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_login_wrong_password_fails(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test login with wrong password returns 401."""
        # First register a user
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Wrong Pass Co",
                "email": "wrongpass@example.com",
                "password": "CorrectPassword123!",
            },
        )

        # Try to login with wrong password
        response = await integration_client.post(
            "/auth/login",
            json={
                "email": "wrongpass@example.com",
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()

    async def test_login_nonexistent_user_fails(
        self,
        integration_client: AsyncClient,
    ):
        """Test login with nonexistent email returns 401."""
        response = await integration_client.post(
            "/auth/login",
            json={
                "email": "doesnotexist@example.com",
                "password": "AnyPassword123!",
            },
        )

        assert response.status_code == 401


class TestTokenRefresh:
    """Token refresh tests."""

    async def test_refresh_token_returns_new_tokens(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test refresh token returns new access and refresh tokens."""
        import asyncio

        # Register and login to get tokens
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Refresh Test Co",
                "email": "refreshtest@example.com",
                "password": "TestPassword123!",
            },
        )

        login_response = await integration_client.post(
            "/auth/login",
            json={
                "email": "refreshtest@example.com",
                "password": "TestPassword123!",
            },
        )
        tokens = login_response.json()

        # Wait for 1 second so new token has different iat timestamp
        await asyncio.sleep(1.1)

        # Refresh the token
        response = await integration_client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # New tokens should be different (different iat timestamp)
        assert data["access_token"] != tokens["access_token"]

    async def test_refresh_with_invalid_token_fails(
        self,
        integration_client: AsyncClient,
    ):
        """Test refresh with invalid token returns 401."""
        response = await integration_client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid.refresh.token"},
        )

        assert response.status_code == 401

    async def test_refresh_with_access_token_fails(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test refresh using an access token (instead of refresh) fails."""
        # Register and login to get tokens
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Access Token Test Co",
                "email": "accesstokentest@example.com",
                "password": "TestPassword123!",
            },
        )

        login_response = await integration_client.post(
            "/auth/login",
            json={
                "email": "accesstokentest@example.com",
                "password": "TestPassword123!",
            },
        )
        tokens = login_response.json()

        # Try to use access_token as refresh_token
        response = await integration_client.post(
            "/auth/refresh",
            json={"refresh_token": tokens["access_token"]},
        )

        assert response.status_code == 401


class TestGetCurrentUser:
    """Current user endpoint tests."""

    async def test_get_me_returns_user_info(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test /auth/me returns current user information."""
        # Register and login
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Me Test Co",
                "email": "metest@example.com",
                "password": "TestPassword123!",
            },
        )

        login_response = await integration_client.post(
            "/auth/login",
            json={
                "email": "metest@example.com",
                "password": "TestPassword123!",
            },
        )
        tokens = login_response.json()

        # Get current user
        response = await integration_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "metest@example.com"
        assert "id" in data
        assert "tenant_id" in data

    async def test_get_me_without_token_fails(
        self,
        integration_client: AsyncClient,
    ):
        """Test /auth/me without token returns 401."""
        response = await integration_client.get("/auth/me")

        assert response.status_code == 401

    async def test_get_me_with_invalid_token_fails(
        self,
        integration_client: AsyncClient,
    ):
        """Test /auth/me with invalid token returns 401."""
        response = await integration_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401


class TestPasswordChange:
    """Password change tests."""

    async def test_change_password_success(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test changing password with correct current password."""
        # Register and login
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Password Change Co",
                "email": "passchange@example.com",
                "password": "OldPassword123!",
            },
        )

        login_response = await integration_client.post(
            "/auth/login",
            json={
                "email": "passchange@example.com",
                "password": "OldPassword123!",
            },
        )
        tokens = login_response.json()

        # Change password
        response = await integration_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword456!",
            },
        )

        assert response.status_code == 200

        # Verify can login with new password
        new_login = await integration_client.post(
            "/auth/login",
            json={
                "email": "passchange@example.com",
                "password": "NewPassword456!",
            },
        )
        assert new_login.status_code == 200

        # Verify old password no longer works
        old_login = await integration_client.post(
            "/auth/login",
            json={
                "email": "passchange@example.com",
                "password": "OldPassword123!",
            },
        )
        assert old_login.status_code == 401

    async def test_change_password_wrong_current_fails(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test changing password with wrong current password fails."""
        # Register and login
        await integration_client.post(
            "/auth/register",
            json={
                "tenant_name": "Wrong Current Co",
                "email": "wrongcurrent@example.com",
                "password": "RealPassword123!",
            },
        )

        login_response = await integration_client.post(
            "/auth/login",
            json={
                "email": "wrongcurrent@example.com",
                "password": "RealPassword123!",
            },
        )
        tokens = login_response.json()

        # Try to change with wrong current password
        response = await integration_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewPassword456!",
            },
        )

        assert response.status_code == 400
