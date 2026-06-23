"""Per-tenant Alpaca credential resolution.

Single source of truth for turning a stored ``AlpacaCredentials`` row into a
decrypted, ready-to-use credential. Shared by the live-session runner and the
manual order path so neither ever falls back to platform/env credentials
(CONTRACTS.md / trading-hardening 2A).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_common.utils import decrypt_value
from llamatrade_db.models.auth import AlpacaCredentials
from llamatrade_db.models.trading import TradingSession


class DecryptedCredentials(BaseModel):
    """Decrypted Alpaca credentials for internal use."""

    id: UUID
    name: str
    api_key: str
    api_secret: str
    is_paper: bool


async def resolve_credentials(
    db: AsyncSession, credentials_id: UUID, tenant_id: UUID
) -> DecryptedCredentials | None:
    """Fetch + decrypt active credentials for a tenant, or None if not found."""
    stmt = (
        select(AlpacaCredentials)
        .where(AlpacaCredentials.id == credentials_id)
        .where(AlpacaCredentials.tenant_id == tenant_id)  # tenant isolation
        .where(AlpacaCredentials.is_active.is_(True))
    )
    creds = (await db.execute(stmt)).scalar_one_or_none()
    if not creds:
        return None
    return DecryptedCredentials(
        id=creds.id,
        name=creds.name,
        api_key=decrypt_value(creds.api_key_encrypted),
        api_secret=decrypt_value(creds.api_secret_encrypted),
        is_paper=creds.is_paper,
    )


async def resolve_session_credentials(
    db: AsyncSession, session_id: UUID, tenant_id: UUID
) -> DecryptedCredentials | None:
    """Resolve the decrypted Alpaca credentials a trading session was started with.

    Returns None if the session doesn't exist for the tenant, or its credentials
    are missing/inactive — the manual order path treats that as a hard failure
    rather than silently using platform/env credentials.
    """
    session = await db.scalar(
        select(TradingSession).where(
            TradingSession.tenant_id == tenant_id,
            TradingSession.id == session_id,
        )
    )
    if session is None:
        return None
    return await resolve_credentials(db, session.credentials_id, tenant_id)
