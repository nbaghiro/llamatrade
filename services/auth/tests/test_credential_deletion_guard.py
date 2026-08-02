"""End-to-end tests for the broker-credential deletion guard.

``TenantService.delete_alpaca_credentials`` must refuse while live trading
sessions or funded ledger sleeves still point at the credential set. These run
the real SQL against a real (SQLite) schema so the tenant filters are exercised;
the mock-based cases in ``test_tenant_service.py`` cover the message shape.

SQLite has no JSONB and no async driver installed, hence the type rendering and
the awaitable facade over a synchronous session.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
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
from llamatrade_db.models.auth import AlpacaCredentials
from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated import common_pb2

from src.services.tenant_service import CredentialsInUseError, TenantService

_TABLES = [
    AlpacaCredentials.__table__,
    TradingSession.__table__,
    Account.__table__,
    Sleeve.__table__,
]


@compiles(JSONB, "sqlite")
def _render_jsonb_on_sqlite(type_: JSONB, compiler: GenericTypeCompiler, **kw: Any) -> str:
    """SQLite has no JSONB; its JSON type stores the same values."""
    return "JSON"


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
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
    """Awaitable facade over a synchronous Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement: Executable) -> Result[tuple[object, ...]]:
        return self._session.execute(statement)

    async def scalars(self, statement: Executable) -> ScalarResult[object]:
        return self._session.scalars(statement)

    async def commit(self) -> None:
        self._session.flush()


@pytest.fixture
def service(db_session: Session) -> TenantService:
    return TenantService(cast(AsyncSession, _SyncSessionAdapter(db_session)))


def _make_credentials(session: Session, tenant_id: UUID) -> AlpacaCredentials:
    creds = AlpacaCredentials(
        tenant_id=tenant_id,
        name="Paper Keys",
        auth_type="api_key",
        api_key_encrypted="encrypted_key",
        api_secret_encrypted="encrypted_secret",
        api_key_prefix="PKTEST12",
        is_paper=True,
        is_active=True,
    )
    session.add(creds)
    session.flush()
    return creds


def _make_trading_session(
    session: Session,
    *,
    tenant_id: UUID,
    credentials_id: UUID,
    status: common_pb2.ExecutionStatus.ValueType = common_pb2.EXECUTION_STATUS_RUNNING,
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
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _make_funded_sleeve(
    session: Session,
    *,
    tenant_id: UUID,
    credentials_id: UUID,
    strategy_execution_id: UUID | None = None,
) -> Sleeve:
    account = Account(tenant_id=tenant_id, credentials_id=credentials_id, base_currency="USD")
    session.add(account)
    session.flush()
    sleeve = Sleeve(
        tenant_id=tenant_id,
        account_id=account.id,
        type=SleeveType.STRATEGY.value,
        status=SleeveStatus.ACTIVE.value,
        name="Momentum",
        strategy_execution_id=strategy_execution_id,
        allocated_capital=Decimal("25000.00"),
        created_at=datetime.now(UTC),
    )
    session.add(sleeve)
    session.flush()
    return sleeve


async def test_delete_succeeds_without_dependents(
    service: TenantService, db_session: Session
) -> None:
    tenant_id = uuid4()
    creds = _make_credentials(db_session, tenant_id)

    assert await service.delete_alpaca_credentials(creds.id, tenant_id) is True
    assert creds.is_active is False


async def test_delete_refused_while_a_session_is_running(
    service: TenantService, db_session: Session
) -> None:
    tenant_id = uuid4()
    creds = _make_credentials(db_session, tenant_id)
    live = _make_trading_session(db_session, tenant_id=tenant_id, credentials_id=creds.id)

    with pytest.raises(CredentialsInUseError) as exc_info:
        await service.delete_alpaca_credentials(creds.id, tenant_id)

    assert str(live.id) in str(exc_info.value)
    assert exc_info.value.dependents.session_ids == (live.id,)
    assert creds.is_active is True


async def test_delete_refused_while_a_funded_sleeve_is_open(
    service: TenantService, db_session: Session
) -> None:
    tenant_id, execution_id = uuid4(), uuid4()
    creds = _make_credentials(db_session, tenant_id)
    sleeve = _make_funded_sleeve(
        db_session,
        tenant_id=tenant_id,
        credentials_id=creds.id,
        strategy_execution_id=execution_id,
    )

    with pytest.raises(CredentialsInUseError) as exc_info:
        await service.delete_alpaca_credentials(creds.id, tenant_id)

    message = str(exc_info.value)
    assert str(sleeve.id) in message
    assert str(execution_id) in message
    assert creds.is_active is True


async def test_delete_allowed_after_stop_and_close(
    service: TenantService, db_session: Session
) -> None:
    """Stopping the session and closing the sleeve clears the refusal."""
    tenant_id = uuid4()
    creds = _make_credentials(db_session, tenant_id)
    live = _make_trading_session(db_session, tenant_id=tenant_id, credentials_id=creds.id)
    sleeve = _make_funded_sleeve(
        db_session, tenant_id=tenant_id, credentials_id=creds.id, strategy_execution_id=uuid4()
    )

    with pytest.raises(CredentialsInUseError):
        await service.delete_alpaca_credentials(creds.id, tenant_id)

    live.status = common_pb2.EXECUTION_STATUS_STOPPED
    sleeve.status = SleeveStatus.CLOSED.value
    db_session.flush()

    assert await service.delete_alpaca_credentials(creds.id, tenant_id) is True
    assert creds.is_active is False


async def test_other_tenants_session_does_not_block_deletion(
    service: TenantService, db_session: Session
) -> None:
    """Tenant B's running session on the same credentials id never blocks tenant A."""
    tenant_a, tenant_b = uuid4(), uuid4()
    creds = _make_credentials(db_session, tenant_a)
    _make_trading_session(db_session, tenant_id=tenant_b, credentials_id=creds.id)

    assert await service.delete_alpaca_credentials(creds.id, tenant_a) is True
    assert creds.is_active is False


async def test_other_tenants_funded_sleeve_does_not_block_deletion(
    service: TenantService, db_session: Session
) -> None:
    """Tenant B's funded sleeve never blocks tenant A."""
    tenant_a, tenant_b = uuid4(), uuid4()
    creds = _make_credentials(db_session, tenant_a)
    _make_funded_sleeve(db_session, tenant_id=tenant_b, credentials_id=creds.id)

    assert await service.delete_alpaca_credentials(creds.id, tenant_a) is True
    assert creds.is_active is False


async def test_deleting_another_tenants_credentials_is_not_found(
    service: TenantService, db_session: Session
) -> None:
    """The credential lookup stays tenant-scoped, so no dependency check even runs."""
    tenant_a, tenant_b = uuid4(), uuid4()
    creds = _make_credentials(db_session, tenant_a)
    _make_trading_session(db_session, tenant_id=tenant_a, credentials_id=creds.id)

    assert await service.delete_alpaca_credentials(creds.id, tenant_b) is False
    assert creds.is_active is True
