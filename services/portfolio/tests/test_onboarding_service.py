"""Account-onboarding tests — pure, folded through the real ledger kernel.

An in-memory repo + event log (folded by the real projection kernel) verify that
onboarding creates the account + base sleeves and seeds broker cash → Unallocated
and positions → Unmanaged, conserving cash, and is idempotent on re-run.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

from llamatrade_db.models.ledger import Account, LedgerEventType, Sleeve, SleeveType

from src.ledger.projection import fold
from src.ports import BrokerHolding, BrokerSnapshot
from src.services.onboarding_service import AccountOnboardingService, _backfill_event_id
from src.services.sleeve_service import SleeveService

TENANT = uuid4()
CREDS = uuid4()


class FakeSleeveRepo:
    """In-memory ``SleeveRepository`` that assigns ids on insert."""

    def __init__(self) -> None:
        self.accounts: list[Account] = []
        self.sleeves: list[Sleeve] = []

    async def get_account_by_credentials(self, tenant_id, credentials_id):
        return next(
            (
                a
                for a in self.accounts
                if a.tenant_id == tenant_id and a.credentials_id == credentials_id
            ),
            None,
        )

    async def get_account_by_broker_id(self, tenant_id, broker_account_id):
        return next(
            (
                a
                for a in self.accounts
                if a.tenant_id == tenant_id and a.alpaca_account_id == broker_account_id
            ),
            None,
        )

    async def add_account(self, account: Account) -> None:
        account.id = uuid4()
        self.accounts.append(account)

    async def set_account_credentials(self, account: Account, credentials_id) -> None:
        account.credentials_id = credentials_id

    async def set_account_broker_id(self, account: Account, broker_account_id) -> None:
        account.alpaca_account_id = broker_account_id

    async def get_sleeve(self, tenant_id, sleeve_id):
        return next(
            (s for s in self.sleeves if s.tenant_id == tenant_id and s.id == sleeve_id), None
        )

    async def get_sleeve_by_type(self, tenant_id, account_id, sleeve_type):
        return next(
            (
                s
                for s in self.sleeves
                if s.tenant_id == tenant_id
                and s.account_id == account_id
                and s.type == sleeve_type.value
                and s.strategy_execution_id is None
            ),
            None,
        )

    async def get_strategy_sleeve(self, tenant_id, account_id, strategy_execution_id):
        return next(
            (
                s
                for s in self.sleeves
                if s.tenant_id == tenant_id
                and s.account_id == account_id
                and s.strategy_execution_id == strategy_execution_id
            ),
            None,
        )

    async def list_sleeves(self, tenant_id, account_id):
        return [s for s in self.sleeves if s.tenant_id == tenant_id and s.account_id == account_id]

    async def add_sleeve(self, sleeve: Sleeve) -> None:
        sleeve.id = uuid4()
        self.sleeves.append(sleeve)


class FakeStore:
    """In-memory ``LedgerStore`` that dedups on event_id and folds via the kernel."""

    def __init__(self) -> None:
        self.events: list[Any] = []

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
    ) -> Any:
        if any(getattr(e, "event_id", None) == event_id for e in self.events):
            return None
        ev = SimpleNamespace(event_id=event_id, event_type=event_type, data=data)
        self.events.append(ev)
        return ev

    async def project_account(self, tenant_id: UUID, account_id: UUID):
        return fold(self.events)


class FakeBroker:
    """Broker truth for the account under test; ``current`` is swappable per pass."""

    def __init__(self, snapshot: BrokerSnapshot) -> None:
        self.current = snapshot

    async def snapshot(self, tenant_id, account) -> BrokerSnapshot:
        return self.current


def _service_with_broker(
    snapshot: BrokerSnapshot,
) -> tuple[AccountOnboardingService, FakeSleeveRepo, FakeStore, FakeBroker]:
    repo = FakeSleeveRepo()
    store = FakeStore()
    broker = FakeBroker(snapshot)
    svc = AccountOnboardingService(SleeveService(cast(Any, repo)), store, broker)
    return svc, repo, store, broker


def _service(
    snapshot: BrokerSnapshot,
) -> tuple[AccountOnboardingService, FakeSleeveRepo, FakeStore]:
    svc, repo, store, _broker = _service_with_broker(snapshot)
    return svc, repo, store


async def test_onboard_creates_account_and_base_sleeves() -> None:
    svc, repo, _store = _service(BrokerSnapshot(cash=Decimal("0"), holdings=[]))
    account = await svc.onboard(TENANT, CREDS)

    assert account.tenant_id == TENANT
    assert account.credentials_id == CREDS
    types = {s.type for s in repo.sleeves}
    assert types == {
        SleeveType.UNALLOCATED.value,
        SleeveType.MANUAL.value,
        SleeveType.UNMANAGED.value,
    }


async def test_onboard_seeds_cash_to_unallocated() -> None:
    svc, repo, store = _service(BrokerSnapshot(cash=Decimal("5000"), holdings=[]))
    await svc.onboard(TENANT, CREDS)

    unalloc = next(s for s in repo.sleeves if s.type == SleeveType.UNALLOCATED.value)
    proj = fold(store.events)
    assert proj.sleeve(str(unalloc.id)).cash == Decimal("5000")
    assert proj.total_cash() == Decimal("5000")
    deposits = [e for e in store.events if e.event_type == LedgerEventType.FUNDS_DEPOSITED]
    assert len(deposits) == 1


async def test_onboard_seeds_positions_to_unmanaged() -> None:
    snapshot = BrokerSnapshot(
        cash=Decimal("1000"),
        holdings=[BrokerHolding(symbol="AAPL", qty=Decimal("10"), avg_price=Decimal("150"))],
    )
    svc, repo, store = _service(snapshot)
    await svc.onboard(TENANT, CREDS)

    unmanaged = next(s for s in repo.sleeves if s.type == SleeveType.UNMANAGED.value)
    proj = fold(store.events)
    positions = proj.sleeve(str(unmanaged.id)).positions
    assert positions["AAPL"].qty == Decimal("10")
    externals = [e for e in store.events if e.event_type == LedgerEventType.EXTERNAL_TRADE_DETECTED]
    assert len(externals) == 1


async def test_onboard_is_idempotent() -> None:
    snapshot = BrokerSnapshot(
        cash=Decimal("1000"),
        holdings=[BrokerHolding(symbol="AAPL", qty=Decimal("10"), avg_price=Decimal("150"))],
    )
    svc, repo, store = _service(snapshot)
    first = await svc.onboard(TENANT, CREDS)
    events_after_first = len(store.events)
    second = await svc.onboard(TENANT, CREDS)

    assert first.id == second.id  # same account
    assert len(store.events) == events_after_first  # no duplicate seed events
    assert len(repo.accounts) == 1
    # Base sleeves not duplicated either.
    assert len([s for s in repo.sleeves if s.type == SleeveType.UNALLOCATED.value]) == 1


async def test_onboard_no_broker_state_seeds_nothing() -> None:
    svc, _repo, store = _service(BrokerSnapshot(cash=Decimal("0"), holdings=[]))
    await svc.onboard(TENANT, CREDS)
    assert store.events == []


async def test_onboard_records_the_broker_account_id() -> None:
    snapshot = BrokerSnapshot(cash=Decimal("0"), holdings=[], broker_account_id="broker-1")
    svc, _repo, _store = _service(snapshot)
    account = await svc.onboard(TENANT, CREDS)
    assert account.alpaca_account_id == "broker-1"


async def test_re_added_credentials_onboard_into_the_existing_book() -> None:
    """The whole point: the sleeves, cash and history of the first account survive."""
    snapshot = BrokerSnapshot(
        cash=Decimal("1000"),
        holdings=[BrokerHolding(symbol="AAPL", qty=Decimal("10"), avg_price=Decimal("150"))],
        broker_account_id="broker-1",
    )
    svc, repo, store = _service(snapshot)
    first = await svc.onboard(TENANT, CREDS)
    sleeves_before = {s.id for s in repo.sleeves}
    events_before = len(store.events)

    new_creds = uuid4()
    second = await svc.onboard(TENANT, new_creds)

    assert second.id == first.id
    assert second.credentials_id == new_creds
    assert len(repo.accounts) == 1
    assert {s.id for s in repo.sleeves} == sleeves_before
    assert len(store.events) == events_before  # no second genesis over the same positions
    proj = fold(store.events)
    assert proj.total_cash() == Decimal("1000")


async def test_onboard_backfills_a_missing_broker_account_id() -> None:
    """An account booked before the broker id existed adopts it on the next pass."""
    svc, repo, _store, broker = _service_with_broker(BrokerSnapshot(cash=Decimal("0"), holdings=[]))
    account = await svc.onboard(TENANT, CREDS)
    assert account.alpaca_account_id is None

    broker.current = BrokerSnapshot(cash=Decimal("0"), holdings=[], broker_account_id="broker-1")
    again = await svc.onboard(TENANT, CREDS)

    assert again.id == account.id
    assert again.alpaca_account_id == "broker-1"
    assert len(repo.accounts) == 1


async def test_re_link_does_not_re_import_positions_bought_since_genesis() -> None:
    """A book that traded after genesis must not adopt its holdings a second time."""
    svc, _repo, store, broker = _service_with_broker(
        BrokerSnapshot(
            cash=Decimal("1000"),
            holdings=[BrokerHolding(symbol="AAPL", qty=Decimal("10"), avg_price=Decimal("150"))],
            broker_account_id="broker-1",
        )
    )
    await svc.onboard(TENANT, CREDS)
    events_before = len(store.events)

    # The strategy bought MSFT after onboarding, so the broker now reports it too.
    broker.current = BrokerSnapshot(
        cash=Decimal("400"),
        holdings=[
            BrokerHolding(symbol="AAPL", qty=Decimal("10"), avg_price=Decimal("150")),
            BrokerHolding(symbol="MSFT", qty=Decimal("2"), avg_price=Decimal("300")),
        ],
        broker_account_id="broker-1",
    )
    await svc.onboard(TENANT, uuid4())

    assert len(store.events) == events_before
    symbols = {e.data.get("symbol") for e in store.events if "symbol" in e.data}
    assert symbols == {"AAPL"}


async def test_existing_account_is_not_re_seeded_when_broker_state_moves() -> None:
    svc, _repo, store, broker = _service_with_broker(
        BrokerSnapshot(cash=Decimal("1000"), holdings=[], broker_account_id="broker-1")
    )
    await svc.onboard(TENANT, CREDS)
    events_before = len(store.events)

    broker.current = BrokerSnapshot(
        cash=Decimal("2500"),
        holdings=[BrokerHolding(symbol="TSLA", qty=Decimal("1"), avg_price=Decimal("200"))],
        broker_account_id="broker-1",
    )
    await svc.onboard(TENANT, CREDS)

    assert len(store.events) == events_before
    assert fold(store.events).total_cash() == Decimal("1000")


async def test_two_broker_accounts_in_one_tenant_stay_separate() -> None:
    svc, repo, _store, broker = _service_with_broker(
        BrokerSnapshot(cash=Decimal("0"), holdings=[], broker_account_id="broker-1")
    )
    first = await svc.onboard(TENANT, CREDS)

    broker.current = BrokerSnapshot(cash=Decimal("0"), holdings=[], broker_account_id="broker-2")
    second = await svc.onboard(TENANT, uuid4())

    assert first.id != second.id
    assert len(repo.accounts) == 2


def test_backfill_event_id_is_pinned_and_deterministic() -> None:
    # Pinning the exact output guards the idempotency key against silent
    # algorithm changes (which would orphan already-seeded events in prod).
    acct = UUID("00000000-0000-0000-0000-0000000000aa")
    assert _backfill_event_id(acct, "backfill:cash") == UUID("572a9587-23d3-e7cf-1573-9a62699889e2")
    # Distinct dedup keys -> distinct ids.
    assert _backfill_event_id(acct, "backfill:cash") != _backfill_event_id(
        acct, "backfill:pos:AAPL"
    )
