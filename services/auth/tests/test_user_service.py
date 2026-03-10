"""Tests for UserService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.models import UserUpdate
from src.services.user_service import UserService

# === Test Fixtures ===


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def user_service(mock_db: MagicMock) -> UserService:
    """Create a UserService instance with mock db."""
    return UserService(mock_db)


@pytest.fixture
def test_tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def test_user_id() -> UUID:
    return uuid4()


# === create_user Tests ===


class TestCreateUser:
    """Tests for create_user method."""

    async def test_create_user_success(
        self, user_service: UserService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test creating a user successfully."""
        email = "test@example.com"
        password = "SecurePass123"

        result = await user_service.create_user(
            tenant_id=test_tenant_id,
            email=email,
            password=password,
            role="user",
        )

        assert result.email == email
        assert result.tenant_id == test_tenant_id
        assert result.role == "user"
        assert result.is_active is True
        mock_db.execute.assert_called_once()

    async def test_create_user_with_admin_role(
        self, user_service: UserService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test creating a user with admin role."""
        result = await user_service.create_user(
            tenant_id=test_tenant_id,
            email="admin@example.com",
            password="AdminPass123",
            role="admin",
        )

        assert result.role == "admin"


# === get_user Tests ===


class TestGetUser:
    """Tests for get_user method."""

    async def test_get_user_found(
        self,
        user_service: UserService,
        mock_db: MagicMock,
        test_user_id: UUID,
        test_tenant_id: UUID,
    ) -> None:
        """Test getting a user that exists."""
        now = datetime.now(UTC)
        mock_row = MagicMock()
        mock_row.id = test_user_id
        mock_row.tenant_id = test_tenant_id
        mock_row.email = "test@example.com"
        mock_row.role = "user"
        mock_row.is_active = True
        mock_row.created_at = now

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user(test_user_id)

        assert result is not None
        assert result.id == test_user_id
        assert result.email == "test@example.com"

    async def test_get_user_not_found(
        self, user_service: UserService, mock_db: MagicMock, test_user_id: UUID
    ) -> None:
        """Test getting a user that doesn't exist."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user(test_user_id)

        assert result is None


# === get_user_with_password Tests ===


class TestGetUserWithPassword:
    """Tests for get_user_with_password method."""

    async def test_get_user_with_password_found(
        self,
        user_service: UserService,
        mock_db: MagicMock,
        test_user_id: UUID,
        test_tenant_id: UUID,
    ) -> None:
        """Test getting user with password hash."""
        now = datetime.now(UTC)
        mock_row = MagicMock()
        mock_row.id = test_user_id
        mock_row.tenant_id = test_tenant_id
        mock_row.email = "test@example.com"
        mock_row.password_hash = "$2b$12$hashedpassword"
        mock_row.role = "user"
        mock_row.is_active = True
        mock_row.created_at = now

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user_with_password(test_user_id)

        assert result is not None
        assert result.password_hash == "$2b$12$hashedpassword"

    async def test_get_user_with_password_not_found(
        self, user_service: UserService, mock_db: MagicMock, test_user_id: UUID
    ) -> None:
        """Test getting non-existent user with password."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user_with_password(test_user_id)

        assert result is None


# === get_user_by_email Tests ===


class TestGetUserByEmail:
    """Tests for get_user_by_email method."""

    async def test_get_user_by_email_found(
        self,
        user_service: UserService,
        mock_db: MagicMock,
        test_user_id: UUID,
        test_tenant_id: UUID,
    ) -> None:
        """Test getting user by email."""
        now = datetime.now(UTC)
        mock_row = MagicMock()
        mock_row.id = test_user_id
        mock_row.tenant_id = test_tenant_id
        mock_row.email = "test@example.com"
        mock_row.password_hash = "$2b$12$hashedpassword"
        mock_row.role = "user"
        mock_row.is_active = True
        mock_row.created_at = now

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user_by_email("test@example.com")

        assert result is not None
        assert result.email == "test@example.com"

    async def test_get_user_by_email_not_found(
        self, user_service: UserService, mock_db: MagicMock
    ) -> None:
        """Test getting non-existent user by email."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await user_service.get_user_by_email("nonexistent@example.com")

        assert result is None


# === list_users Tests ===


class TestListUsers:
    """Tests for list_users method."""

    async def test_list_users_returns_empty(
        self, user_service: UserService, test_tenant_id: UUID
    ) -> None:
        """Test listing users returns empty (stub)."""
        users, total = await user_service.list_users(test_tenant_id)

        assert users == []
        assert total == 0


# === update_user Tests ===


class TestUpdateUser:
    """Tests for update_user method."""

    async def test_update_user_returns_none(
        self, user_service: UserService, test_user_id: UUID, test_tenant_id: UUID
    ) -> None:
        """Test updating user returns None (stub)."""
        update = UserUpdate(email="new@example.com")

        result = await user_service.update_user(test_user_id, test_tenant_id, update)

        assert result is None


# === update_password Tests ===


class TestUpdatePassword:
    """Tests for update_password method."""

    async def test_update_password_executes(
        self, user_service: UserService, mock_db: MagicMock, test_user_id: UUID
    ) -> None:
        """Test updating password executes query."""
        new_hash = "$2b$12$newhash"

        await user_service.update_password(test_user_id, new_hash)

        mock_db.execute.assert_called_once()


# === delete_user Tests ===


class TestDeleteUser:
    """Tests for delete_user method."""

    async def test_delete_user_returns_false(
        self, user_service: UserService, test_user_id: UUID, test_tenant_id: UUID
    ) -> None:
        """Test deleting user returns False (stub)."""
        result = await user_service.delete_user(test_user_id, test_tenant_id)

        assert result is False


# === _hash_password Tests ===


class TestHashPassword:
    """Tests for _hash_password method."""

    def test_hash_password_returns_hash(self, user_service: UserService) -> None:
        """Test password hashing returns bcrypt hash."""
        password = "TestPassword123"

        hashed = user_service._hash_password(password)

        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_hash_password_different_each_time(self, user_service: UserService) -> None:
        """Test password hashing produces different hashes."""
        password = "TestPassword123"

        hash1 = user_service._hash_password(password)
        hash2 = user_service._hash_password(password)

        assert hash1 != hash2  # Different salts
