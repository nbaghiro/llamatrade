"""Tests for vectorized backtest engine."""

from datetime import UTC, datetime

import numpy as np
import pytest
from src.engine.backtester import BacktestConfig, Trade
from src.engine.vectorized_engine import (
    CompiledStrategy,
    VectorizedBacktestEngine,
    prepare_vectorized_bars,
)


class TestCompiledStrategy:
    """Tests for CompiledStrategy dataclass."""

    def test_default_values(self):
        """Test default strategy values."""
        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: np.ones((1, 10), dtype=bool),
            exit_fn=lambda bars, ind: np.zeros((1, 10), dtype=bool),
        )

        assert strategy.position_size_pct == 10.0
        assert strategy.stop_loss_pct is None
        assert strategy.take_profit_pct is None
        assert strategy.indicators == {}

    def test_custom_values(self):
        """Test custom strategy values."""
        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: np.ones((1, 10), dtype=bool),
            exit_fn=lambda bars, ind: np.zeros((1, 10), dtype=bool),
            position_size_pct=20.0,
            stop_loss_pct=5.0,
            take_profit_pct=15.0,
            indicators={"sma_20": np.ones((1, 10))},
        )

        assert strategy.position_size_pct == 20.0
        assert strategy.stop_loss_pct == 5.0
        assert strategy.take_profit_pct == 15.0
        assert "sma_20" in strategy.indicators


class TestPrepareVectorizedBars:
    """Tests for prepare_vectorized_bars function."""

    def test_single_symbol(self):
        """Test converting single symbol bars."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 102,
                    "volume": 1000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 102,
                    "high": 107,
                    "low": 101,
                    "close": 105,
                    "volume": 1200,
                },
            ]
        }
        symbols = ["AAPL"]

        result, timestamps = prepare_vectorized_bars(bars, symbols)

        assert result["closes"].shape == (1, 2)
        assert result["opens"].shape == (1, 2)
        assert len(timestamps) == 2
        np.testing.assert_array_almost_equal(result["closes"][0], [102, 105])

    def test_multiple_symbols(self):
        """Test converting multiple symbol bars."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 102,
                    "volume": 1000,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 200,
                    "high": 210,
                    "low": 198,
                    "close": 205,
                    "volume": 500,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]

        result, timestamps = prepare_vectorized_bars(bars, symbols)

        assert result["closes"].shape == (2, 1)
        assert result["closes"][0, 0] == 102  # AAPL
        assert result["closes"][1, 0] == 205  # GOOGL

    def test_missing_timestamps_filled(self):
        """Test that missing timestamps are forward-filled."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 102,
                    "volume": 1000,
                },
                # Missing 2024-1-2
                {
                    "timestamp": datetime(2024, 1, 3, tzinfo=UTC),
                    "open": 105,
                    "high": 110,
                    "low": 104,
                    "close": 108,
                    "volume": 1300,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 200,
                    "high": 210,
                    "low": 198,
                    "close": 205,
                    "volume": 500,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 205,
                    "high": 215,
                    "low": 203,
                    "close": 212,
                    "volume": 600,
                },
                {
                    "timestamp": datetime(2024, 1, 3, tzinfo=UTC),
                    "open": 212,
                    "high": 220,
                    "low": 210,
                    "close": 218,
                    "volume": 700,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]

        result, timestamps = prepare_vectorized_bars(bars, symbols)

        assert len(timestamps) == 3
        # AAPL's missing Jan 2 should be forward-filled with Jan 1's close
        assert result["closes"][0, 1] == 102  # Forward-filled

    def test_empty_bars(self):
        """Test with empty bars."""
        bars = {}
        symbols = []

        result, timestamps = prepare_vectorized_bars(bars, symbols)

        assert len(timestamps) == 0


class TestVectorizedBacktestEngine:
    """Tests for VectorizedBacktestEngine class."""

    @pytest.fixture
    def engine(self):
        """Create a test engine."""
        config = BacktestConfig(
            initial_capital=100000,
            commission_rate=1.0,
            risk_free_rate=0.02,
        )
        return VectorizedBacktestEngine(config)

    @pytest.fixture
    def sample_bars(self):
        """Create sample vectorized bar data."""
        num_bars = 30
        base_price = 100.0
        prices = np.array([base_price * (1.001**i) for i in range(num_bars)])

        return {
            "timestamps": np.array([datetime(2024, 1, 1, tzinfo=UTC) for _ in range(num_bars)]),
            "opens": prices.reshape(1, -1),
            "highs": (prices * 1.02).reshape(1, -1),
            "lows": (prices * 0.98).reshape(1, -1),
            "closes": prices.reshape(1, -1),
            "volumes": np.full((1, num_bars), 10000.0),
        }

    def test_engine_init_default_config(self):
        """Test engine initializes with default config."""
        engine = VectorizedBacktestEngine()
        assert engine.config.initial_capital == 100000

    def test_engine_init_custom_config(self, engine):
        """Test engine initializes with custom config."""
        assert engine.config.initial_capital == 100000
        assert engine.config.commission_rate == 1.0

    def test_run_always_entry_exit(self, engine, sample_bars):
        """Test run with strategy that enters and exits."""
        # Entry at bar 0, exit at bar 10
        entry_signals = np.zeros((1, 30), dtype=bool)
        exit_signals = np.zeros((1, 30), dtype=bool)
        entry_signals[0, 0] = True
        exit_signals[0, 10] = True

        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: entry_signals,
            exit_fn=lambda bars, ind: exit_signals,
            position_size_pct=10.0,
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        assert len(result.trades) >= 1
        assert result.final_equity > 0

    def test_run_no_trades(self, engine, sample_bars):
        """Test run with no entry signals."""
        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
            exit_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        assert len(result.trades) == 0
        assert result.final_equity == 100000

    def test_run_multiple_symbols(self, engine):
        """Test run with multiple symbols."""
        num_bars = 10
        bars = {
            "timestamps": np.array([datetime(2024, 1, i + 1, tzinfo=UTC) for i in range(num_bars)]),
            "opens": np.full((2, num_bars), 100.0),
            "highs": np.full((2, num_bars), 105.0),
            "lows": np.full((2, num_bars), 95.0),
            "closes": np.full((2, num_bars), 102.0),
            "volumes": np.full((2, num_bars), 10000.0),
        }

        entry_signals = np.zeros((2, num_bars), dtype=bool)
        entry_signals[0, 0] = True  # AAPL entry
        entry_signals[1, 2] = True  # GOOGL entry

        exit_signals = np.zeros((2, num_bars), dtype=bool)
        exit_signals[0, 5] = True  # AAPL exit
        exit_signals[1, 7] = True  # GOOGL exit

        strategy = CompiledStrategy(
            entry_fn=lambda b, ind: entry_signals,
            exit_fn=lambda b, ind: exit_signals,
            position_size_pct=10.0,
        )

        result = engine.run(bars, strategy, ["AAPL", "GOOGL"])

        assert len(result.trades) == 2
        symbols_traded = {t.symbol for t in result.trades}
        assert "AAPL" in symbols_traded
        assert "GOOGL" in symbols_traded

    def test_run_with_stop_loss(self, engine):
        """Test run with stop loss."""
        num_bars = 10
        # Prices drop sharply after entry
        prices = np.array([100.0, 100.0, 90.0, 85.0, 80.0, 78.0, 75.0, 73.0, 70.0, 68.0])

        bars = {
            "timestamps": np.array([datetime(2024, 1, i + 1, tzinfo=UTC) for i in range(num_bars)]),
            "opens": prices.reshape(1, -1),
            "highs": (prices * 1.02).reshape(1, -1),
            "lows": (prices * 0.98).reshape(1, -1),
            "closes": prices.reshape(1, -1),
            "volumes": np.full((1, num_bars), 10000.0),
        }

        entry_signals = np.zeros((1, num_bars), dtype=bool)
        entry_signals[0, 0] = True  # Enter at 100

        strategy = CompiledStrategy(
            entry_fn=lambda b, ind: entry_signals,
            exit_fn=lambda b, ind: np.zeros((1, num_bars), dtype=bool),
            stop_loss_pct=5.0,  # 5% stop loss
        )

        result = engine.run(bars, strategy, ["AAPL"])

        # Should have at least one trade (entry + stop loss exit or end-of-period)
        assert len(result.trades) >= 1

    def test_run_with_take_profit(self, engine):
        """Test run with take profit."""
        num_bars = 10
        # Prices rise after entry
        prices = np.array([100.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 135.0, 140.0])

        bars = {
            "timestamps": np.array([datetime(2024, 1, i + 1, tzinfo=UTC) for i in range(num_bars)]),
            "opens": prices.reshape(1, -1),
            "highs": (prices * 1.02).reshape(1, -1),
            "lows": (prices * 0.98).reshape(1, -1),
            "closes": prices.reshape(1, -1),
            "volumes": np.full((1, num_bars), 10000.0),
        }

        entry_signals = np.zeros((1, num_bars), dtype=bool)
        entry_signals[0, 0] = True  # Enter at 100

        strategy = CompiledStrategy(
            entry_fn=lambda b, ind: entry_signals,
            exit_fn=lambda b, ind: np.zeros((1, num_bars), dtype=bool),
            take_profit_pct=15.0,  # 15% take profit
        )

        result = engine.run(bars, strategy, ["AAPL"])

        assert len(result.trades) >= 1

    def test_equity_curve_length(self, engine, sample_bars):
        """Test that equity curve has correct length."""
        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
            exit_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        assert len(result.equity_curve) == 30

    def test_daily_returns_computed(self, engine, sample_bars):
        """Test that daily returns are computed."""
        entry_signals = np.zeros((1, 30), dtype=bool)
        entry_signals[0, 0] = True

        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: entry_signals,
            exit_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
            position_size_pct=50.0,
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        # Should have daily returns (n-1 returns for n bars)
        assert len(result.daily_returns) == 29

    def test_monthly_returns_computed(self, engine, sample_bars):
        """Test that monthly returns are computed."""
        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
            exit_fn=lambda bars, ind: np.zeros((1, 30), dtype=bool),
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        # Should have at least one month
        assert isinstance(result.monthly_returns, dict)

    def test_exposure_time_computed(self, engine, sample_bars):
        """Test that exposure time is computed correctly."""
        # Entry on bar 0, hold until bar 15
        entry_signals = np.zeros((1, 30), dtype=bool)
        exit_signals = np.zeros((1, 30), dtype=bool)
        entry_signals[0, 0] = True
        exit_signals[0, 15] = True

        strategy = CompiledStrategy(
            entry_fn=lambda bars, ind: entry_signals,
            exit_fn=lambda bars, ind: exit_signals,
        )

        result = engine.run(sample_bars, strategy, ["AAPL"])

        # Should have positive exposure time
        assert result.exposure_time > 0
        assert result.exposure_time <= 100  # Percentage

    def test_trade_pnl_calculated(self, engine):
        """Test that trade PnL is calculated correctly."""
        num_bars = 5
        prices = np.array([100.0, 110.0, 120.0, 130.0, 140.0])

        bars = {
            "timestamps": np.array([datetime(2024, 1, i + 1, tzinfo=UTC) for i in range(num_bars)]),
            "opens": prices.reshape(1, -1),
            "highs": prices.reshape(1, -1),
            "lows": prices.reshape(1, -1),
            "closes": prices.reshape(1, -1),
            "volumes": np.full((1, num_bars), 10000.0),
        }

        entry_signals = np.zeros((1, num_bars), dtype=bool)
        exit_signals = np.zeros((1, num_bars), dtype=bool)
        entry_signals[0, 0] = True  # Enter at 100
        exit_signals[0, 3] = True  # Exit at 130

        strategy = CompiledStrategy(
            entry_fn=lambda b, ind: entry_signals,
            exit_fn=lambda b, ind: exit_signals,
            position_size_pct=10.0,
        )

        result = engine.run(bars, strategy, ["AAPL"])

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_price == 100.0
        assert trade.exit_price == 130.0
        assert trade.pnl > 0  # Should be profitable


class TestApplyRiskExits:
    """Tests for _apply_risk_exits method."""

    @pytest.fixture
    def engine(self):
        return VectorizedBacktestEngine()

    def test_stop_loss_trigger(self, engine):
        """Test stop loss exit signals."""
        num_bars = 5
        exit_signals = np.zeros((1, num_bars), dtype=bool)
        closes = np.array([[100, 95, 90, 85, 80]])  # Prices falling
        entry_prices = np.full((1, num_bars), 100.0)  # Entered at 100
        positions = np.ones((1, num_bars))  # In position throughout

        result = engine._apply_risk_exits(
            exit_signals, closes, entry_prices, positions, stop_loss_pct=10.0, take_profit_pct=None
        )

        # Should trigger exit when price drops 10%+ (at 90 or below)
        assert result[0, 2] is True or result[0, 2]  # At price 90
        assert result[0, 3] is True or result[0, 3]  # At price 85
        assert result[0, 4] is True or result[0, 4]  # At price 80

    def test_take_profit_trigger(self, engine):
        """Test take profit exit signals."""
        num_bars = 5
        exit_signals = np.zeros((1, num_bars), dtype=bool)
        closes = np.array([[100, 105, 115, 125, 130]])  # Prices rising
        entry_prices = np.full((1, num_bars), 100.0)  # Entered at 100
        positions = np.ones((1, num_bars))  # In position throughout

        result = engine._apply_risk_exits(
            exit_signals, closes, entry_prices, positions, stop_loss_pct=None, take_profit_pct=15.0
        )

        # Should trigger exit when price rises 15%+ (at 115 or above)
        assert result[0, 2] is True or result[0, 2]  # At price 115
        assert result[0, 3] is True or result[0, 3]  # At price 125


class TestCalculateMetrics:
    """Tests for _calculate_metrics method."""

    @pytest.fixture
    def engine(self):
        return VectorizedBacktestEngine()

    def test_empty_equity(self, engine):
        """Test with empty equity array."""
        result = engine._calculate_metrics(
            trades=[],
            equity_curve=[],
            equity=np.array([]),
            initial_capital=100000,
            days_with_position=0,
            total_days=0,
            risk_free_rate=0.02,
        )

        assert result.final_equity == 0
        assert result.total_return == 0

    def test_basic_metrics(self, engine):
        """Test basic metrics calculation."""
        equity = np.array([100000, 101000, 102000, 101500, 103000])
        equity_curve = [
            (datetime(2024, 1, i + 1, tzinfo=UTC), float(equity[i])) for i in range(len(equity))
        ]

        result = engine._calculate_metrics(
            trades=[],
            equity_curve=equity_curve,
            equity=equity,
            initial_capital=100000,
            days_with_position=3,
            total_days=5,
            risk_free_rate=0.02,
        )

        assert result.final_equity == 103000
        assert result.total_return == pytest.approx(0.03, rel=0.01)
        assert result.exposure_time == pytest.approx(60.0, rel=0.01)

    def test_max_drawdown(self, engine):
        """Test max drawdown calculation."""
        # Peak at 120000, trough at 100000
        equity = np.array([100000, 110000, 120000, 105000, 100000, 110000])
        equity_curve = [
            (datetime(2024, 1, i + 1, tzinfo=UTC), float(equity[i])) for i in range(len(equity))
        ]

        result = engine._calculate_metrics(
            trades=[],
            equity_curve=equity_curve,
            equity=equity,
            initial_capital=100000,
            days_with_position=0,
            total_days=6,
            risk_free_rate=0.02,
        )

        # Max drawdown: (120000 - 100000) / 120000 = 16.67%
        assert result.max_drawdown == pytest.approx(0.1667, rel=0.01)

    def test_win_rate_and_profit_factor(self, engine):
        """Test win rate and profit factor."""
        trades = [
            Trade(
                entry_date=datetime(2024, 1, 1, tzinfo=UTC),
                exit_date=datetime(2024, 1, 2, tzinfo=UTC),
                symbol="AAPL",
                side="long",
                entry_price=100,
                exit_price=110,
                quantity=10,
                commission=0,
            ),  # Win: $100
            Trade(
                entry_date=datetime(2024, 1, 3, tzinfo=UTC),
                exit_date=datetime(2024, 1, 4, tzinfo=UTC),
                symbol="AAPL",
                side="long",
                entry_price=100,
                exit_price=95,
                quantity=10,
                commission=0,
            ),  # Loss: -$50
        ]

        equity = np.array([100000, 100100, 100050])
        equity_curve = [
            (datetime(2024, 1, i + 1, tzinfo=UTC), float(equity[i])) for i in range(len(equity))
        ]

        result = engine._calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            equity=equity,
            initial_capital=100000,
            days_with_position=2,
            total_days=3,
            risk_free_rate=0.02,
        )

        assert result.win_rate == 0.5  # 1 win, 1 loss
        assert result.profit_factor == 2.0  # $100 win / $50 loss


class TestIdxToDatetime:
    """Tests for _idx_to_datetime helper method."""

    @pytest.fixture
    def engine(self):
        return VectorizedBacktestEngine()

    def test_numpy_datetime64(self, engine):
        """Test conversion of numpy datetime64."""
        timestamps = np.array(
            [
                np.datetime64("2024-01-01"),
                np.datetime64("2024-01-02"),
            ]
        )

        result = engine._idx_to_datetime(timestamps, 0)
        assert isinstance(result, datetime)

    def test_python_datetime(self, engine):
        """Test passthrough of Python datetime."""
        timestamps = np.array(
            [
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 2, tzinfo=UTC),
            ]
        )

        result = engine._idx_to_datetime(timestamps, 1)
        assert result == datetime(2024, 1, 2, tzinfo=UTC)
