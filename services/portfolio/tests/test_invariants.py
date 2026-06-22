"""Sleeve invariant checks — pure, no DB.

The post-fill audit freezes any sleeve these flag (negative cash / negative
position) so a fill that escaped trading's guards can't silently corrupt a
balance the per-event dollar checksum can't catch.
"""

from decimal import Decimal

from src.ledger.invariants import InvariantViolation, check_sleeve_invariants
from src.ledger.projection import PositionState, SleeveProjection

D = Decimal


def test_healthy_sleeve_has_no_violations() -> None:
    sleeve = SleeveProjection(
        cash=D("100"), positions={"SPY": PositionState(qty=D("5"), cost_basis=D("2400"))}
    )
    assert check_sleeve_invariants(sleeve) == []


def test_zero_cash_and_zero_qty_are_healthy() -> None:
    sleeve = SleeveProjection(cash=D("0"), positions={"SPY": PositionState(qty=D("0"))})
    assert check_sleeve_invariants(sleeve) == []


def test_negative_cash_is_flagged() -> None:
    violations = check_sleeve_invariants(SleeveProjection(cash=D("-0.01")))
    assert violations == [InvariantViolation("negative_cash", "cash=-0.01")]


def test_negative_position_is_flagged() -> None:
    sleeve = SleeveProjection(cash=D("0"), positions={"SPY": PositionState(qty=D("-3"))})
    violations = check_sleeve_invariants(sleeve)
    assert [v.kind for v in violations] == ["negative_position"]
    assert "SPY" in violations[0].detail


def test_both_violations_reported() -> None:
    sleeve = SleeveProjection(
        cash=D("-5"), positions={"SPY": PositionState(qty=D("-1")), "QQQ": PositionState(qty=D("2"))}
    )
    kinds = {v.kind for v in check_sleeve_invariants(sleeve)}
    assert kinds == {"negative_cash", "negative_position"}
