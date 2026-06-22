"""Perf-regression guard for bar-by-bar strategy evaluation (Issue 14).

Wave 1 (13A) bounded the indicator history window, making per-bar evaluation cost
O(window) — flat in run length — instead of O(N) (which made a full run O(N^2)).
These tests lock that in: per-bar cost must stay roughly flat as the run grows, and
a realistic multi-symbol / multi-indicator backtest must finish well under a coarse
wall-clock ceiling. A revert of the window cap (unbounded history) would regress the
per-bar cost ~linearly with N and trip the scaling assertion.

The wall-clock bounds are deliberately generous (~10x observed) so the test guards
against catastrophic regressions, not normal timing noise.
"""

import time
from datetime import UTC, datetime, timedelta

import numpy as np

from llamatrade_compiler.session import StrategySession
from llamatrade_compiler.sizing import SizingMode
from llamatrade_compiler.types import Bar

# Several indicators (RSI, SMA crossover, ATR, MACD) + weight methods that read
# history (momentum, inverse-vol) — representative of a real strategy's eval cost.
_BENCH_SEXPR = (
    '(strategy "Perf" :rebalance daily '
    "(if (and (> (rsi SPY 14) 50) (crosses-above (sma SPY 20) (sma SPY 50)) "
    "(> (atr SPY 14) 0) (< (macd SPY 12 26 9 :signal) 5)) "
    "(weight :method momentum :lookback 90 (asset SPY) (asset QQQ) (asset IWM)) "
    "(else (weight :method inverse-volatility :lookback 60 (asset TLT) (asset GLD)))))"
)
_SYMBOLS = ["SPY", "QQQ", "IWM", "TLT", "GLD"]


def _run(num_bars: int) -> float:
    """Evaluate the strategy over `num_bars` and return seconds per bar."""
    rng = np.random.RandomState(7)
    series = {s: 100.0 + np.cumsum(rng.randn(num_bars)) for s in _SYMBOLS}
    start = datetime(2010, 1, 1, tzinfo=UTC)
    steps = [
        {
            s: Bar(
                timestamp=start + timedelta(days=i),
                open=float(series[s][i]),
                high=float(series[s][i]) + 0.5,
                low=float(series[s][i]) - 0.5,
                close=float(series[s][i]),
                volume=1_000_000,
            )
            for s in _SYMBOLS
        }
        for i in range(num_bars)
    ]
    session = StrategySession(_BENCH_SEXPR, sizing_mode=SizingMode.DRIFT)
    t0 = time.perf_counter()
    for step in steps:
        session.evaluate(step, {}, 100_000.0)
    elapsed = time.perf_counter() - t0
    # The window must stay bounded — the precondition for flat scaling.
    assert session._compiled.history_window is not None
    return elapsed / num_bars


def test_per_bar_cost_is_flat_in_run_length() -> None:
    """Per-bar cost must not grow with run length (the 13A bounded-window guarantee)."""
    short = _run(252 * 2)  # 2y
    long = _run(252 * 8)  # 8y
    # Bounded window => roughly flat. Unbounded (regression) => ~4x growth.
    assert long < short * 2.5, f"per-bar cost grew {long / short:.1f}x (window cap regressed?)"


def test_full_backtest_under_wall_clock_ceiling() -> None:
    """A 10y, 5-symbol, multi-indicator backtest finishes well under a coarse ceiling."""
    n = 252 * 10
    per_bar = _run(n)
    total = per_bar * n
    assert total < 8.0, f"10y backtest took {total:.2f}s (expected ~1s)"
