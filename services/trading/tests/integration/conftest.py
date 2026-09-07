"""Real-Postgres fixtures for trading DB-constraint tests (testcontainers).

Mirrors the strategy service's tenant-isolation harness: a throwaway Postgres
container per module, only the trading tables created, and a clean skip when
Docker or testcontainers is unavailable so the fast unit suite stays green on
constrained machines — except under ``CI_REQUIRE_DOCKER=1`` (CI), where the
guard fails loudly instead.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from typing import NoReturn, cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_db.base import Base
from llamatrade_db.models.trading import Order, TradingSession

POSTGRES_IMAGE = "postgres:16-alpine"
_TABLES = [cast(Table, TradingSession.__table__), cast(Table, Order.__table__)]

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"


def _skip_or_fail(reason: str) -> NoReturn:
    """Skip locally; fail when CI_REQUIRE_DOCKER=1 demands the Docker-gated tests run."""
    if _REQUIRE_DOCKER:
        pytest.fail(f"CI_REQUIRE_DOCKER=1: {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def kafka_bootstrap() -> Iterator[str]:
    """Bootstrap servers for a real Kafka broker (env-provided or a throwaway container).

    Honors ``KAFKA_BOOTSTRAP_SERVERS`` when set (CI points it at a shared broker);
    otherwise spins a throwaway ``KafkaContainer``, skipping (or failing under
    ``CI_REQUIRE_DOCKER=1``) when Docker / the container image is unavailable.
    """
    env_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if env_bootstrap:
        yield env_bootstrap
        return

    if _REQUIRE_DOCKER:
        import testcontainers.kafka as kafka_mod
    else:
        kafka_mod = pytest.importorskip("testcontainers.kafka")
    try:
        container = kafka_mod.KafkaContainer()
        container.start()
    except Exception as exc:  # Docker down / image pull blocked
        _skip_or_fail(f"Kafka container unavailable: {exc}")
    try:
        yield container.get_bootstrap_server()
    finally:
        container.stop()


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    """Start a throwaway Postgres for the module, or skip without Docker."""
    if _REQUIRE_DOCKER:
        import testcontainers.postgres as postgres_mod
    else:
        postgres_mod = pytest.importorskip("testcontainers.postgres")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="trading_constraints"
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


@pytest.fixture(scope="module")
def schema(pg_url: str) -> str:
    """Create just the trading tables once (they FK only among themselves)."""

    async def _create() -> None:
        engine = create_async_engine(pg_url)
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=_TABLES, checkfirst=True)
            )
        await engine.dispose()

    asyncio.run(_create())
    return pg_url


@pytest_asyncio.fixture
async def db(schema: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(schema, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()
