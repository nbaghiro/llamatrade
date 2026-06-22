"""Analytics edge-case tests — degenerate equity series stay finite.

An all-zero (or zero-then-funded) equity series must not produce NaN/inf, which
would poison the metrics and serialize as invalid JSON.
"""

import math

import numpy as np

from src.ledger.analytics import equity_metrics, max_drawdown


def test_equity_metrics_all_zero_series_is_finite_and_zero() -> None:
    m = equity_metrics(np.array([0.0, 0.0, 0.0], dtype=np.float64))
    for v in (
        m.volatility,
        m.sharpe_ratio,
        m.sortino_ratio,
        m.max_drawdown,
        m.best_day,
        m.worst_day,
        m.avg_daily_return,
        m.annualized_return,
        m.total_return_percent,
    ):
        assert math.isfinite(v)
        assert v == 0.0


def test_equity_metrics_zero_then_funded_is_finite() -> None:
    """A 0 → 100 step (account funded after a zero point) yields no NaN."""
    m = equity_metrics(np.array([0.0, 100.0, 110.0], dtype=np.float64))
    assert math.isfinite(m.volatility)
    assert math.isfinite(m.sharpe_ratio)
    assert math.isfinite(m.sortino_ratio)
    assert math.isfinite(m.max_drawdown)


def test_max_drawdown_all_zero_is_zero() -> None:
    assert max_drawdown(np.array([0.0, 0.0], dtype=np.float64)) == 0.0


def test_max_drawdown_normal_peak_to_trough() -> None:
    # 100 → 120 → 90: peak 120, trough 90 → 25% drawdown.
    assert max_drawdown(np.array([100.0, 120.0, 90.0], dtype=np.float64)) == 25.0
