"""Pure-domain analytics tests — no DB, no network, no third-party dependency."""

from datetime import date

import numpy as np
import pytest
from numpy.typing import NDArray

from src import domain

# =============================================================================
# unrealized_pnl
# =============================================================================


def test_unrealized_pnl_long_gain() -> None:
    assert domain.unrealized_pnl("long", 10, 100.0, 110.0) == pytest.approx(100.0)


def test_unrealized_pnl_long_loss() -> None:
    assert domain.unrealized_pnl("long", 10, 100.0, 90.0) == pytest.approx(-100.0)


def test_unrealized_pnl_short_gain() -> None:
    assert domain.unrealized_pnl("short", 10, 100.0, 90.0) == pytest.approx(100.0)


def test_unrealized_pnl_short_loss() -> None:
    assert domain.unrealized_pnl("short", 10, 100.0, 110.0) == pytest.approx(-100.0)


def test_unrealized_pnl_zero_qty() -> None:
    assert domain.unrealized_pnl("long", 0, 100.0, 110.0) == 0.0


# =============================================================================
# pnl_percent
# =============================================================================


def test_pnl_percent_basic() -> None:
    assert domain.pnl_percent(50.0, 500.0) == pytest.approx(10.0)


def test_pnl_percent_negative() -> None:
    assert domain.pnl_percent(-25.0, 500.0) == pytest.approx(-5.0)


def test_pnl_percent_zero_cost_basis() -> None:
    assert domain.pnl_percent(50.0, 0.0) == 0.0


# =============================================================================
# benchmark_metrics
# =============================================================================


def test_benchmark_tracks_one_to_one() -> None:
    """Portfolio == benchmark => beta 1.0, alpha ~0, return = compounded."""
    d = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = {d[0]: 100.0, d[1]: 110.0, d[2]: 99.0, d[3]: 118.8}
    equities: NDArray[np.float64] = np.array([closes[x] for x in d])

    beta, alpha, benchmark_return = domain.benchmark_metrics(d, equities, closes)

    assert beta == pytest.approx(1.0, abs=1e-9)
    assert alpha == pytest.approx(0.0, abs=1e-6)
    assert benchmark_return == pytest.approx(18.8, abs=1e-6)  # 1.10*0.90*1.20 - 1


def test_benchmark_scaled_2x_beta() -> None:
    """Portfolio returns exactly 2x benchmark => beta 2.0, alpha ~rf (2%)."""
    d = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    closes = {d[0]: 100.0, d[1]: 110.0, d[2]: 104.5, d[3]: 125.4}  # rets 0.10,-0.05,0.20
    equities: NDArray[np.float64] = np.array([100.0, 120.0, 108.0, 151.2])  # 2x each

    beta, alpha, benchmark_return = domain.benchmark_metrics(d, equities, closes)

    assert beta == pytest.approx(2.0, abs=1e-9)
    assert alpha == pytest.approx(2.0, abs=1e-6)  # rf annualized
    assert benchmark_return == pytest.approx(25.4, abs=1e-6)  # 1.10*0.95*1.20 - 1


def test_benchmark_insufficient_overlap() -> None:
    d = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    equities: NDArray[np.float64] = np.array([100.0, 110.0, 120.0])
    assert domain.benchmark_metrics(d, equities, {d[0]: 400.0}) == (0.0, 0.0, 0.0)


def test_benchmark_flat_benchmark_zero_beta() -> None:
    """A benchmark with zero variance yields beta 0 (guarded division)."""
    d = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    closes = {d[0]: 100.0, d[1]: 100.0, d[2]: 100.0}  # flat -> var 0
    equities: NDArray[np.float64] = np.array([100.0, 110.0, 105.0])
    beta, _alpha, _ret = domain.benchmark_metrics(d, equities, closes)
    assert beta == 0.0


def test_benchmark_skips_missing_dates() -> None:
    """Intervals where the benchmark has no close are skipped."""
    d = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    # d[2] missing -> only intervals (d0->d1) and (d3 has no prior with data) usable;
    # effectively one aligned interval -> insufficient -> zeros
    closes = {d[0]: 100.0, d[1]: 110.0, d[3]: 120.0}
    equities: NDArray[np.float64] = np.array([100.0, 110.0, 105.0, 120.0])
    assert domain.benchmark_metrics(d, equities, closes) == (0.0, 0.0, 0.0)
