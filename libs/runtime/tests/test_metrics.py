"""Tests for the performance-metrics module."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_runtime import metrics


def test_sharpe_zero_when_no_variance() -> None:
    assert metrics.calculate_sharpe_ratio(np.array([0.01, 0.01, 0.01])) == 0.0


def test_sharpe_positive_for_positive_drift() -> None:
    rng = np.random.default_rng(0)
    returns = rng.normal(0.001, 0.01, 500)
    assert metrics.calculate_sharpe_ratio(returns) > 0


def test_sortino_downside_deviation_against_hand_computed_series() -> None:
    """Golden: downside deviation about the target, not std of losers about their mean.

    Series [0.03, -0.01, 0.02, -0.02] with rf=0: mean excess 0.005; downside
    deviation sqrt(mean([0, 0.01, 0, 0.02]^2)) = sqrt(0.000125) = 0.0111803;
    Sortino = sqrt(252) * 0.005 / 0.0111803 = 7.0993. The old formula divided by
    std of the two losing days about their own mean (0.005) and returned 15.87.
    """
    returns = np.array([0.03, -0.01, 0.02, -0.02])
    assert metrics.calculate_sortino_ratio(returns, risk_free_rate=0.0) == pytest.approx(
        7.0993, rel=1e-4
    )


def test_sortino_zero_when_no_downside() -> None:
    """No return falls below the target, so downside deviation is zero."""
    returns = np.array([0.01, 0.02, 0.03])
    assert metrics.calculate_sortino_ratio(returns, risk_free_rate=0.0) == 0.0


def test_max_drawdown_and_duration() -> None:
    equity = np.array([100.0, 120.0, 90.0, 130.0])
    dd, duration = metrics.calculate_max_drawdown(equity)
    assert dd == pytest.approx((120 - 90) / 120)
    assert duration >= 1


def test_max_drawdown_guards_nonpositive_peak() -> None:
    dd, duration = metrics.calculate_max_drawdown(np.array([0.0, -5.0, 10.0]))
    assert np.isfinite(dd)
    assert duration >= 0


def test_returns_total_annual_and_daily() -> None:
    equity = np.array([100.0, 110.0, 121.0])
    total, annual, daily = metrics.calculate_returns(equity, 100.0, 3)
    assert total == pytest.approx(0.21)
    assert annual > 0
    assert len(daily) == 2


def test_resample_daily_keeps_last_point_per_day() -> None:
    d = datetime(2024, 1, 1, 10, tzinfo=UTC)
    curve = [(d, 100.0), (d.replace(hour=15), 105.0), (d + timedelta(days=1), 110.0)]
    out = metrics.resample_daily(curve)
    assert len(out) == 2
    assert out[0][1] == 105.0


def test_monthly_returns_compound_off_prior_month_end() -> None:
    curve = [
        (datetime(2024, 1, 31, tzinfo=UTC), 110.0),
        (datetime(2024, 2, 29, tzinfo=UTC), 121.0),
    ]
    monthly = metrics.calculate_monthly_returns(curve, 100.0)
    assert monthly["2024-01"] == pytest.approx(0.10)
    assert monthly["2024-02"] == pytest.approx(0.10)


def test_profit_factor_none_when_no_losses() -> None:
    class _T:
        def __init__(self, pnl: float) -> None:
            self._pnl = pnl

        @property
        def pnl(self) -> float:
            return self._pnl

    win_rate, profit_factor = metrics.calculate_trade_statistics([_T(10), _T(20)])
    assert win_rate == 1.0
    assert profit_factor is None
