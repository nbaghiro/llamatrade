"""Tests for benchmark calculations."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.engine.benchmarks import BenchmarkBarData, BenchmarkCalculator, align_daily_returns


def _day(day: int, hour: int = 16) -> datetime:
    return datetime(2024, 1, day, hour, tzinfo=UTC)


def _bench(points: list[tuple[datetime, float]]) -> list[BenchmarkBarData]:
    return [BenchmarkBarData(timestamp=ts, close=close) for ts, close in points]


class TestAlignDailyReturns:
    """Date-joined day-over-day returns, pinned to exact expected values."""

    def test_returns_pinned_on_fully_overlapping_days(self):
        strategy = [(_day(1), 100.0), (_day(2), 110.0), (_day(3), 99.0)]
        benchmark = _bench([(_day(1), 200.0), (_day(2), 210.0), (_day(3), 189.0)])

        strat, bench = align_daily_returns(strategy, benchmark)

        assert strat.tolist() == pytest.approx([0.10, -0.10])
        assert bench.tolist() == pytest.approx([0.05, -0.10])

    def test_missing_benchmark_date_is_dropped_from_both(self):
        """A date absent from one series must not positionally skew the other."""
        strategy = [(_day(1), 100.0), (_day(2), 110.0), (_day(3), 121.0)]
        # Benchmark has no Jan 2 bar: only the Jan-3 return exists on both grids
        # once the missing date breaks the day-2 join.
        benchmark = _bench([(_day(1), 200.0), (_day(3), 220.0)])

        strat, bench = align_daily_returns(strategy, benchmark)

        assert strat.tolist() == pytest.approx([0.10])
        assert bench.tolist() == pytest.approx([0.10])

    def test_intraday_points_collapse_to_last_value_per_day(self):
        strategy = [
            (_day(1, hour=10), 100.0),
            (_day(1, hour=16), 104.0),
            (_day(2, hour=10), 130.0),
            (_day(2, hour=16), 130.0),
        ]
        benchmark = _bench([(_day(1), 200.0), (_day(2), 220.0)])

        strat, bench = align_daily_returns(strategy, benchmark)

        # Day-1 close is the LAST point (104), so the day-2 return is 25%, not 30%.
        assert strat.tolist() == pytest.approx([0.25])
        assert bench.tolist() == pytest.approx([0.10])

    def test_non_positive_previous_value_skips_that_return(self):
        strategy = [(_day(1), 0.0), (_day(2), 50.0), (_day(3), 55.0)]
        benchmark = _bench([(_day(1), 100.0), (_day(2), 100.0), (_day(3), 110.0)])

        strat, bench = align_daily_returns(strategy, benchmark)

        # The day-2 strategy return divides by zero equity and is dropped.
        assert strat.tolist() == pytest.approx([0.10])
        assert bench.tolist() == pytest.approx([0.10])

    def test_no_common_dates_yields_empty_arrays(self):
        strategy = [(_day(1), 100.0), (_day(2), 110.0)]
        benchmark = _bench([(_day(10), 200.0), (_day(11), 210.0)])

        strat, bench = align_daily_returns(strategy, benchmark)

        assert strat.size == 0
        assert bench.size == 0

    def test_empty_inputs_yield_empty_arrays(self):
        strat, bench = align_daily_returns([], [])
        assert strat.size == 0
        assert bench.size == 0


class TestBenchmarkCalculator:
    """Tests for BenchmarkCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create a calculator instance."""
        return BenchmarkCalculator(risk_free_rate=0.02)

    @pytest.fixture
    def spy_bars(self):
        """Create sample SPY bar data."""
        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        return [
            {"timestamp": base_date + timedelta(days=i), "close": 100.0 * (1.0005**i)}
            for i in range(252)  # One year of data
        ]

    def test_spy_buy_hold_basic(self, calculator, spy_bars):
        """Test SPY buy & hold calculation."""
        total_return, equity_curve = calculator.calculate_spy_buy_hold(spy_bars, 100000)

        assert total_return > 0  # Should be positive with rising prices
        assert len(equity_curve) == len(spy_bars)
        assert equity_curve[0][1] == pytest.approx(100000)  # Initial equity

    def test_spy_buy_hold_empty(self, calculator):
        """Test SPY buy & hold with empty data."""
        total_return, equity_curve = calculator.calculate_spy_buy_hold([], 100000)

        assert total_return == 0.0
        assert equity_curve == []

    def test_alpha_beta_basic(self, calculator):
        """Test alpha and beta calculation."""
        # Create correlated returns
        benchmark_returns = np.array([0.01, -0.005, 0.008, -0.003, 0.012, -0.002, 0.007])
        strategy_returns = benchmark_returns * 1.2 + 0.001  # Beta > 1, positive alpha

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        assert isinstance(alpha, float)
        assert isinstance(beta, float)
        assert beta > 1.0  # Strategy is more volatile than benchmark

    def test_beta_is_one_for_identical_series(self, calculator):
        """A series identical to the benchmark has beta exactly 1.0.

        With a ddof mismatch (cov ddof=1 over var ddof=0) this reported n/(n-1):
        1.5 over three points, 1.05 over twenty. Shared ddof=1 makes it exact.
        """
        benchmark_returns = np.array([0.01, -0.02, 0.03])
        strategy_returns = benchmark_returns.copy()

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        assert beta == pytest.approx(1.0)
        # Identical series, so alpha reduces to (1 - beta) * (benchmark - rf) == 0.
        assert alpha == pytest.approx(0.0, abs=1e-12)

    def test_alpha_beta_insufficient_data(self, calculator):
        """Test alpha/beta with insufficient data."""
        strategy_returns = np.array([0.01])
        benchmark_returns = np.array([0.02])

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        # Undefined with <2 points: None, not a misleading 0.0
        assert alpha is None
        assert beta is None

    def test_alpha_beta_none_for_flat_benchmark(self, calculator):
        """A zero-variance benchmark makes beta a 0/0 — undefined, so None."""
        benchmark_returns = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        strategy_returns = np.array([0.01, -0.005, 0.008, -0.003, 0.012])

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        assert alpha is None
        assert beta is None

    def test_alpha_beta_different_lengths(self, calculator):
        """Test alpha/beta with different length arrays."""
        strategy_returns = np.array([0.01, -0.005, 0.008, -0.003, 0.012])
        benchmark_returns = np.array([0.01, -0.005, 0.008])  # Shorter

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        # Should use minimum length
        assert isinstance(alpha, float)
        assert isinstance(beta, float)

    def test_information_ratio_basic(self, calculator):
        """Test information ratio calculation."""
        benchmark_returns = np.array(
            [0.01, -0.005, 0.008, -0.003, 0.012, -0.002, 0.007, 0.005, -0.004, 0.009]
        )
        strategy_returns = benchmark_returns + 0.002  # Consistent outperformance

        ir = calculator.calculate_information_ratio(strategy_returns, benchmark_returns)

        assert ir > 0  # Should be positive with consistent outperformance

    def test_information_ratio_insufficient_data(self, calculator):
        """Test IR with insufficient data."""
        strategy_returns = np.array([0.01])
        benchmark_returns = np.array([0.02])

        ir = calculator.calculate_information_ratio(strategy_returns, benchmark_returns)

        # Undefined with <2 points: None, not a misleading 0.0
        assert ir is None
