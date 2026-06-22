"""Real-Postgres tenant-isolation tests for StrategyService (Issue 9A).

Unlike the mock-based unit tests, these run the actual SQL against Postgres, so a
dropped or forgotten tenant filter is caught — the mocks can't catch that because
they stub out the query builder. Requires Docker (testcontainers Postgres).
"""

import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from llamatrade_db.base import Base
from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion

from src.models import ExecutionCreate, StrategyCreate
from src.services.strategy_service import StrategyService


def _docker_available() -> bool:
    """True if a Docker daemon is reachable (testcontainers needs it)."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


# Skip cleanly (rather than error) where Docker isn't available — e.g. a
# pre-commit run on a machine without Docker. CI runs these with Docker up.
pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available for testcontainers"
)

_SEXPR = '(strategy "ISO Test" (weight :method equal (asset SPY) (asset AGG)))'
_TABLES = [Strategy.__table__, StrategyVersion.__table__, StrategyExecution.__table__]


@pytest.fixture(scope="module")
def pg_url():
    """Start a throwaway Postgres for the module."""
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="strategy_iso",
        driver="asyncpg",
    ) as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="module")
def schema(pg_url: str) -> str:
    """Create just the strategy tables once (they FK only among themselves)."""

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
async def db(schema: str):
    engine = create_async_engine(schema, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _create(db: AsyncSession, tenant_id, name: str):
    return await StrategyService(db).create_strategy(
        tenant_id=tenant_id,
        user_id=uuid4(),
        data=StrategyCreate(name=name, config_sexpr=_SEXPR),
    )


class TestTenantIsolationDB:
    """Each test uses fresh random tenant IDs, so rows never collide across tests."""

    async def test_get_strategy_blocks_cross_tenant(self, db: AsyncSession) -> None:
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        created = await _create(db, a, "S")

        assert await svc.get_strategy(a, created.id) is not None
        assert await svc.get_strategy(b, created.id) is None

    async def test_list_strategies_scoped(self, db: AsyncSession) -> None:
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        await _create(db, a, "A1")
        await _create(db, b, "B1")

        a_list, _ = await svc.list_strategies(a)
        b_list, _ = await svc.list_strategies(b)
        a_names = {s.name for s in a_list}

        assert "A1" in a_names
        assert "B1" not in a_names  # would fail if list_strategies dropped its tenant filter
        assert all(s.name != "A1" for s in b_list)

    async def test_list_versions_blocks_cross_tenant(self, db: AsyncSession) -> None:
        """Regression for 7A: a version query must not leak across tenants."""
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        created = await _create(db, a, "V")

        assert len(await svc.list_versions(a, created.id)) == 1
        assert await svc.list_versions(b, created.id) == []

    async def test_delete_blocks_cross_tenant(self, db: AsyncSession) -> None:
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        created = await _create(db, a, "D")

        assert await svc.delete_strategy(b, created.id) is False  # invisible to B
        assert await svc.get_strategy(a, created.id) is not None  # untouched for A
        assert await svc.delete_strategy(a, created.id) is True

    async def test_execution_isolation(self, db: AsyncSession) -> None:
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        created = await _create(db, a, "E")
        execution = await svc.create_execution(a, created.id, ExecutionCreate(version=1))
        assert execution is not None

        assert await svc.get_execution(a, execution.id) is not None
        assert await svc.get_execution(b, execution.id) is None

        a_execs, _ = await svc.list_executions(a)
        b_execs, _ = await svc.list_executions(b)
        assert any(e.id == execution.id for e in a_execs)
        assert all(e.id != execution.id for e in b_execs)

    async def test_create_execution_cross_tenant_strategy_returns_none(
        self, db: AsyncSession
    ) -> None:
        a, b = uuid4(), uuid4()
        svc = StrategyService(db)
        created = await _create(db, a, "X")

        # B must not be able to attach an execution to A's strategy.
        assert await svc.create_execution(b, created.id, ExecutionCreate(version=1)) is None
