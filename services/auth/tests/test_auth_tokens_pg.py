"""Auth-token semantics over real Postgres: single-use, expiry, invalidation.

Runs under the enforcing RLS role (see conftest); the token layer is exercised
with the system bypass, exactly as the servicer's identity-authority session
provides it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.auth import AuthToken, Tenant, User

from src.services.tokens import (
    PURPOSE_EMAIL_VERIFY,
    PURPOSE_PASSWORD_RESET,
    consume_token,
    issue_token,
)


async def _seed_user(session_factory: async_sessionmaker) -> tuple[object, object]:
    tenant_id, user_id = uuid4(), uuid4()
    async with system_session(session_factory) as db:
        db.add(Tenant(id=tenant_id, name="t", slug=f"t-{tenant_id.hex[:8]}"))
        db.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=f"{user_id.hex[:8]}@test",
                password_hash="x",
                is_active=True,
            )
        )
        await db.commit()
    return tenant_id, user_id


async def test_issue_and_consume_round_trip(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    assert "/reset-password?token=" in issued.link

    async with system_session(session_factory) as db:
        token = await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)
        await db.commit()
    assert token is not None
    assert token.user_id == user_id


async def test_token_is_single_use(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with system_session(session_factory) as db:
        assert await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)
        await db.commit()
    async with system_session(session_factory) as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_wrong_purpose_rejected(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_EMAIL_VERIFY
        )
        await db.commit()
    async with system_session(session_factory) as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_expired_token_rejected(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with system_session(session_factory) as db:
        rows = await db.execute(select(AuthToken))
        for row in rows.scalars():
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    async with system_session(session_factory) as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_reissue_invalidates_older_token(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        first = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with system_session(session_factory) as db:
        second = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with system_session(session_factory) as db:
        assert (await consume_token(db, token=first.token, purpose=PURPOSE_PASSWORD_RESET)) is None
        assert await consume_token(db, token=second.token, purpose=PURPOSE_PASSWORD_RESET)


async def test_raw_token_never_stored(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_EMAIL_VERIFY
        )
        await db.commit()
    async with system_session(session_factory) as db:
        rows = await db.execute(select(AuthToken))
        hashes = [row.token_hash for row in rows.scalars()]
    assert issued.token not in hashes
    assert all(len(h) == 64 for h in hashes)
