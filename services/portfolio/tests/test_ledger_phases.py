"""Unit tests for the ledger non-postings kernel cores — pure, no IO.

Covers fund disbursement (allocate/transfer/withdraw + raise-cash + admission),
sleeve-aware sizing (drift bands, free-cash fit, FIFO lots), desired-state
rebalancing, block-and-allocate netting, and per-sleeve P&L.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.desired_state import SleeveDesired, plan_rebalance
from src.ledger.funds import (
    FundError,
    check_admission,
    plan_allocate,
    plan_transfer,
    plan_withdraw,
)
from src.ledger.netting import net_orders
from src.ledger.performance import account_pnl, sleeve_pnl
from src.ledger.projection import AccountProjection, PositionState, SleeveProjection
from src.ledger.sizing import (
    IntendedOrder,
    Lot,
    fit_to_free_cash,
    select_lots_fifo,
    sleeve_equity,
    target_orders,
)

D = Decimal


class TestFunds:
    def test_allocate_ok_and_insufficient(self) -> None:
        a, b = uuid4(), uuid4()
        ev = plan_allocate(
            from_sleeve_id=a, to_sleeve_id=b, amount=D("40000"), from_free_cash=D("100000")
        )
        assert ev[0].event_type is LedgerEventType.CAPITAL_ALLOCATED
        with pytest.raises(FundError):
            plan_allocate(
                from_sleeve_id=a, to_sleeve_id=b, amount=D("40000"), from_free_cash=D("100")
            )

    def test_withdraw_insufficient(self) -> None:
        with pytest.raises(FundError):
            plan_withdraw(sleeve_id=uuid4(), amount=D("10"), free_cash=D("5"))

    def test_transfer_liquid_no_raise(self) -> None:
        plan = plan_transfer(
            from_sleeve_id=uuid4(), to_sleeve_id=uuid4(), amount=D("100"), from_free_cash=D("500")
        )
        assert not plan.needs_raise_cash

    def test_transfer_raises_cash_by_selling(self) -> None:
        plan = plan_transfer(
            from_sleeve_id=uuid4(),
            to_sleeve_id=uuid4(),
            amount=D("10000"),
            from_free_cash=D("0"),
            from_positions={"SPY": (D("50"), D("480"))},  # $24,000 available
        )
        assert plan.needs_raise_cash
        assert plan.raise_cash[0].symbol == "SPY"
        # only enough to cover the shortfall (10000 / 480)
        assert plan.raise_cash[0].qty * D("480") >= D("10000")

    def test_transfer_impossible_raises(self) -> None:
        with pytest.raises(FundError):
            plan_transfer(
                from_sleeve_id=uuid4(),
                to_sleeve_id=uuid4(),
                amount=D("10000"),
                from_free_cash=D("0"),
                from_positions={"SPY": (D("1"), D("480"))},  # only $480
            )

    def test_admission_checks(self) -> None:
        # infeasible: 2% of $10 = $0.20 < $1 min notional; and over budget
        v = check_admission(
            requested=D("100000"),
            unallocated_free=D("50000"),
            target_weights={"BRKA": D("2")},
            min_notional=D("1"),
        )
        assert any("insufficient" in x for x in v)


class TestSizing:
    def test_sleeve_equity(self) -> None:
        eq = sleeve_equity(D("1000"), {"SPY": D("10")}, {"SPY": D("480")})
        assert eq == D("5800")

    def test_target_orders_initial_buy(self) -> None:
        orders = target_orders(
            sleeve_id="A",
            equity=D("40000"),
            target_weights={"SPY": D("60"), "BND": D("40")},
            current_positions={},
            prices={"SPY": D("480"), "BND": D("75")},
        )
        sides = {o.symbol: o.side for o in orders}
        assert sides == {"SPY": "buy", "BND": "buy"}

    def test_target_orders_full_exit(self) -> None:
        orders = target_orders(
            sleeve_id="A",
            equity=D("40000"),
            target_weights={"BND": D("100")},
            current_positions={"SPY": D("50"), "BND": D("0")},
            prices={"SPY": D("480"), "BND": D("75")},
        )
        spy = [o for o in orders if o.symbol == "SPY"][0]
        assert spy.side == "sell" and spy.qty == D("50")

    def test_drift_band_skips_small_moves(self) -> None:
        # target 60% of 40k = 24k = 50 sh @480; already hold 50 → no trade
        orders = target_orders(
            sleeve_id="A",
            equity=D("40000"),
            target_weights={"SPY": D("60")},
            current_positions={"SPY": D("50")},
            prices={"SPY": D("480")},
        )
        assert orders == []

    def test_fit_to_free_cash_scales_buy(self) -> None:
        o = IntendedOrder("A", "SPY", "buy", D("100"), D("480"))  # needs 48,000
        fitted = fit_to_free_cash(o, D("24000"))
        assert fitted is not None and fitted.qty == D("50")
        assert fit_to_free_cash(o, D("0")) is None

    def test_select_lots_fifo(self) -> None:
        lots = [Lot(D("10"), D("4800"), 1), Lot(D("10"), D("5000"), 2)]
        res = select_lots_fifo(lots, D("15"))
        # consumes lot1 fully (4800) + half of lot2 (2500) = 7300
        assert res.closed_cost_basis == D("7300")
        assert res.remaining_lots[0].qty == D("5")
        with pytest.raises(ValueError):
            select_lots_fifo(lots, D("999"))


class TestDesiredState:
    def test_plan_orders_sells_before_buys_and_fits_cash(self) -> None:
        desired = [
            SleeveDesired(
                sleeve_id="A",
                equity=D("40000"),
                target_weights={"SPY": D("50"), "BND": D("50")},
                current_positions={"QQQ": D("100")},  # not targeted → exit
                free_cash=D("20000"),
            )
        ]
        plan = plan_rebalance(desired, {"SPY": D("400"), "BND": D("80"), "QQQ": D("300")})
        a = plan["A"]
        # first order is the QQQ exit (sell), buys follow
        assert a[0].symbol == "QQQ" and a[0].side == "sell"
        assert all(o.side == "buy" for o in a[1:])


class TestNetting:
    def test_offsetting_orders_cross_internally(self) -> None:
        orders = [
            IntendedOrder("A", "SPY", "buy", D("5"), D("480")),
            IntendedOrder("B", "SPY", "sell", D("50"), D("480")),
        ]
        res = net_orders(orders)
        # net = +5 - 50 = -45 → one SELL 45 to the broker
        assert len(res.broker_orders) == 1
        assert res.broker_orders[0].side == "sell" and res.broker_orders[0].qty == D("45")
        # both sleeves still get their allocation
        assert len(res.allocations) == 2

    def test_full_cross_no_broker_order(self) -> None:
        orders = [
            IntendedOrder("A", "SPY", "buy", D("10"), D("480")),
            IntendedOrder("B", "SPY", "sell", D("10"), D("480")),
        ]
        res = net_orders(orders)
        assert res.broker_orders == []  # fully internalized
        assert len(res.allocations) == 2


class TestPerformance:
    def test_sleeve_pnl_marks_to_market(self) -> None:
        sleeve = SleeveProjection(
            cash=D("21000"),
            realized_pnl=D("200"),
            positions={"SPY": PositionState(qty=D("40"), cost_basis=D("19200"))},
        )
        pnl = sleeve_pnl("A", sleeve, {"SPY": D("500")})
        assert pnl.positions_value == D("20000")
        assert pnl.unrealized_pnl == D("800")  # 20000 - 19200
        assert pnl.equity == D("41000")  # 21000 + 20000
        assert pnl.realized_pnl == D("200")

    def test_account_pnl_marks_every_sleeve_ordered_by_id(self) -> None:
        acc = AccountProjection(
            sleeves={
                "B": SleeveProjection(cash=D("1000")),
                "A": SleeveProjection(
                    cash=D("21000"),
                    realized_pnl=D("200"),
                    positions={"SPY": PositionState(qty=D("40"), cost_basis=D("19200"))},
                ),
            }
        )
        pnls = account_pnl(acc, {"SPY": D("500")})
        assert [p.sleeve_id for p in pnls] == ["A", "B"]  # sorted by sleeve id
        assert pnls[0].equity == D("41000")  # sleeve A marked to market
        assert pnls[1].equity == D("1000")  # sleeve B, cash only
