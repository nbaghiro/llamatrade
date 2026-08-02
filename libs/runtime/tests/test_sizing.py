"""Tests for the single sizing implementation (weights -> intended orders)."""

from llamatrade_runtime.sizing import (
    Holding,
    ShareQuantization,
    SizingMode,
    SizingState,
    affordable_quantity,
    quantize_quantity,
    size_orders,
)


def _prices(**kw: float) -> dict[str, float]:
    return dict(kw)


def test_binary_opens_when_flat():
    orders = size_orders(
        {"SPY": 100.0}, {}, _prices(SPY=100.0), equity=10_000.0, mode=SizingMode.BINARY
    )
    assert len(orders) == 1
    o = orders[0]
    assert o.symbol == "SPY" and o.side == "buy"
    assert o.quantity == 100.0  # 10000 * 100% / 100


def test_binary_closes_when_target_zero():
    orders = size_orders(
        {"SPY": 0.0},
        {"SPY": Holding("SPY", 50.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.BINARY,
    )
    assert len(orders) == 1
    assert orders[0].side == "sell" and orders[0].quantity == 50.0


def test_binary_does_not_resize():
    # Held 60 shares; target drops 100%->60%; BINARY must NOT resize.
    orders = size_orders(
        {"SPY": 60.0},
        {"SPY": Holding("SPY", 100.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.BINARY,
    )
    assert orders == []


def test_drift_resizes_on_weight_change():
    # equity 10k, held 100 @ $100 = $10k (100%); target 40% = $4k -> sell $6k = 60 shares.
    orders = size_orders(
        {"SPY": 40.0},
        {"SPY": Holding("SPY", 100.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    assert len(orders) == 1
    assert orders[0].side == "sell"
    assert abs(orders[0].quantity - 60.0) < 1e-9


def test_drift_skips_within_band():
    # held value $9.8k vs target $10k -> 2% drift, under 5% band -> no trade.
    orders = size_orders(
        {"SPY": 100.0},
        {"SPY": Holding("SPY", 98.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    assert orders == []


def test_drift_sell_clamped_to_held():
    # target 0, held 30 shares -> sell exactly 30 (never more).
    orders = size_orders(
        {"SPY": 0.0},
        {"SPY": Holding("SPY", 30.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    assert len(orders) == 1
    assert orders[0].side == "sell" and orders[0].quantity == 30.0


def test_multi_symbol_switch_sells_old_buys_new():
    # Switch from SPY (held) to TLT (target).
    orders = size_orders(
        {"TLT": 100.0, "SPY": 0.0},
        {"SPY": Holding("SPY", 100.0)},
        _prices(SPY=100.0, TLT=50.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    by_symbol = {o.symbol: o for o in orders}
    assert by_symbol["SPY"].side == "sell" and by_symbol["SPY"].quantity == 100.0
    assert by_symbol["TLT"].side == "buy" and abs(by_symbol["TLT"].quantity - 200.0) < 1e-9


def test_sells_ordered_before_buys():
    # Rotate ZZZ -> AAA: the buy (AAA) sorts before the sell (ZZZ) alphabetically, but the sell
    # must come first so its freed cash funds the buy within the same rebalance.
    orders = size_orders(
        {"AAA": 100.0, "ZZZ": 0.0},
        {"ZZZ": Holding("ZZZ", 100.0)},
        _prices(AAA=50.0, ZZZ=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    assert [o.side for o in orders] == ["sell", "buy"]
    assert orders[0].symbol == "ZZZ" and orders[1].symbol == "AAA"


def test_missing_or_nonpositive_price_skipped():
    orders = size_orders(
        {"SPY": 100.0}, {}, _prices(SPY=0.0), equity=10_000.0, mode=SizingMode.DRIFT
    )
    assert orders == []


def test_sub_notional_buy_skipped_others_proceed():
    # Equity $5k: AAA targets $4999.50, BBB targets $0.50 — under the $1 broker floor.
    state = SizingState()
    orders = size_orders(
        {"AAA": 99.99, "BBB": 0.01},
        {},
        _prices(AAA=100.0, BBB=10.0),
        equity=5_000.0,
        mode=SizingMode.DRIFT,
        state=state,
    )
    assert [o.symbol for o in orders] == ["AAA"]
    assert abs(orders[0].quantity - 49.995) < 1e-9  # untouched by the skip
    assert state.sub_notional_skips == 1


def test_sub_notional_sell_skipped_and_buys_refit_to_the_cash_that_arrives():
    # Held SPY $10,000 + a $0.50 dust position; rotate the book into TLT.
    # The dust sell is under the floor, so its $0.50 never funds the TLT buy: the buy is
    # trimmed from 200.01 to the 200.0 shares the realized $10,000 of proceeds affords.
    state = SizingState()
    orders = size_orders(
        {"TLT": 100.0, "SPY": 0.0, "DUST": 0.0},
        {"SPY": Holding("SPY", 100.0), "DUST": Holding("DUST", 0.005)},
        _prices(SPY=100.0, TLT=50.0, DUST=100.0),
        equity=10_000.5,
        mode=SizingMode.DRIFT,
        state=state,
    )
    by_symbol = {o.symbol: o for o in orders}
    assert "DUST" not in by_symbol
    assert by_symbol["SPY"].side == "sell" and by_symbol["SPY"].quantity == 100.0
    assert by_symbol["TLT"].side == "buy"
    assert abs(by_symbol["TLT"].quantity - 200.0) < 1e-9
    # Buy notional never exceeds the sell proceeds that actually land.
    assert by_symbol["TLT"].quantity * 50.0 <= 100.0 * 100.0 + 1e-9
    assert state.sub_notional_skips == 1


def test_buy_left_under_the_floor_by_the_refit_is_skipped_too():
    # The $1.20 TLT buy clears the floor on its own, but the skipped $0.50 dust sell leaves
    # only $0.70 of funding behind it, so the refit drops it as well — both are counted.
    state = SizingState()
    orders = size_orders(
        {"TLT": 100.0, "DUST": 0.0},
        {"DUST": Holding("DUST", 0.005)},
        _prices(TLT=50.0, DUST=100.0),
        equity=1.2,
        mode=SizingMode.DRIFT,
        state=state,
    )
    assert orders == []
    assert state.sub_notional_skips == 2


def test_order_exactly_at_the_floor_is_kept():
    at_floor = size_orders({"AAA": 100.0}, {}, _prices(AAA=1.0), equity=1.0, mode=SizingMode.DRIFT)
    assert len(at_floor) == 1 and at_floor[0].quantity == 1.0

    below_floor = size_orders(
        {"AAA": 100.0}, {}, _prices(AAA=1.0), equity=0.99, mode=SizingMode.DRIFT
    )
    assert below_floor == []


def test_zero_floor_disables_the_guard():
    state = SizingState()
    orders = size_orders(
        {"AAA": 100.0},
        {},
        _prices(AAA=100.0),
        equity=0.05,
        mode=SizingMode.DRIFT,
        min_order_notional=0.0,
        state=state,
    )
    assert len(orders) == 1
    assert abs(orders[0].quantity - 0.0005) < 1e-12
    assert state.sub_notional_skips == 0


def test_affordable_quantity_covers_the_cash_fit_edges():
    assert affordable_quantity(10.0, 100.0, cash=500.0) == 5.0  # trimmed to what cash covers
    assert affordable_quantity(10.0, 100.0, cash=5_000.0) == 10.0  # never more than asked
    assert affordable_quantity(10.0, 0.0, cash=500.0) == 0.0  # no price, nothing affordable
    assert affordable_quantity(10.0, 100.0, cash=1.0, commission=5.0) == 0.0  # fee exceeds cash


def test_zero_equity_produces_no_orders():
    orders = size_orders({"SPY": 100.0}, {}, _prices(SPY=100.0), equity=0.0, mode=SizingMode.BINARY)
    assert orders == []


def test_drift_buy_dropped_when_a_suppressed_sell_leaves_no_funding():
    # Fully invested (free_cash 0): A's small trim is inside the 5% band (no sell), while B's
    # buy is outside it. Without a funding fit the buy is emitted and Alpaca rejects it; with
    # free_cash known it is trimmed to the 0 dollars available and dropped.
    state = SizingState()
    orders = size_orders(
        {"A": 95.0, "B": 5.0},
        {"A": Holding("A", 194.0), "B": Holding("B", 3.0)},
        _prices(A=50.0, B=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
        free_cash=0.0,
        state=state,
    )
    assert orders == []
    assert state.sub_notional_skips == 1


def test_drift_without_free_cash_keeps_the_legacy_unfundable_buy():
    # Same inputs, but free_cash omitted -> legacy path assumes same-tick sells fund the buy,
    # so the unfundable buy is still emitted.
    orders = size_orders(
        {"A": 95.0, "B": 5.0},
        {"A": Holding("A", 194.0), "B": Holding("B", 3.0)},
        _prices(A=50.0, B=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
    )
    assert [o.symbol for o in orders] == ["B"]


def test_drift_buy_funded_by_existing_free_cash_is_untouched():
    orders = size_orders(
        {"A": 100.0},
        {},
        _prices(A=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
        free_cash=10_000.0,
    )
    assert len(orders) == 1 and orders[0].side == "buy"
    assert orders[0].quantity == 100.0


def test_binary_open_is_fit_to_free_cash_not_marked_up_equity():
    # Equity is 10k but only 3k is free cash (the rest sits in an untouched position); a fresh
    # 100% open must size to the cash it can actually spend.
    orders = size_orders(
        {"B": 100.0},
        {},
        _prices(B=100.0),
        equity=10_000.0,
        mode=SizingMode.BINARY,
        free_cash=3_000.0,
    )
    assert len(orders) == 1 and orders[0].side == "buy"
    assert orders[0].quantity == 30.0  # 3000 / 100, not the full 100 shares


def test_buys_scaled_proportionally_under_a_budget_shortfall():
    # 50/50 intent, budget (free cash) covers only half: both buys trim to 25 shares each,
    # preserving the target weights — not A fully funded and B starved (the greedy failure).
    orders = size_orders(
        {"AAA": 50.0, "BBB": 50.0},
        {},
        _prices(AAA=100.0, BBB=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
        free_cash=5_000.0,
    )
    by_symbol = {o.symbol: o for o in orders}
    assert set(by_symbol) == {"AAA", "BBB"}
    assert abs(by_symbol["AAA"].quantity - 25.0) < 1e-9
    assert abs(by_symbol["BBB"].quantity - 25.0) < 1e-9


def test_quantize_quantity_rounds_down():
    assert abs(quantize_quantity(1.2345678901, decimals=9) - 1.23456789) < 1e-12
    assert quantize_quantity(1.9, fractional=False) == 1.0
    assert quantize_quantity(2.0, fractional=False) == 2.0
    assert quantize_quantity(0.0) == 0.0
    assert quantize_quantity(-5.0) == 0.0


def test_size_orders_fractional_quantization_keeps_a_normal_order():
    orders = size_orders(
        {"AAA": 100.0},
        {},
        _prices(AAA=100.0),
        equity=1_000.0,
        mode=SizingMode.DRIFT,
        quantization=ShareQuantization(),
    )
    assert len(orders) == 1
    assert abs(orders[0].quantity - 10.0) < 1e-9  # 1000 / 100, unchanged by 9dp rounding


def test_size_orders_quantizes_to_whole_shares():
    # equity $270 at $100 sizes 2.7 shares; whole-share rounding floors it to 2.
    orders = size_orders(
        {"AAA": 100.0},
        {},
        _prices(AAA=100.0),
        equity=270.0,
        mode=SizingMode.DRIFT,
        quantization=ShareQuantization(fractional=False),
    )
    assert len(orders) == 1
    assert orders[0].quantity == 2.0


def test_size_orders_quantization_drops_an_order_that_rounds_below_floor():
    # 0.5 shares clears the $1 notional floor pre-rounding ($50), but whole-share rounding
    # floors it to zero, so it is dropped and counted (mirrors the live re-check).
    state = SizingState()
    orders = size_orders(
        {"AAA": 100.0},
        {},
        _prices(AAA=100.0),
        equity=50.0,
        mode=SizingMode.DRIFT,
        quantization=ShareQuantization(fractional=False),
        state=state,
    )
    assert orders == []
    assert state.sub_notional_skips == 1


def test_churn_guard_skips_tiny_weight_change_same_state():
    # Previously 100%, now 100.05% and already held -> below min_weight_change, skip.
    orders = size_orders(
        {"SPY": 100.05},
        {"SPY": Holding("SPY", 100.0)},
        _prices(SPY=100.0),
        equity=10_000.0,
        mode=SizingMode.DRIFT,
        current_weights={"SPY": 100.0},
    )
    assert orders == []
