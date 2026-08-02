"""Tests for TenantService."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_db.credential_dependents import CredentialDependents

from src.services.tenant_service import CredentialsInUseError, TenantService

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


def _mock_creds(
    name: str = "Keys",
    api_key_prefix: str | None = "PKTEST12",
    api_key_encrypted: str | None = "encrypted_key",
    is_paper: bool = True,
) -> MagicMock:
    """Credential-row stand-in with the prefix/encrypted attrs set explicitly."""
    from datetime import UTC, datetime

    creds = MagicMock()
    creds.id = uuid4()
    creds.name = name
    creds.api_key_prefix = api_key_prefix
    creds.api_key_encrypted = api_key_encrypted
    creds.api_secret_encrypted = "encrypted_secret" if api_key_encrypted else None
    creds.is_paper = is_paper
    creds.is_active = True
    creds.created_at = datetime.now(UTC)
    return creds


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

    async def test_get_alpaca_credentials_uses_stored_prefix_without_decrypting(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Get returns the stored key prefix and never decrypts (write-only creds)."""
        mock_creds = _mock_creds(name="My Paper Keys", api_key_prefix="PKTEST12")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            result = await tenant_service.get_alpaca_credentials(
                credentials_id=mock_creds.id,
                tenant_id=test_tenant_id,
            )

            assert result is not None
            assert result.api_key == "PKTEST12"
            assert result.api_secret == ""
            mock_decrypt.assert_not_called()

    async def test_get_alpaca_credentials_legacy_row_falls_back_to_decrypt(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """A pre-column row (NULL prefix) decrypts the key once for its prefix."""
        mock_creds = _mock_creds(name="Legacy Keys", api_key_prefix=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            mock_decrypt.return_value = "PKTEST12345678901234"

            result = await tenant_service.get_alpaca_credentials(
                credentials_id=mock_creds.id,
                tenant_id=test_tenant_id,
            )

            assert result is not None
            assert result.api_key == "PKTEST12"
            assert result.api_secret == ""
            mock_decrypt.assert_called_once_with("encrypted_key")

    async def test_get_alpaca_credentials_oauth_row_has_no_prefix(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """An OAuth row (no API key at all) yields an empty prefix, no decryption."""
        mock_creds = _mock_creds(name="Alpaca (OAuth)", api_key_prefix=None, api_key_encrypted=None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            result = await tenant_service.get_alpaca_credentials(
                credentials_id=mock_creds.id,
                tenant_id=test_tenant_id,
            )

            assert result is not None
            assert result.api_key == ""
            mock_decrypt.assert_not_called()


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

        with patch("src.services.tenant_service.async_encrypt_value") as mock_encrypt:
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

    async def test_create_alpaca_credentials_stores_key_prefix(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Create persists the display prefix so reads never need decryption."""
        from datetime import UTC, datetime

        from src.models import AlpacaCredentialsCreate

        def mock_refresh(obj: Any) -> None:
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        tenant_service.db.add = MagicMock()
        tenant_service.db.refresh = AsyncMock(side_effect=mock_refresh)

        data = AlpacaCredentialsCreate(
            name="Test Keys",
            api_key="PKTEST12345678901234",
            api_secret="SKTEST12345678901234567890123456789012345",
            is_paper=True,
        )
        await tenant_service.create_alpaca_credentials(tenant_id=test_tenant_id, data=data)

        added = tenant_service.db.add.call_args[0][0]
        assert added.api_key_prefix == "PKTEST12"


# === list_alpaca_credentials Tests ===


class TestListAlpacaCredentials:
    """Tests for list_alpaca_credentials method."""

    def _stub_list(self, tenant_service: TenantService, rows: list[MagicMock]) -> None:
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rows
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        tenant_service.db.execute.return_value = mock_result

    async def test_list_alpaca_credentials_uses_stored_prefixes(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Listing returns stored prefixes and never decrypts prefixed rows."""
        rows = [
            _mock_creds(name="Paper Keys", api_key_prefix="PKTEST12"),
            _mock_creds(name="Live Keys", api_key_prefix="AKTEST98", is_paper=False),
        ]
        self._stub_list(tenant_service, rows)

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            result = await tenant_service.list_alpaca_credentials(test_tenant_id)

            assert len(result) == 2
            assert result[0].api_key_prefix == "PKTEST12"
            assert result[1].api_key_prefix == "AKTEST98"
            # Full secrets should NOT be included
            assert not hasattr(result[0], "api_secret")
            assert not hasattr(result[1], "api_secret")
            mock_decrypt.assert_not_called()

    async def test_list_alpaca_credentials_legacy_rows_fall_back_to_decrypt(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Pre-column rows (NULL prefix) still mask via decryption."""
        rows = [
            _mock_creds(name="Legacy Keys", api_key_prefix=None, api_key_encrypted="encrypted1"),
            _mock_creds(name="New Keys", api_key_prefix="AKTEST98"),
        ]
        self._stub_list(tenant_service, rows)

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            mock_decrypt.return_value = "PKTEST12345678901234"

            result = await tenant_service.list_alpaca_credentials(test_tenant_id)

            assert result[0].api_key_prefix == "PKTEST12"
            assert result[1].api_key_prefix == "AKTEST98"
            mock_decrypt.assert_called_once_with("encrypted1")

    async def test_list_alpaca_credentials_oauth_rows_have_empty_prefix(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """OAuth rows have no API key: empty prefix, no decryption attempt."""
        rows = [_mock_creds(name="Alpaca (OAuth)", api_key_prefix=None, api_key_encrypted=None)]
        self._stub_list(tenant_service, rows)

        with patch("src.services.tenant_service.async_decrypt_value") as mock_decrypt:
            result = await tenant_service.list_alpaca_credentials(test_tenant_id)

            assert result[0].api_key_prefix == ""
            mock_decrypt.assert_not_called()


# === delete_alpaca_credentials Tests ===


class TestDeleteAlpacaCredentials:
    """Tests for delete_alpaca_credentials method."""

    def _stub_creds_row(self, tenant_service: TenantService) -> MagicMock:
        mock_creds = MagicMock()
        mock_creds.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_creds
        tenant_service.db.execute.return_value = mock_result
        return mock_creds

    async def test_delete_alpaca_credentials_soft_deletes(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """Test deleting credentials sets is_active=False (soft delete)."""
        mock_creds = self._stub_creds_row(tenant_service)

        credentials_id = uuid4()
        with patch(
            "src.services.tenant_service.get_credential_dependents",
            AsyncMock(return_value=CredentialDependents()),
        ):
            result = await tenant_service.delete_alpaca_credentials(
                credentials_id=credentials_id,
                tenant_id=test_tenant_id,
            )

        assert result is True
        assert mock_creds.is_active is False
        tenant_service.db.commit.assert_called_once()

    async def test_delete_refused_while_a_live_session_depends_on_them(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """A live trading session blocks deletion and is named in the message."""
        mock_creds = self._stub_creds_row(tenant_service)
        session_id = uuid4()

        credentials_id = uuid4()
        with patch(
            "src.services.tenant_service.get_credential_dependents",
            AsyncMock(return_value=CredentialDependents(session_ids=(session_id,))),
        ):
            with pytest.raises(CredentialsInUseError) as exc_info:
                await tenant_service.delete_alpaca_credentials(
                    credentials_id=credentials_id,
                    tenant_id=test_tenant_id,
                )

        assert str(session_id) in str(exc_info.value)
        assert "live trading sessions" in str(exc_info.value)
        assert mock_creds.is_active is True
        tenant_service.db.commit.assert_not_called()

    async def test_delete_refused_while_a_funded_sleeve_depends_on_them(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """A funded sleeve blocks deletion; its sleeve and execution ids are listed."""
        mock_creds = self._stub_creds_row(tenant_service)
        sleeve_id, execution_id = uuid4(), uuid4()

        credentials_id = uuid4()
        with patch(
            "src.services.tenant_service.get_credential_dependents",
            AsyncMock(
                return_value=CredentialDependents(
                    sleeve_ids=(sleeve_id,), strategy_execution_ids=(execution_id,)
                )
            ),
        ):
            with pytest.raises(CredentialsInUseError) as exc_info:
                await tenant_service.delete_alpaca_credentials(
                    credentials_id=credentials_id,
                    tenant_id=test_tenant_id,
                )

        message = str(exc_info.value)
        assert str(sleeve_id) in message
        assert str(execution_id) in message
        assert "funded sleeves" in message
        assert mock_creds.is_active is True
        tenant_service.db.commit.assert_not_called()

    async def test_delete_checks_dependents_for_the_calling_tenant_only(
        self, tenant_service: TenantService, test_tenant_id: UUID
    ) -> None:
        """The dependency query is scoped to the caller's tenant and credentials."""
        self._stub_creds_row(tenant_service)
        credentials_id = uuid4()
        dependents = AsyncMock(return_value=CredentialDependents())

        with patch("src.services.tenant_service.get_credential_dependents", dependents):
            await tenant_service.delete_alpaca_credentials(
                credentials_id=credentials_id,
                tenant_id=test_tenant_id,
            )

        dependents.assert_awaited_once_with(tenant_service.db, test_tenant_id, credentials_id)

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
