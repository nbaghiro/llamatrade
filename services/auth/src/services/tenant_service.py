"""Tenant service - tenant management operations."""

import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_common.utils import decrypt_value, encrypt_value
from llamatrade_db.models.auth import AlpacaCredentials as AlpacaCredentialsModel

from src.models import (
    AlpacaCredentialsCreate,
    AlpacaCredentialsListItem,
    AlpacaCredentialsResponse,
    TenantDetailResponse,
    TenantResponse,
)
from src.services.database import get_db


def _slugify(name: str) -> str:
    """Convert name to URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]


class TenantService:
    """Service for tenant management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(
        self,
        name: str,
        plan_id: str = "free",
        settings: dict[str, str | int | bool | None] | None = None,
    ) -> TenantDetailResponse:
        """Create a new tenant."""
        tenant_id = uuid4()
        now = datetime.now(UTC)
        # Generate unique slug from name
        base_slug = _slugify(name)
        slug = f"{base_slug}-{str(tenant_id)[:8]}"

        query = text("""
            INSERT INTO tenants (id, name, slug, is_active, settings)
            VALUES (:id, :name, :slug, :is_active, CAST(:settings AS jsonb))
            RETURNING id, name, slug, is_active, settings, created_at
        """)

        await self.db.execute(
            query,
            {
                "id": tenant_id,
                "name": name,
                "slug": slug,
                "is_active": True,
                "settings": json.dumps(settings or {}),
            },
        )

        # Flush to ensure tenant exists before creating user
        await self.db.flush()

        return TenantDetailResponse(
            id=tenant_id,
            name=name,
            slug=slug,
            plan_id=plan_id,
            settings=settings or {},
            created_at=now,
        )

    async def get_tenant(self, tenant_id: UUID) -> TenantResponse | None:
        """Get a tenant by ID."""
        # Simplified - in production use SQLAlchemy ORM
        return None

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        settings: dict[str, str | int | bool | None],
    ) -> TenantResponse | None:
        """Update tenant settings."""
        # Simplified - in production use SQLAlchemy ORM
        return None

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
            api_key=decrypt_value(creds.api_key_encrypted),
            api_secret=decrypt_value(creds.api_secret_encrypted),
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
            api_key = decrypt_value(creds.api_key_encrypted)
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
