"""Unit tests for the portfolio ledger kernel — pure, no IO.

Covers the conservation invariant (double-entry postings), projection folding
(cash / positions / realized P&L / aggregate), holding-history provenance, and
shadow reconciliation drift classification.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import LedgerFill, LedgerReservation

from src.ledger.backfill import BrokerPosition, plan_backfill
from src.ledger.corporate import PlannedCorporateEvent, plan_split, plan_symbol_change
from src.ledger.ingestion import (
    FillQuarantineError,
    LedgerAppend,
    append_from_message,
    enrich_sell_fill,
    fill_to_append,
    needs_cost_basis,
)
from src.ledger.invariants import check_sleeve_invariants
from src.ledger.postings import (
    Bucket,
    Posting,
    UnbalancedEventError,
    assert_balanced,
    build_postings,
)
from src.ledger.projection import (
    AccountProjection,
    ReservationState,
    fold,
    fold_into,
    holding_history,
    open_lots,
)
from src.ledger.reconciliation import DriftKind, reconcile
from src.ledger.sizing import Lot, select_lots_fifo

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
            assert_balanced(build_postings(*cast(Any, ev)))

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
        with pytest.raises(UnbalancedEventError):
            assert_balanced([Posting(A, Bucket.CASH, D("10"))])

    def test_opposite_signed_position_rejected(self) -> None:
        """A position leg that adds shares while removing cost (or vice versa) is
        rejected even though the dollar total nets to zero — sign-consistency, not
        just the sum, must hold."""
        with pytest.raises(UnbalancedEventError, match="opposite-signed"):
            assert_balanced(
                [
                    Posting(A, Bucket.CASH, D("100")),
                    Posting(A, Bucket.POSITION, D("-100"), symbol="SPY", qty=D("5")),
                ]
            )


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
            LedgerFill(
                tenant_id=tid,
                account_id=aid,
                sleeve_id=sid,
                client_order_id="lt-abc123",
                symbol="SPY",
                side="BUY",
                qty="50",
                price="480",
                fees="1.00",
            )
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
                LedgerFill(
                    tenant_id=tid,
                    account_id=aid,
                    sleeve_id=sid,
                    client_order_id="lt-abc123",
                    symbol="SPY",
                    side="buy",
                    qty="50",
                    price="480",
                )
            ).event_id
        )

    def test_sell_without_cost_basis_is_valid(self) -> None:
        """cost_basis is optional on sells: the consumer computes FIFO at ingestion."""
        append = fill_to_append(
            LedgerFill(
                tenant_id="11111111-1111-1111-1111-111111111111",
                account_id="22222222-2222-2222-2222-222222222222",
                sleeve_id="33333333-3333-3333-3333-333333333333",
                client_order_id="lt-sell-1",
                symbol="SPY",
                side="sell",
                qty="50",
                price="500",
            )
        )
        assert append.event_type is LedgerEventType.ORDER_FILLED
        assert "cost_basis" not in append.data
        assert "realized_pnl" not in append.data

    def test_sell_with_cost_basis_passes_through(self) -> None:
        append = fill_to_append(
            LedgerFill(
                tenant_id="11111111-1111-1111-1111-111111111111",
                account_id="22222222-2222-2222-2222-222222222222",
                sleeve_id="33333333-3333-3333-3333-333333333333",
                client_order_id="lt-sell-2",
                symbol="SPY",
                side="sell",
                qty="50",
                price="500",
                cost_basis="24000",
                realized_pnl="1000",
            )
        )
        assert append.data["cost_basis"] == "24000"
        assert append.data["realized_pnl"] == "1000"


def _buy(sleeve: str, qty: str, price: str, symbol: str = "SPY") -> Ev:
    return Ev(
        LedgerEventType.ORDER_FILLED,
        {"sleeve_id": sleeve, "symbol": symbol, "side": "buy", "qty": qty, "price": price},
    )


def _sell(sleeve: str, qty: str, price: str, cost_basis: str, symbol: str = "SPY") -> Ev:
    return Ev(
        LedgerEventType.ORDER_FILLED,
        {
            "sleeve_id": sleeve,
            "symbol": symbol,
            "side": "sell",
            "qty": qty,
            "price": price,
            "cost_basis": cost_basis,
        },
    )


class TestOpenLots:
    def test_buys_open_lots_in_order(self) -> None:
        lots = open_lots([_buy(A, "50", "480"), _buy(A, "30", "500")], A, "SPY")
        assert [(lot.qty, lot.cost_basis) for lot in lots] == [
            (D("50"), D("24000")),
            (D("30"), D("15000")),
        ]
        assert lots[0].opened_seq < lots[1].opened_seq

    def test_sell_consumes_oldest_lot_first(self) -> None:
        lots = open_lots(
            [_buy(A, "50", "480"), _buy(A, "30", "500"), _sell(A, "60", "510", "29000")],
            A,
            "SPY",
        )
        # 50 @ 480 fully consumed, 10 of the 30 @ 500 consumed → 20 @ 500 remain.
        assert len(lots) == 1
        assert lots[0].qty == D("20")
        assert lots[0].cost_basis == D("10000")

    def test_other_sleeves_and_symbols_ignored(self) -> None:
        lots = open_lots(
            [_buy(A, "50", "480"), _buy(B, "20", "480"), _buy(A, "5", "100", symbol="QQQ")],
            A,
            "SPY",
        )
        assert len(lots) == 1
        assert lots[0].qty == D("50")

    def test_overdrawn_sell_clears_lots(self) -> None:
        lots = open_lots([_buy(A, "10", "480"), _sell(A, "25", "500", "4800")], A, "SPY")
        assert lots == []

    def test_uses_db_sequence_when_present(self) -> None:
        @dataclass
        class SeqEv(Ev):
            sequence: int = 0

        events = [
            SeqEv(
                LedgerEventType.ORDER_FILLED,
                {"sleeve_id": A, "symbol": "SPY", "side": "buy", "qty": "10", "price": "480"},
                sequence=7,
            )
        ]
        assert open_lots(events, A, "SPY")[0].opened_seq == 7


_TENANT = "11111111-1111-1111-1111-111111111111"
_ACCOUNT = "22222222-2222-2222-2222-222222222222"
# Sleeve the corporate-action tests hold positions in (planners emit UUID ids).
_SLEEVE = "33333333-3333-3333-3333-333333333333"


def _split_ev(sleeve: str, qty_delta: str, symbol: str = "SPY") -> Ev:
    return Ev(
        LedgerEventType.SPLIT_APPLIED,
        {"sleeve_id": sleeve, "symbol": symbol, "qty_delta": qty_delta},
    )


def _rename_ev(sleeve: str, old: str, new: str, qty: str, cost_basis: str) -> Ev:
    return Ev(
        LedgerEventType.SYMBOL_CHANGED,
        {
            "sleeve_id": sleeve,
            "old_symbol": old,
            "new_symbol": new,
            "qty": qty,
            "cost_basis": cost_basis,
        },
    )


def _planned(planned: PlannedCorporateEvent) -> Ev:
    """A planner's event as the fold sees it."""
    return Ev(planned.event_type, dict(planned.data))


def _sell_fill(symbol: str, qty: str, price: str) -> LedgerAppend:
    return fill_to_append(
        LedgerFill(
            tenant_id=_TENANT,
            account_id=_ACCOUNT,
            sleeve_id=_SLEEVE,
            client_order_id=f"lt-{symbol}-{qty}",
            symbol=symbol,
            side="sell",
            qty=qty,
            price=price,
        )
    )


class TestSplitLots:
    """A split re-bases the lots it finds; it never opens a zero-cost lot."""

    def _two_lots(self) -> list[Ev]:
        """100 shares at $10 then 50 at $20: 150 shares carrying $2,000 of cost."""
        return [_buy(_SLEEVE, "100", "10"), _buy(_SLEEVE, "50", "20")]

    def test_forward_split_scales_qty_and_keeps_each_lot_cost(self) -> None:
        lots = open_lots([*self._two_lots(), _split_ev(_SLEEVE, "150")], _SLEEVE, "SPY")
        assert [(lot.qty, lot.cost_basis) for lot in lots] == [
            (D("200"), D("1000")),
            (D("100"), D("1000")),
        ]
        # Per-unit cost is divided by the ratio: $10 -> $5 and $20 -> $10.
        assert [lot.cost_basis / lot.qty for lot in lots] == [D("5"), D("10")]

    def test_total_lot_cost_is_unchanged_by_the_split(self) -> None:
        before = open_lots(self._two_lots(), _SLEEVE, "SPY")
        after = open_lots([*self._two_lots(), _split_ev(_SLEEVE, "150")], _SLEEVE, "SPY")
        assert sum((lot.cost_basis for lot in after), D("0")) == D("2000")
        assert sum((lot.cost_basis for lot in after), D("0")) == sum(
            (lot.cost_basis for lot in before), D("0")
        )

    def test_lots_reconcile_with_the_folded_position(self) -> None:
        events = [*self._two_lots(), _split_ev(_SLEEVE, "150")]
        pos = fold(events).sleeve(_SLEEVE).positions["SPY"]
        lots = open_lots(events, _SLEEVE, "SPY")
        assert sum((lot.qty for lot in lots), D("0")) == pos.qty == D("300")
        assert sum((lot.cost_basis for lot in lots), D("0")) == pos.cost_basis == D("2000")

    def test_sell_after_a_split_realizes_the_rebased_basis(self) -> None:
        lots = open_lots([*self._two_lots(), _split_ev(_SLEEVE, "150")], _SLEEVE, "SPY")
        enriched = enrich_sell_fill(_sell_fill("SPY", "250", "8"), lots)
        # 200 shares from the $5 lot ($1,000) + 50 from the $10 lot ($500).
        assert enriched.data["cost_basis"] == "1500"
        assert enriched.data["realized_pnl"] == "500"  # 250 x $8 - $1,500
        assert_balanced(build_postings(enriched.event_type, enriched.data))

    def test_split_preserves_fifo_order(self) -> None:
        events = [_buy(_SLEEVE, "10", "1"), _buy(_SLEEVE, "10", "3"), _split_ev(_SLEEVE, "20")]
        lots = open_lots(events, _SLEEVE, "SPY")
        assert [lot.opened_seq for lot in lots] == [0, 1]
        enriched = enrich_sell_fill(_sell_fill("SPY", "20", "5"), lots)
        # The oldest lot (20 shares at $0.50) is consumed whole, not blended.
        assert enriched.data["cost_basis"] == "10"
        remaining = select_lots_fifo(lots, D("20")).remaining_lots
        assert [(lot.qty, lot.cost_basis) for lot in remaining] == [(D("20"), D("30"))]

    def test_reverse_split_keeps_fractional_quantities(self) -> None:
        planned = plan_split(
            symbol="SPY", ratio=D("0.1"), holders={UUID(_SLEEVE): D("25")}, external_id="ca-rev"
        )[0]
        lots = open_lots([_buy(_SLEEVE, "25", "40"), _planned(planned)], _SLEEVE, "SPY")
        assert [(lot.qty, lot.cost_basis) for lot in lots] == [(D("2.5"), D("1000"))]
        assert lots[0].cost_basis / lots[0].qty == D("400")

    def test_uneven_split_conserves_qty_and_cost_across_lots(self) -> None:
        planned = plan_split(
            symbol="SPY", ratio=D("1.5"), holders={UUID(_SLEEVE): D("31")}, external_id="ca-uneven"
        )[0]
        events = [
            _buy(_SLEEVE, "7", "10"),
            _buy(_SLEEVE, "11", "20"),
            _buy(_SLEEVE, "13", "30"),
            _planned(planned),
        ]
        lots = open_lots(events, _SLEEVE, "SPY")
        pos = fold(events).sleeve(_SLEEVE).positions["SPY"]
        assert [lot.qty for lot in lots] == [D("10.5"), D("16.5"), D("19.5")]
        assert sum((lot.qty for lot in lots), D("0")) == pos.qty == D("46.5")
        assert sum((lot.cost_basis for lot in lots), D("0")) == pos.cost_basis == D("680")

    def test_split_without_tracked_lots_opens_no_zero_cost_lot(self) -> None:
        assert open_lots([_split_ev(_SLEEVE, "40")], _SLEEVE, "SPY") == []

    def test_split_of_another_sleeve_leaves_these_lots_alone(self) -> None:
        events = [_buy(_SLEEVE, "10", "10"), _split_ev(A, "10")]
        assert [(lot.qty, lot.cost_basis) for lot in open_lots(events, _SLEEVE, "SPY")] == [
            (D("10"), D("100"))
        ]

    def test_sleeve_invariants_stay_green_across_a_split(self) -> None:
        events = [
            Ev(LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": _SLEEVE, "amount": "5000"}),
            *self._two_lots(),
            _split_ev(_SLEEVE, "150"),
        ]
        assert check_sleeve_invariants(fold(events).sleeve(_SLEEVE)) == []


class TestSymbolChangeLots:
    """A rename carries every lot across with its own basis and acquisition order."""

    def _renamed(self) -> list[Ev]:
        """10 FB at $200 and 5 at $100, then FB renamed to META."""
        rename = plan_symbol_change(
            old_symbol="FB",
            new_symbol="META",
            holders={UUID(_SLEEVE): (D("15"), D("2500"))},
            external_id="ca-rename",
        )[0]
        return [
            _buy(_SLEEVE, "10", "200", symbol="FB"),
            _buy(_SLEEVE, "5", "100", symbol="FB"),
            _planned(rename),
        ]

    def test_each_lot_keeps_its_own_basis_and_order(self) -> None:
        lots = open_lots(self._renamed(), _SLEEVE, "META")
        assert [(lot.qty, lot.cost_basis) for lot in lots] == [
            (D("10"), D("2000")),
            (D("5"), D("500")),
        ]
        assert [lot.opened_seq for lot in lots] == [0, 1]

    def test_the_old_symbol_keeps_no_lots(self) -> None:
        assert open_lots(self._renamed(), _SLEEVE, "FB") == []

    def test_total_cost_and_qty_are_conserved_by_the_rename(self) -> None:
        events = self._renamed()
        lots = open_lots(events, _SLEEVE, "META")
        pos = fold(events).sleeve(_SLEEVE).positions["META"]
        assert sum((lot.cost_basis for lot in lots), D("0")) == pos.cost_basis == D("2500")
        assert sum((lot.qty for lot in lots), D("0")) == pos.qty == D("15")

    def test_sell_after_a_rename_realizes_the_oldest_lot(self) -> None:
        enriched = enrich_sell_fill(
            _sell_fill("META", "10", "250"), open_lots(self._renamed(), _SLEEVE, "META")
        )
        # The $200 lot, not a 15-share blend of $166.66... per share.
        assert enriched.data["cost_basis"] == "2000"
        assert enriched.data["realized_pnl"] == "500"

    def test_chained_renames_keep_the_lots(self) -> None:
        events = [*self._renamed(), _rename_ev(_SLEEVE, "META", "MTA", "15", "2500")]
        assert [(lot.qty, lot.cost_basis) for lot in open_lots(events, _SLEEVE, "MTA")] == [
            (D("10"), D("2000")),
            (D("5"), D("500")),
        ]

    def test_rename_without_tracked_lots_falls_back_to_the_payload(self) -> None:
        rename = _rename_ev(_SLEEVE, "FB", "META", "15", "2500")
        assert [(lot.qty, lot.cost_basis) for lot in open_lots([rename], _SLEEVE, "META")] == [
            (D("15"), D("2500"))
        ]

    def test_rename_of_another_sleeve_is_ignored(self) -> None:
        events = [
            _buy(_SLEEVE, "10", "200", symbol="FB"),
            _rename_ev(A, "FB", "META", "10", "2000"),
        ]
        assert [(lot.qty, lot.cost_basis) for lot in open_lots(events, _SLEEVE, "FB")] == [
            (D("10"), D("2000"))
        ]

    def test_split_after_a_rename_rebases_the_carried_lots(self) -> None:
        events = [*self._renamed(), _split_ev(_SLEEVE, "15", symbol="META")]
        assert [(lot.qty, lot.cost_basis) for lot in open_lots(events, _SLEEVE, "META")] == [
            (D("20"), D("2000")),
            (D("10"), D("500")),
        ]


def test_corporate_action_replay_is_deterministic() -> None:
    """Lots and balances are identical however often (or from where) they refold."""
    events = [
        Ev(LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": _SLEEVE, "amount": "10000"}),
        _buy(_SLEEVE, "100", "10"),
        _buy(_SLEEVE, "50", "20"),
        _split_ev(_SLEEVE, "150"),
        _rename_ev(_SLEEVE, "SPY", "SPYX", "300", "2000"),
    ]
    assert open_lots(events, _SLEEVE, "SPYX") == open_lots(events, _SLEEVE, "SPYX")

    full = fold(events)
    assert full == fold(events)
    for k in range(len(events) + 1):
        base = AccountProjection()
        reservations = ReservationState()
        fold_into(base, reservations, events[:k])
        fold_into(base, reservations, events[k:])
        assert base == full, f"checkpoint at index {k} diverged from the full fold"


class TestSellEnrichment:
    def _sell_append(self, qty: str = "60", **extra: str):
        fields = {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "account_id": "22222222-2222-2222-2222-222222222222",
            "sleeve_id": "33333333-3333-3333-3333-333333333333",
            "client_order_id": "lt-sell-enrich",
            "symbol": "SPY",
            "side": "sell",
            "qty": qty,
            "price": "510",
        }
        fields.update(extra)
        return fill_to_append(LedgerFill(**fields))

    def test_needs_cost_basis_predicate(self) -> None:
        assert needs_cost_basis(self._sell_append()) is True
        assert needs_cost_basis(self._sell_append(cost_basis="100")) is False

    def test_enrich_computes_fifo_cost_and_realized_pnl(self) -> None:
        lots = [
            Lot(qty=D("50"), cost_basis=D("24000"), opened_seq=1),
            Lot(qty=D("30"), cost_basis=D("15000"), opened_seq=2),
        ]
        enriched = enrich_sell_fill(self._sell_append("60"), lots)
        # 50 @ 480 + 10 @ 500 = 29000 closed cost; 60*510 - 29000 = 1600 realized.
        assert enriched.data["cost_basis"] == "29000"
        assert enriched.data["realized_pnl"] == "1600"
        # The enriched event balances and folds with the right P&L.
        assert_balanced(build_postings(enriched.event_type, enriched.data))

    def test_enrich_subtracts_fees_from_realized(self) -> None:
        lots = [Lot(qty=D("60"), cost_basis=D("28800"), opened_seq=1)]
        enriched = enrich_sell_fill(self._sell_append("60", fees="10"), lots)
        assert enriched.data["realized_pnl"] == "1790"  # 30600 - 28800 - 10

    def test_existing_cost_basis_untouched(self) -> None:
        append = self._sell_append(cost_basis="25000")
        assert enrich_sell_fill(append, []) is append

    def test_insufficient_lots_quarantines_sell(self) -> None:
        """A sell the open lots can't cover is quarantined (fail-closed), not
        silently recorded with a fabricated cost basis."""
        lots = [Lot(qty=D("10"), cost_basis=D("4800"), opened_seq=1)]
        with pytest.raises(FillQuarantineError):
            enrich_sell_fill(self._sell_append("60"), lots)

    def test_build_postings_rejects_sell_without_cost_basis(self) -> None:
        """The writer/fold path refuses a basis-less sell rather than defaulting
        cost to notional (which would fabricate zero realized P&L)."""
        data = {"sleeve_id": A, "symbol": "SPY", "side": "sell", "qty": "50", "price": "500"}
        with pytest.raises(ValueError, match="cost_basis"):
            build_postings(LedgerEventType.ORDER_FILLED, cast(Any, data))


class TestReservationProjection:
    """§4 cash-reservation lifecycle folded into sleeve projections."""

    def _submitted(self, coid: str = "lt-r1", reserved: str = "24000") -> Ev:
        return Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": A, "client_order_id": coid, "reserved": reserved},
        )

    def test_submitted_reserves_cash(self) -> None:
        acc = fold([*_scenario(), self._submitted()])
        assert acc.sleeve(A).reserved == D("24000")

    def test_cancel_releases_reservation(self) -> None:
        cancel = Ev(LedgerEventType.ORDER_CANCELLED, {"sleeve_id": A, "client_order_id": "lt-r1"})
        acc = fold([*_scenario(), self._submitted(), cancel])
        assert acc.sleeve(A).reserved == D("0")

    def test_fill_consumes_reservation(self) -> None:
        fill = Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": A,
                "symbol": "SPY",
                "side": "buy",
                "qty": "50",
                "price": "480",
                "client_order_id": "lt-r1",
            },
        )
        acc = fold([*_scenario(), self._submitted(), fill])
        assert acc.sleeve(A).reserved == D("0")
        # The fill itself still moves cash (conservation untouched by reservations)
        assert acc.sleeve(A).positions["SPY"].qty == D("90")  # scenario 50 − 10, then +50

    def test_release_without_reservation_is_noop(self) -> None:
        reject = Ev(LedgerEventType.ORDER_REJECTED, {"sleeve_id": A, "client_order_id": "ghost"})
        acc = fold([*_scenario(), reject])
        assert acc.sleeve(A).reserved == D("0")

    def test_reservations_are_per_sleeve(self) -> None:
        other = Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": B, "client_order_id": "lt-r2", "reserved": "1000"},
        )
        acc = fold([*_scenario(), self._submitted(), other])
        assert acc.sleeve(A).reserved == D("24000")
        assert acc.sleeve(B).reserved == D("1000")


class TestLateReservation:
    """An ORDER_SUBMITTED reservation racing its own terminal event."""

    def _submitted(self, coid: str = "lt-r1") -> Ev:
        return Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": A, "client_order_id": coid, "reserved": "24000"},
        )

    def _fill(self, coid: str = "lt-r1") -> Ev:
        return Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": A,
                "symbol": "SPY",
                "side": "buy",
                "qty": "50",
                "price": "480",
                "client_order_id": coid,
            },
        )

    def test_submit_then_fill_leaves_reserved_zero(self) -> None:
        acc = fold([*_scenario(), self._submitted(), self._fill()])
        assert acc.sleeve(A).reserved == D("0")

    def test_late_submit_after_fill_is_noop_and_matches_submit_first(self) -> None:
        ordered = fold([*_scenario(), self._submitted(), self._fill()])
        late = fold([*_scenario(), self._fill(), self._submitted()])
        assert late.sleeve(A).reserved == D("0")
        assert late == ordered

    def test_late_submit_after_cancel_is_noop(self) -> None:
        cancel = Ev(LedgerEventType.ORDER_CANCELLED, {"sleeve_id": A, "client_order_id": "lt-r1"})
        acc = fold([*_scenario(), cancel, self._submitted()])
        assert acc.sleeve(A).reserved == D("0")

    def test_late_submit_after_reject_is_noop(self) -> None:
        reject = Ev(LedgerEventType.ORDER_REJECTED, {"sleeve_id": A, "client_order_id": "lt-r1"})
        acc = fold([*_scenario(), reject, self._submitted()])
        assert acc.sleeve(A).reserved == D("0")

    def test_unseen_order_reservation_still_earmarks(self) -> None:
        acc = fold([*_scenario(), self._fill(coid="lt-other"), self._submitted(coid="lt-new")])
        assert acc.sleeve(A).reserved == D("24000")


class TestPayloadRouting:
    def _message(self, **overrides: str):
        base = {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "account_id": "22222222-2222-2222-2222-222222222222",
            "sleeve_id": "33333333-3333-3333-3333-333333333333",
            "client_order_id": "lt-route-1",
            "symbol": "SPY",
            "side": "buy",
        }
        event_type = overrides.pop("event_type", None)
        if event_type is not None:
            return LedgerReservation(event_type=event_type, **base, **overrides)
        return LedgerFill(qty="50", price="480", **base, **overrides)

    def test_default_routes_to_fill(self) -> None:
        append = append_from_message(self._message())
        assert append.event_type is LedgerEventType.ORDER_FILLED

    def test_reservation_stages_route_and_have_distinct_event_ids(self) -> None:
        submitted = append_from_message(
            self._message(event_type="order_submitted", reserved="24000")
        )
        cancelled = append_from_message(self._message(event_type="order_cancelled"))
        filled = append_from_message(self._message())

        assert submitted.event_type is LedgerEventType.ORDER_SUBMITTED
        assert submitted.data["reserved"] == "24000"
        assert submitted.data["client_order_id"] == "lt-route-1"
        assert cancelled.event_type is LedgerEventType.ORDER_CANCELLED
        # Each lifecycle stage is independently idempotent.
        assert len({submitted.event_id, cancelled.event_id, filled.event_id}) == 3

    def test_lifecycle_events_carry_no_postings_yet(self) -> None:
        submitted = append_from_message(self._message(event_type="order_submitted"))
        assert build_postings(submitted.event_type, submitted.data) == []

    def test_unknown_event_type_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown ledger reservation event_type"):
            append_from_message(self._message(event_type="order_teleported"))


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


def test_fold_split_invariance() -> None:
    """fold(checkpoint at any split) + delta == fold from zero.

    This is the invariant the incremental projection (LedgerProjector.
    project_account_incremental) relies on: resuming a fold from a checkpoint
    plus the delta must be IDENTICAL to a full replay — across every posting
    type, the reservation lifecycle spanning the split, AND a poison event.
    """
    s, u = "strat-x", "unalloc"
    events = [
        Ev(LedgerEventType.FUNDS_DEPOSITED, {"sleeve_id": u, "amount": "100000"}),
        Ev(
            LedgerEventType.CAPITAL_ALLOCATED,
            {"from_sleeve_id": u, "to_sleeve_id": s, "amount": "40000"},
        ),
        Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": s, "client_order_id": "o1", "reserved": "5000"},
        ),
        Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": s,
                "client_order_id": "o1",
                "symbol": "SPY",
                "side": "buy",
                "qty": "50",
                "price": "100",
            },
        ),
        Ev(LedgerEventType.DIVIDEND_RECEIVED, {"sleeve_id": s, "amount": "120"}),
        Ev(LedgerEventType.FEE_CHARGED, {"sleeve_id": s, "amount": "3"}),
        Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": s,
                "symbol": "SPY",
                "side": "sell",
                "qty": "20",
                "price": "110",
                "cost_basis": "2000",
            },
        ),
        Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": s, "client_order_id": "o2", "reserved": "1000"},
        ),
        Ev(LedgerEventType.ORDER_CANCELLED, {"sleeve_id": s, "client_order_id": "o2"}),
        Ev(LedgerEventType.SPLIT_APPLIED, {"sleeve_id": s, "symbol": "SPY", "qty_delta": "30"}),
        Ev(
            LedgerEventType.ORDER_FILLED, {"sleeve_id": s, "symbol": "SPY"}
        ),  # poison: missing side/qty/price
        Ev(
            LedgerEventType.SYMBOL_CHANGED,
            {
                "sleeve_id": s,
                "old_symbol": "SPY",
                "new_symbol": "SPYX",
                "qty": "60",
                "cost_basis": "3000",
            },
        ),
        # Late reservation: the fill for o3 lands BEFORE its submission, so
        # the reservation must fold as a no-op — including across any split.
        Ev(
            LedgerEventType.ORDER_FILLED,
            {
                "sleeve_id": s,
                "client_order_id": "o3",
                "symbol": "SPYX",
                "side": "buy",
                "qty": "1",
                "price": "50",
            },
        ),
        Ev(
            LedgerEventType.ORDER_SUBMITTED,
            {"sleeve_id": s, "client_order_id": "o3", "reserved": "50"},
        ),
    ]
    full = fold(events)
    # The projection reports its own incompleteness (read-path signal): the
    # ORDER_FILLED with no side/qty/price was skipped as poison.
    assert full.poison_events == 1
    assert not full.is_complete
    assert full.sleeves[s].reserved == Decimal("0")  # late o3 reservation was a no-op
    for k in range(len(events) + 1):
        base = AccountProjection()
        reservations = ReservationState()
        fold_into(base, reservations, events[:k], on_error=None)
        fold_into(base, reservations, events[k:], on_error=None)
        assert base == full, f"checkpoint split at index {k} diverged from full fold"
