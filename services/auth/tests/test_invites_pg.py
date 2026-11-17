"""Invite-only registration and the invite tools over real Postgres.

Covers redeeming through Register, each refusal (missing, unknown, wrong email,
used, expired), single-winner redemption under concurrency, the OAuth sign-up
path, and ``make waitlist-invite`` end to end through to a successful sign-up.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.auth import InviteCode, Tenant, User, WaitlistEntry
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_proto.generated import auth_pb2, events_pb2
from tests.conftest import NewInvite
from tests.fakes import MockRequestContext, published_envelopes, published_notifications

from src.services.invites import (
    CODE_EXPIRED,
    CODE_INVALID,
    CODE_REQUIRED,
    CODE_USED,
    InviteCodeError,
    format_code,
    redeem_invite,
)
from src.services.waitlist import join_waitlist

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

PASSWORD = "SecurePass123"


@pytest.fixture
def servicer(session_factory: async_sessionmaker) -> AuthServicer:
    from src.grpc.servicer import AuthServicer

    instance = AuthServicer()
    instance._session_maker = session_factory
    instance._rate_limiter = None
    instance._revocation = None
    return instance


async def _register(servicer: AuthServicer, email: str, code: str) -> auth_pb2.RegisterResponse:
    request = auth_pb2.RegisterRequest(
        tenant_name="Acme", email=email, password=PASSWORD, invite_code=code
    )
    return await servicer.register(request, MockRequestContext())


async def _invite(session_factory: async_sessionmaker, code: str) -> InviteCode:
    async with system_session(session_factory) as db:
        row = await db.scalar(select(InviteCode).where(InviteCode.code == code))
    assert row is not None
    return row


async def _users(session_factory: async_sessionmaker) -> list[str]:
    async with system_session(session_factory) as db:
        return list((await db.execute(select(User.email))).scalars().all())


async def _refusal(servicer: AuthServicer, email: str, code: str) -> ConnectError:
    with pytest.raises(ConnectError) as exc_info:
        await _register(servicer, email, code)
    assert exc_info.value.code == Code.INVALID_ARGUMENT
    return exc_info.value


async def test_register_with_open_code_marks_it_used_by_the_new_user(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite()

    response = await _register(servicer, "new@example.com", code)

    invite = await _invite(session_factory, code)
    assert invite.used_by == UUID(response.user.id)
    assert invite.used_at is not None


async def test_code_is_accepted_in_display_form_and_any_case(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite()

    await _register(servicer, "new@example.com", f" {format_code(code).lower()} ")

    assert (await _invite(session_factory, code)).used_at is not None


async def test_email_bound_code_matches_case_insensitively(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite(email="Invited@Example.com")

    await _register(servicer, "INVITED@example.COM", code)

    assert (await _invite(session_factory, code)).used_at is not None


async def test_email_bound_code_refuses_another_email(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite(email="invited@example.com")

    error = await _refusal(servicer, "someone-else@example.com", code)

    assert error.message == CODE_INVALID
    assert (await _invite(session_factory, code)).used_at is None
    assert await _users(session_factory) == []


async def test_missing_code_is_refused(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    error = await _refusal(servicer, "new@example.com", "")

    assert error.message == CODE_REQUIRED
    assert await _users(session_factory) == []


async def test_unknown_code_is_refused_like_a_wrong_email(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    error = await _refusal(servicer, "new@example.com", "ZZZZ-ZZZZ")

    assert error.message == CODE_INVALID
    assert await _users(session_factory) == []


async def test_used_code_is_refused(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite()
    await _register(servicer, "first@example.com", code)

    error = await _refusal(servicer, "second@example.com", code)

    assert error.message == CODE_USED
    assert await _users(session_factory) == ["first@example.com"]


async def test_expired_code_is_refused(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite(ttl=timedelta(seconds=-1))

    error = await _refusal(servicer, "new@example.com", code)

    assert error.message == CODE_EXPIRED
    assert (await _invite(session_factory, code)).used_at is None


async def test_failed_signup_does_not_burn_the_code(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite()

    with pytest.raises(ConnectError):
        await servicer.register(
            auth_pb2.RegisterRequest(
                tenant_name="Acme", email="new@example.com", password="short", invite_code=code
            ),
            MockRequestContext(),
        )

    assert (await _invite(session_factory, code)).used_at is None
    await _register(servicer, "new@example.com", code)


async def test_concurrent_registrations_have_exactly_one_winner(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    code = await new_invite()

    results = await asyncio.gather(
        _register(servicer, "a@example.com", code),
        _register(servicer, "b@example.com", code),
        return_exceptions=True,
    )

    winners = [r for r in results if isinstance(r, auth_pb2.RegisterResponse)]
    losers = [r for r in results if isinstance(r, ConnectError)]
    assert len(winners) == 1
    assert [e.message for e in losers] == [CODE_USED]
    assert await _users(session_factory) == [winners[0].user.email]


async def _seed_user(session_factory: async_sessionmaker, email: str) -> UUID:
    tenant_id, user_id = uuid4(), uuid4()
    async with system_session(session_factory) as db:
        db.add(Tenant(id=tenant_id, name="t", slug=f"t-{tenant_id.hex[:8]}"))
        db.add(User(id=user_id, tenant_id=tenant_id, email=email, password_hash="x"))
        await db.commit()
    return user_id


async def test_redemption_waits_on_the_row_lock_and_loses_after_commit(
    session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    """Deterministic race: B's UPDATE blocks on A's uncommitted claim, then finds it used."""
    code = await new_invite()
    first = await _seed_user(session_factory, "a@example.com")
    second = await _seed_user(session_factory, "b@example.com")

    async with system_session(session_factory) as db_a, system_session(session_factory) as db_b:
        await redeem_invite(db_a, code, "a@example.com", first)
        contender = asyncio.create_task(redeem_invite(db_b, code, "b@example.com", second))
        await asyncio.sleep(0.2)
        assert not contender.done()
        await db_a.commit()
        with pytest.raises(InviteCodeError, match=CODE_USED):
            await contender

    assert (await _invite(session_factory, code)).used_by == first


async def test_waitlist_invite_end_to_end(
    servicer: AuthServicer,
    session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``make waitlist-invite``: entry marked invited, bound code created and emailed,
    and the emailed code then registers that address."""
    from src.tools import invites as invites_tool
    from src.tools import waitlist as waitlist_tool

    async with system_session(session_factory) as db:
        await join_waitlist(db, email="waiting@example.com", source="landing", ip_hash=None)
        await db.commit()

    async def _no_close() -> None:
        return None

    monkeypatch.setattr(waitlist_tool, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(waitlist_tool, "close_db", _no_close)
    monkeypatch.setattr(invites_tool, "NotificationEvents", lambda: notifications_module._shared)
    out = io.StringIO()
    monkeypatch.setattr(waitlist_tool.sys, "stdout", out)

    assert await waitlist_tool.run(["invite", "Waiting@Example.com"]) == 0

    async with system_session(session_factory) as db:
        entry = await db.scalar(select(WaitlistEntry))
        invite = await db.scalar(select(InviteCode))
    assert entry is not None and entry.status == "invited"
    assert invite is not None and invite.email == "waiting@example.com"
    assert invite.expires_at > datetime.now(UTC) + timedelta(days=29)

    [event] = published_notifications()
    [envelope] = published_envelopes()
    assert event.category == events_pb2.NOTIFICATION_CATEGORY_INVITE
    assert envelope.tenant_id == ""
    assert event.extra["to"] == "waiting@example.com"
    assert event.extra["code"] == format_code(invite.code)
    assert event.extra["link"].endswith(
        f"/register?email=waiting%40example.com&code={format_code(invite.code)}"
    )
    assert format_code(invite.code) in out.getvalue()

    await _register(servicer, "waiting@example.com", event.extra["code"])
    assert (await _invite(session_factory, invite.code)).used_at is not None


async def test_waitlist_invite_for_unknown_email_creates_no_code(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.tools import waitlist as waitlist_tool

    async def _no_close() -> None:
        return None

    monkeypatch.setattr(waitlist_tool, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(waitlist_tool, "close_db", _no_close)
    monkeypatch.setattr(waitlist_tool.sys, "stderr", io.StringIO())

    assert await waitlist_tool.run(["invite", "nobody@example.com"]) == 1

    async with system_session(session_factory) as db:
        assert (await db.execute(select(InviteCode))).first() is None
    assert published_notifications() == []


async def test_invite_create_without_email_sends_nothing(
    session_factory: async_sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.tools import invites as invites_tool

    async def _no_close() -> None:
        return None

    monkeypatch.setattr(invites_tool, "get_session_maker", lambda: session_factory)
    monkeypatch.setattr(invites_tool, "close_db", _no_close)
    out = io.StringIO()
    monkeypatch.setattr(invites_tool.sys, "stdout", out)

    assert await invites_tool.run(["create", "--days", "7"]) == 0

    async with system_session(session_factory) as db:
        invite = await db.scalar(select(InviteCode))
    assert invite is not None and invite.email is None
    assert "/register?code=" in out.getvalue()
    assert published_notifications() == []
