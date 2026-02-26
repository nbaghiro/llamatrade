"""Tests for authentication endpoints and services."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import (
    TokenResponse,
    UserResponse,
    UserWithPassword,
)
from src.services.auth_service import (
    JWT_ALGORITHM,
    JWT_SECRET,
    AuthService,
    get_auth_service,
)
from src.services.tenant_service import TenantService
from src.services.user_service import UserService, get_user_service

# ===================
# Fixtures
# ===================


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_auth_service():
    """Create a mock auth service."""
    return AsyncMock(spec=AuthService)


@pytest.fixture
def mock_user_service():
    """Create a mock user service."""
    return AsyncMock(spec=UserService)


@pytest.fixture
def mock_tenant_service():
    """Create a mock tenant service."""
    return AsyncMock(spec=TenantService)


def make_auth_context(tenant_id: UUID, user_id: UUID, roles: list[str] | None = None):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="test@example.com",
        roles=roles or ["admin"],
    )


def make_user_response(
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    email: str = "test@example.com",
    role: str = "user",
    is_active: bool = True,
) -> UserResponse:
    """Create a mock UserResponse."""
    return UserResponse(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        email=email,  # Pydantic validates automatically
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def make_user_with_password(
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    email: str = "test@example.com",
    password_hash: str = "hashed_password",
    role: str = "user",
    is_active: bool = True,
) -> UserWithPassword:
    """Create a mock UserWithPassword."""
    return UserWithPassword(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        email=email,  # Pydantic validates automatically
        password_hash=password_hash,
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def make_token_response() -> TokenResponse:
    """Create a mock TokenResponse."""
    return TokenResponse(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_type="bearer",
        expires_in=1800,
    )


# ===================
# Health Check Tests
# ===================


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth"


# ===================
# Registration Tests
# ===================


class TestRegistration:
    """Tests for /auth/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, mock_auth_service):
        """Test successful user registration."""
        mock_auth_service.register.return_value = make_user_response(
            email="newuser@example.com",
            role="admin",
        )

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/register",
                    json={
                        "tenant_name": "Test Company",
                        "email": "newuser@example.com",
                        "password": "SecurePass123",
                    },
                )
                assert response.status_code == 201
                data = response.json()
                assert data["email"] == "newuser@example.com"
                assert data["role"] == "admin"
                mock_auth_service.register.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_register_invalid_password_too_short(self, client):
        """Test registration with password too short."""
        response = await client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "test@example.com",
                "password": "short",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_password_no_uppercase(self, client):
        """Test registration with password missing uppercase."""
        response = await client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "test@example.com",
                "password": "alllowercase123",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_password_no_digit(self, client):
        """Test registration with password missing digit."""
        response = await client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "test@example.com",
                "password": "NoDigitsHere",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client):
        """Test registration with invalid email."""
        response = await client.post(
            "/auth/register",
            json={
                "tenant_name": "Test Company",
                "email": "not-an-email",
                "password": "SecurePass123",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, mock_auth_service):
        """Test registration with already existing email."""
        mock_auth_service.register.side_effect = ValueError("Email already registered")

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/register",
                    json={
                        "tenant_name": "Test Company",
                        "email": "existing@example.com",
                        "password": "SecurePass123",
                    },
                )
                assert response.status_code == 400
                assert "already registered" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_register_missing_tenant_name(self, client):
        """Test registration without tenant name."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "SecurePass123",
            },
        )
        assert response.status_code == 422


# ===================
# Login Tests
# ===================


class TestLogin:
    """Tests for /auth/login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, mock_auth_service):
        """Test successful login."""
        mock_auth_service.login.return_value = make_token_response()

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/login",
                    json={
                        "email": "test@example.com",
                        "password": "SecurePass123",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "refresh_token" in data
                assert data["token_type"] == "bearer"
                mock_auth_service.login.assert_called_once_with(
                    email="test@example.com",
                    password="SecurePass123",
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, mock_auth_service):
        """Test login with invalid credentials."""
        mock_auth_service.login.return_value = None

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/login",
                    json={
                        "email": "test@example.com",
                        "password": "WrongPassword123",
                    },
                )
                assert response.status_code == 401
                assert "invalid" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client):
        """Test login with invalid email format."""
        response = await client.post(
            "/auth/login",
            json={
                "email": "invalid-email",
                "password": "SecurePass123",
            },
        )
        assert response.status_code == 422


# ===================
# Token Refresh Tests
# ===================


class TestTokenRefresh:
    """Tests for /auth/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, mock_auth_service):
        """Test successful token refresh."""
        mock_auth_service.refresh_token.return_value = make_token_response()

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/refresh",
                    json={"refresh_token": "valid_refresh_token"},
                )
                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "refresh_token" in data
                mock_auth_service.refresh_token.assert_called_once_with("valid_refresh_token")
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, mock_auth_service):
        """Test token refresh with invalid token."""
        mock_auth_service.refresh_token.return_value = None

        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/refresh",
                    json={"refresh_token": "invalid_token"},
                )
                assert response.status_code == 401
                assert "invalid" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_refresh_token_missing(self, client):
        """Test token refresh without providing token."""
        response = await client.post(
            "/auth/refresh",
            json={},
        )
        assert response.status_code == 422


# ===================
# Logout Tests
# ===================


class TestLogout:
    """Tests for /auth/logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, tenant_id, user_id, mock_auth_service):
        """Test successful logout."""
        ctx = make_auth_context(tenant_id, user_id)
        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/auth/logout")
                assert response.status_code == 200
                assert "logged out" in response.json()["message"].lower()
                mock_auth_service.logout.assert_called_once_with(user_id=user_id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_logout_unauthorized(self, client):
        """Test logout without authentication."""
        response = await client.post("/auth/logout")
        assert response.status_code == 401


# ===================
# Get Current User Tests
# ===================


class TestGetCurrentUser:
    """Tests for /auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_success(self, tenant_id, user_id, mock_user_service):
        """Test getting current user info."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_user_service.get_user.return_value = make_user_response(
            user_id=user_id,
            tenant_id=tenant_id,
        )

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/auth/me")
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(user_id)
                assert data["tenant_id"] == str(tenant_id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_me_user_not_found(self, tenant_id, user_id, mock_user_service):
        """Test getting current user when user doesn't exist."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_user_service.get_user.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/auth/me")
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_me_unauthorized(self, client):
        """Test getting current user without authentication."""
        response = await client.get("/auth/me")
        assert response.status_code == 401


# ===================
# Change Password Tests
# ===================


class TestChangePassword:
    """Tests for /auth/change-password endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, tenant_id, user_id, mock_auth_service):
        """Test successful password change."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_auth_service.change_password.return_value = True

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/change-password",
                    json={
                        "current_password": "OldPass123",
                        "new_password": "NewPass456",
                    },
                )
                assert response.status_code == 200
                assert "changed" in response.json()["message"].lower()
                mock_auth_service.change_password.assert_called_once_with(
                    user_id=user_id,
                    current_password="OldPass123",
                    new_password="NewPass456",
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, tenant_id, user_id, mock_auth_service):
        """Test password change with wrong current password."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_auth_service.change_password.return_value = False

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/change-password",
                    json={
                        "current_password": "WrongPass123",
                        "new_password": "NewPass456",
                    },
                )
                assert response.status_code == 400
                assert "incorrect" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_change_password_invalid_new_password(self, tenant_id, user_id):
        """Test password change with invalid new password."""
        ctx = make_auth_context(tenant_id, user_id)
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/auth/change-password",
                    json={
                        "current_password": "OldPass123",
                        "new_password": "weak",
                    },
                )
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_change_password_unauthorized(self, client):
        """Test password change without authentication."""
        response = await client.post(
            "/auth/change-password",
            json={
                "current_password": "OldPass123",
                "new_password": "NewPass456",
            },
        )
        assert response.status_code == 401


# ===================
# Auth Service Unit Tests
# ===================


class TestAuthServiceUnit:
    """Unit tests for AuthService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def auth_service(self, mock_db, mock_user_service, mock_tenant_service):
        """Create AuthService with mocked dependencies."""
        return AuthService(mock_db, mock_user_service, mock_tenant_service)

    @pytest.mark.asyncio
    async def test_login_returns_tokens_on_valid_credentials(self, auth_service, mock_user_service):
        """Test that login returns tokens for valid credentials."""
        user = make_user_with_password(
            password_hash="$2b$12$validhash",
        )
        mock_user_service.get_user_by_email.return_value = user

        with patch.object(auth_service, "_verify_password", return_value=True):
            result = await auth_service.login(
                email="test@example.com",
                password="ValidPass123",
            )

        assert result is not None
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_returns_none_for_nonexistent_user(self, auth_service, mock_user_service):
        """Test that login returns None for non-existent user."""
        mock_user_service.get_user_by_email.return_value = None

        result = await auth_service.login(
            email="nonexistent@example.com",
            password="AnyPass123",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_login_returns_none_for_inactive_user(self, auth_service, mock_user_service):
        """Test that login returns None for inactive user."""
        user = make_user_with_password(is_active=False)
        mock_user_service.get_user_by_email.return_value = user

        result = await auth_service.login(
            email="inactive@example.com",
            password="ValidPass123",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_login_returns_none_for_wrong_password(self, auth_service, mock_user_service):
        """Test that login returns None for wrong password."""
        user = make_user_with_password()
        mock_user_service.get_user_by_email.return_value = user

        with patch.object(auth_service, "_verify_password", return_value=False):
            result = await auth_service.login(
                email="test@example.com",
                password="WrongPass123",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_token_returns_new_tokens(self, auth_service, mock_user_service):
        """Test that refresh_token returns new tokens for valid refresh token."""
        user = make_user_response()
        mock_user_service.get_user.return_value = user

        # Create a valid refresh token
        payload = {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "type": "refresh",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(days=7),
        }
        valid_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = await auth_service.refresh_token(valid_token)

        assert result is not None
        assert result.access_token
        assert result.refresh_token

    @pytest.mark.asyncio
    async def test_refresh_token_returns_none_for_access_token(
        self, auth_service, mock_user_service
    ):
        """Test that refresh_token returns None when given an access token."""
        # Create an access token (not refresh)
        payload = {
            "sub": str(uuid4()),
            "type": "access",  # Wrong type
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        }
        access_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = await auth_service.refresh_token(access_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_token_returns_none_for_expired_token(self, auth_service):
        """Test that refresh_token returns None for expired token."""
        payload = {
            "sub": str(uuid4()),
            "type": "refresh",
            "iat": datetime.now(UTC) - timedelta(days=10),
            "exp": datetime.now(UTC) - timedelta(days=3),  # Expired
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = await auth_service.refresh_token(expired_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_token_returns_none_for_invalid_token(self, auth_service):
        """Test that refresh_token returns None for malformed token."""
        result = await auth_service.refresh_token("invalid_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_change_password_success(self, auth_service, mock_user_service):
        """Test successful password change."""
        user = make_user_with_password()
        mock_user_service.get_user_with_password.return_value = user

        with patch.object(auth_service, "_verify_password", return_value=True):
            result = await auth_service.change_password(
                user_id=user.id,
                current_password="OldPass123",
                new_password="NewPass456",
            )

        assert result is True
        mock_user_service.update_password.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_fails_for_nonexistent_user(
        self, auth_service, mock_user_service
    ):
        """Test password change fails for non-existent user."""
        mock_user_service.get_user_with_password.return_value = None

        result = await auth_service.change_password(
            user_id=uuid4(),
            current_password="OldPass123",
            new_password="NewPass456",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_change_password_fails_for_wrong_current_password(
        self, auth_service, mock_user_service
    ):
        """Test password change fails with wrong current password."""
        user = make_user_with_password()
        mock_user_service.get_user_with_password.return_value = user

        with patch.object(auth_service, "_verify_password", return_value=False):
            result = await auth_service.change_password(
                user_id=user.id,
                current_password="WrongPass123",
                new_password="NewPass456",
            )

        assert result is False
        mock_user_service.update_password.assert_not_called()

    def test_verify_password_correct(self, auth_service):
        """Test password verification with correct password."""
        import bcrypt

        password = "TestPass123"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt).decode()

        result = auth_service._verify_password(password, hashed)

        assert result is True

    def test_verify_password_incorrect(self, auth_service):
        """Test password verification with incorrect password."""
        import bcrypt

        correct_password = "CorrectPass123"
        wrong_password = "WrongPass456"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(correct_password.encode(), salt).decode()

        result = auth_service._verify_password(wrong_password, hashed)

        assert result is False

    def test_hash_password(self, auth_service):
        """Test password hashing."""
        password = "TestPass123"

        hashed = auth_service._hash_password(password)

        # Verify it's a valid bcrypt hash
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_create_access_token(self, auth_service):
        """Test access token creation."""
        user = make_user_response()

        token = auth_service._create_access_token(user)

        # Decode and verify
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == str(user.id)
        assert payload["tenant_id"] == str(user.tenant_id)
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self, auth_service):
        """Test refresh token creation."""
        user = make_user_response()

        token = auth_service._create_refresh_token(user)

        # Decode and verify
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == str(user.id)
        assert payload["tenant_id"] == str(user.tenant_id)
        assert payload["type"] == "refresh"
        assert "exp" in payload
