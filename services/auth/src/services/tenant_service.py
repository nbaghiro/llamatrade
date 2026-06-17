"""Tenant service - tenant management operations."""

import binascii
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_common.utils import decrypt_value, encrypt_value
from llamatrade_db import get_db
from llamatrade_db.models.auth import AlpacaCredentials as AlpacaCredentialsModel
from llamatrade_telemetry import metrics

from src.models import (
    AlpacaCredentialsCreate,
    AlpacaCredentialsListItem,
    AlpacaCredentialsResponse,
)


class TenantService:
    """Service for tenant management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _decrypt_credential(self, encrypted_value: str) -> str:
        """Decrypt a stored Alpaca credential, recording decryption failures.

        Re-raises the underlying error so existing error propagation is preserved.
        """
        try:
            return decrypt_value(encrypted_value)
        except InvalidToken, binascii.Error:
            metrics.auth.credential_decryption_failure()
            raise

    async def get_alpaca_credentials(
        self, credentials_id: UUID, tenant_id: UUID
    ) -> AlpacaCredentialsResponse | None:
        """Get decrypted Alpaca credentials by ID.

        Args:
            credentials_id: The credentials ID to fetch.
            tenant_id: Tenant ID for isolation (must match).

        Returns:
            Decrypted credentials or None if not found/not authorized.
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
            api_key=self._decrypt_credential(creds.api_key_encrypted),
            api_secret=self._decrypt_credential(creds.api_secret_encrypted),
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
            api_key_encrypted=encrypt_value(data.api_key),
            api_secret_encrypted=encrypt_value(data.api_secret),
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

        items: list[AlpacaCredentialsListItem] = []
        for creds in creds_list:
            # Decrypt just to get prefix, then mask
            api_key = self._decrypt_credential(creds.api_key_encrypted)
            items.append(
                AlpacaCredentialsListItem(
                    id=creds.id,
                    name=creds.name,
                    api_key_prefix=api_key[:8] if len(api_key) >= 8 else api_key,
                    is_paper=creds.is_paper,
                    is_active=creds.is_active,
                    created_at=creds.created_at,
                )
            )

        return items

    async def delete_alpaca_credentials(self, credentials_id: UUID, tenant_id: UUID) -> bool:
        """Soft-delete Alpaca credentials.

        Args:
            credentials_id: The credentials to delete.
            tenant_id: Tenant ID for isolation.

        Returns:
            True if deleted, False if not found.
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

        creds.is_active = False
        await self.db.commit()
        return True


async def get_tenant_service(db: AsyncSession = Depends(get_db)) -> TenantService:
    """Dependency to get tenant service."""
    return TenantService(db)
