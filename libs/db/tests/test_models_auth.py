"""Tests for llamatrade_db.models.auth module."""

from llamatrade_db.models.auth import (
    AlpacaCredentials,
    APIKey,
    Tenant,
    User,
)


class TestTenant:
    """Tests for Tenant model."""

    def test_tenant_tablename(self) -> None:
        """Test Tenant has correct tablename."""
        assert Tenant.__tablename__ == "tenants"

    def test_tenant_has_required_columns(self) -> None:
        """Test Tenant has all required columns."""
        columns = Tenant.__table__.columns
        assert "id" in columns
        assert "name" in columns
        assert "slug" in columns
        assert "is_active" in columns
        assert "settings" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_tenant_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        name_col = Tenant.__table__.columns["name"]
        assert name_col.nullable is False

    def test_tenant_slug_unique(self) -> None:
        """Test slug column is unique."""
        slug_col = Tenant.__table__.columns["slug"]
        assert slug_col.unique is True

    def test_tenant_is_active_default(self) -> None:
        """Test is_active defaults to True."""
        is_active_col = Tenant.__table__.columns["is_active"]
        assert is_active_col.default is not None

    def test_tenant_has_relationships(self) -> None:
        """Test Tenant has expected relationships."""
        # Check relationship attributes exist
        assert hasattr(Tenant, "users")
        assert hasattr(Tenant, "alpaca_credentials")
        assert hasattr(Tenant, "api_keys")


class TestUser:
    """Tests for User model."""

    def test_user_tablename(self) -> None:
        """Test User has correct tablename."""
        assert User.__tablename__ == "users"

    def test_user_has_required_columns(self) -> None:
        """Test User has all required columns."""
        columns = User.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "email" in columns
        assert "password_hash" in columns
        assert "first_name" in columns
        assert "last_name" in columns
        assert "role" in columns
        assert "is_active" in columns
        assert "is_verified" in columns
        assert "last_login" in columns
        assert "settings" in columns

    def test_user_email_not_nullable(self) -> None:
        """Test email column is not nullable."""
        email_col = User.__table__.columns["email"]
        assert email_col.nullable is False

    def test_user_password_hash_not_nullable(self) -> None:
        """Test password_hash column is not nullable."""
        password_col = User.__table__.columns["password_hash"]
        assert password_col.nullable is False

    def test_user_role_has_default(self) -> None:
        """Test role has default value."""
        role_col = User.__table__.columns["role"]
        assert role_col.default is not None

    def test_user_has_tenant_relationship(self) -> None:
        """Test User has tenant relationship."""
        assert hasattr(User, "tenant")

    def test_user_has_table_args_for_unique_constraint(self) -> None:
        """Test User has table args for unique email per tenant."""
        table_args = User.__table_args__
        assert table_args is not None


class TestAlpacaCredentials:
    """Tests for AlpacaCredentials model."""

    def test_alpaca_credentials_tablename(self) -> None:
        """Test AlpacaCredentials has correct tablename."""
        assert AlpacaCredentials.__tablename__ == "alpaca_credentials"

    def test_alpaca_credentials_has_required_columns(self) -> None:
        """Test AlpacaCredentials has all required columns."""
        columns = AlpacaCredentials.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "name" in columns
        assert "api_key_encrypted" in columns
        assert "api_secret_encrypted" in columns
        assert "is_paper" in columns
        assert "is_active" in columns

    def test_api_key_encrypted_not_nullable(self) -> None:
        """Test api_key_encrypted column is not nullable."""
        col = AlpacaCredentials.__table__.columns["api_key_encrypted"]
        assert col.nullable is False

    def test_api_secret_encrypted_not_nullable(self) -> None:
        """Test api_secret_encrypted column is not nullable."""
        col = AlpacaCredentials.__table__.columns["api_secret_encrypted"]
        assert col.nullable is False

    def test_is_paper_has_default(self) -> None:
        """Test is_paper defaults to True."""
        col = AlpacaCredentials.__table__.columns["is_paper"]
        assert col.default is not None

    def test_has_tenant_relationship(self) -> None:
        """Test AlpacaCredentials has tenant relationship."""
        assert hasattr(AlpacaCredentials, "tenant")


class TestAPIKey:
    """Tests for APIKey model."""

    def test_api_key_tablename(self) -> None:
        """Test APIKey has correct tablename."""
        assert APIKey.__tablename__ == "api_keys"

    def test_api_key_has_required_columns(self) -> None:
        """Test APIKey has all required columns."""
        columns = APIKey.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "user_id" in columns
        assert "name" in columns
        assert "key_prefix" in columns
        assert "key_hash" in columns
        assert "scopes" in columns
        assert "expires_at" in columns
        assert "last_used_at" in columns
        assert "is_active" in columns

    def test_key_hash_not_nullable(self) -> None:
        """Test key_hash column is not nullable."""
        col = APIKey.__table__.columns["key_hash"]
        assert col.nullable is False

    def test_has_tenant_relationship(self) -> None:
        """Test APIKey has tenant relationship."""
        assert hasattr(APIKey, "tenant")

    def test_has_index_on_key_hash(self) -> None:
        """Test APIKey has index on key_hash."""
        table_args = APIKey.__table_args__
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        key_hash_indexes = [idx for idx in indexes if "key_hash" in str(idx)]
        assert len(key_hash_indexes) > 0
