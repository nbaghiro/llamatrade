"""Unit tests for auth service layer.

These tests verify the AuthService business logic without HTTP/gRPC layer.
For endpoint tests, see test_grpc_auth.py.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.models import UserResponse, UserWithPassword
from src.services.auth_service import (
    JWT_ALGORITHM,
    JWT_SECRET,
    AuthService,
)
from src.services.tenant_service import TenantService
from src.services.user_service import UserService

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
def mock_user_service():
    """Create a mock user service."""
    return AsyncMock(spec=UserService)


@pytest.fixture
def mock_tenant_service():
    """Create a mock tenant service."""
    return AsyncMock(spec=TenantService)


def make_user_response(
    user_id=None,
    tenant_id=None,
    email="test@example.com",
    role="user",
    is_active=True,
):
    """Create a mock UserResponse."""
    return UserResponse(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        email=email,
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


def make_user_with_password(
    user_id=None,
    tenant_id=None,
    email="test@example.com",
    password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.",
    role="user",
    is_active=True,
):
    """Create a mock UserWithPassword."""
    return UserWithPassword(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        email=email,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


# ===================
# Health Check Test
# ===================


async def test_health_check(client):
    """Test health endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth"


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

    async def test_login_returns_tokens_on_valid_credentials(self, auth_service, mock_user_service):
        """Test that login returns tokens for valid credentials."""
        user = make_user_with_password(password_hash="$2b$12$validhash")
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

    async def test_login_returns_none_for_nonexistent_user(self, auth_service, mock_user_service):
        """Test that login returns None for non-existent user."""
        mock_user_service.get_user_by_email.return_value = None

        result = await auth_service.login(
            email="nonexistent@example.com",
            password="AnyPass123",
        )

        assert result is None

    async def test_login_returns_none_for_inactive_user(self, auth_service, mock_user_service):
        """Test that login returns None for inactive user."""
        user = make_user_with_password(is_active=False)
        mock_user_service.get_user_by_email.return_value = user

        result = await auth_service.login(
            email="inactive@example.com",
            password="ValidPass123",
        )

        assert result is None

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

    async def test_refresh_token_returns_none_for_access_token(
        self, auth_service, mock_user_service
    ):
        """Test that refresh_token returns None when given an access token."""
        payload = {
            "sub": str(uuid4()),
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        }
        access_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = await auth_service.refresh_token(access_token)

        assert result is None

    async def test_refresh_token_returns_none_for_expired_token(self, auth_service):
        """Test that refresh_token returns None for expired token."""
        payload = {
            "sub": str(uuid4()),
            "type": "refresh",
            "iat": datetime.now(UTC) - timedelta(days=10),
            "exp": datetime.now(UTC) - timedelta(days=3),
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = await auth_service.refresh_token(expired_token)

        assert result is None

    async def test_refresh_token_returns_none_for_invalid_token(self, auth_service):
        """Test that refresh_token returns None for malformed token."""
        result = await auth_service.refresh_token("invalid_token")

        assert result is None

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

        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_create_access_token(self, auth_service):
        """Test access token creation."""
        user = make_user_response()

        token = auth_service._create_access_token(user)

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == str(user.id)
        assert payload["tenant_id"] == str(user.tenant_id)
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self, auth_service):
        """Test refresh token creation."""
        user = make_user_response()

        token = auth_service._create_refresh_token(user)

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == str(user.id)
        assert payload["tenant_id"] == str(user.tenant_id)
        assert payload["type"] == "refresh"
        assert "exp" in payload
