"""Integration fixtures: real Postgres + real Redis via testcontainers.

The schema is stood up from the ORM metadata (backtest + strategy modules only).
The native enum types the models reference carry ``create_type=False`` (the
migration chain owns them in production), so they are created here first,
straight from the TypeDecorator impls. The ``backtest_results`` tenant-fill
trigger from migration 039 is recreated too, because the worker never sets
``tenant_id`` on result rows and the column is NOT NULL.

These require Docker; when it is unavailable the fixtures ``skip`` so the fast
unit suite still runs in constrained environments, except under
``CI_REQUIRE_DOCKER=1`` (set in CI) where the guard fails loudly instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker, create_async_engine

POSTGRES_IMAGE = "postgres:16-alpine"
REDIS_IMAGE = "redis:7-alpine"

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"


def _skip_or_fail(reason: str) -> NoReturn:
    """Skip locally; fail when CI_REQUIRE_DOCKER=1 demands the Docker-gated tests run."""
    if _REQUIRE_DOCKER:
        pytest.fail(f"CI_REQUIRE_DOCKER=1: {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway Postgres and yield an asyncpg URL, or skip."""
    if _REQUIRE_DOCKER:
        import testcontainers.postgres as postgres_mod
    else:
        postgres_mod = pytest.importorskip("testcontainers.postgres")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="backtest"
        )
        container.start()
    except Exception as exc:  # Docker down / image pull blocked
        _skip_or_fail(f"Postgres container unavailable: {exc}")
    try:
        raw_url = container.get_connection_url()
        yield raw_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Start a throwaway Redis and yield its URL, or skip."""
    if _REQUIRE_DOCKER:
        import testcontainers.redis as redis_mod
    else:
        redis_mod = pytest.importorskip("testcontainers.redis")
    try:
        container = redis_mod.RedisContainer(REDIS_IMAGE)
        container.start()
    except Exception as exc:  # Docker down / image pull blocked
        _skip_or_fail(f"Redis container unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


def _schema_tables() -> list[Table]:
    """The explicit table subset for this tier.

    Other suites in the process register the full model package on
    ``Base.metadata`` (the servicer imports ``plan_limits``), which includes
    extension-backed tables; creating only these keeps the schema on vanilla
    Postgres.
    """
    from typing import cast

    from llamatrade_db.models.backtest import Backtest, BacktestResult
    from llamatrade_db.models.strategy import Strategy, StrategyVersion

    return [
        cast(Table, Strategy.__table__),
        cast(Table, StrategyVersion.__table__),
        cast(Table, Backtest.__table__),
        cast(Table, BacktestResult.__table__),
    ]


async def _create_enum_types(conn: AsyncConnection, tables: list[Table]) -> None:
    """Create the native enum types the models reference with create_type=False."""
    from sqlalchemy import Enum as SAEnum

    seen: set[str] = set()
    for table in tables:
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


# Mirrors migration 039: writers never set backtest_results.tenant_id; a BEFORE
# INSERT trigger copies it from the parent backtests row.
_TENANT_FILL_FUNCTION = """
CREATE OR REPLACE FUNCTION backtest_results_fill_tenant_id() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS NULL THEN
        SELECT tenant_id INTO NEW.tenant_id
        FROM backtests WHERE id = NEW.backtest_id;
    END IF;
    RETURN NEW;
END;
$$
"""

_TENANT_FILL_TRIGGER = """
CREATE TRIGGER trg_backtest_results_fill_tenant_id
    BEFORE INSERT ON backtest_results
    FOR EACH ROW EXECUTE FUNCTION backtest_results_fill_tenant_id()
"""


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker]:
    """An async session factory with a fresh backtest + strategy schema per test."""
    from llamatrade_db.base import Base

    tables = _schema_tables()
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))
        await _create_enum_types(conn, tables)
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.execute(text(_TENANT_FILL_FUNCTION))
        await conn.execute(text(_TENANT_FILL_TRIGGER))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
