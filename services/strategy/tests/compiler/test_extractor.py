"""Tests for the indicator extractor module."""

import pytest
from llamatrade_dsl import parse_strategy
from src.compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
)

# Sample strategies for testing
SIMPLE_SMA_STRATEGY = """
(strategy
  :name "SMA Crossover"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (cross-above (sma close 20) (sma close 50))
  :exit (cross-below (sma close 20) (sma close 50)))
"""

MULTI_INDICATOR_STRATEGY = """
(strategy
  :name "Multi Indicator"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (and
    (> (rsi close 14) 30)
    (cross-above (macd close 12 26 9 :line) 0))
  :exit (or
    (< (rsi close 14) 70)
    (cross-below (macd close 12 26 9 :line) 0)))
"""

BOLLINGER_STRATEGY = """
(strategy
  :name "Bollinger Bounce"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (< close (bbands close 20 2.0 :lower))
  :exit (> close (bbands close 20 2.0 :upper)))
"""

VOLUME_STRATEGY = """
(strategy
  :name "Volume Based"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (and
    (> (obv) (sma (obv) 20))
    (> (mfi close 14) 20))
  :exit (< (mfi close 14) 80))
"""


class TestExtractIndicators:
    """Tests for extract_indicators function."""

    def test_extract_simple_sma(self) -> None:
        """Test extracting SMA indicators."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 2

        # Check SMA 20
        sma_20 = next((i for i in indicators if "20" in i.output_key), None)
        assert sma_20 is not None
        assert sma_20.indicator_type == "sma"
        assert sma_20.source == "close"
        assert sma_20.params == (20,)
        assert sma_20.output_key == "sma_close_20"

        # Check SMA 50
        sma_50 = next((i for i in indicators if "50" in i.output_key), None)
        assert sma_50 is not None
        assert sma_50.indicator_type == "sma"
        assert sma_50.source == "close"
        assert sma_50.params == (50,)
        assert sma_50.output_key == "sma_close_50"

    def test_extract_multi_output_indicator(self) -> None:
        """Test extracting indicator with output field selector."""
        strategy = parse_strategy(MULTI_INDICATOR_STRATEGY)
        indicators = extract_indicators(strategy)

        # Find MACD indicator
        macd = next((i for i in indicators if i.indicator_type == "macd"), None)
        assert macd is not None
        assert macd.source == "close"
        assert macd.params == (12, 26, 9)
        assert macd.output_field == "line"
        assert "line" in macd.output_key

    def test_extract_rsi(self) -> None:
        """Test extracting RSI indicator."""
        strategy = parse_strategy(MULTI_INDICATOR_STRATEGY)
        indicators = extract_indicators(strategy)

        rsi = next((i for i in indicators if i.indicator_type == "rsi"), None)
        assert rsi is not None
        assert rsi.source == "close"
        assert rsi.params == (14,)
        assert rsi.output_key == "rsi_close_14"

    def test_extract_bollinger_bands(self) -> None:
        """Test extracting Bollinger Bands with multiple outputs."""
        strategy = parse_strategy(BOLLINGER_STRATEGY)
        indicators = extract_indicators(strategy)

        # Should have lower and upper bands
        lower = next((i for i in indicators if i.output_field == "lower"), None)
        upper = next((i for i in indicators if i.output_field == "upper"), None)

        assert lower is not None
        assert lower.indicator_type == "bbands"
        assert lower.params == (20, 2.0)

        assert upper is not None
        assert upper.indicator_type == "bbands"
        assert upper.params == (20, 2.0)

    def test_deduplication(self) -> None:
        """Test that same indicator used twice is deduplicated."""
        # RSI appears in both entry and exit with same params
        strategy = parse_strategy(MULTI_INDICATOR_STRATEGY)
        indicators = extract_indicators(strategy)

        rsi_count = sum(1 for i in indicators if i.indicator_type == "rsi")
        assert rsi_count == 1

    def test_extract_volume_indicators(self) -> None:
        """Test extracting volume-based indicators."""
        strategy = parse_strategy(VOLUME_STRATEGY)
        indicators = extract_indicators(strategy)

        obv = next((i for i in indicators if i.indicator_type == "obv"), None)
        mfi = next((i for i in indicators if i.indicator_type == "mfi"), None)

        assert obv is not None
        assert mfi is not None
        assert mfi.params == (14,)


class TestIndicatorSpec:
    """Tests for IndicatorSpec dataclass."""

    def test_str_representation(self) -> None:
        """Test string representation of IndicatorSpec."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )
        assert str(spec) == "sma(close, (20,))"

    def test_str_with_output_field(self) -> None:
        """Test string representation with output field."""
        spec = IndicatorSpec(
            indicator_type="macd",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_signal",
            output_field="signal",
            required_bars=26,
        )
        assert str(spec) == "macd(close, (12, 26, 9)):signal"

    def test_frozen_dataclass(self) -> None:
        """Test that IndicatorSpec is immutable."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )
        with pytest.raises(AttributeError):
            spec.indicator_type = "ema"  # type: ignore


class TestGetMaxLookback:
    """Tests for get_max_lookback function."""

    def test_single_indicator(self) -> None:
        """Test max lookback with single indicator."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            )
        ]
        assert get_max_lookback(indicators) == 20

    def test_multiple_indicators(self) -> None:
        """Test max lookback picks the largest."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            ),
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(50,),
                output_key="sma_close_50",
                output_field=None,
                required_bars=50,
            ),
        ]
        assert get_max_lookback(indicators) == 50

    def test_empty_list(self) -> None:
        """Test max lookback with empty list."""
        assert get_max_lookback([]) == 0


class TestGetRequiredSources:
    """Tests for get_required_sources function."""

    def test_close_only(self) -> None:
        """Test sources for close-only indicators."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            )
        ]
        sources = get_required_sources(indicators)
        assert sources == {"close"}

    def test_hlc_indicator(self) -> None:
        """Test sources for ATR (needs H, L, C)."""
        indicators = [
            IndicatorSpec(
                indicator_type="atr",
                source="close",
                params=(14,),
                output_key="atr_close_14",
                output_field=None,
                required_bars=15,
            )
        ]
        sources = get_required_sources(indicators)
        assert "high" in sources
        assert "low" in sources
        assert "close" in sources

    def test_volume_indicator(self) -> None:
        """Test sources for volume-based indicators."""
        indicators = [
            IndicatorSpec(
                indicator_type="obv",
                source="close",
                params=(),
                output_key="obv_close",
                output_field=None,
                required_bars=1,
            )
        ]
        sources = get_required_sources(indicators)
        assert "volume" in sources

    def test_combined_sources(self) -> None:
        """Test combining sources from multiple indicators."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            ),
            IndicatorSpec(
                indicator_type="sma",
                source="volume",
                params=(20,),
                output_key="sma_volume_20",
                output_field=None,
                required_bars=20,
            ),
        ]
        sources = get_required_sources(indicators)
        assert "close" in sources
        assert "volume" in sources
