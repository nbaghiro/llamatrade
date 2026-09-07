"""``load_statement`` against real Postgres.

The rendering kernel is golden-pinned in the unit suite; this exercises the
database shell — account resolution by each selector, the audited system
session, and the event read — over rows written by the real services.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import Account, LedgerEventType, SleeveType

from src.ledger.ingestion import LedgerAppend
from src.repositories import SqlLedgerStore, SqlSleeveRepository
from src.services.fund_service import FundService
from src.services.sleeve_service import SleeveService
from src.tasks.fill_ingestion import persist_append
from src.tools.statement import StatementError, load_statement, render_json, render_text

pytestmark = pytest.mark.integration

D = Decimal


async def _seed_account(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> tuple[Account, UUID, UUID]:
    """Deposit 10000, allocate 4000, buy 5 SPY @ 100. Returns (account, sleeve, credentials)."""
    credentials_id = uuid4()
    async with tenant_session(tenant_id, session_factory) as db:
        repo = SqlSleeveRepository(db)
        sleeves = SleeveService(repo)
        account = await sleeves.get_or_create_account(tenant_id, credentials_id)
        await sleeves.ensure_base_sleeves(account)
        strategy = await sleeves.get_or_create_strategy_sleeve(
            account, strategy_execution_id=uuid4(), name="Statement Strategy"
        )
        await db.flush()
        fund = FundService(repo, SqlLedgerStore(db))
        await fund.deposit(tenant_id=tenant_id, account_id=account.id, amount=D("10000"))
        await fund.allocate(
            tenant_id=tenant_id, account_id=account.id, to_sleeve_id=strategy.id, amount=D("4000")
        )
        sleeve_id = strategy.id
        await db.commit()

    async with session_factory() as db:
        await persist_append(
            db,
            LedgerAppend(
                tenant_id=tenant_id,
                account_id=account.id,
                sleeve_id=sleeve_id,
                event_type=LedgerEventType.ORDER_FILLED,
                data={
                    "sleeve_id": str(sleeve_id),
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": "5",
                    "price": "100",
                },
                event_id=UUID(bytes=hashlib.sha256(b"stmt-buy").digest()[:16]),
                occurred_at=datetime.now(UTC),
            ),
        )
    return account, sleeve_id, credentials_id


async def test_load_statement_reads_the_account_book(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid4()
    account, sleeve_id, _credentials_id = await _seed_account(session_factory, tenant_id)

    statement = await load_statement(
        tenant_id=tenant_id, account_id=account.id, session_maker=session_factory
    )

    assert statement.account.account_id == account.id
    assert statement.account.tenant_id == tenant_id
    assert statement.events_through_end == 3  # deposit + allocation + fill
    assert statement.total_cash == D("9500")  # 10000 − 500 spent on SPY
    assert statement.total_positions_cost == D("500")
    assert statement.invariants.balanced is True

    by_sleeve = {b.sleeve_id: b for b in statement.closing}
    strategy = by_sleeve[str(sleeve_id)]
    assert strategy.cash == D("3500")
    assert [(p.symbol, p.qty, p.cost_basis) for p in strategy.positions] == [
        ("SPY", D("5"), D("500"))
    ]
    unallocated = next(b for b in statement.closing if b.type == SleeveType.UNALLOCATED.value)
    assert unallocated.cash == D("6000")

    # Both renderers run over the loaded statement without error.
    assert "SPY" in render_text(statement)
    assert '"SPY"' in render_json(statement)


async def test_load_statement_resolves_by_credentials_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid4()
    account, _sleeve_id, credentials_id = await _seed_account(session_factory, tenant_id)

    statement = await load_statement(
        tenant_id=tenant_id, credentials_id=credentials_id, session_maker=session_factory
    )

    assert statement.account.account_id == account.id


async def test_load_statement_unknown_account_raises_statement_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(StatementError, match="no ledger account"):
        await load_statement(tenant_id=uuid4(), account_id=uuid4(), session_maker=session_factory)


async def test_load_statement_is_tenant_scoped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Another tenant's id cannot resolve this account even by its exact UUID."""
    tenant_id = uuid4()
    account, _sleeve_id, _credentials_id = await _seed_account(session_factory, tenant_id)

    with pytest.raises(StatementError):
        await load_statement(
            tenant_id=uuid4(), account_id=account.id, session_maker=session_factory
        )
