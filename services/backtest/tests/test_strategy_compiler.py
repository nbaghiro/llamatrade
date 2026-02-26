"""Tests for strategy compiler module."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestBuildIndicatorKey:
    """Tests for _build_indicator_key function."""

    def test_basic_key(self):
        """Test building basic indicator key."""
        from src.engine.strategy_compiler import _build_indicator_key

        key = _build_indicator_key("sma", "close", [20], None)
        assert key == "sma_close_20"

    def test_key_with_multiple_params(self):
        """Test building key with multiple parameters."""
        from src.engine.strategy_compiler import _build_indicator_key

        key = _build_indicator_key("macd", "close", [12, 26, 9], None)
        assert key == "macd_close_12_26_9"

    def test_key_with_output_field(self):
        """Test building key with output field."""
        from src.engine.strategy_compiler import _build_indicator_key

        key = _build_indicator_key("bbands", "close", [20, 2.0], "upper")
        assert key == "bbands_close_20_2.0_upper"

    def test_key_with_different_source(self):
        """Test building key with different source."""
        from src.engine.strategy_compiler import _build_indicator_key

        key = _build_indicator_key("sma", "high", [10], None)
        assert key == "sma_high_10"


class TestShouldUseVectorizedEngine:
    """Tests for should_use_vectorized_engine function."""

    def test_below_threshold(self):
        """Test returns False below threshold."""
        from src.engine.strategy_compiler import should_use_vectorized_engine

        result = should_use_vectorized_engine(5, 1000, threshold=10000)
        assert result is False

    def test_at_threshold(self):
        """Test returns False at exactly threshold."""
        from src.engine.strategy_compiler import should_use_vectorized_engine

        result = should_use_vectorized_engine(100, 100, threshold=10000)
        assert result is False

    def test_above_threshold(self):
        """Test returns True above threshold."""
        from src.engine.strategy_compiler import should_use_vectorized_engine

        result = should_use_vectorized_engine(100, 200, threshold=10000)
        assert result is True

    def test_default_threshold(self):
        """Test with default threshold."""
        from src.engine.strategy_compiler import should_use_vectorized_engine

        # 5 symbols * 3000 bars = 15000 > default 10000
        result = should_use_vectorized_engine(5, 3000)
        assert result is True


class TestComputeSingleIndicator:
    """Tests for _compute_single_indicator function."""

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data."""
        n = 100
        return {
            "source": np.linspace(100, 110, n),
            "highs": np.linspace(102, 112, n),
            "lows": np.linspace(98, 108, n),
            "closes": np.linspace(100, 110, n),
            "volumes": np.full(n, 10000.0),
        }

    def test_sma_indicator(self, sample_data):
        """Test SMA indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "sma",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            None,
        )

        assert len(result) == len(sample_data["source"])
        # First 19 values should be NaN (not enough data for SMA-20)
        assert np.isnan(result[18])
        # From index 19 onwards should have values
        assert not np.isnan(result[19])

    def test_ema_indicator(self, sample_data):
        """Test EMA indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "ema",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_rsi_indicator(self, sample_data):
        """Test RSI indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "rsi",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,
        )

        assert len(result) == len(sample_data["source"])
        # RSI should be between 0 and 100 (excluding NaN)
        valid = result[~np.isnan(result)]
        if len(valid) > 0:
            assert valid.min() >= 0
            assert valid.max() <= 100

    def test_macd_line(self, sample_data):
        """Test MACD line computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "macd",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [12, 26, 9],
            None,  # Default: MACD line
        )

        assert len(result) == len(sample_data["source"])

    def test_macd_signal(self, sample_data):
        """Test MACD signal line computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "macd",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [12, 26, 9],
            "signal",
        )

        assert len(result) == len(sample_data["source"])

    def test_macd_histogram(self, sample_data):
        """Test MACD histogram computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "macd",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [12, 26, 9],
            "histogram",
        )

        assert len(result) == len(sample_data["source"])

    def test_bbands_middle(self, sample_data):
        """Test Bollinger Bands middle computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "bbands",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20, 2.0],
            None,  # Default: middle band
        )

        assert len(result) == len(sample_data["source"])

    def test_bbands_upper(self, sample_data):
        """Test Bollinger Bands upper computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "bbands",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20, 2.0],
            "upper",
        )

        assert len(result) == len(sample_data["source"])

    def test_bbands_lower(self, sample_data):
        """Test Bollinger Bands lower computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "bbands",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20, 2.0],
            "lower",
        )

        assert len(result) == len(sample_data["source"])

    def test_atr_indicator(self, sample_data):
        """Test ATR indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "atr",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_adx_indicator(self, sample_data):
        """Test ADX indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "adx",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,  # Default: ADX
        )

        assert len(result) == len(sample_data["source"])

    def test_adx_plus_di(self, sample_data):
        """Test ADX +DI computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "adx",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            "plus_di",
        )

        assert len(result) == len(sample_data["source"])

    def test_stochastic_k(self, sample_data):
        """Test Stochastic %K computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "stoch",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14, 3],
            None,  # Default: %K
        )

        assert len(result) == len(sample_data["source"])

    def test_stochastic_d(self, sample_data):
        """Test Stochastic %D computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "stoch",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14, 3],
            "d",
        )

        assert len(result) == len(sample_data["source"])

    def test_cci_indicator(self, sample_data):
        """Test CCI indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "cci",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_williams_r_indicator(self, sample_data):
        """Test Williams %R indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "williams-r",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_obv_indicator(self, sample_data):
        """Test OBV indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "obv",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_mfi_indicator(self, sample_data):
        """Test MFI indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "mfi",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [14],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_vwap_indicator(self, sample_data):
        """Test VWAP indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "vwap",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_keltner_middle(self, sample_data):
        """Test Keltner Channel middle computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "keltner",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20, 2.0],
            None,  # Default: middle
        )

        assert len(result) == len(sample_data["source"])

    def test_keltner_upper(self, sample_data):
        """Test Keltner Channel upper computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "keltner",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20, 2.0],
            "upper",
        )

        assert len(result) == len(sample_data["source"])

    def test_donchian_upper(self, sample_data):
        """Test Donchian Channel upper computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "donchian",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            None,  # Default: upper
        )

        assert len(result) == len(sample_data["source"])

    def test_donchian_lower(self, sample_data):
        """Test Donchian Channel lower computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "donchian",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            "lower",
        )

        assert len(result) == len(sample_data["source"])

    def test_stddev_indicator(self, sample_data):
        """Test StdDev indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "stddev",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_momentum_indicator(self, sample_data):
        """Test Momentum indicator computation."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "momentum",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [10],
            None,
        )

        assert len(result) == len(sample_data["source"])

    def test_unknown_indicator_fallback(self, sample_data):
        """Test unknown indicator falls back to SMA."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "unknown_indicator",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [20],
            None,
        )

        # Should fall back to SMA
        assert len(result) == len(sample_data["source"])

    def test_default_period(self, sample_data):
        """Test default period when no params provided."""
        from src.engine.strategy_compiler import _compute_single_indicator

        result = _compute_single_indicator(
            "sma",
            sample_data["source"],
            sample_data["highs"],
            sample_data["lows"],
            sample_data["closes"],
            sample_data["volumes"],
            [],  # No params
            None,
        )

        # Should use default period of 14
        assert len(result) == len(sample_data["source"])


class TestEvaluateVectorized:
    """Tests for _evaluate_vectorized function."""

    @pytest.fixture
    def sample_bars(self):
        """Create sample vectorized bar data."""
        return {
            "opens": np.array([[100.0, 101.0, 102.0, 103.0, 104.0]]),
            "highs": np.array([[102.0, 103.0, 104.0, 105.0, 106.0]]),
            "lows": np.array([[98.0, 99.0, 100.0, 101.0, 102.0]]),
            "closes": np.array([[101.0, 102.0, 103.0, 104.0, 105.0]]),
            "volumes": np.array([[10000.0, 10100.0, 10200.0, 10300.0, 10400.0]]),
        }

    def test_literal_true(self, sample_bars):
        """Test evaluating literal True."""
        from llamatrade_dsl.ast import Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = Literal(value=True)
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.shape == (1, 5)
        assert result.all()

    def test_literal_false(self, sample_bars):
        """Test evaluating literal False."""
        from llamatrade_dsl.ast import Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = Literal(value=False)
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.shape == (1, 5)
        assert not result.any()

    def test_and_operation(self, sample_bars):
        """Test evaluating AND operation."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name="and",
            args=[Literal(value=True), Literal(value=True)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.all()

    def test_and_operation_mixed(self, sample_bars):
        """Test evaluating AND with mixed values."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name="and",
            args=[Literal(value=True), Literal(value=False)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert not result.any()

    def test_or_operation(self, sample_bars):
        """Test evaluating OR operation."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name="or",
            args=[Literal(value=False), Literal(value=True)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.all()

    def test_not_operation(self, sample_bars):
        """Test evaluating NOT operation."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name="not",
            args=[Literal(value=True)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert not result.any()

    def test_greater_than_comparison(self, sample_bars):
        """Test > comparison."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name=">",
            args=[Literal(value=105.0), Literal(value=100.0)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.all()

    def test_less_than_comparison(self, sample_bars):
        """Test < comparison."""
        from llamatrade_dsl.ast import FunctionCall, Literal
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(
            name="<",
            args=[Literal(value=95.0), Literal(value=100.0)],
        )
        result = _evaluate_vectorized(node, sample_bars, {})

        assert result.all()

    def test_has_position_returns_false(self, sample_bars):
        """Test has-position returns false array (handled at runtime)."""
        from llamatrade_dsl.ast import FunctionCall
        from src.engine.strategy_compiler import _evaluate_vectorized

        node = FunctionCall(name="has-position", args=[])
        result = _evaluate_vectorized(node, sample_bars, {})

        assert not result.any()


class TestGetVectorizedValue:
    """Tests for _get_vectorized_value function."""

    @pytest.fixture
    def sample_bars(self):
        """Create sample vectorized bar data."""
        return {
            "opens": np.array([[100.0, 101.0, 102.0]]),
            "highs": np.array([[105.0, 106.0, 107.0]]),
            "lows": np.array([[95.0, 96.0, 97.0]]),
            "closes": np.array([[102.0, 103.0, 104.0]]),
            "volumes": np.array([[10000, 10100, 10200]]),
        }

    def test_literal_value(self, sample_bars):
        """Test getting literal value."""
        from llamatrade_dsl.ast import Literal
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Literal(value=50.0)
        result = _get_vectorized_value(node, sample_bars, {})

        assert result.shape == (1, 3)
        np.testing.assert_array_equal(result, 50.0)

    def test_close_symbol(self, sample_bars):
        """Test getting close prices."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="close")
        result = _get_vectorized_value(node, sample_bars, {})

        np.testing.assert_array_equal(result, sample_bars["closes"])

    def test_open_symbol(self, sample_bars):
        """Test getting open prices."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="open")
        result = _get_vectorized_value(node, sample_bars, {})

        np.testing.assert_array_equal(result, sample_bars["opens"])

    def test_high_symbol(self, sample_bars):
        """Test getting high prices."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="high")
        result = _get_vectorized_value(node, sample_bars, {})

        np.testing.assert_array_equal(result, sample_bars["highs"])

    def test_low_symbol(self, sample_bars):
        """Test getting low prices."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="low")
        result = _get_vectorized_value(node, sample_bars, {})

        np.testing.assert_array_equal(result, sample_bars["lows"])

    def test_volume_symbol(self, sample_bars):
        """Test getting volumes."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="volume")
        result = _get_vectorized_value(node, sample_bars, {})

        assert result.dtype == float

    def test_unknown_symbol(self, sample_bars):
        """Test unknown symbol returns zeros."""
        from llamatrade_dsl.ast import Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        node = Symbol(name="unknown")
        result = _get_vectorized_value(node, sample_bars, {})

        assert result.shape == (1, 3)
        np.testing.assert_array_equal(result, 0.0)

    def test_indicator_from_cache(self, sample_bars):
        """Test getting indicator value from cache."""
        from llamatrade_dsl.ast import FunctionCall, Literal, Symbol
        from src.engine.strategy_compiler import _get_vectorized_value

        indicators = {
            "sma_close_20": np.array([[101.0, 102.0, 103.0]]),
        }

        node = FunctionCall(
            name="sma",
            args=[Symbol(name="close"), Literal(value=20)],
        )
        result = _get_vectorized_value(node, sample_bars, indicators)

        np.testing.assert_array_equal(result, indicators["sma_close_20"])


class TestCompileStrategy:
    """Tests for compile_strategy function."""

    def test_compile_valid_strategy(self):
        """Test compiling a valid strategy."""
        with (
            patch("src.engine.strategy_compiler.parse_strategy") as mock_parse,
            patch("src.engine.strategy_compiler.validate_strategy") as mock_validate,
        ):
            # Mock parsed strategy
            mock_strategy = MagicMock()
            mock_strategy.risk = {"stop_loss_pct": 5.0, "take_profit_pct": 10.0}
            mock_strategy.sizing = {"value": 15.0}
            mock_strategy.entry = MagicMock()
            mock_strategy.exit = MagicMock()

            mock_parse.return_value = mock_strategy
            mock_validate.return_value = MagicMock(valid=True)

            from src.engine.strategy_compiler import compile_strategy

            result = compile_strategy("(strategy ...)")

            assert result.position_size_pct == 15.0
            assert result.stop_loss_pct == 5.0
            assert result.take_profit_pct == 10.0

    def test_compile_invalid_strategy_raises(self):
        """Test that invalid strategy raises ValueError."""
        with (
            patch("src.engine.strategy_compiler.parse_strategy") as mock_parse,
            patch("src.engine.strategy_compiler.validate_strategy") as mock_validate,
        ):
            mock_strategy = MagicMock()
            mock_parse.return_value = mock_strategy

            mock_error = MagicMock()
            mock_error.__str__ = MagicMock(return_value="Test error")
            mock_validate.return_value = MagicMock(valid=False, errors=[mock_error])

            from src.engine.strategy_compiler import compile_strategy

            with pytest.raises(ValueError, match="Invalid strategy"):
                compile_strategy("(invalid ...)")
