"""Shared session helpers: token minting + tenant/user creation.

Single source used by both the Connect servicer (login/register) and the OAuth
routes so every path issues identical sessions and creates users the same way.

Importing this module resolves the user-token signing key, so a
production/staging auth service without the RS256 keypair fails at startup.
"""

from __future__ import annotations

import asyncio
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

from llamatrade_common.auth import user_token_signing_key, user_token_verification_key
from llamatrade_db.models.auth import Tenant, User
from llamatrade_telemetry import metrics

SIGNING_KEY, SIGNING_ALGORITHM = user_token_signing_key()
VERIFY_KEY, VERIFY_ALGORITHM = user_token_verification_key()
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
_HANDOFF_PURPOSE = "alpaca_oauth_handoff"
HANDOFF_TTL_SECONDS = 120

_MIN_PASSWORD_LENGTH = 8


class PasswordPolicyError(ValueError):
    """Password fails the strength policy."""


def validate_password_strength(password: str) -> None:
    """Raise ``PasswordPolicyError`` when the password fails the policy."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must be at least {_MIN_PASSWORD_LENGTH} characters")
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise PasswordPolicyError("password must contain at least one letter and one digit")


@dataclass
class AccessRefresh:
    """A minted access + refresh token pair with expiries."""

    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime


def mint_access_refresh(user: User) -> AccessRefresh:
    """Mint the access + refresh JWTs for a user (the canonical login session).

    Each token carries a unique ``jti`` so it can be individually revoked.
    """
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
            "jti": uuid4().hex,
            "iat": now,
            "exp": access_expire,
        },
        SIGNING_KEY,
        algorithm=SIGNING_ALGORITHM,
    )
    refresh = jwt.encode(
        {
            "sub": str(user.id),
            "tenant_id": str(user.tenant_id),
            "type": "refresh",
            "jti": uuid4().hex,
            "iat": now,
            "exp": refresh_expire,
        },
        SIGNING_KEY,
        algorithm=SIGNING_ALGORITHM,
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
) -> tuple[User, Tenant]:
    """Create a tenant + its first (admin) user; ``flush`` but do not commit.

    Raises ``PasswordPolicyError`` for a weak password and
    ``ValueError("email_taken")`` if the email already exists.
    """
    validate_password_strength(password)

    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ValueError("email_taken")

    base_slug = re.sub(r"[^a-z0-9]+", "-", tenant_name.lower()).strip("-")
    slug = f"{base_slug}-{secrets.token_hex(4)}"
    tenant = Tenant(id=uuid4(), name=tenant_name, slug=slug, is_active=True)
    db.add(tenant)
    await db.flush()

    with metrics.auth.bcrypt_hash_duration.time():
        password_hash = (
            await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())
        ).decode()
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
    return user, tenant


@dataclass
class Handoff:
    """Verified contents of a one-time handoff token."""

    user_id: str
    jti: str


def mint_handoff(user_id: str) -> str:
    """Mint a short-TTL one-time handoff token (login success → frontend exchange)."""
    now = int(time.time())
    return jwt.encode(
        {
            "purpose": _HANDOFF_PURPOSE,
            "sub": user_id,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + HANDOFF_TTL_SECONDS,
        },
        SIGNING_KEY,
        algorithm=SIGNING_ALGORITHM,
    )


def verify_handoff(token: str) -> Handoff | None:
    """Return the verified handoff claims, or None."""
    try:
        payload = jwt.decode(token, VERIFY_KEY, algorithms=[VERIFY_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _HANDOFF_PURPOSE:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    return Handoff(user_id=str(sub), jti=str(payload.get("jti", "")))
