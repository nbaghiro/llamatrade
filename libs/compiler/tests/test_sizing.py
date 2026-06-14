"""Tests for the single sizing implementation (weights -> intended orders)."""

from llamatrade_compiler.sizing import Holding, SizingMode, size_orders


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


def test_missing_or_nonpositive_price_skipped():
    orders = size_orders(
        {"SPY": 100.0}, {}, _prices(SPY=0.0), equity=10_000.0, mode=SizingMode.DRIFT
    )
    assert orders == []


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
