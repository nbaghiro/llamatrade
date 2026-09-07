"""Integration fixtures: a real TimescaleDB via testcontainers.

These tests exercise real SQL / hypertables / continuous aggregates with no
mocking of the store. They require Docker; when it's unavailable the fixtures
``skip`` so the unit suite still runs in constrained environments, except under
``CI_REQUIRE_DOCKER=1`` (set in CI) where the guard fails loudly instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llamatrade_events import EventBus

from src.store.migrate import run_migrations
from src.store.repository import BarStore

# Community Timescale on pg16 (matches the deployed image).
TIMESCALE_IMAGE = "timescale/timescaledb:2.17.2-pg16"

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"


def _skip_or_fail(reason: str) -> NoReturn:
    """Skip locally; fail when CI_REQUIRE_DOCKER=1 demands the Docker-gated tests run."""
    if _REQUIRE_DOCKER:
        pytest.fail(f"CI_REQUIRE_DOCKER=1: {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def timescale_url() -> Iterator[str]:
    """Start a throwaway TimescaleDB and yield an asyncpg URL, or skip."""
    if _REQUIRE_DOCKER:
        import testcontainers.postgres as postgres_mod
    else:
        postgres_mod = pytest.importorskip("testcontainers.postgres")
    container = postgres_mod.PostgresContainer(
        TIMESCALE_IMAGE, username="test", password="test", dbname="market_data"
    )
    try:
        container.start()
    except Exception as exc:  # Docker not reachable, image pull blocked, etc.
        _skip_or_fail(f"TimescaleDB container unavailable: {exc}")

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
    """Start a throwaway Redis and yield its URL, or skip (fail under CI_REQUIRE_DOCKER)."""
    if _REQUIRE_DOCKER:
        import testcontainers.redis as redis_mod
    else:
        redis_mod = pytest.importorskip("testcontainers.redis")
    container = redis_mod.RedisContainer("redis:7-alpine")
    try:
        container.start()
    except Exception as exc:
        _skip_or_fail(f"Redis container unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


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
    if _REQUIRE_DOCKER:
        import testcontainers.kafka as kafka_mod
    else:
        kafka_mod = pytest.importorskip("testcontainers.kafka")
    try:
        container = kafka_mod.KafkaContainer()
        container.start()
    except Exception as exc:
        _skip_or_fail(f"Kafka container unavailable: {exc}")
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
