"""FundService tests — fund ops folded through the REAL ledger kernel.

No DB, no network: an in-memory event log is folded by the real ``projection``
kernel, so these assert true cash conservation and the funds invariants.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.ledger import Sleeve, SleeveStatus, SleeveType

from src.ledger.funds import FundError
from src.ledger.projection import AccountProjection, fold
from src.services.fund_service import FundService

TENANT = uuid4()
ACCOUNT = uuid4()
ZERO = Decimal("0")


class FakeLedger:
    """LedgerStore over an in-memory event list, projected by the real kernel."""

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
        eid = event_id or uuid4()
        if any(getattr(e, "event_id", None) == eid for e in self.events):
            return None
        ev = SimpleNamespace(event_id=eid, event_type=event_type, data=data)
        self.events.append(ev)
        return ev

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        return fold(self.events)


class FakeRepo:
    def __init__(self) -> None:
        self.sleeves: list[Sleeve] = []

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

    async def get_sleeve(self, tenant_id, sleeve_id):
        return next(
            (s for s in self.sleeves if s.tenant_id == tenant_id and s.id == sleeve_id), None
        )


def _sleeve(stype: SleeveType, *, strategy_execution_id: UUID | None = None) -> Sleeve:
    s = Sleeve(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        type=stype.value,
        status=SleeveStatus.ACTIVE.value,
        name=stype.value,
        strategy_execution_id=strategy_execution_id,
        allocated_capital=ZERO,
    )
    s.id = uuid4()
    return s


def _setup() -> tuple[FundService, FakeRepo, FakeLedger, Sleeve, Sleeve]:
    repo = FakeRepo()
    ledger = FakeLedger()
    unalloc = _sleeve(SleeveType.UNALLOCATED)
    strat = _sleeve(SleeveType.STRATEGY, strategy_execution_id=uuid4())
    repo.sleeves = [unalloc, strat]
    return FundService(repo, ledger), repo, ledger, unalloc, strat


async def test_deposit_credits_unallocated() -> None:
    svc, _repo, ledger, unalloc, _ = _setup()
    view = await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("10000"))
    assert view.cash == Decimal("10000")
    assert fold(ledger.events).total_cash() == Decimal("10000")


async def test_allocate_moves_cash_and_conserves() -> None:
    svc, _repo, ledger, unalloc, strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("10000"))
    view = await svc.allocate(
        tenant_id=TENANT, account_id=ACCOUNT, to_sleeve_id=strat.id, amount=Decimal("1000")
    )
    proj = fold(ledger.events)
    assert view.cash == Decimal("1000")  # strategy sleeve now funded
    assert proj.sleeve(str(unalloc.id)).cash == Decimal("9000")
    assert proj.sleeve(str(strat.id)).cash == Decimal("1000")
    assert proj.total_cash() == Decimal("10000")  # conserved


async def test_allocate_insufficient_free_cash_raises() -> None:
    svc, _repo, _ledger, _unalloc, strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("500"))
    with pytest.raises(FundError, match="insufficient free cash"):
        await svc.allocate(
            tenant_id=TENANT, account_id=ACCOUNT, to_sleeve_id=strat.id, amount=Decimal("1000")
        )


async def test_withdraw_reduces_then_insufficient_raises() -> None:
    svc, _repo, ledger, unalloc, _ = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))
    view = await svc.withdraw(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("400"))
    assert view.cash == Decimal("600")
    with pytest.raises(FundError, match="insufficient free cash"):
        await svc.withdraw(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))


async def test_transfer_liquid_moves_cash() -> None:
    svc, _repo, _ledger, unalloc, strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("5000"))
    await svc.allocate(
        tenant_id=TENANT, account_id=ACCOUNT, to_sleeve_id=strat.id, amount=Decimal("2000")
    )
    from_view, to_view = await svc.transfer(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        from_sleeve_id=strat.id,
        to_sleeve_id=unalloc.id,
        amount=Decimal("500"),
    )
    assert from_view.cash == Decimal("1500")
    assert to_view.cash == Decimal("3500")  # 3000 left + 500 back


async def test_transfer_illiquid_raises() -> None:
    svc, _repo, _ledger, unalloc, strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))
    # strat has no cash -> transferring from it needs raise-cash -> rejected
    with pytest.raises(FundError, match="raising cash"):
        await svc.transfer(
            tenant_id=TENANT,
            account_id=ACCOUNT,
            from_sleeve_id=strat.id,
            to_sleeve_id=unalloc.id,
            amount=Decimal("100"),
        )


async def _reserve(ledger: FakeLedger, sleeve_id: UUID, amount: str, coid: str) -> None:
    """Append an ORDER_SUBMITTED reservation event (earmarks free cash)."""
    from llamatrade_db.models.ledger import LedgerEventType

    await ledger.append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.ORDER_SUBMITTED,
        data={"sleeve_id": str(sleeve_id), "client_order_id": coid, "reserved": amount},
    )


async def test_withdraw_cannot_spend_reserved_cash() -> None:
    """Reserved cash (open buy orders) is not free: withdraw must exclude it."""
    svc, _repo, ledger, unalloc, _ = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))
    await _reserve(ledger, unalloc.id, "600", "lt-coid-1")
    # balance is 1000 but free is only 400 — a 600 withdraw must be rejected.
    assert fold(ledger.events).sleeve(str(unalloc.id)).reserved == Decimal("600")
    with pytest.raises(FundError, match="insufficient free cash"):
        await svc.withdraw(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("600"))
    # within free cash succeeds
    view = await svc.withdraw(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("400"))
    assert view.cash == Decimal("600")  # display balance = 1000 − 400


async def test_allocate_cannot_spend_reserved_cash() -> None:
    """Allocation affordability also excludes reserved cash."""
    svc, _repo, ledger, unalloc, strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))
    await _reserve(ledger, unalloc.id, "700", "lt-coid-2")
    with pytest.raises(FundError, match="insufficient free cash"):
        await svc.allocate(
            tenant_id=TENANT, account_id=ACCOUNT, to_sleeve_id=strat.id, amount=Decimal("500")
        )


async def test_deposit_without_unallocated_raises() -> None:
    repo = FakeRepo()  # no sleeves
    svc = FundService(repo, FakeLedger())
    with pytest.raises(FundError, match="no Unallocated sleeve"):
        await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("100"))


async def test_allocate_to_unknown_sleeve_raises() -> None:
    svc, _repo, _ledger, _unalloc, _strat = _setup()
    await svc.deposit(tenant_id=TENANT, account_id=ACCOUNT, amount=Decimal("1000"))
    with pytest.raises(FundError, match="not found"):
        await svc.allocate(
            tenant_id=TENANT, account_id=ACCOUNT, to_sleeve_id=uuid4(), amount=Decimal("100")
        )


async def test_deposit_with_foreign_tenant_cannot_reach_account() -> None:
    """A caller from another tenant can't resolve this account's Unallocated
    sleeve — the repo is tenant-scoped, so it looks unbootstrapped to them."""
    svc, _repo, _ledger, _unalloc, _strat = _setup()  # sleeves belong to TENANT
    other_tenant = uuid4()
    with pytest.raises(FundError, match="no Unallocated sleeve"):
        await svc.deposit(tenant_id=other_tenant, account_id=ACCOUNT, amount=Decimal("100"))
