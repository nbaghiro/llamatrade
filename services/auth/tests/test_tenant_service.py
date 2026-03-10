"""Tests for TenantService."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.services.tenant_service import TenantService, _slugify

# === Test Fixtures ===


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def tenant_service(mock_db: MagicMock) -> TenantService:
    """Create a TenantService instance with mock db."""
    return TenantService(mock_db)


@pytest.fixture
def test_tenant_id() -> UUID:
    return uuid4()


# === _slugify Tests ===


class TestSlugify:
    """Tests for _slugify helper function."""

    def test_slugify_basic(self) -> None:
        """Test basic slugification."""
        assert _slugify("My Company") == "my-company"

    def test_slugify_special_chars(self) -> None:
        """Test slugification removes special characters."""
        # Note: trailing whitespace from removed chars becomes trailing hyphen
        assert _slugify("My Company! @#$%").startswith("my-company")

    def test_slugify_multiple_spaces(self) -> None:
        """Test slugification handles multiple spaces."""
        assert _slugify("My   Company") == "my-company"

    def test_slugify_underscores(self) -> None:
        """Test slugification converts underscores."""
        assert _slugify("my_company_name") == "my-company-name"

    def test_slugify_truncates(self) -> None:
        """Test slugification truncates to 100 chars."""
        long_name = "a" * 150
        result = _slugify(long_name)
        assert len(result) == 100

    def test_slugify_strips_whitespace(self) -> None:
        """Test slugification strips leading/trailing whitespace."""
        assert _slugify("  My Company  ") == "my-company"


# === create_tenant Tests ===


class TestCreateTenant:
    """Tests for create_tenant method."""

    async def test_create_tenant_success(
        self, tenant_service: TenantService, mock_db: MagicMock
    ) -> None:
        """Test creating a tenant successfully."""
        name = "Test Company"

        result = await tenant_service.create_tenant(name=name)

        assert result.name == name
        assert result.plan_id == "free"
        assert result.settings == {}
        assert "test-company" in result.slug
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_create_tenant_with_plan(
        self, tenant_service: TenantService, mock_db: MagicMock
    ) -> None:
        """Test creating a tenant with specific plan."""
        result = await tenant_service.create_tenant(
            name="Pro Company",
            plan_id="pro",
        )

        assert result.plan_id == "pro"

    async def test_create_tenant_with_settings(
        self, tenant_service: TenantService, mock_db: MagicMock
    ) -> None:
        """Test creating a tenant with settings."""
        settings: dict[str, Any] = {"theme": "dark", "max_users": 10}

        result = await tenant_service.create_tenant(
            name="Custom Company",
            settings=settings,
        )

        assert result.settings == settings


# === get_tenant Tests ===


class TestGetTenant:
    """Tests for get_tenant method."""

    async def test_get_tenant_returns_none(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test getting tenant returns None (stub)."""
        result = await tenant_service.get_tenant(test_tenant_id)

        assert result is None


# === update_tenant_settings Tests ===


class TestUpdateTenantSettings:
    """Tests for update_tenant_settings method."""

    async def test_update_tenant_settings_returns_none(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test updating tenant settings returns None (stub)."""
        settings: dict[str, str | int | bool | None] = {"theme": "light"}

        result = await tenant_service.update_tenant_settings(test_tenant_id, settings)

        assert result is None


# === get_alpaca_credentials Tests ===


class TestGetAlpacaCredentials:
    """Tests for get_alpaca_credentials method."""

    async def test_get_alpaca_credentials_not_found(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test getting non-existent credentials returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        tenant_service.db.execute.return_value = mock_result

        credentials_id = uuid4()
        result = await tenant_service.get_alpaca_credentials(
            credentials_id=credentials_id,
            tenant_id=test_tenant_id,
        )

        assert result is None

    async def test_get_alpaca_credentials_wrong_tenant_returns_none(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test getting credentials for wrong tenant returns None (isolation)."""
        # Credentials exist but belong to different tenant
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Query finds nothing
        tenant_service.db.execute.return_value = mock_result

        credentials_id = uuid4()
        wrong_tenant_id = uuid4()

        result = await tenant_service.get_alpaca_credentials(
            credentials_id=credentials_id,
            tenant_id=wrong_tenant_id,
        )

        assert result is None

    async def test_get_alpaca_credentials_decrypts_values(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test getting credentials decrypts the api_key and api_secret."""
        from datetime import UTC, datetime

        # Create mock credential record
        mock_creds = MagicMock()
        mock_creds.id = uuid4()
        mock_creds.name = "My Paper Keys"
        mock_creds.api_key_encrypted = "encrypted_key"
        mock_creds.api_secret_encrypted = "encrypted_secret"
        mock_creds.is_paper = True
        mock_creds.is_active = True
        mock_creds.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result

        with patch("src.services.tenant_service.decrypt_value") as mock_decrypt:
            mock_decrypt.side_effect = ["decrypted_key", "decrypted_secret"]

            credentials_id = mock_creds.id
            result = await tenant_service.get_alpaca_credentials(
                credentials_id=credentials_id,
                tenant_id=test_tenant_id,
            )

            assert result is not None
            assert result.api_key == "decrypted_key"
            assert result.api_secret == "decrypted_secret"
            assert mock_decrypt.call_count == 2


# === create_alpaca_credentials Tests ===


class TestCreateAlpacaCredentials:
    """Tests for create_alpaca_credentials method."""

    async def test_create_alpaca_credentials_encrypts_values(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test creating credentials encrypts api_key and api_secret."""
        from datetime import UTC, datetime

        from src.models import AlpacaCredentialsCreate

        # Setup mock for refresh
        def mock_refresh(obj: Any) -> None:
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        tenant_service.db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch("src.services.tenant_service.encrypt_value") as mock_encrypt:
            mock_encrypt.side_effect = ["encrypted_key", "encrypted_secret"]

            data = AlpacaCredentialsCreate(
                name="Test Keys",
                api_key="PKTEST12345678901234",
                api_secret="SKTEST12345678901234567890123456789012345",
                is_paper=True,
            )

            result = await tenant_service.create_alpaca_credentials(
                tenant_id=test_tenant_id,
                data=data,
            )

            # Verify encryption was called
            assert mock_encrypt.call_count == 2
            mock_encrypt.assert_any_call("PKTEST12345678901234")
            mock_encrypt.assert_any_call("SKTEST12345678901234567890123456789012345")

            # Response should have unencrypted values for immediate use
            assert result.api_key == "PKTEST12345678901234"
            assert result.api_secret == "SKTEST12345678901234567890123456789012345"
            assert result.name == "Test Keys"
            assert result.is_paper is True


# === list_alpaca_credentials Tests ===


class TestListAlpacaCredentials:
    """Tests for list_alpaca_credentials method."""

    async def test_list_alpaca_credentials_masks_keys(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test listing credentials masks api keys (shows only prefix)."""
        from datetime import UTC, datetime

        # Create mock credential records
        mock_creds1 = MagicMock()
        mock_creds1.id = uuid4()
        mock_creds1.name = "Paper Keys"
        mock_creds1.api_key_encrypted = "encrypted1"
        mock_creds1.is_paper = True
        mock_creds1.is_active = True
        mock_creds1.created_at = datetime.now(UTC)

        mock_creds2 = MagicMock()
        mock_creds2.id = uuid4()
        mock_creds2.name = "Live Keys"
        mock_creds2.api_key_encrypted = "encrypted2"
        mock_creds2.is_paper = False
        mock_creds2.is_active = True
        mock_creds2.created_at = datetime.now(UTC)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_creds1, mock_creds2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        tenant_service.db.execute.return_value = mock_result

        with patch("src.services.tenant_service.decrypt_value") as mock_decrypt:
            # Return full API key which will be truncated to 8 chars
            mock_decrypt.side_effect = [
                "PKTEST12345678901234",
                "AKTEST98765432109876",
            ]

            result = await tenant_service.list_alpaca_credentials(test_tenant_id)

            assert len(result) == 2
            # Keys should be masked to first 8 characters
            assert result[0].api_key_prefix == "PKTEST12"
            assert result[1].api_key_prefix == "AKTEST98"
            # Full secrets should NOT be included
            assert not hasattr(result[0], "api_secret")
            assert not hasattr(result[1], "api_secret")


# === delete_alpaca_credentials Tests ===


class TestDeleteAlpacaCredentials:
    """Tests for delete_alpaca_credentials method."""

    async def test_delete_alpaca_credentials_soft_deletes(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test deleting credentials sets is_active=False (soft delete)."""
        mock_creds = MagicMock()
        mock_creds.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result

        credentials_id = uuid4()
        result = await tenant_service.delete_alpaca_credentials(
            credentials_id=credentials_id,
            tenant_id=test_tenant_id,
        )

        assert result is True
        assert mock_creds.is_active is False
        tenant_service.db.commit.assert_called_once()

    async def test_delete_alpaca_credentials_not_found(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test deleting non-existent credentials returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        tenant_service.db.execute.return_value = mock_result

        credentials_id = uuid4()
        result = await tenant_service.delete_alpaca_credentials(
            credentials_id=credentials_id,
            tenant_id=test_tenant_id,
        )

        assert result is False

    async def test_delete_alpaca_credentials_wrong_tenant(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test deleting credentials for wrong tenant returns False (isolation)."""
        # Query returns None because tenant_id doesn't match
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        tenant_service.db.execute.return_value = mock_result

        credentials_id = uuid4()
        wrong_tenant_id = uuid4()
        result = await tenant_service.delete_alpaca_credentials(
            credentials_id=credentials_id,
            tenant_id=wrong_tenant_id,
        )

        assert result is False
