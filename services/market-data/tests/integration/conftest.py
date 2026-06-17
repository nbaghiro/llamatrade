"""Integration fixtures: a real TimescaleDB via testcontainers.

These tests exercise real SQL / hypertables / continuous aggregates with no
mocking of the store. They require Docker; when it's unavailable the fixtures
``skip`` (rather than fail) so the unit suite still runs in constrained
environments.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.store.migrate import run_migrations
from src.store.repository import BarStore

# Community Timescale on pg16 (matches the deployed image).
TIMESCALE_IMAGE = "timescale/timescaledb:2.17.2-pg16"


@pytest.fixture(scope="session")
def timescale_url() -> Iterator[str]:
    """Start a throwaway TimescaleDB and yield an asyncpg URL, or skip."""
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    container = postgres_mod.PostgresContainer(
        TIMESCALE_IMAGE, username="test", password="test", dbname="market_data"
    )
    try:
        container.start()
    except Exception as exc:  # Docker not reachable, image pull blocked, etc.
        pytest.skip(f"TimescaleDB container unavailable: {exc}")

    try:
        raw_url = container.get_connection_url()  # postgresql+psycopg2://...
        async_url = raw_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        yield async_url
    finally:
        container.stop()


@pytest_asyncio.fixture
async def timescale_engine(timescale_url: str):
    """A migrated engine with the base tables truncated for per-test isolation.

    The container is shared across tests, so each test starts from empty base
    tables (migrations are idempotent and only run once effectively).
    """
    engine = create_async_engine(timescale_url)
    await run_migrations(engine)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("TRUNCATE bars_1m, bars_daily")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def bar_store(timescale_engine) -> AsyncIterator[BarStore]:
    """A BarStore bound to the isolated Timescale engine."""
    session_factory = async_sessionmaker(timescale_engine, expire_on_commit=False)
    yield BarStore(session_factory)


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """Start a throwaway Redis and yield its URL, or skip."""
    redis_mod = pytest.importorskip("testcontainers.redis")
    container = redis_mod.RedisContainer("redis:7-alpine")
    try:
        container.start()
    except Exception as exc:
        pytest.skip(f"Redis container unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest_asyncio.fixture
async def event_bus(redis_url: str):
    """A real EventBus (Redis Streams transport) on a throwaway Redis, flushed per test."""
    from llamatrade_events import EventBus, RedisStreamsTransport

    transport = RedisStreamsTransport(redis_url)
    client = await transport._client()
    await client.flushdb()
    bus = EventBus(transport)
    try:
        yield bus
    finally:
        await bus.close()
