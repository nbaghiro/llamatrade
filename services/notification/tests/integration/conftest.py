"""Integration fixtures: real Postgres (testcontainers) + FakeTransport bus.

The schema is stood up from the ORM metadata (auth + notification modules
only). The native enum types the models reference carry ``create_type=False``
(the migration chain owns them in production), so they are created here first,
straight from the TypeDecorator impls to stay in lockstep with the models.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration

POSTGRES_IMAGE = "postgres:16-alpine"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway Postgres and yield an asyncpg URL, or skip."""
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    if not _docker_available():
        pytest.skip("Docker unavailable")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="notification"
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


async def _create_enum_types(conn: AsyncConnection) -> None:
    from sqlalchemy import Enum as SAEnum

    from llamatrade_db.base import Base

    seen: set[str] = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            impl = getattr(column.type, "impl", None)
            if isinstance(impl, SAEnum) and impl.name and impl.name not in seen:
                seen.add(impl.name)
                values = ", ".join(f"'{v}'" for v in impl.enums)
                await conn.execute(
                    text(
                        f"DO $$ BEGIN CREATE TYPE {impl.name} AS ENUM ({values}); "
                        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                    )
                )


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker]:
    """An async session factory with a fresh schema per test."""
    import llamatrade_db.models.auth
    import llamatrade_db.models.notification
    from llamatrade_db.base import Base

    _ = (llamatrade_db.models.auth, llamatrade_db.models.notification)

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await _create_enum_types(conn)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
