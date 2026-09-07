"""Two concurrent starts must fund a strategy execution exactly once.

``start_execution`` reads the row ``FOR UPDATE`` before checking PENDING and
allocating capital, so a double-click or a retried RPC cannot double-allocate.
That lock is invisible to the mock-based unit tests (they stub the query
builder), so this drives two real sessions against real Postgres: the loser must
block on the lock, observe RUNNING, and refuse without calling the ledger.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_db.base import Base
from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER

from src.models import ExecutionCreate, StrategyCreate
from src.services.strategy_service import StrategyService

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"

if _REQUIRE_DOCKER:
    from testcontainers.postgres import PostgresContainer
else:
    PostgresContainer = pytest.importorskip("testcontainers.postgres").PostgresContainer


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


_docker_up = _docker_available()
if _REQUIRE_DOCKER and not _docker_up:
    pytest.fail("CI_REQUIRE_DOCKER=1: Docker is required but unavailable", pytrace=False)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_up, reason="Docker not available for testcontainers"),
]

_SEXPR = '(strategy "Race" (weight :method equal (asset SPY) (asset AGG)))'
_TABLES = [Strategy.__table__, StrategyVersion.__table__, StrategyExecution.__table__]


@pytest.fixture(scope="module")
def pg_url() -> str:
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="strategy_race",
        driver="asyncpg",
    ) as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="module")
def schema(pg_url: str) -> str:
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
async def maker(schema: str):
    """A session factory: the race needs two independent sessions."""
    engine = create_async_engine(schema, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _ledger(sleeve_id: UUID, account_id: UUID) -> AsyncMock:
    """A ledger double recording every allocate call."""
    ledger = AsyncMock()
    ledger.get_or_create_account.return_value = AsyncMock(account=AsyncMock(id=str(account_id)))
    ledger.allocate_capital.return_value = AsyncMock(id=str(sleeve_id))
    return ledger


async def _pending_execution(maker: async_sessionmaker[AsyncSession], tenant_id: UUID) -> UUID:
    """A PENDING execution carrying funding intent (capital + credentials)."""
    async with maker() as db:
        service = StrategyService(db)
        strategy, version = await service.create_strategy(
            tenant_id=tenant_id,
            user_id=uuid4(),
            data=StrategyCreate(name="Race", config_sexpr=_SEXPR),
        )
        execution = await service.create_execution(
            tenant_id=tenant_id,
            strategy_id=strategy.id,
            data=ExecutionCreate(
                version=version.version,
                mode=EXECUTION_MODE_PAPER,
                allocated_capital=Decimal("10000"),
                credentials_id=uuid4(),
            ),
        )
        assert execution is not None
        return execution.id


async def test_concurrent_starts_allocate_capital_exactly_once(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """The FOR UPDATE row lock serializes the PENDING check with the funding call."""
    tenant_id = uuid4()
    execution_id = await _pending_execution(maker, tenant_id)
    sleeve_id, account_id = uuid4(), uuid4()
    ledger_a, ledger_b = _ledger(sleeve_id, account_id), _ledger(sleeve_id, account_id)

    async def start(ledger: AsyncMock) -> object:
        async with maker() as db:
            try:
                return await StrategyService(db).start_execution(
                    tenant_id, execution_id, ledger=ledger, user_id=uuid4()
                )
            except ValueError as exc:
                return exc

    results = await asyncio.gather(start(ledger_a), start(ledger_b))

    started = [r for r in results if isinstance(r, StrategyExecution)]
    refused = [r for r in results if isinstance(r, ValueError)]
    assert len(started) == 1, "exactly one start may win"
    assert len(refused) == 1, "the loser must refuse, not start a second run"

    allocations = ledger_a.allocate_capital.await_count + ledger_b.allocate_capital.await_count
    assert allocations == 1, "capital must be allocated once, not twice"


async def test_the_losing_start_leaves_one_running_row(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    """After the race the row is RUNNING once, with the winner's sleeve attached."""
    tenant_id = uuid4()
    execution_id = await _pending_execution(maker, tenant_id)
    sleeve_id, account_id = uuid4(), uuid4()

    async def start() -> None:
        async with maker() as db:
            with pytest.raises(ValueError, match="status is running, expected pending"):
                await StrategyService(db).start_execution(
                    tenant_id,
                    execution_id,
                    ledger=_ledger(sleeve_id, account_id),
                    user_id=uuid4(),
                )

    async with maker() as db:
        await StrategyService(db).start_execution(
            tenant_id, execution_id, ledger=_ledger(sleeve_id, account_id), user_id=uuid4()
        )
    await start()

    async with maker() as db:
        execution = await db.get(StrategyExecution, execution_id)
        assert execution is not None
        assert execution.sleeve_id == sleeve_id
        assert execution.started_at is not None
