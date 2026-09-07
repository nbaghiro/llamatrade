"""Integration fixtures: a real Postgres via testcontainers.

These exercise the full ledger stack — ``LedgerWriter`` (real unique/idempotency
constraint + balance check), the projector folding real rows, the fund/lifecycle
services, and the servicers — against real SQL (JSONB, BigInteger sequences,
UUID). They require Docker; when it's unavailable the fixtures ``skip`` so the
fast unit suite still runs in constrained environments, except under
``CI_REQUIRE_DOCKER=1`` (set in CI) where the guard fails loudly instead.

Run them with: ``pytest -m integration`` (or the repo's ``ci-local.sh --integration``).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import NoReturn

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

POSTGRES_IMAGE = "postgres:16-alpine"

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


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway Postgres and yield an asyncpg URL, or skip."""
    if _REQUIRE_DOCKER:
        import testcontainers.postgres as postgres_mod
    else:
        postgres_mod = pytest.importorskip("testcontainers.postgres")
    try:
        # Construction itself opens a Docker client, so guard it too.
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="portfolio"
        )
        container.start()
    except Exception as exc:  # Docker not reachable / image pull blocked
        _skip_or_fail(f"Postgres container unavailable: {exc}")
    try:
        raw_url = container.get_connection_url()  # postgresql+psycopg2://...
        yield raw_url.replace("+psycopg2", "+asyncpg").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker]:
    """A migrated async session factory with a fresh schema per test."""
    # Import the model modules so their tables register on Base.metadata. Only
    # these three load (not the whole models package) so the integration schema
    # stays free of extension-backed tables such as pgvector embeddings.
    import llamatrade_db.models.auth
    import llamatrade_db.models.ledger
    import llamatrade_db.models.strategy
    from llamatrade_db.base import Base

    # Touch the modules so they are not pruned as unused; the imports exist purely
    # for their table-registration side effects above.
    _ = (llamatrade_db.models.auth, llamatrade_db.models.ledger, llamatrade_db.models.strategy)

    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
