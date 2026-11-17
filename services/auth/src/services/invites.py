"""Invite codes: mint, check and redeem the single-use codes sign-up requires."""

from __future__ import annotations

import os
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.auth import InviteCode
from llamatrade_events.catalog.notifications import NotificationEvent, NotificationEvents
from llamatrade_proto.generated import events_pb2

from src.services.waitlist import normalize_email

# No 0/O, 1/I/L: codes get read aloud and retyped from email.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
DEFAULT_TTL = timedelta(days=30)
_MAX_GENERATE_ATTEMPTS = 5

_APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8800")

CODE_REQUIRED = "Enter your invite code to create an account."
CODE_INVALID = "That invite code isn't valid. Check the code, and use the email address the invite was sent to."
CODE_USED = "That invite code has already been used."
CODE_EXPIRED = "That invite code has expired. Ask for a new invite."


class InviteCodeError(Exception):
    """The invite code cannot be used for this sign-up; the message is safe to show."""


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw: str) -> str:
    """Uppercase with spaces and dashes removed, the form stored in ``invite_codes``."""
    return "".join(ch for ch in raw.upper() if ch not in " -\t")


def format_code(code: str) -> str:
    """Display form, e.g. ``ABCD-EFGH``."""
    half = len(code) // 2
    return f"{code[:half]}-{code[half:]}"


def invite_link(code: str, email: str | None) -> str:
    """Sign-up link that pre-fills the code (and the email, when the code is bound to one)."""
    params = {"email": email, "code": format_code(code)} if email else {"code": format_code(code)}
    return f"{_APP_BASE_URL}/register?{urlencode(params)}"


async def create_invite(
    db: AsyncSession, *, email: str | None = None, ttl: timedelta = DEFAULT_TTL
) -> InviteCode:
    """Add a fresh code (flushed, not committed), bound to ``email`` when given."""
    for _ in range(_MAX_GENERATE_ATTEMPTS):
        code = generate_code()
        taken = await db.scalar(select(InviteCode.id).where(InviteCode.code == code))
        if taken is None:
            break
    else:
        raise RuntimeError("could not generate a unique invite code")
    invite = InviteCode(
        code=code,
        email=normalize_email(email) if email else None,
        expires_at=datetime.now(UTC) + ttl,
    )
    db.add(invite)
    await db.flush()
    return invite


async def list_invites(db: AsyncSession) -> Sequence[InviteCode]:
    """Every code, newest first."""
    query = select(InviteCode).order_by(InviteCode.created_at.desc(), InviteCode.code)
    return (await db.execute(query)).scalars().all()


def _refusal(invite: InviteCode | None, email: str, now: datetime) -> str | None:
    """Why ``invite`` cannot be redeemed by ``email``; None when it can."""
    if invite is None or (invite.email is not None and invite.email != email):
        return CODE_INVALID
    if invite.used_at is not None:
        return CODE_USED
    if invite.expires_at <= now:
        return CODE_EXPIRED
    return None


async def check_invite(db: AsyncSession, raw_code: str, raw_email: str) -> None:
    """Raise ``InviteCodeError`` unless the code is redeemable by this email right now."""
    code = normalize_code(raw_code)
    if not code:
        raise InviteCodeError(CODE_REQUIRED)
    invite = await db.scalar(select(InviteCode).where(InviteCode.code == code))
    reason = _refusal(invite, normalize_email(raw_email), datetime.now(UTC))
    if reason is not None:
        raise InviteCodeError(reason)


async def redeem_invite(db: AsyncSession, raw_code: str, raw_email: str, user_id: UUID) -> None:
    """Mark the code used by ``user_id`` in one conditional UPDATE.

    Concurrent redemptions serialize on the row lock; the loser re-reads
    ``used_at`` as set, matches nothing, and gets ``InviteCodeError``.
    """
    code = normalize_code(raw_code)
    email = normalize_email(raw_email)
    now = datetime.now(UTC)
    claimed = await db.scalar(
        update(InviteCode)
        .where(
            InviteCode.code == code,
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
            or_(InviteCode.email.is_(None), InviteCode.email == email),
        )
        .values(used_at=now, used_by=user_id)
        .returning(InviteCode.id)
        .execution_options(synchronize_session=False)
    )
    if claimed is None:
        await check_invite(db, raw_code, raw_email)
        raise InviteCodeError(CODE_USED)


async def send_invite_email(invite: InviteCode, events: NotificationEvents) -> None:
    """Publish the invite email to the notification service; raises if the publish fails."""
    if invite.email is None:
        raise ValueError("invite has no email address")
    event = NotificationEvent(
        category=events_pb2.NOTIFICATION_CATEGORY_INVITE,
        extra={
            "to": invite.email,
            "code": format_code(invite.code),
            "link": invite_link(invite.code, invite.email),
            "expires": invite.expires_at.date().isoformat(),
        },
    )
    await events.publish(event, tenant_id="", dedup_parts=(invite.code,))
