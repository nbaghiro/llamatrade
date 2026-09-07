"""Writer-side sweep wiring against real Postgres.

Covers the session-factory bindings the unit suite fakes out — the drift
handler and cash-drift freezer running real transactions — and the scheduler
loops' election behavior: one real pass, then a prompt exit when the pod loses
the ledger-writer lock.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import (
    Account,
    LedgerEvent,
    LedgerEventType,
    SleeveStatus,
)
from llamatrade_events import EventBus
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport

from src.ledger.ingestion import LedgerAppend
from src.ledger.reconciliation import Drift, DriftKind
from src.repositories import SqlLedgerStore, SqlSleeveRepository
from src.services.fund_service import FundService
from src.services.sleeve_service import SleeveService
from src.tasks.corporate_actions import corporate_actions_loop
from src.tasks.drift_policy import make_cash_drift_freezer, make_drift_handler
from src.tasks.fill_ingestion import persist_append
from src.tasks.reconciliation import reconciliation_loop
from src.tasks.supervisor import LeadershipProbe

pytestmark = pytest.mark.integration

D = Decimal


@pytest.fixture
def alert_transport(monkeypatch: pytest.MonkeyPatch) -> FakeTransport:
    """Route freshly built alert dispatchers onto an in-memory stream."""
    transport = FakeTransport()
    monkeypatch.setattr(
        "src.alerts.shared_notification_events",
        lambda: NotificationEvents(bus=EventBus(transport)),
    )
    return transport


async def _genesis(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> tuple[Account, UUID]:
    """Account + base sleeves + one funded strategy sleeve, committed."""
    async with tenant_session(tenant_id, session_factory) as db:
        repo = SqlSleeveRepository(db)
        sleeves = SleeveService(repo)
        account = await sleeves.get_or_create_account(tenant_id, uuid4())
        await sleeves.ensure_base_sleeves(account)
        strategy = await sleeves.get_or_create_strategy_sleeve(
            account, strategy_execution_id=uuid4(), name="Loop Strategy"
        )
        await db.flush()
        fund = FundService(repo, SqlLedgerStore(db))
        await fund.deposit(tenant_id=tenant_id, account_id=account.id, amount=D("10000"))
        await fund.allocate(
            tenant_id=tenant_id, account_id=account.id, to_sleeve_id=strategy.id, amount=D("5000")
        )
        sleeve_id = strategy.id
        await db.commit()
    return account, sleeve_id


async def _buy(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    account_id: UUID,
    sleeve_id: UUID,
    *,
    qty: str,
    price: str,
) -> None:
    append = LedgerAppend(
        tenant_id=tenant_id,
        account_id=account_id,
        sleeve_id=sleeve_id,
        event_type=LedgerEventType.ORDER_FILLED,
        data={
            "sleeve_id": str(sleeve_id),
            "symbol": "SPY",
            "side": "buy",
            "qty": qty,
            "price": price,
        },
        event_id=UUID(bytes=hashlib.sha256(f"loop-buy-{sleeve_id}".encode()).digest()[:16]),
        occurred_at=datetime.now(UTC),
    )
    async with session_factory() as db:
        await persist_append(db, append)


async def _sleeve_statuses(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID, account_id: UUID
) -> dict[str, str]:
    async with tenant_session(tenant_id, session_factory) as db:
        rows = await SqlSleeveRepository(db).list_sleeves(tenant_id, account_id)
        return {str(s.id): s.status for s in rows}


async def _frozen_event_count(
    session_factory: async_sessionmaker[AsyncSession], account_id: UUID
) -> int:
    async with session_factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(LedgerEvent)
            .where(
                LedgerEvent.account_id == account_id,
                LedgerEvent.event_type == LedgerEventType.SLEEVE_FROZEN.value,
            )
        )
    return int(count or 0)


async def test_cash_drift_freezer_freezes_the_account_on_real_postgres(
    session_factory: async_sessionmaker[AsyncSession], alert_transport: FakeTransport
) -> None:
    """The loop's bound freezer runs a real transaction: statuses flip, the
    SLEEVE_FROZEN audit events land, and the alert publishes."""
    tenant_id = uuid4()
    account, _sleeve_id = await _genesis(session_factory, tenant_id)

    freeze = make_cash_drift_freezer(session_factory)
    await freeze(account, D("-42.50"))

    statuses = await _sleeve_statuses(session_factory, tenant_id, account.id)
    assert statuses  # base sleeves + strategy sleeve
    assert set(statuses.values()) == {SleeveStatus.FROZEN.value}
    assert await _frozen_event_count(session_factory, account.id) == len(statuses)
    assert len(alert_transport.records) == 1  # one account-level alert, not per sleeve

    # Idempotent within the pass day: everything already frozen, nothing re-appends.
    await freeze(account, D("-42.50"))
    assert await _frozen_event_count(session_factory, account.id) == len(statuses)
    assert len(alert_transport.records) == 1


async def test_drift_handler_freezes_contradicted_sleeve_on_real_postgres(
    session_factory: async_sessionmaker[AsyncSession], alert_transport: FakeTransport
) -> None:
    """The loop's bound drift handler applies the freeze policy transactionally."""
    tenant_id = uuid4()
    account, sleeve_id = await _genesis(session_factory, tenant_id)
    await _buy(session_factory, tenant_id, account.id, sleeve_id, qty="10", price="100")

    handle = make_drift_handler(session_factory)
    await handle(
        account,
        Drift(
            symbol="SPY",
            ledger_qty=D("10"),
            broker_qty=D("0"),
            kind=DriftKind.MISSING_AT_BROKER,
        ),
    )

    statuses = await _sleeve_statuses(session_factory, tenant_id, account.id)
    assert statuses[str(sleeve_id)] == SleeveStatus.FROZEN.value
    # Only the holding sleeve froze; empty base sleeves stay active.
    assert sum(1 for s in statuses.values() if s == SleeveStatus.FROZEN.value) == 1
    assert await _frozen_event_count(session_factory, account.id) == 1
    assert len(alert_transport.records) == 1


def _leader_for_one_pass() -> LeadershipProbe:
    """A LeadershipProbe that grants exactly one pass, then reports the lock lost."""
    grants = [True]

    async def probe() -> bool:
        if grants:
            return grants.pop()
        return False

    return probe


async def test_reconciliation_loop_runs_one_pass_then_exits_on_election_loss(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With a real account, the loop loads it, runs a pass (skipped: the account
    has no broker credentials), and exits as soon as leadership is lost."""
    tenant_id = uuid4()
    account, _sleeve_id = await _genesis(session_factory, tenant_id)
    probe = _leader_for_one_pass()

    with caplog.at_level(logging.INFO, logger="src.tasks.reconciliation"):
        await asyncio.wait_for(
            reconciliation_loop(
                session_factory,
                interval_seconds=0.05,
                stop_event=asyncio.Event(),
                is_leader=probe,
            ),
            timeout=30.0,
        )

    # The pass really ran over the account (skipped: no broker credentials) and
    # the election loss stopped the loop rather than a timeout.
    assert f"skipping reconciliation for account {account.id}" in caplog.text
    assert "ledger reconciliation loop stopped" in caplog.text


async def test_corporate_actions_loop_runs_one_pass_then_exits_on_election_loss(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant_id = uuid4()
    account, sleeve_id = await _genesis(session_factory, tenant_id)
    # A held symbol forces the pass through the announcement source, which is
    # skipped per account (no broker credentials) without aborting the loop.
    await _buy(session_factory, tenant_id, account.id, sleeve_id, qty="5", price="100")
    probe = _leader_for_one_pass()

    with caplog.at_level(logging.INFO, logger="src.tasks.corporate_actions"):
        await asyncio.wait_for(
            corporate_actions_loop(
                session_factory,
                stop_event=asyncio.Event(),
                interval_seconds=0.05,
                is_leader=probe,
            ),
            timeout=30.0,
        )

    assert f"skipping corporate-action detection for account {account.id}" in caplog.text
    assert "corporate-action detection loop stopped" in caplog.text
