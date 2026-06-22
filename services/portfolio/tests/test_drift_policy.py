"""Drift-policy tests — pure, no DB/broker.

Material drift actions (ledger is authoritative): external trades adopted into
Unmanaged, contradicted sleeves frozen; shadow mode stays observe-only.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from llamatrade_db.models.ledger import (
    Account,
    LedgerEventType,
    Sleeve,
    SleeveStatus,
    SleeveType,
)

from src.ledger.projection import AccountProjection, fold
from src.ledger.reconciliation import Drift, DriftKind
from src.ports import BrokerHolding, BrokerSnapshot
from src.tasks.drift_policy import apply_drift_action

TENANT = uuid4()
D = Decimal


def _account() -> Account:
    acct = Account(tenant_id=TENANT, credentials_id=uuid4())
    acct.id = uuid4()
    return acct


def _sleeve(account: Account, stype: SleeveType, name: str) -> Sleeve:
    s = Sleeve(
        tenant_id=TENANT,
        account_id=account.id,
        type=stype.value,
        status=SleeveStatus.ACTIVE.value,
        name=name,
        strategy_execution_id=uuid4() if stype is SleeveType.STRATEGY else None,
        allocated_capital=D("0"),
    )
    s.id = uuid4()
    return s


class FakeRepo:
    def __init__(self, sleeves: list[Sleeve]) -> None:
        self.sleeves = sleeves
        self.status_changes: list[tuple[Sleeve, str]] = []

    async def get_sleeve_by_type(self, tenant_id, account_id, sleeve_type):
        return next((s for s in self.sleeves if s.type == sleeve_type.value), None)

    async def list_sleeves(self, tenant_id, account_id):
        return self.sleeves

    async def set_sleeve_status(self, sleeve: Sleeve, status: str) -> None:
        sleeve.status = status
        self.status_changes.append((sleeve, status))


class FakeStore:
    """LedgerStore over an in-memory event list, projected by the real kernel."""

    def __init__(self, events: list[Any] | None = None) -> None:
        self.events: list[Any] = events or []
        self.appended: list[Any] = []

    async def append(
        self,
        *,
        tenant_id,
        account_id,
        event_type,
        data,
        sleeve_id=None,
        event_id=None,
        occurred_at=None,
    ):
        ev = SimpleNamespace(event_id=event_id, event_type=event_type, data=data)
        if any(e.event_id == event_id for e in self.events):
            return None
        self.events.append(ev)
        self.appended.append(ev)
        return ev

    async def project_account(self, tenant_id, account_id) -> AccountProjection:
        return fold(self.events)


class FakeBroker:
    def __init__(self, holdings: list[BrokerHolding]) -> None:
        self._snapshot = BrokerSnapshot(cash=D("0"), holdings=holdings)

    async def snapshot(self, tenant_id, account) -> BrokerSnapshot:
        return self._snapshot


def _drift(kind: DriftKind, *, ledger: str = "0", broker: str = "10") -> Drift:
    return Drift(symbol="SPY", ledger_qty=D(ledger), broker_qty=D(broker), kind=kind)


@pytest.fixture
def account() -> Account:
    return _account()


async def test_missing_in_ledger_adopted_into_unmanaged(account: Account) -> None:
    unmanaged = _sleeve(account, SleeveType.UNMANAGED, "Unmanaged")
    repo = FakeRepo([unmanaged])
    store = FakeStore()
    broker = FakeBroker([BrokerHolding(symbol="SPY", qty=D("10"), avg_price=D("480"))])

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=broker,
        account=account,
        drift=_drift(DriftKind.MISSING_IN_LEDGER, ledger="0", broker="10"),
    )

    assert action == "adopted"
    event = store.appended[0]
    assert event.event_type is LedgerEventType.EXTERNAL_TRADE_DETECTED
    assert event.data["sleeve_id"] == str(unmanaged.id)
    assert event.data["qty"] == "10"
    assert event.data["price"] == "480"
    # The adoption heals the invariant: ledger now matches broker for SPY
    projection = await store.project_account(TENANT, account.id)
    assert projection.account_positions() == {"SPY": D("10")}


class _FlakyBroker:
    """Broker whose snapshot raises ``failures`` times before succeeding."""

    def __init__(self, holdings: list[BrokerHolding], *, failures: int) -> None:
        self._snapshot = BrokerSnapshot(cash=D("0"), holdings=holdings)
        self._failures = failures
        self.calls = 0

    async def snapshot(self, tenant_id: Any, account: Any) -> BrokerSnapshot:
        self.calls += 1
        if self._failures > 0:
            self._failures -= 1
            raise ConnectionError("broker down")
        return self._snapshot


async def test_adoption_retries_broker_snapshot_then_succeeds(
    account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.tasks.drift_policy._SNAPSHOT_BASE_DELAY", 0.0)  # no real backoff
    repo = FakeRepo([_sleeve(account, SleeveType.UNMANAGED, "Unmanaged")])
    store = FakeStore()
    broker = _FlakyBroker(
        [BrokerHolding(symbol="SPY", qty=D("10"), avg_price=D("480"))], failures=2
    )

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=broker,
        account=account,
        drift=_drift(DriftKind.MISSING_IN_LEDGER),
    )

    assert action == "adopted"
    assert broker.calls == 3  # 2 transient failures + 1 success


async def test_adoption_skips_when_broker_unavailable(
    account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.tasks.drift_policy._SNAPSHOT_BASE_DELAY", 0.0)
    repo = FakeRepo([_sleeve(account, SleeveType.UNMANAGED, "Unmanaged")])
    store = FakeStore()
    broker = _FlakyBroker([], failures=99)  # never recovers

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=broker,
        account=account,
        drift=_drift(DriftKind.MISSING_IN_LEDGER),
    )

    assert action == "skipped"
    assert not store.appended  # nothing adopted when the broker can't be reached


async def test_adoption_is_idempotent(account: Account) -> None:
    repo = FakeRepo([_sleeve(account, SleeveType.UNMANAGED, "Unmanaged")])
    store = FakeStore()
    broker = FakeBroker([BrokerHolding(symbol="SPY", qty=D("10"), avg_price=D("480"))])
    drift = _drift(DriftKind.MISSING_IN_LEDGER)

    await apply_drift_action(repo=repo, store=store, broker=broker, account=account, drift=drift)
    await apply_drift_action(repo=repo, store=store, broker=broker, account=account, drift=drift)

    assert len(store.appended) == 1  # deterministic event_id dedups the re-detection


async def test_vanished_holding_skipped(account: Account) -> None:
    repo = FakeRepo([_sleeve(account, SleeveType.UNMANAGED, "Unmanaged")])
    store = FakeStore()

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=FakeBroker([]),
        account=account,
        drift=_drift(DriftKind.MISSING_IN_LEDGER),
    )

    assert action == "skipped"
    assert store.appended == []


async def test_qty_mismatch_freezes_holding_sleeves(account: Account) -> None:
    holder = _sleeve(account, SleeveType.STRATEGY, "Strategy A")
    bystander = _sleeve(account, SleeveType.STRATEGY, "Strategy B")
    repo = FakeRepo([holder, bystander])
    # Seed the store so only `holder` has a SPY position
    store = FakeStore(
        [
            SimpleNamespace(
                event_id=uuid4(),
                event_type=LedgerEventType.ORDER_FILLED,
                data={
                    "sleeve_id": str(holder.id),
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": "60",
                    "price": "480",
                },
            )
        ]
    )

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=FakeBroker([]),
        account=account,
        drift=_drift(DriftKind.QTY_MISMATCH, ledger="60", broker="59"),
    )

    assert action == "froze:1"
    assert holder.status == SleeveStatus.FROZEN.value
    assert bystander.status == SleeveStatus.ACTIVE.value
    freeze_events = [e for e in store.appended if e.event_type is LedgerEventType.SLEEVE_FROZEN]
    assert len(freeze_events) == 1
    assert freeze_events[0].data["sleeve_id"] == str(holder.id)


async def test_already_frozen_sleeve_not_refrozen(account: Account) -> None:
    holder = _sleeve(account, SleeveType.STRATEGY, "Strategy A")
    holder.status = SleeveStatus.FROZEN.value
    repo = FakeRepo([holder])
    store = FakeStore(
        [
            SimpleNamespace(
                event_id=uuid4(),
                event_type=LedgerEventType.ORDER_FILLED,
                data={
                    "sleeve_id": str(holder.id),
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": "60",
                    "price": "480",
                },
            )
        ]
    )

    action = await apply_drift_action(
        repo=repo,
        store=store,
        broker=FakeBroker([]),
        account=account,
        drift=_drift(DriftKind.MISSING_AT_BROKER, ledger="60", broker="0"),
    )

    assert action == "froze:0"
    assert repo.status_changes == []
