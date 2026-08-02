"""Auth-token semantics over real Postgres: single-use, expiry, invalidation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llamatrade_db.models.auth import AuthToken, Tenant, User

from src.services.tokens import (
    PURPOSE_EMAIL_VERIFY,
    PURPOSE_PASSWORD_RESET,
    consume_token,
    issue_token,
)

POSTGRES_IMAGE = "postgres:16-alpine"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    if not _docker_available():
        pytest.skip("Docker unavailable")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="auth"
        )
        container.start()
    except Exception as exc:
        pytest.skip(f"Postgres container unavailable: {exc}")
    try:
        raw_url = container.get_connection_url()
        yield raw_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker]:
    import llamatrade_db.models.auth
    from llamatrade_db.base import Base

    _ = llamatrade_db.models.auth
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_user(session_factory: async_sessionmaker) -> tuple[object, object]:
    tenant_id, user_id = uuid4(), uuid4()
    async with session_factory() as db:
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
    async with session_factory() as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    assert "/reset-password?token=" in issued.link

    async with session_factory() as db:
        token = await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)
        await db.commit()
    assert token is not None
    assert token.user_id == user_id


async def test_token_is_single_use(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with session_factory() as db:
        assert await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)
        await db.commit()
    async with session_factory() as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_wrong_purpose_rejected(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_EMAIL_VERIFY
        )
        await db.commit()
    async with session_factory() as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_expired_token_rejected(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with session_factory() as db:
        rows = await db.execute(select(AuthToken))
        for row in rows.scalars():
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    async with session_factory() as db:
        assert (await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)) is None


async def test_reissue_invalidates_older_token(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        first = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with session_factory() as db:
        second = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()
    async with session_factory() as db:
        assert (await consume_token(db, token=first.token, purpose=PURPOSE_PASSWORD_RESET)) is None
        assert await consume_token(db, token=second.token, purpose=PURPOSE_PASSWORD_RESET)


async def test_raw_token_never_stored(session_factory: async_sessionmaker) -> None:
    tenant_id, user_id = await _seed_user(session_factory)
    async with session_factory() as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_EMAIL_VERIFY
        )
        await db.commit()
    async with session_factory() as db:
        rows = await db.execute(select(AuthToken))
        hashes = [row.token_hash for row in rows.scalars()]
    assert issued.token not in hashes
    assert all(len(h) == 64 for h in hashes)
