"""Real-Postgres proof that a ledger account is keyed to its broker account.

An account that is deleted and re-added at the credential level must resolve back
to the book that already holds the broker's positions; two accounts over one
broker account double-count them in every tenant-level read. The service resolves
the broker id before creating an account, and this constraint is the backstop
when two callers race. Postgres treats NULLs as distinct, so accounts whose
broker id was never recorded stay insertable — proven here rather than assumed.

Requires Docker (testcontainers Postgres); skips cleanly otherwise (see conftest).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType


def _account(tenant_id: UUID, broker_account_id: str | None, credentials_id: UUID) -> Account:
    return Account(
        tenant_id=tenant_id,
        credentials_id=credentials_id,
        alpaca_account_id=broker_account_id,
        base_currency="USD",
    )


async def test_duplicate_broker_account_in_one_tenant_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid4()
    async with session_factory() as s:
        s.add(_account(tenant_id, "broker-1", uuid4()))
        await s.commit()

    async with session_factory() as s:
        s.add(_account(tenant_id, "broker-1", uuid4()))
        with pytest.raises(IntegrityError, match="uq_ledger_accounts_broker"):
            await s.commit()
        await s.rollback()


async def test_same_broker_account_in_two_tenants_is_allowed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    broker_account_id = f"broker-{uuid4().hex[:8]}"
    async with session_factory() as s:
        s.add(_account(uuid4(), broker_account_id, uuid4()))
        s.add(_account(uuid4(), broker_account_id, uuid4()))
        await s.commit()

        rows = (
            await s.scalars(select(Account).where(Account.alpaca_account_id == broker_account_id))
        ).all()
        assert len(rows) == 2


async def test_null_broker_accounts_do_not_collide(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Accounts booked before the broker id was recorded must stay insertable."""
    tenant_id = uuid4()
    async with session_factory() as s:
        s.add(_account(tenant_id, None, uuid4()))
        s.add(_account(tenant_id, None, uuid4()))
        s.add(_account(tenant_id, None, uuid4()))
        await s.commit()

        rows = (await s.scalars(select(Account).where(Account.tenant_id == tenant_id))).all()
        assert len(rows) == 3


async def test_relink_keeps_the_book_and_its_sleeves(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-pointing credentials is an UPDATE: the account id and sleeves survive."""
    tenant_id = uuid4()
    async with session_factory() as s:
        account = _account(tenant_id, "broker-1", uuid4())
        s.add(account)
        await s.flush()
        s.add(
            Sleeve(
                tenant_id=tenant_id,
                account_id=account.id,
                type=SleeveType.UNALLOCATED.value,
                status=SleeveStatus.ACTIVE.value,
                name="Unallocated",
            )
        )
        await s.commit()
        account_id = account.id

    new_credentials_id = uuid4()
    async with session_factory() as s:
        booked = await s.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id, Account.alpaca_account_id == "broker-1"
            )
        )
        assert booked is not None
        booked.credentials_id = new_credentials_id
        await s.commit()

    async with session_factory() as s:
        accounts = (await s.scalars(select(Account).where(Account.tenant_id == tenant_id))).all()
        assert [a.id for a in accounts] == [account_id]
        assert accounts[0].credentials_id == new_credentials_id
        sleeves = (await s.scalars(select(Sleeve).where(Sleeve.account_id == account_id))).all()
        assert [sl.type for sl in sleeves] == [SleeveType.UNALLOCATED.value]
