"""Real-schema proof that a ledger account is keyed to its broker account.

``ledger_accounts`` is unique per ``(tenant_id, alpaca_account_id)`` so a
credential set that is deleted and re-added cannot fork a second book over the
same broker positions. The application resolves the broker id before creating an
account; this constraint is the backstop when two callers race.

The tests run against a real (SQLite) schema rather than mocks so a dropped
constraint fails here. SQLite and PostgreSQL agree on the property that matters:
NULLs are distinct, so accounts whose broker id was never recorded never collide.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.base import Base
from llamatrade_db.models.ledger import Account

_TABLES = [Account.__table__]


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    """A SQLite engine holding only the ledger-account table."""
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


def _account(
    session: Session,
    *,
    tenant_id: UUID,
    broker_account_id: str | None = None,
    credentials_id: UUID | None = None,
) -> Account:
    account = Account(
        tenant_id=tenant_id,
        credentials_id=credentials_id or uuid4(),
        alpaca_account_id=broker_account_id,
        base_currency="USD",
    )
    session.add(account)
    session.flush()
    return account


def test_duplicate_broker_account_in_one_tenant_is_rejected(db_session: Session) -> None:
    """Two accounts over one broker account would double-count its positions."""
    tenant_id = uuid4()
    _account(db_session, tenant_id=tenant_id, broker_account_id="acct-1")

    with pytest.raises(IntegrityError):
        _account(db_session, tenant_id=tenant_id, broker_account_id="acct-1")


def test_same_broker_account_in_two_tenants_is_allowed(db_session: Session) -> None:
    """Uniqueness is per tenant; the id space is the broker's, not ours."""
    first = _account(db_session, tenant_id=uuid4(), broker_account_id="acct-1")
    second = _account(db_session, tenant_id=uuid4(), broker_account_id="acct-1")

    assert first.id != second.id


def test_null_broker_accounts_do_not_collide(db_session: Session) -> None:
    """Unrecorded broker ids stay distinct, so the constraint applies to old rows."""
    tenant_id = uuid4()
    first = _account(db_session, tenant_id=tenant_id)
    second = _account(db_session, tenant_id=tenant_id)
    third = _account(db_session, tenant_id=tenant_id)

    assert len({first.id, second.id, third.id}) == 3
    assert [a.alpaca_account_id for a in (first, second, third)] == [None, None, None]


def test_distinct_broker_accounts_in_one_tenant_both_insert(db_session: Session) -> None:
    tenant_id = uuid4()
    first = _account(db_session, tenant_id=tenant_id, broker_account_id="acct-1")
    second = _account(db_session, tenant_id=tenant_id, broker_account_id="acct-2")

    assert first.id != second.id


def test_credentials_stay_unique(db_session: Session) -> None:
    """The credential key is unchanged: one account may claim a credential set."""
    credentials_id = uuid4()
    _account(
        db_session, tenant_id=uuid4(), broker_account_id="acct-1", credentials_id=credentials_id
    )

    with pytest.raises(IntegrityError):
        _account(
            db_session,
            tenant_id=uuid4(),
            broker_account_id="acct-2",
            credentials_id=credentials_id,
        )


def test_relinking_credentials_keeps_one_account(db_session: Session) -> None:
    """Re-pointing an account at re-added credentials is an update, not a second row."""
    tenant_id = uuid4()
    account = _account(db_session, tenant_id=tenant_id, broker_account_id="acct-1")
    original_id = account.id

    new_credentials_id = uuid4()
    account.credentials_id = new_credentials_id
    db_session.flush()

    rows = db_session.query(Account).filter(Account.tenant_id == tenant_id).all()
    assert [r.id for r in rows] == [original_id]
    assert rows[0].credentials_id == new_credentials_id
