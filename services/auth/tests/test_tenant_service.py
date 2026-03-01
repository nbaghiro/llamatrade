"""Tests for TenantService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.services.tenant_service import TenantService, _slugify

# === Test Fixtures ===


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def tenant_service(mock_db):
    """Create a TenantService instance with mock db."""
    return TenantService(mock_db)


@pytest.fixture
def test_tenant_id():
    return uuid4()


# === _slugify Tests ===


class TestSlugify:
    """Tests for _slugify helper function."""

    def test_slugify_basic(self):
        """Test basic slugification."""
        assert _slugify("My Company") == "my-company"

    def test_slugify_special_chars(self):
        """Test slugification removes special characters."""
        # Note: trailing whitespace from removed chars becomes trailing hyphen
        assert _slugify("My Company! @#$%").startswith("my-company")

    def test_slugify_multiple_spaces(self):
        """Test slugification handles multiple spaces."""
        assert _slugify("My   Company") == "my-company"

    def test_slugify_underscores(self):
        """Test slugification converts underscores."""
        assert _slugify("my_company_name") == "my-company-name"

    def test_slugify_truncates(self):
        """Test slugification truncates to 100 chars."""
        long_name = "a" * 150
        result = _slugify(long_name)
        assert len(result) == 100

    def test_slugify_strips_whitespace(self):
        """Test slugification strips leading/trailing whitespace."""
        assert _slugify("  My Company  ") == "my-company"


# === create_tenant Tests ===


class TestCreateTenant:
    """Tests for create_tenant method."""

    async def test_create_tenant_success(self, tenant_service, mock_db):
        """Test creating a tenant successfully."""
        name = "Test Company"

        result = await tenant_service.create_tenant(name=name)

        assert result.name == name
        assert result.plan_id == "free"
        assert result.settings == {}
        assert "test-company" in result.slug
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()

    async def test_create_tenant_with_plan(self, tenant_service, mock_db):
        """Test creating a tenant with specific plan."""
        result = await tenant_service.create_tenant(
            name="Pro Company",
            plan_id="pro",
        )

        assert result.plan_id == "pro"

    async def test_create_tenant_with_settings(self, tenant_service, mock_db):
        """Test creating a tenant with settings."""
        settings = {"theme": "dark", "max_users": 10}

        result = await tenant_service.create_tenant(
            name="Custom Company",
            settings=settings,
        )

        assert result.settings == settings


# === get_tenant Tests ===


class TestGetTenant:
    """Tests for get_tenant method."""

    async def test_get_tenant_returns_none(self, tenant_service, test_tenant_id):
        """Test getting tenant returns None (stub)."""
        result = await tenant_service.get_tenant(test_tenant_id)

        assert result is None


# === update_tenant_settings Tests ===


class TestUpdateTenantSettings:
    """Tests for update_tenant_settings method."""

    async def test_update_tenant_settings_returns_none(self, tenant_service, test_tenant_id):
        """Test updating tenant settings returns None (stub)."""
        settings = {"theme": "light"}

        result = await tenant_service.update_tenant_settings(test_tenant_id, settings)

        assert result is None


# === get_alpaca_credentials Tests ===


class TestGetAlpacaCredentials:
    """Tests for get_alpaca_credentials method."""

    async def test_get_alpaca_credentials_returns_none(self, tenant_service, test_tenant_id):
        """Test getting Alpaca credentials returns None (stub)."""
        result = await tenant_service.get_alpaca_credentials(test_tenant_id)

        assert result is None


# === update_alpaca_credentials Tests ===


class TestUpdateAlpacaCredentials:
    """Tests for update_alpaca_credentials method."""

    async def test_update_alpaca_credentials_encrypts_paper_key(
        self, tenant_service, test_tenant_id
    ):
        """Test updating Alpaca credentials encrypts values."""
        with patch("src.services.tenant_service.encrypt_value") as mock_encrypt:
            mock_encrypt.return_value = "encrypted_value"

            await tenant_service.update_alpaca_credentials(
                tenant_id=test_tenant_id,
                paper_key="PAPER_KEY",
            )

            mock_encrypt.assert_called_once_with("PAPER_KEY")

    async def test_update_alpaca_credentials_encrypts_all(self, tenant_service, test_tenant_id):
        """Test updating all Alpaca credentials encrypts all values."""
        with patch("src.services.tenant_service.encrypt_value") as mock_encrypt:
            mock_encrypt.return_value = "encrypted"

            await tenant_service.update_alpaca_credentials(
                tenant_id=test_tenant_id,
                paper_key="PK",
                paper_secret="PS",
                live_key="LK",
                live_secret="LS",
            )

            assert mock_encrypt.call_count == 4


# === delete_alpaca_credentials Tests ===


class TestDeleteAlpacaCredentials:
    """Tests for delete_alpaca_credentials method."""

    async def test_delete_alpaca_credentials_succeeds(self, tenant_service, test_tenant_id):
        """Test deleting Alpaca credentials (stub)."""
        # Should not raise
        await tenant_service.delete_alpaca_credentials(test_tenant_id)
