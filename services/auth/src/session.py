"""Shared session helpers: token minting + tenant/user creation.

Single source used by both the Connect servicer (login/register) and the OAuth
routes so every path issues identical sessions and creates users the same way.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_common.utils import require_secret
from llamatrade_db.models.auth import Tenant, User

JWT_SECRET = require_secret("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
_HANDOFF_PURPOSE = "alpaca_oauth_handoff"
_HANDOFF_TTL_SECONDS = 120


@dataclass
class AccessRefresh:
    """A minted access + refresh token pair with expiries."""

    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def mint_access_refresh(user: User) -> AccessRefresh:
    """Mint the access + refresh JWTs for a user (the canonical login session)."""
    now = datetime.now(UTC)
    access_expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    access = jwt.encode(
        {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "email": user.email,
            "roles": [user.role],
            "type": "access",
            "iat": now,
            "exp": access_expire,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    refresh = jwt.encode(
        {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "type": "refresh",
            "iat": now,
            "exp": refresh_expire,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return AccessRefresh(access, refresh, access_expire, refresh_expire)


def user_to_dict(user: User) -> dict[str, object]:
    """JSON user shape (camelCase) mirroring the auth User proto for HTTP responses."""
    return {
        "id": str(user.id),
        "tenantId": str(user.tenant_id),
        "email": user.email,
        "firstName": user.first_name or "",
        "lastName": user.last_name or "",
        "roles": [user.role],
        "isActive": user.is_active,
        "avatarUrl": user.avatar_url or "",
    }


async def create_tenant_and_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    tenant_name: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    """Create a tenant + its first (admin) user; ``flush`` but do not commit.

    Raises ``ValueError("email_taken")`` if the email already exists.
    """
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ValueError("email_taken")

    base_slug = re.sub(r"[^a-z0-9]+", "-", tenant_name.lower()).strip("-")
    slug = f"{base_slug}-{secrets.token_hex(4)}"
    tenant = Tenant(id=uuid4(), name=tenant_name, slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email=email,
        password_hash=password_hash,
        first_name=first_name or None,
        last_name=last_name or None,
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


def mint_handoff(user_id: str) -> str:
    """Mint a short-TTL one-time handoff token (login success → frontend exchange)."""
    now = int(time.time())
    return jwt.encode(
        {
            "purpose": _HANDOFF_PURPOSE,
            "sub": user_id,
            "iat": now,
            "exp": now + _HANDOFF_TTL_SECONDS,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def verify_handoff(token: str) -> str | None:
    """Return the user id from a valid handoff token, or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _HANDOFF_PURPOSE:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None
