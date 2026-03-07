"""Tests for APIKeyService to improve coverage."""

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.services.api_key_service import APIKeyService, get_api_key_service

# === Test Fixtures ===


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def api_key_service(mock_db: MagicMock) -> APIKeyService:
    """Create an APIKeyService instance."""
    return APIKeyService(mock_db)


@pytest.fixture
def test_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def test_tenant_id() -> UUID:
    return uuid4()


# === create_api_key Tests ===


class TestCreateAPIKey:
    """Tests for create_api_key method."""

    async def test_create_api_key_success(
        self, api_key_service: APIKeyService, test_user_id: UUID, test_tenant_id: UUID
    ) -> None:
        """Test creating an API key successfully."""
        with patch("src.services.api_key_service.generate_api_key") as mock_gen:
            mock_gen.return_value = ("lt_test_key_123", "hashed_key")

            result = await api_key_service.create_api_key(
                user_id=test_user_id,
                tenant_id=test_tenant_id,
                name="Test Key",
                scopes=["read", "write"],
            )

            assert result.name == "Test Key"
            assert result.api_key == "lt_test_key_123"
            assert result.scopes == ["read", "write"]
            assert result.id is not None

    async def test_create_api_key_default_scopes(
        self, api_key_service: APIKeyService, test_user_id: UUID, test_tenant_id: UUID
    ) -> None:
        """Test creating an API key with default scopes."""
        with patch("src.services.api_key_service.generate_api_key") as mock_gen:
            mock_gen.return_value = ("lt_test_key_456", "hashed_key")

            result = await api_key_service.create_api_key(
                user_id=test_user_id,
                tenant_id=test_tenant_id,
                name="Default Scopes Key",
                scopes=None,
            )

            assert result.scopes == ["read"]

    async def test_create_api_key_has_created_at(
        self, api_key_service: APIKeyService, test_user_id: UUID, test_tenant_id: UUID
    ) -> None:
        """Test that created API key has created_at timestamp."""
        with patch("src.services.api_key_service.generate_api_key") as mock_gen:
            mock_gen.return_value = ("lt_key", "hash")

            result = await api_key_service.create_api_key(
                user_id=test_user_id,
                tenant_id=test_tenant_id,
                name="Timestamped Key",
            )

            assert result.created_at is not None
            assert result.created_at.tzinfo == UTC


# === list_api_keys Tests ===


class TestListAPIKeys:
    """Tests for list_api_keys method."""

    async def test_list_api_keys_empty(
        self, api_key_service: APIKeyService, test_user_id: UUID
    ) -> None:
        """Test listing API keys returns empty list (stub implementation)."""
        keys, total = await api_key_service.list_api_keys(test_user_id)

        assert keys == []
        assert total == 0

    async def test_list_api_keys_with_pagination(
        self, api_key_service: APIKeyService, test_user_id: UUID
    ) -> None:
        """Test listing API keys with pagination params."""
        keys, total = await api_key_service.list_api_keys(
            user_id=test_user_id,
            page=2,
            page_size=10,
        )

        assert keys == []
        assert total == 0


# === validate_api_key Tests ===


class TestValidateAPIKey:
    """Tests for validate_api_key method."""

    async def test_validate_api_key_returns_none(self, api_key_service: APIKeyService) -> None:
        """Test validating API key returns None (stub implementation)."""
        result = await api_key_service.validate_api_key("lt_some_key_123")

        assert result is None

    async def test_validate_api_key_invalid_format(self, api_key_service: APIKeyService) -> None:
        """Test validating invalid API key format."""
        result = await api_key_service.validate_api_key("invalid_key")

        assert result is None


# === delete_api_key Tests ===


class TestDeleteAPIKey:
    """Tests for delete_api_key method."""

    async def test_delete_api_key_returns_false(
        self, api_key_service: APIKeyService, test_user_id: UUID
    ) -> None:
        """Test deleting API key returns False (stub implementation)."""
        key_id = uuid4()
        result = await api_key_service.delete_api_key(key_id, test_user_id)

        assert result is False


# === update_last_used Tests ===


class TestUpdateLastUsed:
    """Tests for update_last_used method."""

    async def test_update_last_used_completes(self, api_key_service: APIKeyService) -> None:
        """Test update_last_used completes without error."""
        key_id = uuid4()

        # Should not raise
        await api_key_service.update_last_used(key_id)


# === get_api_key_service Dependency ===


class TestGetAPIKeyServiceDependency:
    """Tests for get_api_key_service dependency."""

    async def test_returns_service_instance(self) -> None:
        """Test that get_api_key_service returns an APIKeyService."""
        mock_db = MagicMock()

        service = await get_api_key_service(db=mock_db)

        assert isinstance(service, APIKeyService)
        assert service.db == mock_db
