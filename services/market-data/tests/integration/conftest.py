"""Integration fixtures: a real TimescaleDB via testcontainers.

These tests exercise real SQL / hypertables / continuous aggregates with no
mocking of the store. They require Docker; when it's unavailable the fixtures
``skip`` (rather than fail) so the unit suite still runs in constrained
environments.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llamatrade_events import EventBus

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
def kafka_bootstrap() -> Iterator[str]:
    """A Kafka bootstrap server: a provided broker (CI) or a throwaway container.

    Prefers ``KAFKA_BOOTSTRAP_SERVERS`` (the CI service container); otherwise
    spins a throwaway ``KafkaContainer`` via testcontainers, skipping when
    neither is available.
    """
    provided = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if provided:
        yield provided
        return
    kafka_mod = pytest.importorskip("testcontainers.kafka")
    try:
        container = kafka_mod.KafkaContainer()
        container.start()
    except Exception as exc:
        pytest.skip(f"Kafka container unavailable: {exc}")
    try:
        yield container.get_bootstrap_server()
    finally:
        container.stop()


@pytest_asyncio.fixture
async def event_bus(
    kafka_bootstrap: str, request: pytest.FixtureRequest
) -> AsyncIterator[EventBus]:
    """A real EventBus (Kafka transport) on a throwaway broker, isolated per test by namespace."""
    from llamatrade_events.transport.kafka import KafkaTransport

    namespace = f"itest{abs(hash(request.node.nodeid)) % 1_000_000}"
    bus = EventBus(KafkaTransport(kafka_bootstrap, namespace=namespace))
    try:
        yield bus
    finally:
        await bus.close()
