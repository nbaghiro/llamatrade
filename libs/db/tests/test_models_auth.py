"""Behavioural pins for llamatrade_db.models.auth.

Column presence and nullability are proven against the migrated schema by the
metadata-drift test (``test_migrated_schema_pg.py``); what stays here are the
intent pins: named uniqueness rules and default values.
"""

from llamatrade_db.models.auth import (
    AlpacaCredentials,
    APIKey,
    Tenant,
    User,
)


class TestTenant:
    def test_slug_unique(self) -> None:
        assert Tenant.__table__.columns["slug"].unique is True

    def test_is_active_defaults_true(self) -> None:
        column = Tenant.__table__.columns["is_active"]
        assert column.default is not None and column.default.arg is True


class TestUser:
    def test_role_defaults_to_user(self) -> None:
        column = User.__table__.columns["role"]
        assert column.default is not None and column.default.arg == "user"

    def test_email_unique_per_tenant(self) -> None:
        """The named unique index scopes email uniqueness to the tenant, not globally."""
        # The tenant mixin also contributes ix_users_tenant_id; select the unique one.
        index = next(i for i in User.__table__.indexes if i.name == "ix_users_tenant_email")
        assert index.unique is True
        assert [c.name for c in index.columns] == ["tenant_id", "email"]
        assert User.__table__.columns["email"].unique is not True


class TestAlpacaCredentials:
    def test_api_key_encrypted_nullable_for_oauth(self) -> None:
        """api_key_encrypted is nullable: OAuth rows omit the key/secret pair (migration 029)."""
        assert AlpacaCredentials.__table__.columns["api_key_encrypted"].nullable is True

    def test_api_secret_encrypted_nullable_for_oauth(self) -> None:
        """api_secret_encrypted is nullable: OAuth rows omit the key/secret pair (migration 029)."""
        assert AlpacaCredentials.__table__.columns["api_secret_encrypted"].nullable is True

    def test_is_paper_defaults_true(self) -> None:
        column = AlpacaCredentials.__table__.columns["is_paper"]
        assert column.default is not None and column.default.arg is True


class TestAPIKey:
    def test_key_hash_lookup_index(self) -> None:
        """Key verification looks rows up by hash; the named index backs that path."""
        names = {i.name for i in APIKey.__table__.indexes}
        assert "ix_api_keys_key_hash" in names
