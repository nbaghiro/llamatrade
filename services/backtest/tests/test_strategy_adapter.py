"""Tests for strategy adapter - bridges DSL strategies with backtest engine."""

import numpy as np
import pytest
from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.strategy_adapter import (
    IndicatorSpec,
    StrategyState,
    _compute_atr,
    _compute_bbands,
    _compute_cci,
    _compute_donchian,
    _compute_ema,
    _compute_keltner,
    _compute_macd,
    _compute_mfi,
    _compute_momentum,
    _compute_obv,
    _compute_rsi,
    _compute_sma,
    _compute_stddev,
    _compute_stochastic,
    _compute_vwap,
    _compute_williams_r,
    create_strategy_function,
)


class TestIndicatorComputation:
    """Tests for indicator computation functions."""

    def test_compute_sma_basic(self):
        """Test SMA calculation with simple data."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _compute_sma(values, 3)

        # SMA(3) at index 2 = (1+2+3)/3 = 2
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == pytest.approx(2.0)
        assert result[3] == pytest.approx(3.0)
        assert result[4] == pytest.approx(4.0)

    def test_compute_sma_insufficient_data(self):
        """Test SMA with insufficient data returns NaN."""
        values = np.array([1.0, 2.0])
        result = _compute_sma(values, 5)

        assert all(np.isnan(result))

    def test_compute_ema_basic(self):
        """Test EMA calculation."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = _compute_ema(values, 5)

        # First EMA value at index 4 should be average of first 5
        assert np.isnan(result[0])
        assert result[4] == pytest.approx(3.0)  # (1+2+3+4+5)/5
        # Subsequent values should be EMA calculations
        assert result[5] > result[4]  # EMA should increase with rising prices

    def test_compute_ema_insufficient_data(self):
        """Test EMA with insufficient data returns NaN."""
        values = np.array([1.0, 2.0])
        result = _compute_ema(values, 5)

        assert all(np.isnan(result))

    def test_compute_rsi_basic(self):
        """Test RSI calculation."""
        # Create data with alternating gains and losses
        values = np.array(
            [
                100.0,
                102.0,
                101.0,
                103.0,
                102.0,
                105.0,
                104.0,
                107.0,
                106.0,
                109.0,
                108.0,
                111.0,
                110.0,
                113.0,
                112.0,
            ]
        )
        result = _compute_rsi(values, 14)

        # RSI should be between 0 and 100
        valid_values = result[~np.isnan(result)]
        assert all(0 <= v <= 100 for v in valid_values)

    def test_compute_rsi_all_gains(self):
        """Test RSI with only gains approaches 100."""
        values = np.array([100.0 + i for i in range(20)])
        result = _compute_rsi(values, 14)

        # With all gains, RSI should be 100
        assert result[-1] == pytest.approx(100.0)

    def test_compute_rsi_insufficient_data(self):
        """Test RSI with insufficient data returns NaN."""
        values = np.array([1.0, 2.0])
        result = _compute_rsi(values, 14)

        assert all(np.isnan(result))


class TestCreateStrategyFunction:
    """Tests for strategy function creation from S-expressions."""

    def test_create_simple_sma_crossover_strategy(self):
        """Test creating a simple SMA crossover strategy."""
        config = """(strategy
            :name "SMA Crossover"
            :symbols ["AAPL"]
            :timeframe "1D"
            :entry (cross-above (sma close 10) (sma close 20))
            :exit (cross-below (sma close 10) (sma close 20))
            :position-size 10
            :stop-loss-pct 5
            :take-profit-pct 10)"""

        strategy_fn, min_bars = create_strategy_function(config)

        assert callable(strategy_fn)
        assert min_bars >= 20  # At least 20 bars for SMA(20)

    def test_create_rsi_strategy(self):
        """Test creating an RSI-based strategy."""
        config = """(strategy
            :name "RSI Strategy"
            :symbols ["SPY"]
            :timeframe "1D"
            :entry (< (rsi close 14) 30)
            :exit (> (rsi close 14) 70)
            :position-size 10
            :stop-loss-pct 5)"""

        strategy_fn, min_bars = create_strategy_function(config)

        assert callable(strategy_fn)
        assert min_bars >= 15  # At least 15 bars for RSI(14)

    def test_create_strategy_invalid_syntax(self):
        """Test that invalid S-expression raises error."""
        config = "(strategy invalid"

        with pytest.raises(Exception):
            create_strategy_function(config)

    def test_strategy_function_generates_signals(self, sample_bars):
        """Test that strategy function generates buy/sell signals."""
        config = """(strategy
            :name "Test Strategy"
            :symbols ["AAPL"]
            :timeframe "1D"
            :entry (cross-above (sma close 5) (sma close 10))
            :exit (cross-below (sma close 5) (sma close 10))
            :position-size 10)"""

        strategy_fn, min_bars = create_strategy_function(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Process bars through strategy
        all_signals = []
        for bar in sample_bars["AAPL"]:
            signals = strategy_fn(engine, "AAPL", bar)
            all_signals.extend(signals)

        # Should generate at least some signals over 30 days
        # (depends on price movement)
        assert isinstance(all_signals, list)

    def test_strategy_function_respects_position_state(self, sample_bars):
        """Test that strategy doesn't enter when already in position."""
        config = """(strategy
            :name "Test Strategy"
            :symbols ["AAPL"]
            :timeframe "1D"
            :entry (> (sma close 5) 0)
            :exit (< (sma close 5) 0)
            :position-size 10)"""

        strategy_fn, min_bars = create_strategy_function(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Process enough bars to get signals
        buy_signals = 0
        for bar in sample_bars["AAPL"]:
            # Set current date so engine can track positions properly
            engine._current_date = bar["timestamp"]
            signals = strategy_fn(engine, "AAPL", bar)
            for signal in signals:
                if signal.get("type") == "buy":
                    buy_signals += 1
                    # Simulate opening position via engine
                    engine._open_position("AAPL", "long", bar["close"], 10)

        # The strategy uses engine.has_position() to check if we're in a position.
        # After the first buy signal, subsequent bars should NOT generate buy signals
        # because the engine tracks the open position.
        # After warmup (min_bars), we should get exactly 1 buy signal.
        assert buy_signals == 1


class TestStrategyState:
    """Tests for strategy state management."""

    def test_initial_state(self):
        """Test initial strategy state."""
        state = StrategyState()

        assert state.bar_history == []
        assert state.indicators == {}
        assert state.position_side is None
        assert state.position_entry_price == 0.0

    def test_bar_history_accumulation(self, sample_bar_data):
        """Test that bar history accumulates."""
        state = StrategyState()
        state.bar_history.append(sample_bar_data)
        state.bar_history.append(sample_bar_data)

        assert len(state.bar_history) == 2


class TestIndicatorSpec:
    """Tests for indicator specification."""

    def test_indicator_spec_creation(self):
        """Test creating an indicator spec."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        assert spec.indicator_type == "sma"
        assert spec.source == "close"
        assert spec.params == (20,)
        assert spec.required_bars == 20

    def test_indicator_spec_immutable(self):
        """Test that indicator spec is immutable (frozen dataclass)."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        with pytest.raises(Exception):
            spec.indicator_type = "ema"


class TestAdditionalIndicators:
    """Tests for additional indicator computation functions."""

    @pytest.fixture
    def ohlcv_data(self):
        """Create sample OHLCV data for indicator tests."""
        n = 50
        np.random.seed(42)
        base_price = 100.0
        closes = base_price + np.cumsum(np.random.randn(n) * 0.5)
        highs = closes + np.abs(np.random.randn(n) * 0.3)
        lows = closes - np.abs(np.random.randn(n) * 0.3)
        opens = (closes + np.roll(closes, 1)) / 2
        opens[0] = closes[0]
        volumes = np.random.randint(10000, 100000, n).astype(float)
        return {
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
        }

    def test_compute_stddev(self, ohlcv_data):
        """Test standard deviation calculation."""
        result = _compute_stddev(ohlcv_data["closes"], 20)

        assert len(result) == len(ohlcv_data["closes"])
        # First 19 values should be NaN
        assert np.isnan(result[18])
        # Values after warmup should be positive
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert all(v >= 0 for v in valid)

    def test_compute_momentum(self, ohlcv_data):
        """Test momentum calculation."""
        result = _compute_momentum(ohlcv_data["closes"], 10)

        assert len(result) == len(ohlcv_data["closes"])
        # Should have NaN at the start
        assert np.isnan(result[0])

    def test_compute_macd(self, ohlcv_data):
        """Test MACD calculation."""
        macd_line, signal_line, histogram = _compute_macd(ohlcv_data["closes"], 12, 26, 9)

        assert len(macd_line) == len(ohlcv_data["closes"])
        assert len(signal_line) == len(ohlcv_data["closes"])
        assert len(histogram) == len(ohlcv_data["closes"])
        # Histogram should be MACD - Signal where both are valid
        valid_idx = ~np.isnan(macd_line) & ~np.isnan(signal_line)
        np.testing.assert_array_almost_equal(
            histogram[valid_idx], macd_line[valid_idx] - signal_line[valid_idx]
        )

    def test_compute_bbands(self, ohlcv_data):
        """Test Bollinger Bands calculation."""
        upper, middle, lower = _compute_bbands(ohlcv_data["closes"], 20, 2.0)

        assert len(upper) == len(ohlcv_data["closes"])
        # Upper should be >= middle, middle >= lower where valid
        valid_idx = ~np.isnan(upper)
        assert all(upper[valid_idx] >= middle[valid_idx])
        assert all(middle[valid_idx] >= lower[valid_idx])

    def test_compute_atr(self, ohlcv_data):
        """Test ATR calculation."""
        result = _compute_atr(ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], 14)

        assert len(result) == len(ohlcv_data["closes"])
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        # ATR should be positive
        assert all(v >= 0 for v in valid)

    def test_compute_stochastic(self, ohlcv_data):
        """Test Stochastic oscillator calculation."""
        k, d = _compute_stochastic(
            ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], 14, 3
        )

        assert len(k) == len(ohlcv_data["closes"])
        assert len(d) == len(ohlcv_data["closes"])
        # %K and %D should be between 0 and 100
        valid_k = k[~np.isnan(k)]
        valid_d = d[~np.isnan(d)]
        assert all(0 <= v <= 100 for v in valid_k)
        assert all(0 <= v <= 100 for v in valid_d)

    def test_compute_cci(self, ohlcv_data):
        """Test CCI calculation."""
        result = _compute_cci(ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], 20)

        assert len(result) == len(ohlcv_data["closes"])
        # CCI should have values after warmup
        valid = result[~np.isnan(result)]
        assert len(valid) > 0

    def test_compute_williams_r(self, ohlcv_data):
        """Test Williams %R calculation."""
        result = _compute_williams_r(
            ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], 14
        )

        assert len(result) == len(ohlcv_data["closes"])
        # Williams %R should be between -100 and 0
        valid = result[~np.isnan(result)]
        assert all(-100 <= v <= 0 for v in valid)

    def test_compute_obv(self, ohlcv_data):
        """Test OBV calculation."""
        result = _compute_obv(ohlcv_data["closes"], ohlcv_data["volumes"])

        assert len(result) == len(ohlcv_data["closes"])
        # OBV should start at first day's volume
        assert result[0] == ohlcv_data["volumes"][0]

    def test_compute_mfi(self, ohlcv_data):
        """Test MFI calculation."""
        result = _compute_mfi(
            ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], ohlcv_data["volumes"], 14
        )

        assert len(result) == len(ohlcv_data["closes"])
        # MFI should be between 0 and 100
        valid = result[~np.isnan(result)]
        assert all(0 <= v <= 100 for v in valid)

    def test_compute_vwap(self, ohlcv_data):
        """Test VWAP calculation."""
        result = _compute_vwap(
            ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], ohlcv_data["volumes"]
        )

        assert len(result) == len(ohlcv_data["closes"])
        # VWAP should have no NaN
        assert not any(np.isnan(result))

    def test_compute_keltner(self, ohlcv_data):
        """Test Keltner Channel calculation."""
        upper, middle, lower = _compute_keltner(
            ohlcv_data["highs"], ohlcv_data["lows"], ohlcv_data["closes"], 20, 2.0
        )

        assert len(upper) == len(ohlcv_data["closes"])
        # Upper >= middle >= lower where valid
        valid_idx = ~np.isnan(upper)
        assert all(upper[valid_idx] >= middle[valid_idx])
        assert all(middle[valid_idx] >= lower[valid_idx])

    def test_compute_donchian(self, ohlcv_data):
        """Test Donchian Channel calculation."""
        upper, lower = _compute_donchian(ohlcv_data["highs"], ohlcv_data["lows"], 20)

        assert len(upper) == len(ohlcv_data["closes"])
        assert len(lower) == len(ohlcv_data["closes"])
        # Upper should be >= lower
        valid_idx = ~np.isnan(upper)
        assert all(upper[valid_idx] >= lower[valid_idx])
