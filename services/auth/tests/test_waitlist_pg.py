"""JoinWaitlist and the operator helpers over real Postgres.

Covers normalised storage, the uniform answer on a repeat join, the honeypot,
server-side validation, the per-IP and per-email rate limits, and mark-invited.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_common import RateLimiter
from llamatrade_common.testing import FakeRedis
from llamatrade_db import system_session
from llamatrade_db.models.auth import WaitlistEntry
from llamatrade_proto.generated import auth_pb2
from tests.fakes import MockRequestContext

from src.services.waitlist import hash_ip, list_entries, mark_invited

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

CLIENT_IP = "203.0.113.7"


def _ctx(ip: str | None = CLIENT_IP) -> MockRequestContext:
    """Request context as the LB would forward it (client IP, then the LB hop)."""
    return MockRequestContext({"x-forwarded-for": f"{ip}, 10.0.0.1"} if ip else {})


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def servicer(session_factory: async_sessionmaker, redis: FakeRedis) -> AuthServicer:
    from src.grpc.servicer import AuthServicer

    instance = AuthServicer()
    instance._session_maker = session_factory
    instance._rate_limiter = RateLimiter(redis, fail_closed=True)
    instance._revocation = None
    return instance


async def _rows(session_factory: async_sessionmaker) -> list[WaitlistEntry]:
    async with system_session(session_factory) as db:
        return list((await db.execute(select(WaitlistEntry))).scalars().all())


async def _join(
    servicer: AuthServicer,
    email: str,
    *,
    source: str = "landing",
    company: str = "",
    ip: str | None = CLIENT_IP,
) -> auth_pb2.JoinWaitlistResponse:
    request = auth_pb2.JoinWaitlistRequest(email=email, source=source, company=company)
    return await servicer.join_waitlist(request, _ctx(ip))


async def test_join_stores_normalised_email_source_and_ip_hash(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    response = await _join(servicer, "  New.Person@Example.COM ", source="join")

    assert response.success
    assert response.message == "You're on the list. We'll email you when a place opens."
    [row] = await _rows(session_factory)
    assert row.email == "new.person@example.com"
    assert row.source == "join"
    assert row.status == "waiting"
    assert row.invited_at is None
    assert row.ip_hash == hash_ip(CLIENT_IP)
    assert row.created_at is not None


async def test_join_without_trusted_ip_stores_no_hash(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    await _join(servicer, "noip@example.com", ip=None)

    [row] = await _rows(session_factory)
    assert row.ip_hash is None


async def test_join_twice_answers_the_same_and_keeps_one_row(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    first = await _join(servicer, "twice@example.com", source="landing")
    second = await _join(servicer, "TWICE@example.com ", source="join")

    assert first == second
    [row] = await _rows(session_factory)
    assert row.email == "twice@example.com"
    assert row.source == "landing"


async def test_repeat_join_does_not_reset_an_invited_entry(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    await _join(servicer, "invited@example.com")
    async with system_session(session_factory) as db:
        await mark_invited(db, "invited@example.com")
        await db.commit()

    await _join(servicer, "invited@example.com")

    [row] = await _rows(session_factory)
    assert row.status == "invited"
    assert row.invited_at is not None


async def test_honeypot_answers_success_and_stores_nothing(
    servicer: AuthServicer, session_factory: async_sessionmaker, redis: FakeRedis
) -> None:
    response = await _join(servicer, "bot@example.com", company="Acme Inc")

    assert response.success
    assert response == await _join(servicer, "real@example.com")
    assert [row.email for row in await _rows(session_factory)] == ["real@example.com"]
    assert not any("bot@example.com" in key for key in redis.store)


async def test_honeypot_wins_even_with_an_invalid_email(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    response = await _join(servicer, "not-an-email", company="x")

    assert response.success
    assert await _rows(session_factory) == []


@pytest.mark.parametrize("email", ["", "not-an-email", "you@example", "a b@example.com"])
async def test_invalid_email_is_rejected_and_not_stored(
    servicer: AuthServicer, session_factory: async_sessionmaker, email: str
) -> None:
    with pytest.raises(ConnectError) as exc:
        await _join(servicer, email)

    assert exc.value.code == Code.INVALID_ARGUMENT
    assert await _rows(session_factory) == []


async def test_unknown_source_is_rejected(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    with pytest.raises(ConnectError) as exc:
        await _join(servicer, "ok@example.com", source="newsletter")

    assert exc.value.code == Code.INVALID_ARGUMENT
    assert await _rows(session_factory) == []


async def test_per_ip_limit_is_five_per_ten_minutes(
    servicer: AuthServicer, session_factory: async_sessionmaker, redis: FakeRedis
) -> None:
    for i in range(5):
        await _join(servicer, f"person{i}@example.com")

    with pytest.raises(ConnectError) as exc:
        await _join(servicer, "person5@example.com")

    assert exc.value.code == Code.RESOURCE_EXHAUSTED
    assert len(await _rows(session_factory)) == 5
    ip_keys = [key for key in redis.store if f"waitlist:ip:{CLIENT_IP}" in key]
    assert ip_keys and all(redis.ttls[key] == 600 for key in ip_keys)
    # Another address is unaffected.
    await _join(servicer, "person5@example.com", ip="198.51.100.9")


async def test_per_email_limit_applies_without_a_trusted_ip(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    for _ in range(5):
        await _join(servicer, "Same@example.com", ip=None)

    with pytest.raises(ConnectError) as exc:
        await _join(servicer, "same@example.com ", ip=None)

    assert exc.value.code == Code.RESOURCE_EXHAUSTED
    assert len(await _rows(session_factory)) == 1


async def test_limiter_outage_fails_closed(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    servicer._rate_limiter = RateLimiter(FakeRedis(error=True), fail_closed=True)

    with pytest.raises(ConnectError) as exc:
        await _join(servicer, "outage@example.com")

    assert exc.value.code == Code.RESOURCE_EXHAUSTED
    assert await _rows(session_factory) == []


async def test_mark_invited_sets_status_once_and_lists_by_status(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    await _join(servicer, "first@example.com")
    await _join(servicer, "second@example.com")

    async with system_session(session_factory) as db:
        entry = await mark_invited(db, "  FIRST@example.com ")
        assert entry is not None
        first_invited_at = entry.invited_at
        await db.commit()
    async with system_session(session_factory) as db:
        again = await mark_invited(db, "first@example.com")
        assert again is not None
        assert again.invited_at == first_invited_at
        assert await mark_invited(db, "missing@example.com") is None

        invited = await list_entries(db, status="invited")
        waiting = await list_entries(db, status="waiting")
        everyone = await list_entries(db)
    assert [e.email for e in invited] == ["first@example.com"]
    assert [e.email for e in waiting] == ["second@example.com"]
    assert [e.email for e in everyone] == ["first@example.com", "second@example.com"]


async def test_email_is_unique_at_the_database(session_factory: async_sessionmaker) -> None:
    from sqlalchemy.exc import IntegrityError

    async with system_session(session_factory) as db:
        db.add(WaitlistEntry(email="dup@example.com", source="landing"))
        await db.commit()
    async with system_session(session_factory) as db:
        db.add(WaitlistEntry(email="dup@example.com", source="join"))
        with pytest.raises(IntegrityError):
            await db.commit()
    async with system_session(session_factory) as db:
        count = await db.scalar(select(func.count()).select_from(WaitlistEntry))
    assert count == 1
