"""Shared auth test fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

POSTGRES_IMAGE = "postgres:16-alpine"

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"

_APP_ROLE = "auth_rls_app"
_APP_PASSWORD = "auth_rls_app_pw"


@pytest.fixture(autouse=True)
def _fake_notification_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the shared notification publisher at an in-memory stream."""
    from llamatrade_events import EventBus
    from llamatrade_events.catalog import notifications as notifications_module
    from llamatrade_events.catalog.notifications import NotificationEvents
    from llamatrade_events.testing import FakeTransport

    monkeypatch.setattr(
        notifications_module,
        "_shared",
        NotificationEvents(bus=EventBus(FakeTransport())),
    )


def _skip_or_fail(reason: str) -> NoReturn:
    """Skip locally; fail when CI_REQUIRE_DOCKER=1 demands the Docker-gated tests run."""
    if _REQUIRE_DOCKER:
        pytest.fail(f"CI_REQUIRE_DOCKER=1: {reason}", pytrace=False)
    pytest.skip(reason)


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    if _REQUIRE_DOCKER:
        import testcontainers.postgres as postgres_mod
    else:
        postgres_mod = pytest.importorskip("testcontainers.postgres")
    if not _docker_available():
        _skip_or_fail("Docker unavailable")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="auth"
        )
        container.start()
    except Exception as exc:
        _skip_or_fail(f"Postgres container unavailable: {exc}")
    try:
        raw_url = container.get_connection_url()
        yield raw_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker]:
    """Schema with tenant RLS enforced, yielded via a NON-superuser app role.

    The container superuser builds the tables and policies and provisions a plain
    login role; the returned factory connects as that role, so every PG-backed
    test runs with the policies actually applying (superusers bypass RLS).
    """
    import llamatrade_db.models.auth
    from llamatrade_db.base import Base
    from llamatrade_db.rls import RLS_TABLES, enable_rls_statements

    _ = llamatrade_db.models.auth
    admin = create_async_engine(postgres_url)
    async with admin.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for table in RLS_TABLES:
            if table not in Base.metadata.tables:
                continue
            for statement in enable_rls_statements(table):
                await conn.execute(text(statement))
        # The container is session-scoped; the role persists, grants are re-run
        # because each test rebuilds the tables.
        role_exists = await conn.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": _APP_ROLE}
        )
        if not role_exists:
            await conn.execute(text(f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_APP_PASSWORD}'"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f"IN SCHEMA public TO {_APP_ROLE}"
            )
        )
        await conn.execute(
            text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_APP_ROLE}")
        )
    await admin.dispose()

    app_url = make_url(postgres_url).set(username=_APP_ROLE, password=_APP_PASSWORD)
    engine = create_async_engine(app_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()
