"""Tests for backtest Pydantic models.

The read-side models (BacktestMetrics/TradeRecord/EquityPoint/…) were collapsed
onto proto (1A) — their read/wire shape is covered by test_proto_mappers.py.
BacktestCreate remains as the request-input DTO and is tested here.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models import VALID_TIMEFRAMES, BacktestCreate


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
