"""API Key service - API key management operations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends
from llamatrade_common.utils import generate_api_key
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.database import get_db


class APIKeyService:
    """Service for API key management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_api_key(
        self,
        user_id: UUID,
        tenant_id: UUID,
        name: str,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new API key."""
        key_id = uuid4()
        api_key, key_hash = generate_api_key(prefix="lt")
        key_prefix = api_key[:10]  # Store prefix for display
        now = datetime.now(UTC)

        # In production, store key_hash (not the full key) in database
        # The full api_key is returned only once to the user

        return {
            "id": key_id,
            "name": name,
            "api_key": api_key,  # Full key - shown only on creation
            "key_prefix": key_prefix,
            "scopes": scopes or ["read"],
            "created_at": now,
        }

    async def list_api_keys(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List API keys for a user."""
        # Simplified - in production use SQLAlchemy ORM
        return [], 0

    async def validate_api_key(self, api_key: str) -> dict[str, Any] | None:
        """Validate an API key and return associated user/tenant info."""
        # In production:
        # 1. Extract prefix from api_key
        # 2. Look up keys with that prefix
        # 3. Verify against stored hash using verify_api_key()
        # 4. Return user/tenant info if valid
        return None

    async def delete_api_key(self, key_id: UUID, user_id: UUID) -> bool:
        """Delete an API key."""
        # Simplified - in production use SQLAlchemy ORM
        return False

    async def update_last_used(self, key_id: UUID) -> None:
        """Update the last used timestamp for an API key."""
        # Simplified - in production use SQLAlchemy ORM
        pass


async def get_api_key_service(db: AsyncSession = Depends(get_db)) -> APIKeyService:
    """Dependency to get API key service."""
    return APIKeyService(db)
