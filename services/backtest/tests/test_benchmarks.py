# pyright: reportArgumentType=false
"""Tests for benchmark calculations."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.engine.benchmarks import (
    BenchmarkCalculator,
    BenchmarkMetrics,
)


class TestBenchmarkMetrics:
    """Tests for BenchmarkMetrics dataclass."""

    def test_default_metrics(self):
        """Test default metric values."""
        metrics = BenchmarkMetrics()

        assert metrics.spy_return == 0.0
        assert metrics.portfolio_60_40_return == 0.0
        assert metrics.risk_free_return == 0.0
        assert metrics.alpha == 0.0
        assert metrics.beta == 0.0
        assert metrics.information_ratio == 0.0


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

    @pytest.fixture
    def bond_bars(self):
        """Create sample bond bar data."""
        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        return [
            {"timestamp": base_date + timedelta(days=i), "close": 50.0 * (1.0002**i)}
            for i in range(252)
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

    def test_60_40_portfolio_basic(self, calculator, spy_bars, bond_bars):
        """Test 60/40 portfolio calculation."""
        total_return, equity_curve = calculator.calculate_60_40_portfolio(
            spy_bars, bond_bars, 100000
        )

        assert isinstance(total_return, float)
        assert len(equity_curve) > 0

    def test_60_40_portfolio_no_bonds(self, calculator, spy_bars):
        """Test 60/40 portfolio without bond data."""
        total_return, equity_curve = calculator.calculate_60_40_portfolio(spy_bars, None, 100000)

        # Should still work, using risk-free rate for bond portion
        assert isinstance(total_return, float)
        assert len(equity_curve) > 0

    def test_60_40_portfolio_empty(self, calculator):
        """Test 60/40 portfolio with empty data."""
        total_return, equity_curve = calculator.calculate_60_40_portfolio([], None, 100000)

        assert total_return == 0.0
        assert equity_curve == []

    def test_risk_free_return_basic(self, calculator):
        """Test risk-free return calculation."""
        total_return, equity_values = calculator.calculate_risk_free_return(252, 100000)

        # Should be approximately 2% annual return
        assert total_return == pytest.approx(0.02, rel=0.1)
        assert len(equity_values) == 252
        assert equity_values[0] == 100000
        assert equity_values[-1] > equity_values[0]

    def test_risk_free_return_zero_days(self, calculator):
        """Test risk-free return with zero days."""
        total_return, equity_values = calculator.calculate_risk_free_return(0, 100000)

        assert total_return == 0.0
        assert len(equity_values) == 1
        assert equity_values[0] == 100000

    def test_alpha_beta_basic(self, calculator):
        """Test alpha and beta calculation."""
        # Create correlated returns
        benchmark_returns = np.array([0.01, -0.005, 0.008, -0.003, 0.012, -0.002, 0.007])
        strategy_returns = benchmark_returns * 1.2 + 0.001  # Beta > 1, positive alpha

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        assert isinstance(alpha, float)
        assert isinstance(beta, float)
        assert beta > 1.0  # Strategy is more volatile than benchmark

    def test_alpha_beta_insufficient_data(self, calculator):
        """Test alpha/beta with insufficient data."""
        strategy_returns = np.array([0.01])
        benchmark_returns = np.array([0.02])

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        assert alpha == 0.0
        assert beta == 0.0

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

        assert ir == 0.0

    def test_calculate_all_metrics(self, calculator, spy_bars, bond_bars):
        """Test calculating all metrics at once."""
        strategy_returns = np.array([0.01, -0.005, 0.008, -0.003, 0.012])
        strategy_total_return = 0.15

        metrics = calculator.calculate_all_metrics(
            strategy_returns=strategy_returns,
            strategy_total_return=strategy_total_return,
            spy_bars=spy_bars[:5],  # Match length
            bond_bars=bond_bars[:5],
            initial_capital=100000,
        )

        assert isinstance(metrics, BenchmarkMetrics)
        assert isinstance(metrics.spy_return, float)
        assert isinstance(metrics.portfolio_60_40_return, float)
        assert isinstance(metrics.alpha, float)
        assert isinstance(metrics.beta, float)
        assert isinstance(metrics.excess_return_vs_spy, float)


class TestRebalancing:
    """Tests for portfolio rebalancing."""

    def test_monthly_rebalancing(self):
        """Test monthly rebalancing frequency."""
        calculator = BenchmarkCalculator(rebalance_frequency="monthly")

        # Create data spanning 3 months
        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        spy_bars = []
        bond_bars = []
        for i in range(90):  # 90 days
            date = base_date + timedelta(days=i)
            spy_bars.append({"timestamp": date, "close": 100.0 * (1.001**i)})
            bond_bars.append({"timestamp": date, "close": 50.0 * (1.0005**i)})

        total_return, equity_curve = calculator.calculate_60_40_portfolio(
            spy_bars, bond_bars, 100000
        )

        assert len(equity_curve) == 90
        assert total_return != 0

    def test_quarterly_rebalancing(self):
        """Test quarterly rebalancing frequency."""
        calculator = BenchmarkCalculator(rebalance_frequency="quarterly")

        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        spy_bars = []
        for i in range(180):  # 6 months
            date = base_date + timedelta(days=i)
            spy_bars.append({"timestamp": date, "close": 100.0 * (1.001**i)})

        total_return, equity_curve = calculator.calculate_60_40_portfolio(spy_bars, None, 100000)

        assert len(equity_curve) == 180

    def test_no_rebalancing(self):
        """Test no rebalancing."""
        calculator = BenchmarkCalculator(rebalance_frequency="none")

        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        spy_bars = [
            {"timestamp": base_date + timedelta(days=i), "close": 100.0 + i} for i in range(30)
        ]

        total_return, equity_curve = calculator.calculate_60_40_portfolio(spy_bars, None, 100000)

        assert len(equity_curve) == 30


class TestCustomWeights:
    """Tests for custom portfolio weights."""

    def test_70_30_portfolio(self):
        """Test 70/30 portfolio weights."""
        calculator = BenchmarkCalculator(portfolio_weights=(0.7, 0.3))

        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        spy_bars = [
            {"timestamp": base_date + timedelta(days=i), "close": 100.0 * (1.001**i)}
            for i in range(30)
        ]

        total_return, equity_curve = calculator.calculate_60_40_portfolio(spy_bars, None, 100000)

        # Should calculate return with 70/30 weights
        assert isinstance(total_return, float)

    def test_100_0_portfolio(self):
        """Test 100% stocks portfolio."""
        calculator = BenchmarkCalculator(portfolio_weights=(1.0, 0.0))

        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        spy_bars = [
            {"timestamp": base_date + timedelta(days=i), "close": 100.0 * (1.001**i)}
            for i in range(30)
        ]

        portfolio_return, _ = calculator.calculate_60_40_portfolio(spy_bars, None, 100000)
        spy_return, _ = calculator.calculate_spy_buy_hold(spy_bars, 100000)

        # 100% stocks should equal SPY buy & hold
        assert portfolio_return == pytest.approx(spy_return, rel=0.01)
