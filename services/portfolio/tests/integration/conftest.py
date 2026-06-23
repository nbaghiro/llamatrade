"""Integration fixtures: a real Postgres via testcontainers.

These exercise the full ledger stack — ``LedgerWriter`` (real unique/idempotency
constraint + balance check), the projector folding real rows, the fund/lifecycle
services, and the servicers — against real SQL (JSONB, BigInteger sequences,
UUID). They require Docker; when it's unavailable the fixtures ``skip`` (rather
than fail) so the fast unit suite still runs in constrained environments.

Run them with: ``pytest -m integration`` (or the repo's ``ci-local.sh --integration``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Every test in this package needs Docker.
pytestmark = pytest.mark.integration

POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Start a throwaway Postgres and yield an asyncpg URL, or skip."""
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    try:
        # Construction itself opens a Docker client, so guard it too.
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname="portfolio"
        )
        container.start()
    except Exception as exc:  # Docker not reachable / image pull blocked
        pytest.skip(f"Postgres container unavailable: {exc}")
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
