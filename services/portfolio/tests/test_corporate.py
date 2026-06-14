"""Corporate-action kernel tests — postings fold + pure planners.

No DB/IO: planners produce events, the real projection kernel folds them, and we
assert share/cash conservation and per-sleeve provenance.
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.corporate import plan_split, plan_symbol_change, split_dividend
from src.ledger.postings import assert_balanced, build_postings
from src.ledger.projection import fold

ZERO = Decimal("0")


def _ev(event_type: LedgerEventType, data: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(event_type=event_type, data=data)


# --------------------------------------------------------------- postings


def test_split_postings_balanced_and_add_shares() -> None:
    postings = build_postings(
        LedgerEventType.SPLIT_APPLIED,
        {"sleeve_id": "s1", "symbol": "AAPL", "qty_delta": "100"},
    )
    assert_balanced(postings)  # zero-dollar leg conserves cash
    assert len(postings) == 1
    assert postings[0].qty == Decimal("100")
    assert postings[0].amount == ZERO


def test_symbol_change_postings_balanced() -> None:
    postings = build_postings(
        LedgerEventType.SYMBOL_CHANGED,
        {
            "sleeve_id": "s1",
            "old_symbol": "FB",
            "new_symbol": "META",
            "qty": "10",
            "cost_basis": "2000",
        },
    )
    assert_balanced(postings)
    assert {p.symbol for p in postings} == {"FB", "META"}


# --------------------------------------------------------------- splits (fold)


def test_plan_split_forward_doubles_qty_preserves_cost() -> None:
    sleeve = uuid4()
    # Seed a 100-share lot at $50 (cost 5000) in the sleeve.
    buy = _ev(
        LedgerEventType.ORDER_FILLED,
        {"sleeve_id": str(sleeve), "symbol": "AAPL", "side": "buy", "qty": "100", "price": "50"},
    )
    events = [buy]
    split = plan_split(symbol="AAPL", ratio=Decimal("2"), holders={sleeve: Decimal("100")})
    assert len(split) == 1
    events.append(_ev(split[0].event_type, split[0].data))

    pos = fold(events).sleeve(str(sleeve)).positions["AAPL"]
    assert pos.qty == Decimal("200")  # doubled
    assert pos.cost_basis == Decimal("5000")  # unchanged → avg price halved


def test_plan_split_reverse_halves_qty() -> None:
    sleeve = uuid4()
    events = [
        _ev(
            LedgerEventType.ORDER_FILLED,
            {"sleeve_id": str(sleeve), "symbol": "X", "side": "buy", "qty": "100", "price": "10"},
        )
    ]
    split = plan_split(symbol="X", ratio=Decimal("0.5"), holders={sleeve: Decimal("100")})
    events.append(_ev(split[0].event_type, split[0].data))
    pos = fold(events).sleeve(str(sleeve)).positions["X"]
    assert pos.qty == Decimal("50")
    assert pos.cost_basis == Decimal("1000")


def test_plan_split_skips_empty_sleeves_and_rejects_bad_ratio() -> None:
    assert plan_split(symbol="A", ratio=Decimal("2"), holders={uuid4(): ZERO}) == []
    with pytest.raises(ValueError, match="ratio must be positive"):
        plan_split(symbol="A", ratio=ZERO, holders={uuid4(): Decimal("1")})


# --------------------------------------------------------- symbol change (fold)


def test_plan_symbol_change_moves_lot() -> None:
    sleeve = uuid4()
    events = [
        _ev(
            LedgerEventType.ORDER_FILLED,
            {"sleeve_id": str(sleeve), "symbol": "FB", "side": "buy", "qty": "10", "price": "200"},
        )
    ]
    rename = plan_symbol_change(
        old_symbol="FB",
        new_symbol="META",
        holders={sleeve: (Decimal("10"), Decimal("2000"))},
    )
    events.append(_ev(rename[0].event_type, rename[0].data))
    proj = fold(events).sleeve(str(sleeve))
    assert proj.positions["FB"].qty == ZERO
    assert proj.positions["META"].qty == Decimal("10")
    assert proj.positions["META"].cost_basis == Decimal("2000")


# --------------------------------------------------------------- dividends


def test_split_dividend_pro_rata_and_conserves() -> None:
    a, b = uuid4(), uuid4()
    events = split_dividend(
        symbol="SPY",
        total_amount=Decimal("100.00"),
        holders={a: Decimal("30"), b: Decimal("70")},
        pay_id="2026Q2",
    )
    by_sleeve = {e.sleeve_id: Decimal(e.data["amount"]) for e in events}
    assert by_sleeve[a] == Decimal("30.00")
    assert by_sleeve[b] == Decimal("70.00")
    assert sum(by_sleeve.values()) == Decimal("100.00")  # exact conservation


def test_split_dividend_rounding_remainder_absorbed_by_largest() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    # 10.00 over 3 equal holders -> 3.33/3.33/3.34 (largest sink takes remainder).
    events = split_dividend(
        symbol="X",
        total_amount=Decimal("10.00"),
        holders={a: Decimal("1"), b: Decimal("1"), c: Decimal("1")},
        pay_id="p1",
    )
    amounts = sorted(Decimal(e.data["amount"]) for e in events)
    assert sum(amounts) == Decimal("10.00")  # conserved despite rounding
    assert amounts == [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")]


def test_split_dividend_no_holders_returns_empty() -> None:
    assert (
        split_dividend(symbol="X", total_amount=Decimal("5"), holders={uuid4(): ZERO}, pay_id="p")
        == []
    )
