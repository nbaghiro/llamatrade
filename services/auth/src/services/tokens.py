"""Single-use email tokens: issue, consume, and notification links.

The issued token is random and only its SHA-256 lands in ``auth_tokens``;
consumption locks the row and sets ``used_at``, so replay is structurally
impossible. Links point at the SPA, which calls the corresponding RPC.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.auth import AuthToken

PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_EMAIL_VERIFY = "email_verify"

_TTL: dict[str, timedelta] = {
    PURPOSE_PASSWORD_RESET: timedelta(hours=1),
    PURPOSE_EMAIL_VERIFY: timedelta(days=7),
}

_APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8800")

_LINK_PATHS: dict[str, str] = {
    PURPOSE_PASSWORD_RESET: "/reset-password",
    PURPOSE_EMAIL_VERIFY: "/verify-email",
}


@dataclass(frozen=True)
class IssuedToken:
    token: str
    link: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_token(
    db: AsyncSession, *, tenant_id: UUID, user_id: UUID, purpose: str
) -> IssuedToken:
    """Mint a fresh single-use token; earlier unused tokens are invalidated."""
    now = datetime.now(UTC)
    stale = await db.execute(
        select(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    )
    for row in stale.scalars():
        row.used_at = now
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            tenant_id=tenant_id,
            user_id=user_id,
            token_hash=_hash(token),
            purpose=purpose,
            expires_at=now + _TTL[purpose],
        )
    )
    return IssuedToken(token=token, link=f"{_APP_BASE_URL}{_LINK_PATHS[purpose]}?token={token}")


async def consume_token(db: AsyncSession, *, token: str, purpose: str) -> AuthToken | None:
    """Redeem a token exactly once; None for unknown, expired, or spent."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(AuthToken)
        .where(AuthToken.token_hash == _hash(token), AuthToken.purpose == purpose)
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None or row.used_at is not None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < now:
        return None
    row.used_at = now
    return row
