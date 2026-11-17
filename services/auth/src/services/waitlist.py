"""Marketing waitlist: normalise and validate signups, store them once, mark invites."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.auth import (
    WAITLIST_STATUS_INVITED,
    WAITLIST_STATUS_WAITING,
    WaitlistEntry,
)

WAITLIST_SOURCES: frozenset[str] = frozenset({"landing", "join"})
DEFAULT_SOURCE = "landing"
MAX_EMAIL_LENGTH = 320


class WaitlistValidationError(ValueError):
    """The submitted email or source is not acceptable."""


def normalize_email(raw: str) -> str:
    """Trimmed, lowercased email, the form every lookup and the unique index use."""
    return raw.strip().lower()


def validate_waitlist_email(raw: str) -> str:
    """Normalised email when it is syntactically valid, else ``WaitlistValidationError``.

    Deliverability (DNS) is not checked: it is slow, and an invite email bounce
    is a cheaper signal than a blocking lookup on a public form.
    """
    email = normalize_email(raw)
    if not email or len(email) > MAX_EMAIL_LENGTH:
        raise WaitlistValidationError("Please enter a valid email address.")
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise WaitlistValidationError("Please enter a valid email address.") from exc
    return email


def resolve_source(raw: str) -> str:
    """Known source tag; empty means the landing page."""
    source = raw.strip().lower() or DEFAULT_SOURCE
    if source not in WAITLIST_SOURCES:
        raise WaitlistValidationError("Unknown waitlist source.")
    return source


def hash_ip(ip: str | None) -> str | None:
    """SHA-256 of the client IP, so abuse can be correlated without keeping the address."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()


async def join_waitlist(db: AsyncSession, *, email: str, source: str, ip_hash: str | None) -> bool:
    """Insert ``email`` unless it is already listed; True when a new row was written."""
    stmt = (
        insert(WaitlistEntry)
        .values(email=email, source=source, status=WAITLIST_STATUS_WAITING, ip_hash=ip_hash)
        .on_conflict_do_nothing(index_elements=[WaitlistEntry.email])
        .returning(WaitlistEntry.id)
    )
    inserted = (await db.execute(stmt)).scalar_one_or_none()
    return inserted is not None


async def list_entries(db: AsyncSession, *, status: str | None = None) -> Sequence[WaitlistEntry]:
    """Entries oldest first, optionally filtered by status."""
    query = select(WaitlistEntry).order_by(WaitlistEntry.created_at, WaitlistEntry.email)
    if status is not None:
        query = query.where(WaitlistEntry.status == status)
    return (await db.execute(query)).scalars().all()


async def mark_invited(db: AsyncSession, raw_email: str) -> WaitlistEntry | None:
    """Set the entry to invited (keeping the first ``invited_at``); None when not listed."""
    email = normalize_email(raw_email)
    result = await db.execute(select(WaitlistEntry).where(WaitlistEntry.email == email))
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    if entry.status != WAITLIST_STATUS_INVITED:
        entry.status = WAITLIST_STATUS_INVITED
        entry.invited_at = datetime.now(UTC)
    return entry
