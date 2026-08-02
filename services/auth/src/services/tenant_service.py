"""Tenant service - tenant management operations."""

import binascii
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_common.utils import async_decrypt_value, async_encrypt_value
from llamatrade_db import get_db
from llamatrade_db.credential_dependents import (
    CredentialDependents,
    get_credential_dependents,
)
from llamatrade_db.models.auth import AlpacaCredentials as AlpacaCredentialsModel
from llamatrade_telemetry import metrics

from src.models import (
    AlpacaCredentialsCreate,
    AlpacaCredentialsListItem,
    AlpacaCredentialsResponse,
)

_KEY_PREFIX_LENGTH = 8


def _describe_dependents(dependents: CredentialDependents) -> str:
    """Message naming every blocker so the client can offer stop-and-close."""
    parts: list[str] = []
    if dependents.session_ids:
        parts.append(f"live trading sessions: {', '.join(str(i) for i in dependents.session_ids)}")
    if dependents.sleeve_ids:
        parts.append(f"funded sleeves: {', '.join(str(i) for i in dependents.sleeve_ids)}")
    if dependents.strategy_execution_ids:
        parts.append(
            f"strategy executions: {', '.join(str(i) for i in dependents.strategy_execution_ids)}"
        )
    return (
        "Credentials are still in use; stop the sessions and close the sleeves "
        f"before deleting ({'; '.join(parts)})"
    )


class CredentialsInUseError(Exception):
    """Raised when credentials still back live sessions or funded ledger sleeves."""

    def __init__(self, dependents: CredentialDependents) -> None:
        self.dependents = dependents
        super().__init__(_describe_dependents(dependents))


class TenantService:
    """Service for tenant management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _decrypt_credential(self, encrypted_value: str) -> str:
        """Decrypt a stored Alpaca credential, recording decryption failures.

        Re-raises the underlying error so existing error propagation is preserved.
        """
        try:
            return await async_decrypt_value(encrypted_value)
        except InvalidToken, binascii.Error:
            metrics.auth.credential_decryption_failure()
            raise

    async def _key_prefix(self, creds: AlpacaCredentialsModel) -> str:
        """Stored key prefix; decrypts only legacy rows that predate the column."""
        if creds.api_key_prefix:
            return creds.api_key_prefix
        if not creds.api_key_encrypted:
            return ""
        return (await self._decrypt_credential(creds.api_key_encrypted))[:_KEY_PREFIX_LENGTH]

    async def get_alpaca_credentials(
        self, credentials_id: UUID, tenant_id: UUID
    ) -> AlpacaCredentialsResponse | None:
        """Get Alpaca credentials by ID (key prefix only; write-only after create).

        Args:
            credentials_id: The credentials ID to fetch.
            tenant_id: Tenant ID for isolation (must match).

        Returns:
            Credentials with the stored key prefix (no decryption unless the row
            predates the prefix column) or None if not found/not authorized.
        """
        stmt = (
            select(AlpacaCredentialsModel)
            .where(AlpacaCredentialsModel.id == credentials_id)
            .where(AlpacaCredentialsModel.tenant_id == tenant_id)  # Tenant isolation!
            .where(AlpacaCredentialsModel.is_active.is_(True))
        )
        result = await self.db.execute(stmt)
        creds = result.scalar_one_or_none()

        if not creds:
            return None

        return AlpacaCredentialsResponse(
            id=creds.id,
            name=creds.name,
            api_key=await self._key_prefix(creds),
            api_secret="",
            is_paper=creds.is_paper,
            is_active=creds.is_active,
            created_at=creds.created_at,
        )

    async def create_alpaca_credentials(
        self, tenant_id: UUID, data: AlpacaCredentialsCreate
    ) -> AlpacaCredentialsResponse:
        """Create new encrypted Alpaca credentials.

        Args:
            tenant_id: Tenant to associate credentials with.
            data: Credential data including API key and secret.

        Returns:
            Created credentials with decrypted values for immediate use.
        """
        creds = AlpacaCredentialsModel(
            tenant_id=tenant_id,
            name=data.name,
            api_key_encrypted=await async_encrypt_value(data.api_key),
            api_secret_encrypted=await async_encrypt_value(data.api_secret),
            api_key_prefix=data.api_key[:_KEY_PREFIX_LENGTH],
            is_paper=data.is_paper,
            is_active=True,
        )
        self.db.add(creds)
        await self.db.commit()
        await self.db.refresh(creds)

        return AlpacaCredentialsResponse(
            id=creds.id,
            name=creds.name,
            api_key=data.api_key,  # Return unencrypted for immediate use
            api_secret=data.api_secret,
            is_paper=creds.is_paper,
            is_active=creds.is_active,
            created_at=creds.created_at,
        )

    async def list_alpaca_credentials(self, tenant_id: UUID) -> list[AlpacaCredentialsListItem]:
        """List all active Alpaca credentials for a tenant (keys masked).

        Args:
            tenant_id: Tenant to list credentials for.

        Returns:
            List of active credentials with masked API keys.
        """
        stmt = (
            select(AlpacaCredentialsModel)
            .where(AlpacaCredentialsModel.tenant_id == tenant_id)
            .where(AlpacaCredentialsModel.is_active.is_(True))
            .order_by(AlpacaCredentialsModel.created_at.desc())
        )
        result = await self.db.execute(stmt)
        creds_list = result.scalars().all()

        return [
            AlpacaCredentialsListItem(
                id=creds.id,
                name=creds.name,
                api_key_prefix=await self._key_prefix(creds),
                is_paper=creds.is_paper,
                is_active=creds.is_active,
                created_at=creds.created_at,
            )
            for creds in creds_list
        ]

    async def delete_alpaca_credentials(self, credentials_id: UUID, tenant_id: UUID) -> bool:
        """Soft-delete Alpaca credentials once nothing depends on them.

        Args:
            credentials_id: The credentials to delete.
            tenant_id: Tenant ID for isolation.

        Returns:
            True if deleted, False if not found.

        Raises:
            CredentialsInUseError: Live trading sessions or funded ledger sleeves
                still reference the credentials; the caller must stop and close
                them first (no cascading deletion, no auto-stop).
        """
        stmt = (
            select(AlpacaCredentialsModel)
            .where(AlpacaCredentialsModel.id == credentials_id)
            .where(AlpacaCredentialsModel.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        creds = result.scalar_one_or_none()

        if not creds:
            return False

        dependents = await get_credential_dependents(self.db, tenant_id, credentials_id)
        if dependents:
            raise CredentialsInUseError(dependents)

        creds.is_active = False
        await self.db.commit()
        return True


async def get_tenant_service(db: AsyncSession = Depends(get_db)) -> TenantService:
    """Dependency to get tenant service."""
    return TenantService(db)
