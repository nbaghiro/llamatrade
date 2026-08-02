"""Tests for the credential-dependency read helper.

These run the real SQL against a real (SQLite) schema rather than mocks, so a
dropped tenant filter or a wrong status predicate fails here. Two adaptations
make that work: JSONB needs a SQLite rendering, and the helper is async while
SQLite has no async driver installed, so a thin facade forwards its two awaited
calls to a synchronous session.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Executable, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, Result
from sqlalchemy.engine.result import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.compiler import GenericTypeCompiler

from llamatrade_db.base import Base
from llamatrade_db.credential_dependents import (
    BLOCKING_SESSION_STATUSES,
    CredentialDependents,
    get_credential_dependents,
)
from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated import common_pb2

pytestmark = pytest.mark.asyncio

_TABLES = [TradingSession.__table__, Account.__table__, Sleeve.__table__]


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

    async def execute(self, statement: Executable) -> Result[tuple[object, ...]]:
        return self._session.execute(statement)

    async def scalars(self, statement: Executable) -> ScalarResult[object]:
        return self._session.scalars(statement)


def _db(session: Session) -> AsyncSession:
    return cast(AsyncSession, _SyncSessionAdapter(session))


def _make_session(
    session: Session,
    *,
    tenant_id: UUID,
    credentials_id: UUID,
    status: common_pb2.ExecutionStatus.ValueType = common_pb2.EXECUTION_STATUS_RUNNING,
    created_at: datetime | None = None,
) -> TradingSession:
    row = TradingSession(
        tenant_id=tenant_id,
        strategy_id=uuid4(),
        strategy_version=1,
        credentials_id=credentials_id,
        name="Live SPY",
        mode=common_pb2.EXECUTION_MODE_PAPER,
        status=status,
        config={},
        symbols=["SPY"],
        created_by=uuid4(),
        created_at=created_at or datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _make_account(session: Session, *, tenant_id: UUID, credentials_id: UUID) -> Account:
    account = Account(tenant_id=tenant_id, credentials_id=credentials_id, base_currency="USD")
    session.add(account)
    session.flush()
    return account


def _make_sleeve(
    session: Session,
    *,
    account: Account,
    tenant_id: UUID | None = None,
    sleeve_type: SleeveType = SleeveType.STRATEGY,
    status: SleeveStatus = SleeveStatus.ACTIVE,
    allocated_capital: Decimal = Decimal("10000.00"),
    strategy_execution_id: UUID | None = None,
    created_at: datetime | None = None,
) -> Sleeve:
    sleeve = Sleeve(
        tenant_id=tenant_id or account.tenant_id,
        account_id=account.id,
        type=sleeve_type.value,
        status=status.value,
        name="Momentum",
        strategy_execution_id=strategy_execution_id,
        allocated_capital=allocated_capital,
        created_at=created_at or datetime.now(UTC),
    )
    session.add(sleeve)
    session.flush()
    return sleeve


async def test_no_dependents_is_falsy(db_session: Session) -> None:
    """A credential set nothing points at reports no blockers."""
    dependents = await get_credential_dependents(_db(db_session), uuid4(), uuid4())

    assert dependents == CredentialDependents()
    assert not dependents


async def test_running_session_blocks(db_session: Session) -> None:
    tenant_id, credentials_id = uuid4(), uuid4()
    row = _make_session(db_session, tenant_id=tenant_id, credentials_id=credentials_id)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert bool(dependents)
    assert dependents.session_ids == (row.id,)
    assert dependents.sleeve_ids == ()


@pytest.mark.parametrize("status", BLOCKING_SESSION_STATUSES)
async def test_every_blocking_status_blocks(
    db_session: Session, status: common_pb2.ExecutionStatus.ValueType
) -> None:
    tenant_id, credentials_id = uuid4(), uuid4()
    row = _make_session(
        db_session, tenant_id=tenant_id, credentials_id=credentials_id, status=status
    )

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert dependents.session_ids == (row.id,)


@pytest.mark.parametrize(
    "status",
    [common_pb2.EXECUTION_STATUS_STOPPED, common_pb2.EXECUTION_STATUS_ERROR],
)
async def test_terminal_sessions_do_not_block(
    db_session: Session, status: common_pb2.ExecutionStatus.ValueType
) -> None:
    """A stopped or errored session holds no broker connection."""
    tenant_id, credentials_id = uuid4(), uuid4()
    _make_session(db_session, tenant_id=tenant_id, credentials_id=credentials_id, status=status)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert not dependents


async def test_sessions_on_other_credentials_do_not_block(db_session: Session) -> None:
    tenant_id = uuid4()
    _make_session(db_session, tenant_id=tenant_id, credentials_id=uuid4())

    dependents = await get_credential_dependents(_db(db_session), tenant_id, uuid4())

    assert not dependents


async def test_sessions_are_ordered_by_creation(db_session: Session) -> None:
    tenant_id, credentials_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    second = _make_session(
        db_session,
        tenant_id=tenant_id,
        credentials_id=credentials_id,
        created_at=now,
    )
    first = _make_session(
        db_session,
        tenant_id=tenant_id,
        credentials_id=credentials_id,
        created_at=now - timedelta(hours=1),
    )

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert dependents.session_ids == (first.id, second.id)


async def test_funded_sleeve_blocks_with_its_execution_id(db_session: Session) -> None:
    tenant_id, credentials_id, execution_id = uuid4(), uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    sleeve = _make_sleeve(db_session, account=account, strategy_execution_id=execution_id)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert bool(dependents)
    assert dependents.sleeve_ids == (sleeve.id,)
    assert dependents.strategy_execution_ids == (execution_id,)


async def test_closed_sleeve_does_not_block(db_session: Session) -> None:
    tenant_id, credentials_id = uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    _make_sleeve(db_session, account=account, status=SleeveStatus.CLOSED)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert not dependents


async def test_frozen_funded_sleeve_still_blocks(db_session: Session) -> None:
    """Frozen is not closed: the capital is still on the account."""
    tenant_id, credentials_id = uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    sleeve = _make_sleeve(db_session, account=account, status=SleeveStatus.FROZEN)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert dependents.sleeve_ids == (sleeve.id,)


async def test_base_sleeves_never_block(db_session: Session) -> None:
    """Unallocated/Manual/Unmanaged are always open and carry no allocated capital."""
    tenant_id, credentials_id = uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    for sleeve_type in (SleeveType.UNALLOCATED, SleeveType.MANUAL, SleeveType.UNMANAGED):
        _make_sleeve(
            db_session,
            account=account,
            sleeve_type=sleeve_type,
            allocated_capital=Decimal("0"),
        )

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert not dependents


async def test_sleeve_without_execution_id_reports_no_execution(db_session: Session) -> None:
    tenant_id, credentials_id = uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    sleeve = _make_sleeve(db_session, account=account, sleeve_type=SleeveType.MANUAL)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert dependents.sleeve_ids == (sleeve.id,)
    assert dependents.strategy_execution_ids == ()


async def test_sleeves_on_other_accounts_do_not_block(db_session: Session) -> None:
    tenant_id = uuid4()
    other_account = _make_account(db_session, tenant_id=tenant_id, credentials_id=uuid4())
    _make_sleeve(db_session, account=other_account)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, uuid4())

    assert not dependents


async def test_other_tenant_session_does_not_block(db_session: Session) -> None:
    """Tenant B's live session never blocks tenant A, even on the same credentials id."""
    tenant_a, tenant_b, credentials_id = uuid4(), uuid4(), uuid4()
    _make_session(db_session, tenant_id=tenant_b, credentials_id=credentials_id)

    dependents = await get_credential_dependents(_db(db_session), tenant_a, credentials_id)

    assert not dependents


async def test_other_tenant_sleeve_does_not_block(db_session: Session) -> None:
    """Tenant B's funded sleeve never blocks tenant A."""
    tenant_a, tenant_b, credentials_id = uuid4(), uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_b, credentials_id=credentials_id)
    _make_sleeve(db_session, account=account)

    dependents = await get_credential_dependents(_db(db_session), tenant_a, credentials_id)

    assert not dependents


async def test_sleeve_tenant_must_match_its_account_tenant(db_session: Session) -> None:
    """A sleeve row whose tenant differs from its account's is not a blocker for either."""
    tenant_a, tenant_b, credentials_id = uuid4(), uuid4(), uuid4()
    account = _make_account(db_session, tenant_id=tenant_a, credentials_id=credentials_id)
    _make_sleeve(db_session, account=account, tenant_id=tenant_b)

    assert not await get_credential_dependents(_db(db_session), tenant_a, credentials_id)
    assert not await get_credential_dependents(_db(db_session), tenant_b, credentials_id)


async def test_sessions_and_sleeves_are_reported_together(db_session: Session) -> None:
    tenant_id, credentials_id, execution_id = uuid4(), uuid4(), uuid4()
    row = _make_session(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    sleeve = _make_sleeve(db_session, account=account, strategy_execution_id=execution_id)

    dependents = await get_credential_dependents(_db(db_session), tenant_id, credentials_id)

    assert dependents.session_ids == (row.id,)
    assert dependents.sleeve_ids == (sleeve.id,)
    assert dependents.strategy_execution_ids == (execution_id,)


async def test_deletion_allowed_after_stop_and_close(db_session: Session) -> None:
    """Stopping the session and closing the sleeve clears every blocker."""
    tenant_id, credentials_id = uuid4(), uuid4()
    row = _make_session(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    account = _make_account(db_session, tenant_id=tenant_id, credentials_id=credentials_id)
    sleeve = _make_sleeve(db_session, account=account, strategy_execution_id=uuid4())

    assert bool(await get_credential_dependents(_db(db_session), tenant_id, credentials_id))

    row.status = common_pb2.EXECUTION_STATUS_STOPPED
    sleeve.status = SleeveStatus.CLOSED.value
    db_session.flush()

    assert not await get_credential_dependents(_db(db_session), tenant_id, credentials_id)
