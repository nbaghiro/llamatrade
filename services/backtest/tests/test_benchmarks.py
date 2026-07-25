"""Tests for benchmark calculations."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.engine.benchmarks import BenchmarkCalculator


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

    def test_alpha_beta_insufficient_data(self, calculator):
        """Test alpha/beta with insufficient data."""
        strategy_returns = np.array([0.01])
        benchmark_returns = np.array([0.02])

        alpha, beta = calculator.calculate_alpha_beta(strategy_returns, benchmark_returns)

        # Undefined with <2 points: None, not a misleading 0.0 (8A)
        assert alpha is None
        assert beta is None

    def test_alpha_beta_none_for_flat_benchmark(self, calculator):
        """A zero-variance benchmark makes beta a 0/0 — undefined, so None (8A)."""
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

        # Undefined with <2 points: None, not a misleading 0.0 (8A)
        assert ir is None
