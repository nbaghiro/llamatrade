"""Tests for backtest Pydantic models."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models import (
    VALID_TIMEFRAMES,
    BacktestCreate,
    BacktestMetrics,
    BacktestResultResponse,
    BenchmarkEquityPoint,
)


class TestBacktestCreate:
    """Tests for BacktestCreate model."""

    def test_default_values(self):
        """Test default values are set correctly."""
        backtest = BacktestCreate(
            strategy_id=uuid4(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 30),
        )

        assert backtest.timeframe == "1D"
        assert backtest.benchmark_symbol == "SPY"
        assert backtest.include_benchmark is True
        assert backtest.initial_capital == 100000
        assert backtest.commission == 0
        assert backtest.slippage == 0

    def test_valid_timeframes(self):
        """Test all valid timeframes are accepted."""
        for tf in VALID_TIMEFRAMES:
            backtest = BacktestCreate(
                strategy_id=uuid4(),
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 6, 30),
                timeframe=tf,
            )
            assert backtest.timeframe == tf

    def test_invalid_timeframe_raises(self):
        """Test invalid timeframe raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BacktestCreate(
                strategy_id=uuid4(),
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 6, 30),
                timeframe="invalid",
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "timeframe" in str(errors[0]["loc"])

    def test_invalid_timeframe_variations(self):
        """Test various invalid timeframe values."""
        invalid_timeframes = ["1d", "1day", "1DAY", "daily", "1m", "1min", "5m", "1 H", "hourly"]

        for tf in invalid_timeframes:
            with pytest.raises(ValidationError):
                BacktestCreate(
                    strategy_id=uuid4(),
                    start_date=datetime(2024, 1, 1),
                    end_date=datetime(2024, 6, 30),
                    timeframe=tf,
                )

    def test_custom_benchmark_symbol(self):
        """Test custom benchmark symbol."""
        backtest = BacktestCreate(
            strategy_id=uuid4(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 30),
            benchmark_symbol="QQQ",
        )

        assert backtest.benchmark_symbol == "QQQ"

    def test_benchmark_symbol_max_length(self):
        """Test benchmark symbol max length validation."""
        with pytest.raises(ValidationError):
            BacktestCreate(
                strategy_id=uuid4(),
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 6, 30),
                benchmark_symbol="TOOLONGSYMBOL",  # > 10 chars
            )

    def test_disable_benchmark(self):
        """Test disabling benchmark comparison."""
        backtest = BacktestCreate(
            strategy_id=uuid4(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 30),
            include_benchmark=False,
        )

        assert backtest.include_benchmark is False


class TestBacktestMetrics:
    """Tests for BacktestMetrics model with benchmark fields."""

    def test_default_benchmark_values(self):
        """Test default benchmark metric values."""
        metrics = BacktestMetrics(
            total_return=0.15,
            annual_return=0.20,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            max_drawdown_duration=30,
            win_rate=0.55,
            profit_factor=1.8,
            total_trades=100,
            winning_trades=55,
            losing_trades=45,
            avg_win=500.0,
            avg_loss=300.0,
            largest_win=2000.0,
            largest_loss=1000.0,
            avg_holding_period=5.5,
            exposure_time=75.0,
        )

        # Check default benchmark values
        assert metrics.benchmark_return == 0
        assert metrics.benchmark_symbol == "SPY"
        assert metrics.alpha == 0
        assert metrics.beta == 0
        assert metrics.information_ratio == 0
        assert metrics.excess_return == 0

    def test_with_benchmark_values(self):
        """Test metrics with benchmark values set."""
        metrics = BacktestMetrics(
            total_return=0.15,
            annual_return=0.20,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            max_drawdown_duration=30,
            win_rate=0.55,
            profit_factor=1.8,
            total_trades=100,
            winning_trades=55,
            losing_trades=45,
            avg_win=500.0,
            avg_loss=300.0,
            largest_win=2000.0,
            largest_loss=1000.0,
            avg_holding_period=5.5,
            exposure_time=75.0,
            # Benchmark fields
            benchmark_return=0.10,
            benchmark_symbol="QQQ",
            alpha=0.05,
            beta=1.2,
            information_ratio=0.75,
            excess_return=0.05,
        )

        assert metrics.benchmark_return == 0.10
        assert metrics.benchmark_symbol == "QQQ"
        assert metrics.alpha == 0.05
        assert metrics.beta == 1.2
        assert metrics.information_ratio == 0.75
        assert metrics.excess_return == 0.05


class TestBenchmarkEquityPoint:
    """Tests for BenchmarkEquityPoint model."""

    def test_basic_point(self):
        """Test creating a benchmark equity point."""
        point = BenchmarkEquityPoint(
            date=datetime(2024, 6, 1),
            equity=105000.0,
        )

        assert point.date == datetime(2024, 6, 1)
        assert point.equity == 105000.0


class TestBacktestResultResponse:
    """Tests for BacktestResultResponse with benchmark data."""

    def test_default_benchmark_curve(self):
        """Test default empty benchmark equity curve."""
        response = BacktestResultResponse(
            id=uuid4(),
            backtest_id=uuid4(),
            metrics=BacktestMetrics(
                total_return=0.15,
                annual_return=0.20,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                max_drawdown=0.10,
                max_drawdown_duration=30,
                win_rate=0.55,
                profit_factor=1.8,
                total_trades=100,
                winning_trades=55,
                losing_trades=45,
                avg_win=500.0,
                avg_loss=300.0,
                largest_win=2000.0,
                largest_loss=1000.0,
                avg_holding_period=5.5,
                exposure_time=75.0,
            ),
            equity_curve=[],
            trades=[],
            monthly_returns={},
            created_at=datetime.now(),
        )

        assert response.benchmark_equity_curve == []

    def test_with_benchmark_curve(self):
        """Test response with benchmark equity curve."""
        benchmark_curve = [
            BenchmarkEquityPoint(date=datetime(2024, 1, 1), equity=100000.0),
            BenchmarkEquityPoint(date=datetime(2024, 1, 2), equity=100500.0),
            BenchmarkEquityPoint(date=datetime(2024, 1, 3), equity=101000.0),
        ]

        response = BacktestResultResponse(
            id=uuid4(),
            backtest_id=uuid4(),
            metrics=BacktestMetrics(
                total_return=0.15,
                annual_return=0.20,
                sharpe_ratio=1.5,
                sortino_ratio=2.0,
                max_drawdown=0.10,
                max_drawdown_duration=30,
                win_rate=0.55,
                profit_factor=1.8,
                total_trades=100,
                winning_trades=55,
                losing_trades=45,
                avg_win=500.0,
                avg_loss=300.0,
                largest_win=2000.0,
                largest_loss=1000.0,
                avg_holding_period=5.5,
                exposure_time=75.0,
            ),
            equity_curve=[],
            trades=[],
            monthly_returns={},
            created_at=datetime.now(),
            benchmark_equity_curve=benchmark_curve,
        )

        assert len(response.benchmark_equity_curve) == 3
        assert response.benchmark_equity_curve[0].equity == 100000.0
