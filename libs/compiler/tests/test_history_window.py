"""Tests for history windowing (the indicator cache bound)."""

from datetime import UTC, datetime, timedelta

from llamatrade_compiler import compile_strategy
from llamatrade_compiler.indicators.cache import compute_window
from llamatrade_compiler.types import Bar
from llamatrade_dsl import parse_strategy

MOMENTUM = (
    '(strategy "Mom" :rebalance daily '
    "(weight :method momentum :lookback 90 (asset AAA) (asset BBB)))"
)
NO_PERIOD_METRIC = (
    '(strategy "DD" :rebalance daily '
    "(if (> (drawdown SPY) 0.1) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)
SIMPLE_RSI = (
    '(strategy "RSI" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)


def _feed(sexpr: str, closes: dict[str, list[float]]):
    compiled = compile_strategy(parse_strategy(sexpr))
    n = len(next(iter(closes.values())))
    start = datetime(2024, 1, 1, tzinfo=UTC)
    weights = {}
    for i in range(n):
        ts = start + timedelta(days=i)
        bars = {
            s: Bar(timestamp=ts, open=c[i], high=c[i], low=c[i], close=c[i], volume=1000)
            for s, c in closes.items()
        }
        weights = compiled.compute_allocation(bars)["weights"]
    return compiled, weights


def test_window_covers_momentum_lookback():
    window = compute_window(parse_strategy(MOMENTUM), min_bars=14)
    assert window is not None
    assert window >= 90  # must cover the momentum lookback


def test_no_period_metric_caps_window():
    # (drawdown SPY) reads the whole history -> bounded at the hard cap, not unbounded.
    from llamatrade_compiler.indicators.cache import _MAX_WINDOW

    window = compute_window(parse_strategy(NO_PERIOD_METRIC), min_bars=14)
    assert window == _MAX_WINDOW


def test_no_period_metric_respects_custom_cap():
    window = compute_window(parse_strategy(NO_PERIOD_METRIC), min_bars=14, max_window=500)
    assert window == 500


def test_cap_never_below_warmup():
    # If the indicator warm-up need exceeds the cap, the warm-up requirement wins.
    window = compute_window(parse_strategy(NO_PERIOD_METRIC), min_bars=5000, max_window=500)
    assert window >= 5000


def test_history_is_actually_bounded():
    compiled, _ = _feed(SIMPLE_RSI, {"SPY": [100.0 + i for i in range(300)]})
    assert compiled.history_window is not None
    # 300 bars fed, but retained history is capped at the window.
    assert len(compiled._bar_history["SPY"]) <= compiled.history_window


def test_windowed_results_match_unbounded():
    # A momentum strategy over many bars must produce the same final weights whether or
    # not history is bounded (the window covers everything the strategy reads).
    n = 250
    aaa = [100.0 + i * 0.5 for i in range(n)]  # AAA trends up faster
    bbb = [100.0 + i * 0.1 for i in range(n)]

    _, bounded = _feed(MOMENTUM, {"AAA": aaa, "BBB": bbb})

    # Force unbounded by clearing the window, then replay.
    compiled = compile_strategy(parse_strategy(MOMENTUM))
    compiled.history_window = None
    start = datetime(2024, 1, 1, tzinfo=UTC)
    unbounded = {}
    for i in range(n):
        ts = start + timedelta(days=i)
        bars = {
            s: Bar(timestamp=ts, open=v[i], high=v[i], low=v[i], close=v[i], volume=1000)
            for s, v in {"AAA": aaa, "BBB": bbb}.items()
        }
        unbounded = compiled.compute_allocation(bars)["weights"]

    assert bounded.keys() == unbounded.keys()
    for k in bounded:
        assert abs(bounded[k] - unbounded[k]) < 1e-9
