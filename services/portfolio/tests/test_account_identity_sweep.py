"""Duplicate broker-account sweep: report accounts that share a broker account.

The unique constraint makes this state unreachable for rows written after it
landed, so the sweep is a safety net for rows loaded out of band. It runs the
real SQL against a real (SQLite) schema — a dropped tenant grouping or a NULL
leaking into the report fails here. The helper is async while SQLite has no
async driver installed, so a thin facade forwards its awaited call to a
synchronous session.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Executable, MetaData, Table, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine, Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.models.ledger import Account

from src.ports import DuplicateBrokerAccounts
from src.repositories import find_duplicate_broker_accounts
from src.services.onboarding_service import report_duplicate_broker_accounts

_ACCOUNTS: Table = cast(Table, Account.__table__)


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    """The account table as it looked before the broker-id constraint landed.

    The sweep exists for rows the constraint would now reject, so the schema it
    runs against here has to be able to hold them.
    """
    metadata = MetaData()
    table = _ACCOUNTS.to_metadata(metadata)
    for constraint in list(table.constraints):
        if isinstance(constraint, UniqueConstraint) and constraint.name == (
            "uq_ledger_accounts_broker"
        ):
            table.constraints.discard(constraint)
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
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


def _db(session: Session) -> AsyncSession:
    return cast(AsyncSession, _SyncSessionAdapter(session))


def _account(session: Session, *, tenant_id: UUID, broker_account_id: str | None) -> Account:
    account = Account(
        tenant_id=tenant_id,
        credentials_id=uuid4(),
        alpaca_account_id=broker_account_id,
        base_currency="USD",
    )
    session.add(account)
    session.flush()
    return account


async def test_no_duplicates_reports_nothing(db_session: Session) -> None:
    _account(db_session, tenant_id=uuid4(), broker_account_id="broker-1")
    assert await find_duplicate_broker_accounts(_db(db_session)) == []


async def test_null_broker_ids_are_not_duplicates(db_session: Session) -> None:
    """Accounts whose broker id was never recorded are not a reportable collision."""
    tenant_id = uuid4()
    _account(db_session, tenant_id=tenant_id, broker_account_id=None)
    _account(db_session, tenant_id=tenant_id, broker_account_id=None)

    assert await find_duplicate_broker_accounts(_db(db_session)) == []


async def test_same_broker_id_in_two_tenants_is_not_a_duplicate(db_session: Session) -> None:
    _account(db_session, tenant_id=uuid4(), broker_account_id="broker-1")
    _account(db_session, tenant_id=uuid4(), broker_account_id="broker-1")

    assert await find_duplicate_broker_accounts(_db(db_session)) == []


async def test_duplicates_within_a_tenant_are_reported(db_session: Session) -> None:
    """The constraint blocks this via the ORM, so the rows are written directly."""
    tenant_id = uuid4()
    first, second = uuid4(), uuid4()
    db_session.execute(
        _ACCOUNTS.insert(),
        [
            {
                "id": first,
                "tenant_id": tenant_id,
                "credentials_id": uuid4(),
                "alpaca_account_id": "broker-1",
                "base_currency": "USD",
            },
            {
                "id": second,
                "tenant_id": tenant_id,
                "credentials_id": uuid4(),
                "alpaca_account_id": "broker-1",
                "base_currency": "USD",
            },
        ],
    )

    duplicates = await find_duplicate_broker_accounts(_db(db_session))

    assert len(duplicates) == 1
    assert duplicates[0].tenant_id == tenant_id
    assert duplicates[0].broker_account_id == "broker-1"
    assert set(duplicates[0].account_ids) == {first, second}


async def test_sweep_does_not_mutate(db_session: Session) -> None:
    """Merging two event logs is an operator decision; the sweep only reads."""
    tenant_id = uuid4()
    ids = [uuid4(), uuid4()]
    db_session.execute(
        _ACCOUNTS.insert(),
        [
            {
                "id": account_id,
                "tenant_id": tenant_id,
                "credentials_id": uuid4(),
                "alpaca_account_id": "broker-1",
                "base_currency": "USD",
            }
            for account_id in ids
        ],
    )

    await find_duplicate_broker_accounts(_db(db_session))

    rows = db_session.query(Account).filter(Account.tenant_id == tenant_id).all()
    assert sorted(str(r.id) for r in rows) == sorted(str(i) for i in ids)
    assert [r.alpaca_account_id for r in rows] == ["broker-1", "broker-1"]


def test_report_logs_one_line_per_duplicate(caplog: pytest.LogCaptureFixture) -> None:
    tenant_id = uuid4()
    duplicates = [
        DuplicateBrokerAccounts(
            tenant_id=tenant_id, broker_account_id="broker-1", account_ids=(uuid4(), uuid4())
        ),
        DuplicateBrokerAccounts(
            tenant_id=tenant_id, broker_account_id="broker-2", account_ids=(uuid4(), uuid4())
        ),
    ]

    with caplog.at_level(logging.ERROR):
        count = report_duplicate_broker_accounts(duplicates)

    assert count == 2
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 2
    assert "broker-1" in caplog.text
    assert "broker-2" in caplog.text


def test_report_is_silent_when_clean(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert report_duplicate_broker_accounts([]) == 0
    assert caplog.records == []
