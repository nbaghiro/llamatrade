"""Analytics edge-case tests — degenerate equity series stay finite.

An all-zero (or zero-then-funded) equity series must not produce NaN/inf, which
would poison the metrics and serialize as invalid JSON.
"""

import math

import numpy as np
import pytest

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


# Sharpe / Sortino


def test_sharpe_empty_series_is_zero() -> None:
    from src.ledger.analytics import sharpe_ratio

    assert sharpe_ratio(np.array([], dtype=np.float64)) == 0.0


def test_sharpe_zero_volatility_is_zero() -> None:
    from src.ledger.analytics import sharpe_ratio

    assert sharpe_ratio(np.array([0.01, 0.01, 0.01])) == 0.0


def test_sharpe_positive_excess_return_is_positive_and_finite() -> None:
    from src.ledger.analytics import sharpe_ratio

    value = sharpe_ratio(np.array([0.01, -0.005, 0.02, 0.003]))
    assert math.isfinite(value)
    assert value > 0.0


def test_sharpe_matches_hand_computation() -> None:
    from src.ledger.analytics import sharpe_ratio

    returns = np.array([0.01, -0.005, 0.02, 0.003])
    excess = returns - 0.02 / 252
    expected = float(np.sqrt(252) * np.mean(excess) / np.std(returns))
    assert sharpe_ratio(returns) == expected


def test_sortino_empty_series_is_zero() -> None:
    from src.ledger.analytics import sortino_ratio

    assert sortino_ratio(np.array([], dtype=np.float64)) == 0.0


def test_sortino_without_downside_is_zero() -> None:
    from src.ledger.analytics import sortino_ratio

    assert sortino_ratio(np.array([0.01, 0.02, 0.005])) == 0.0


def test_sortino_zero_downside_deviation_is_zero() -> None:
    """A single repeated negative return has zero downside std — no divide-by-zero."""
    from src.ledger.analytics import sortino_ratio

    assert sortino_ratio(np.array([-0.01, -0.01, -0.01])) == 0.0


def test_sortino_penalizes_only_downside() -> None:
    from src.ledger.analytics import sortino_ratio

    returns = np.array([0.02, -0.01, 0.03, -0.02])
    negative = returns[returns < 0]
    expected = float(
        np.sqrt(252) * (float(np.mean(returns)) - 0.02 / 252) / float(np.std(negative))
    )
    assert sortino_ratio(returns) == expected


# Benchmark beta / alpha


def _dates(n: int) -> list:
    from datetime import date, timedelta

    return [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]


def test_benchmark_perfect_tracker_has_beta_one() -> None:
    from src.ledger.analytics import benchmark_metrics

    dates = _dates(5)
    closes = {d: 100.0 * (1.01**i) for i, d in enumerate(dates)}
    equities = np.array([1000.0 * (1.01**i) for i in range(5)])

    beta, alpha, benchmark_return = benchmark_metrics(dates, equities, closes)

    assert beta == pytest.approx(1.0)
    assert alpha == pytest.approx(0.0, abs=1e-9)
    assert benchmark_return == pytest.approx((1.01**4 - 1) * 100)


def test_benchmark_insufficient_overlap_is_zeros() -> None:
    from src.ledger.analytics import benchmark_metrics

    dates = _dates(3)
    # Only one overlapping return pair (< 2) -> all zeros.
    closes = {dates[0]: 100.0, dates[1]: 101.0}
    equities = np.array([1000.0, 1010.0, 1020.0])

    assert benchmark_metrics(dates, equities, closes) == (0.0, 0.0, 0.0)


def test_benchmark_no_close_data_is_zeros() -> None:
    from src.ledger.analytics import benchmark_metrics

    assert benchmark_metrics(_dates(4), np.array([1.0, 2.0, 3.0, 4.0]), {}) == (0.0, 0.0, 0.0)


def test_benchmark_flat_benchmark_variance_zero_beta_zero() -> None:
    """A constant benchmark has zero variance; beta must be 0, not a division error."""
    from src.ledger.analytics import benchmark_metrics

    dates = _dates(4)
    closes = {d: 100.0 for d in dates}
    equities = np.array([1000.0, 1010.0, 990.0, 1005.0])

    beta, _alpha, benchmark_return = benchmark_metrics(dates, equities, closes)

    assert beta == 0.0
    assert benchmark_return == pytest.approx(0.0)


def test_benchmark_skips_zero_equity_steps() -> None:
    """A zero prior equity (fully withdrawn) is excluded, not a divide-by-zero."""
    from src.ledger.analytics import benchmark_metrics

    dates = _dates(4)
    closes = {d: 100.0 + i for i, d in enumerate(dates)}
    equities = np.array([1000.0, 0.0, 1010.0, 1020.0])

    beta, alpha, benchmark_return = benchmark_metrics(dates, equities, closes)

    assert math.isfinite(beta)
    assert math.isfinite(alpha)
    assert math.isfinite(benchmark_return)


# Position P&L helpers


def test_unrealized_pnl_long_and_short() -> None:
    from decimal import Decimal

    from src.ledger.analytics import unrealized_pnl

    assert unrealized_pnl("long", Decimal("10"), Decimal("100"), Decimal("110")) == Decimal("100")
    assert unrealized_pnl("short", Decimal("10"), Decimal("100"), Decimal("90")) == Decimal("100")


def test_pnl_percent_zero_cost_basis_is_zero() -> None:
    from decimal import Decimal

    from src.ledger.analytics import pnl_percent

    assert pnl_percent(Decimal("50"), Decimal("0")) == Decimal("0")
    assert pnl_percent(Decimal("50"), Decimal("200")) == Decimal("25")
