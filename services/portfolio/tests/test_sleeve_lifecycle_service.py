"""SleeveLifecycleService tests — close folded through the REAL ledger kernel.

No DB, no network: an in-memory event log is folded by the real ``projection``
kernel, so these assert true conservation (account cash and per-symbol qty are
unchanged by a close — value only moves between sleeves) and the close
invariants (idempotency, reserved-cash guard, re-home targets).
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.ledger import LedgerEventType, Sleeve, SleeveStatus, SleeveType

from src.ledger.lifecycle import SleeveCloseError, close_event_id
from src.ledger.postings import Bucket, assert_balanced, build_postings
from src.ledger.projection import AccountProjection, fold
from src.services.sleeve_lifecycle_service import SleeveLifecycleService

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
        tenant_id: UUID,
        account_id: UUID,
        event_type: Any,
        data: Any,
        sleeve_id: Any = None,
        event_id: Any = None,
        occurred_at: Any = None,
    ) -> Any:
        eid = event_id or uuid4()
        if any(getattr(e, "event_id", None) == eid for e in self.events):
            return None  # idempotent: duplicate event_id is a no-op
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

    async def set_sleeve_status(self, sleeve: Sleeve, status: str) -> None:
        sleeve.status = status


def _sleeve(stype: SleeveType, *, strategy_execution_id: UUID | None = None) -> Sleeve:
    s = Sleeve(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        type=stype.value,
        status=SleeveStatus.ACTIVE.value,
        name=stype.value,
        strategy_execution_id=strategy_execution_id,
        allocated_capital=ZERO,
        cash_balance=ZERO,
        reserved_cash=ZERO,
        unsettled_cash=ZERO,
    )
    s.id = uuid4()
    return s


def _setup() -> tuple[SleeveLifecycleService, FakeRepo, FakeLedger, Sleeve, Sleeve, Sleeve]:
    repo = FakeRepo()
    ledger = FakeLedger()
    unalloc = _sleeve(SleeveType.UNALLOCATED)
    unmanaged = _sleeve(SleeveType.UNMANAGED)
    strat = _sleeve(SleeveType.STRATEGY, strategy_execution_id=uuid4())
    repo.sleeves = [unalloc, unmanaged, strat]
    return SleeveLifecycleService(repo, ledger), repo, ledger, unalloc, unmanaged, strat


async def _deposit(ledger: FakeLedger, sleeve_id: UUID, amount: str) -> None:
    await ledger.append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.FUNDS_DEPOSITED,
        data={"sleeve_id": str(sleeve_id), "amount": amount},
    )


async def _allocate(ledger: FakeLedger, frm: UUID, to: UUID, amount: str) -> None:
    await ledger.append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.CAPITAL_ALLOCATED,
        data={"from_sleeve_id": str(frm), "to_sleeve_id": str(to), "amount": amount},
    )


async def _buy(ledger: FakeLedger, sleeve_id: UUID, symbol: str, qty: str, price: str) -> None:
    await ledger.append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.ORDER_FILLED,
        data={
            "sleeve_id": str(sleeve_id),
            "symbol": symbol,
            "side": "buy",
            "qty": qty,
            "price": price,
            "client_order_id": uuid4().hex,
        },
    )


async def _reserve(ledger: FakeLedger, sleeve_id: UUID, amount: str) -> None:
    await ledger.append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.ORDER_SUBMITTED,
        data={"sleeve_id": str(sleeve_id), "client_order_id": uuid4().hex, "reserved": amount},
    )


# --------------------------------------------------------------------------- core


async def test_close_rehomes_positions_and_cash_and_conserves() -> None:
    svc, _repo, ledger, unalloc, unmanaged, strat = _setup()
    # Fund the strategy sleeve and buy a position: 5000 in, buy 10 @ 300 = 3000.
    await _deposit(ledger, unalloc.id, "10000")
    await _allocate(ledger, unalloc.id, strat.id, "5000")
    await _buy(ledger, strat.id, "AAPL", "10", "300")

    before = fold(ledger.events)
    assert before.sleeve(str(strat.id)).cash == Decimal("2000")  # 5000 − 3000
    # 3000 of cash is now position value, so account cash is 7000 (not 10000).
    assert before.total_cash() == Decimal("7000")
    assert before.account_positions() == {"AAPL": Decimal("10")}

    result = await svc.close_sleeve(
        tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id, reason="execution stopped"
    )

    after = fold(ledger.events)
    # Strategy sleeve fully drained.
    assert after.sleeve(str(strat.id)).cash == ZERO
    assert (
        after.sleeve(str(strat.id)).positions.get("AAPL", None) is None
        or after.sleeve(str(strat.id)).positions["AAPL"].qty == ZERO
    )
    # Position re-homed to Unmanaged at cost; free cash to Unallocated.
    assert after.sleeve(str(unmanaged.id)).positions["AAPL"].qty == Decimal("10")
    assert after.sleeve(str(unmanaged.id)).positions["AAPL"].cost_basis == Decimal("3000")
    assert after.sleeve(str(unalloc.id)).cash == Decimal("7000")  # 5000 left + 2000 back
    # Conserved at the account level (cash unchanged; position re-homed, not sold).
    assert after.total_cash() == Decimal("7000")
    assert after.account_positions() == {"AAPL": Decimal("10")}
    # Status flipped and the result reflects the move.
    assert strat.status == SleeveStatus.CLOSED.value
    assert result.rehomed_cash == Decimal("2000")
    assert result.already_closed is False
    assert {p.symbol: p.qty for p in result.rehomed_positions} == {"AAPL": Decimal("10")}


async def test_close_preserves_realized_pnl_is_not_recognized() -> None:
    """Re-homing is not a sale: no realized P&L is recognized on close."""
    svc, _repo, ledger, unalloc, unmanaged, strat = _setup()
    await _deposit(ledger, unalloc.id, "10000")
    await _allocate(ledger, unalloc.id, strat.id, "5000")
    await _buy(ledger, strat.id, "AAPL", "10", "300")

    await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)

    after = fold(ledger.events)
    assert after.sleeve(str(strat.id)).realized_pnl == ZERO
    assert after.sleeve(str(unmanaged.id)).realized_pnl == ZERO


async def test_close_is_idempotent() -> None:
    svc, _repo, ledger, _unalloc, _unmanaged, strat = _setup()
    await _deposit(ledger, _unalloc.id, "5000")
    await _allocate(ledger, _unalloc.id, strat.id, "1000")

    first = await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)
    snapshot = fold(ledger.events)
    n_events = len(ledger.events)

    second = await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)

    assert first.already_closed is False
    assert second.already_closed is True
    assert second.rehomed_cash == ZERO
    # No new events, projection unchanged.
    assert len(ledger.events) == n_events
    assert fold(ledger.events).total_cash() == snapshot.total_cash()


async def test_close_event_id_is_deterministic_so_replay_is_noop() -> None:
    """Even without the status short-circuit, the deterministic id dedups."""
    svc, _repo, ledger, unalloc, _unmanaged, strat = _setup()
    await _deposit(ledger, unalloc.id, "5000")
    await _allocate(ledger, unalloc.id, strat.id, "1000")
    await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)

    # Simulate a status-persistence failure: re-run with status forced back.
    strat.status = SleeveStatus.ACTIVE.value
    n_events = len(ledger.events)
    await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)

    assert len(ledger.events) == n_events  # deterministic event_id → append no-op
    assert strat.status == SleeveStatus.CLOSED.value  # status re-applied


async def test_close_refuses_with_reserved_cash() -> None:
    svc, _repo, ledger, unalloc, _unmanaged, strat = _setup()
    await _deposit(ledger, unalloc.id, "10000")
    await _allocate(ledger, unalloc.id, strat.id, "5000")
    await _reserve(ledger, strat.id, "1000")  # open buy order

    with pytest.raises(SleeveCloseError, match="reserved for in-flight orders"):
        await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)
    assert strat.status == SleeveStatus.ACTIVE.value  # untouched


async def test_close_empty_sleeve_just_marks_closed() -> None:
    svc, _repo, ledger, _unalloc, _unmanaged, strat = _setup()
    result = await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)
    assert result.rehomed_cash == ZERO
    assert result.rehomed_positions == ()
    assert strat.status == SleeveStatus.CLOSED.value
    # A lifecycle marker event was still recorded.
    assert any(e.event_type == LedgerEventType.SLEEVE_CLOSED for e in ledger.events)


async def test_cannot_close_base_sleeve() -> None:
    svc, _repo, _ledger, unalloc, unmanaged, _strat = _setup()
    with pytest.raises(SleeveCloseError, match="cannot close a base"):
        await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=unalloc.id)
    with pytest.raises(SleeveCloseError, match="cannot close a base"):
        await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=unmanaged.id)


async def test_close_unknown_sleeve_raises() -> None:
    svc, _repo, _ledger, _unalloc, _unmanaged, _strat = _setup()
    with pytest.raises(SleeveCloseError, match="not found"):
        await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=uuid4())


async def test_close_requires_base_sleeves() -> None:
    repo = FakeRepo()
    ledger = FakeLedger()
    strat = _sleeve(SleeveType.STRATEGY, strategy_execution_id=uuid4())
    repo.sleeves = [strat]  # no unmanaged/unallocated
    svc = SleeveLifecycleService(repo, ledger)
    with pytest.raises(SleeveCloseError, match="missing base sleeves"):
        await svc.close_sleeve(tenant_id=TENANT, account_id=ACCOUNT, sleeve_id=strat.id)


async def test_close_foreign_tenant_cannot_reach_sleeve() -> None:
    svc, _repo, _ledger, _unalloc, _unmanaged, strat = _setup()
    with pytest.raises(SleeveCloseError, match="not found"):
        await svc.close_sleeve(tenant_id=uuid4(), account_id=ACCOUNT, sleeve_id=strat.id)


# ----------------------------------------------------------------------- postings


def test_sleeve_closed_postings_balance() -> None:
    frm, pos_to, cash_to = uuid4(), uuid4(), uuid4()
    data: dict[str, object] = {
        "sleeve_id": str(frm),
        "to_position_sleeve_id": str(pos_to),
        "to_cash_sleeve_id": str(cash_to),
        "positions": [
            {"symbol": "AAPL", "qty": "10", "cost_basis": "3000"},
            {"symbol": "MSFT", "qty": "5", "cost_basis": "2000"},
        ],
        "cash": "2000",
    }
    postings = build_postings(LedgerEventType.SLEEVE_CLOSED, data)
    assert_balanced(postings)  # must net to zero dollars
    # Source is debited each position + cash; targets credited symmetrically.
    src_position = [p for p in postings if p.sleeve_id == str(frm) and p.bucket is Bucket.POSITION]
    assert {p.symbol: p.qty for p in src_position} == {
        "AAPL": Decimal("-10"),
        "MSFT": Decimal("-5"),
    }
    cash_legs = [p for p in postings if p.bucket is Bucket.CASH]
    assert sum(p.amount for p in cash_legs) == ZERO


def test_sleeve_closed_postings_empty_is_noop() -> None:
    data: dict[str, object] = {
        "sleeve_id": str(uuid4()),
        "to_position_sleeve_id": str(uuid4()),
        "to_cash_sleeve_id": str(uuid4()),
        "positions": [],
        "cash": "0",
    }
    assert build_postings(LedgerEventType.SLEEVE_CLOSED, data) == []


def test_close_event_id_stable() -> None:
    sid = uuid4()
    assert close_event_id(sid) == close_event_id(sid)
