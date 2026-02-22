"""Tenant service - tenant management operations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends
from llamatrade_common.utils import encrypt_value
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.database import get_db


class TenantService:
    """Service for tenant management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(
        self,
        name: str,
        plan_id: str = "free",
        settings: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new tenant."""
        tenant_id = uuid4()
        now = datetime.now(UTC)

        # In production, use SQLAlchemy ORM
        return {
            "id": tenant_id,
            "name": name,
            "plan_id": plan_id,
            "settings": settings or {},
            "created_at": now,
        }

    async def get_tenant(self, tenant_id: UUID) -> dict[str, Any] | None:
        """Get a tenant by ID."""
        # Simplified - in production use SQLAlchemy ORM
        return None

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        settings: dict,
    ) -> dict[str, Any] | None:
        """Update tenant settings."""
        # Simplified - in production use SQLAlchemy ORM
        return None

    async def get_alpaca_credentials(self, tenant_id: UUID) -> dict[str, Any] | None:
        """Get decrypted Alpaca credentials for a tenant."""
        # Simplified - in production:
        # 1. Fetch encrypted credentials from DB
        # 2. Decrypt them using decrypt_value()
        return None

    async def update_alpaca_credentials(
        self,
        tenant_id: UUID,
        paper_key: str | None = None,
        paper_secret: str | None = None,
        live_key: str | None = None,
        live_secret: str | None = None,
    ) -> None:
        """Update Alpaca credentials (encrypted at rest)."""
        # In production:
        # 1. Encrypt credentials using encrypt_value()
        # 2. Store in database
        encrypted_data = {}

        if paper_key:
            encrypted_data["paper_key_enc"] = encrypt_value(paper_key)
        if paper_secret:
            encrypted_data["paper_secret_enc"] = encrypt_value(paper_secret)
        if live_key:
            encrypted_data["live_key_enc"] = encrypt_value(live_key)
        if live_secret:
            encrypted_data["live_secret_enc"] = encrypt_value(live_secret)

        # Store encrypted_data in DB...

    async def delete_alpaca_credentials(self, tenant_id: UUID) -> None:
        """Delete Alpaca credentials for a tenant."""
        # Simplified - in production use SQLAlchemy ORM
        pass


async def get_tenant_service(db: AsyncSession = Depends(get_db)) -> TenantService:
    """Dependency to get tenant service."""
    return TenantService(db)
