"""Tests for the live-session symbol read helper.

These run the real SQL against a real (SQLite) schema rather than mocks, so a
wrong status predicate or a broken execution/version join fails here. Two
adaptations make that work: JSONB needs a SQLite rendering, and the helper is
async while SQLite has no async driver installed, so a thin facade forwards its
awaited calls to a synchronous session.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Executable, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.engine.result import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.compiler import GenericTypeCompiler

from llamatrade_db.base import Base
from llamatrade_db.live_session_symbols import (
    ACTIVE_EXECUTION_STATUSES,
    get_live_session_symbols,
)
from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated import common_pb2

pytestmark = pytest.mark.asyncio

_TABLES = [
    TradingSession.__table__,
    Strategy.__table__,
    StrategyVersion.__table__,
    StrategyExecution.__table__,
]

_TERMINAL_STATUSES = (
    common_pb2.EXECUTION_STATUS_STOPPED,
    common_pb2.EXECUTION_STATUS_ERROR,
)
# Sessions are created RUNNING, so PENDING only exists on an execution.
_INACTIVE_EXECUTION_STATUSES = (*_TERMINAL_STATUSES, common_pb2.EXECUTION_STATUS_PENDING)


@compiles(JSONB, "sqlite")
def _render_jsonb_on_sqlite(type_: JSONB, compiler: GenericTypeCompiler, **kw: Any) -> str:
    """SQLite has no JSONB; its JSON type stores the same values."""
    return "JSON"


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    """A SQLite engine holding only the tables this helper reads."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
    """A rolled-back session per test, so rows never leak between them."""
    session = sessionmaker(bind=sqlite_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class _SyncSessionAdapter:
    """Awaitable facade over a synchronous Session (SQLite has no async driver here)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def scalars(self, statement: Executable) -> ScalarResult[object]:
        return self._session.scalars(statement)


def _db(session: Session) -> AsyncSession:
    return cast(AsyncSession, _SyncSessionAdapter(session))


def _make_session(
    session: Session,
    *,
    symbols: list[str],
    tenant_id: UUID | None = None,
    status: common_pb2.ExecutionStatus.ValueType = common_pb2.EXECUTION_STATUS_RUNNING,
) -> TradingSession:
    row = TradingSession(
        tenant_id=tenant_id or uuid4(),
        strategy_id=uuid4(),
        strategy_version=1,
        credentials_id=uuid4(),
        name="Live",
        mode=common_pb2.EXECUTION_MODE_PAPER,
        status=status,
        config={},
        symbols=symbols,
        created_by=uuid4(),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _make_execution(
    session: Session,
    *,
    symbols: list[str],
    tenant_id: UUID | None = None,
    version_tenant_id: UUID | None = None,
    version: int = 1,
    status: common_pb2.ExecutionStatus.ValueType = common_pb2.EXECUTION_STATUS_RUNNING,
) -> StrategyExecution:
    tenant = tenant_id or uuid4()
    strategy = Strategy(tenant_id=tenant, name=f"S-{uuid4()}", created_by=uuid4())
    session.add(strategy)
    session.flush()
    session.add(
        StrategyVersion(
            tenant_id=version_tenant_id or tenant,
            strategy_id=strategy.id,
            version=version,
            config_sexpr="(strategy)",
            symbols=symbols,
            created_by=uuid4(),
        )
    )
    execution = StrategyExecution(
        tenant_id=tenant,
        strategy_id=strategy.id,
        version=version,
        mode=common_pb2.EXECUTION_MODE_PAPER,
        status=status,
    )
    session.add(execution)
    session.flush()
    return execution


async def test_no_live_execution_is_empty(db_session: Session) -> None:
    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_running_session_symbols(db_session: Session) -> None:
    _make_session(db_session, symbols=["SPY", "QQQ"])

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY", "QQQ"})


@pytest.mark.parametrize("status", ACTIVE_EXECUTION_STATUSES)
async def test_every_active_status_contributes(
    db_session: Session, status: common_pb2.ExecutionStatus.ValueType
) -> None:
    """A paused session resumes into the same subscriptions, so it still counts."""
    _make_session(db_session, symbols=["SPY"], status=status)

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY"})


@pytest.mark.parametrize("status", _TERMINAL_STATUSES)
async def test_inactive_sessions_are_excluded(
    db_session: Session, status: common_pb2.ExecutionStatus.ValueType
) -> None:
    _make_session(db_session, symbols=["SPY"], status=status)

    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_symbols_from_every_tenant_are_unioned(db_session: Session) -> None:
    """This is an infrastructure read: the ingestor needs all tenants' symbols."""
    _make_session(db_session, symbols=["SPY"], tenant_id=uuid4())
    _make_session(db_session, symbols=["TSLA"], tenant_id=uuid4())

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY", "TSLA"})


async def test_symbols_are_deduped_and_upper_cased(db_session: Session) -> None:
    _make_session(db_session, symbols=[" spy ", "SPY"])
    _make_session(db_session, symbols=["spy", ""])

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY"})


async def test_empty_session_symbol_list_contributes_nothing(db_session: Session) -> None:
    _make_session(db_session, symbols=[])

    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_running_execution_uses_its_strategy_version_symbols(db_session: Session) -> None:
    """A funded execution whose session has not started yet still warms the store."""
    _make_execution(db_session, symbols=["NVDA"])

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"NVDA"})


@pytest.mark.parametrize("status", _INACTIVE_EXECUTION_STATUSES)
async def test_inactive_executions_are_excluded(
    db_session: Session, status: common_pb2.ExecutionStatus.ValueType
) -> None:
    _make_execution(db_session, symbols=["NVDA"], status=status)

    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_execution_only_matches_its_own_version(db_session: Session) -> None:
    """The join is on (strategy, version): a v2 execution never reads v1's symbols."""
    execution = _make_execution(db_session, symbols=["NVDA"], version=1)
    execution.version = 2
    db_session.flush()

    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_execution_version_of_another_tenant_is_not_joined(db_session: Session) -> None:
    """A version row whose tenant differs from the execution's is not its version."""
    _make_execution(db_session, symbols=["NVDA"], version_tenant_id=uuid4())

    assert await get_live_session_symbols(_db(db_session)) == frozenset()


async def test_sessions_and_executions_are_unioned(db_session: Session) -> None:
    _make_session(db_session, symbols=["SPY"])
    _make_execution(db_session, symbols=["NVDA", "SPY"])

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY", "NVDA"})


async def test_symbol_leaves_the_set_once_nothing_needs_it(db_session: Session) -> None:
    """Stopping the last consumer of a symbol drops it from the derived universe."""
    first = _make_session(db_session, symbols=["SPY", "TSLA"])
    second = _make_session(db_session, symbols=["TSLA"])

    assert await get_live_session_symbols(_db(db_session)) == frozenset({"SPY", "TSLA"})

    first.status = common_pb2.EXECUTION_STATUS_STOPPED
    db_session.flush()
    assert await get_live_session_symbols(_db(db_session)) == frozenset({"TSLA"})

    second.status = common_pb2.EXECUTION_STATUS_STOPPED
    db_session.flush()
    assert await get_live_session_symbols(_db(db_session)) == frozenset()
