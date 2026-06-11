"""Unit tests for the portfolio ledger kernel (Phase 1) — pure, no IO.

Covers the conservation invariant (double-entry postings), projection folding
(cash / positions / realized P&L / aggregate), holding-history provenance, and
shadow reconciliation drift classification.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.backfill import BrokerPosition, plan_backfill
from src.ledger.ingestion import fill_to_append
from src.ledger.postings import (
    Bucket,
    UnbalancedEventError,
    assert_balanced,
    build_postings,
)
from src.ledger.projection import fold, holding_history
from src.ledger.reconciliation import DriftKind, reconcile

# Sleeve ids used across the scenario
U = "unallocated"
A = "strat-a"
B = "strat-b"
D = Decimal


@dataclass
class Ev:
    """Minimal event view for folding (mirrors a LedgerEvent row)."""

    event_type: LedgerEventType
    data: dict[str, Any]
    occurred_at: Any | None = None


def _scenario() -> list[Ev]:
    """Deposit 100k → allocate 40k each to A & B → trades incl. a realized gain."""
    return [
        Ev(LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": U, "amount": "100000"}),
        Ev(
            LedgerEventType.CAPITAL_ALLOCATED,
            {"from_sleeve_id": U, "to_sleeve_id": A, "amount": "40000"},
        ),
        Ev(
            LedgerEventType.CAPITAL_ALLOCATED,
            {"from_sleeve_id": U, "to_sleeve_id": B, "amount": "40000"},
        ),
        Ev(
            LedgerEventType.ORDER_FILLED,
            {"sleeve_id": A, "symbol": "SPY", "side": "buy", "qty": "50", "price": "480"},
        ),
        Ev(
            LedgerEventType.ORDER_FILLED,
            {"sleeve_id": B, "symbol": "SPY", "side": "buy", "qty": "20", "price": "480"},
        ),
        Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": A,
                "symbol": "SPY",
                "side": "sell",
                "qty": "10",
                "price": "500",
                "cost_basis": "4800",
                "realized_pnl": "200",
            },
        ),
    ]


class TestPostingsConservation:
    def test_buy_balances(self) -> None:
        p = build_postings(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": A,
                "symbol": "SPY",
                "side": "buy",
                "qty": "50",
                "price": "480",
                "fees": "5",
            },
        )
        assert_balanced(p)  # raises if not zero-sum

    def test_sell_balances_with_realized_gain(self) -> None:
        p = build_postings(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": A,
                "symbol": "SPY",
                "side": "sell",
                "qty": "10",
                "price": "500",
                "cost_basis": "4800",
            },
        )
        assert_balanced(p)

    def test_allocate_deposit_withdraw_dividend_fee_balance(self) -> None:
        for ev in (
            (
                LedgerEventType.CAPITAL_ALLOCATED,
                {"from_sleeve_id": U, "to_sleeve_id": A, "amount": "100"},
            ),
            (LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": U, "amount": "100"}),
            (LedgerEventType.FUNDS_WITHDRAWN, {"sleeve_id": U, "amount": "100"}),
            (LedgerEventType.DIVIDEND_RECEIVED, {"sleeve_id": A, "amount": "12"}),
            (LedgerEventType.FEE_CHARGED, {"sleeve_id": A, "amount": "3"}),
        ):
            assert_balanced(build_postings(*ev))

    def test_unknown_side_raises(self) -> None:
        with pytest.raises(ValueError):
            build_postings(
                LedgerEventType.ORDER_FILLED,
                {"sleeve_id": A, "symbol": "SPY", "side": "hodl", "qty": "1", "price": "1"},
            )

    def test_lifecycle_events_have_no_postings(self) -> None:
        assert build_postings(LedgerEventType.SLEEVE_OPENED, {}) == []
        assert build_postings(LedgerEventType.ORDER_SUBMITTED, {}) == []

    def test_unbalanced_detected(self) -> None:
        from src.ledger.postings import Posting

        with pytest.raises(UnbalancedEventError):
            assert_balanced([Posting(A, Bucket.CASH, D("10"))])


class TestProjection:
    def test_fold_cash_positions_pnl(self) -> None:
        acc = fold(_scenario())
        a = acc.sleeves[A]
        b = acc.sleeves[B]
        u = acc.sleeves[U]

        # A: 40000 - 24000 (buy) + 5000 (sell) = 21000 cash; SPY 40 sh cost 19200; +200 realized
        assert a.cash == D("21000")
        assert a.positions["SPY"].qty == D("40")
        assert a.positions["SPY"].cost_basis == D("19200")
        assert a.realized_pnl == D("200")

        # B: 40000 - 9600 = 30400 cash; SPY 20 sh
        assert b.cash == D("30400")
        assert b.positions["SPY"].qty == D("20")

        # Unallocated drained by the two allocations
        assert u.cash == D("20000")

    def test_account_aggregate_positions(self) -> None:
        acc = fold(_scenario())
        # broker would show ONE SPY position = 40 (A) + 20 (B) = 60
        assert acc.account_positions() == {"SPY": D("60")}

    def test_conservation_total_equity(self) -> None:
        acc = fold(_scenario())
        cash = acc.total_cash()
        cost = sum(
            (p.cost_basis for s in acc.sleeves.values() for p in s.positions.values()),
            D("0"),
        )
        # deposited 100000 + realized gain 200 = 100200
        assert cash + cost == D("100200")


class TestHoldingHistory:
    def test_history_has_provenance_and_sides(self) -> None:
        entries = holding_history(_scenario(), "SPY")
        # 2 buys (A, B) + 1 sell (A)
        assert len(entries) == 3
        assert [e.side for e in entries] == ["buy", "buy", "sell"]
        assert {e.sleeve_id for e in entries} == {A, B}
        assert entries[2].sleeve_id == A and entries[2].qty == D("10")


class TestReconciliation:
    def test_match_no_drift(self) -> None:
        acc = fold(_scenario())
        assert reconcile(acc, {"SPY": D("60")}) == []

    def test_qty_mismatch(self) -> None:
        acc = fold(_scenario())
        drifts = reconcile(acc, {"SPY": D("61")})
        assert len(drifts) == 1 and drifts[0].kind is DriftKind.QTY_MISMATCH
        assert drifts[0].delta == D("1")

    def test_missing_in_ledger(self) -> None:
        acc = fold(_scenario())
        drifts = reconcile(acc, {"SPY": D("60"), "QQQ": D("5")})
        kinds = {d.symbol: d.kind for d in drifts}
        assert kinds == {"QQQ": DriftKind.MISSING_IN_LEDGER}

    def test_missing_at_broker(self) -> None:
        acc = fold(_scenario())
        drifts = reconcile(acc, {})
        assert len(drifts) == 1 and drifts[0].kind is DriftKind.MISSING_AT_BROKER

    def test_dust_within_tolerance(self) -> None:
        acc = fold(_scenario())
        drifts = reconcile(acc, {"SPY": D("60.00005")})
        assert len(drifts) == 1 and drifts[0].kind is DriftKind.DUST


class TestFillIngestion:
    def test_fill_translates_to_order_filled_append(self) -> None:
        from uuid import UUID

        tid = "11111111-1111-1111-1111-111111111111"
        aid = "22222222-2222-2222-2222-222222222222"
        sid = "33333333-3333-3333-3333-333333333333"
        append = fill_to_append(
            {
                "tenant_id": tid,
                "account_id": aid,
                "sleeve_id": sid,
                "client_order_id": "lt-abc123",
                "symbol": "SPY",
                "side": "BUY",
                "qty": "50",
                "price": "480",
                "fees": "1.00",
            }
        )
        assert append.event_type is LedgerEventType.ORDER_FILLED
        assert append.tenant_id == UUID(tid)
        assert append.sleeve_id == UUID(sid)
        assert append.data["side"] == "buy"  # normalized
        assert append.data["fees"] == "1.00"
        # event_id is deterministic in the client_order_id (idempotency)
        assert (
            append.event_id
            == fill_to_append(
                {
                    "tenant_id": tid,
                    "account_id": aid,
                    "sleeve_id": sid,
                    "client_order_id": "lt-abc123",
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": "50",
                    "price": "480",
                }
            ).event_id
        )


class TestBackfillPlanner:
    def test_plans_cash_deposit_and_unmanaged_positions(self) -> None:
        from uuid import uuid4

        unalloc, unmanaged = uuid4(), uuid4()
        planned = plan_backfill(
            broker_cash=D("10000"),
            broker_positions=[
                BrokerPosition("AAPL", D("50"), D("185")),
                BrokerPosition("GLD", D("0"), D("190")),  # skipped (zero qty)
            ],
            unallocated_sleeve_id=unalloc,
            unmanaged_sleeve_id=unmanaged,
        )
        assert [p.event_type for p in planned] == [
            LedgerEventType.FUNDS_DEPOSITED,
            LedgerEventType.EXTERNAL_TRADE_DETECTED,
        ]
        assert planned[0].sleeve_id == unalloc
        assert planned[1].sleeve_id == unmanaged
        assert planned[1].data["symbol"] == "AAPL"
        assert {p.dedup_key for p in planned} == {"backfill:cash", "backfill:pos:AAPL"}

    def test_no_cash_event_when_zero(self) -> None:
        from uuid import uuid4

        planned = plan_backfill(
            broker_cash=D("0"),
            broker_positions=[],
            unallocated_sleeve_id=uuid4(),
            unmanaged_sleeve_id=uuid4(),
        )
        assert planned == []
