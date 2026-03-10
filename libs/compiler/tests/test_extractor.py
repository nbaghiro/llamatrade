"""Tests for llamatrade_compiler.extractor module."""

import pytest

from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
    get_required_symbols,
)
from llamatrade_dsl import parse


class TestIndicatorSpec:
    """Tests for IndicatorSpec dataclass."""

    def test_indicator_spec_creation(self) -> None:
        """Test creating an IndicatorSpec."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="AAPL",
            source="close",
            params=(20,),
            output_key="sma_AAPL_close_20",
            output_field=None,
            required_bars=20,
        )

        assert spec.indicator_type == "sma"
        assert spec.symbol == "AAPL"
        assert spec.source == "close"
        assert spec.params == (20,)
        assert spec.output_key == "sma_AAPL_close_20"
        assert spec.output_field is None
        assert spec.required_bars == 20

    def test_indicator_spec_with_output_field(self) -> None:
        """Test creating an IndicatorSpec with output field."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="AAPL",
            source="close",
            params=(12, 26, 9),
            output_key="macd_AAPL_close_12_26_9_signal",
            output_field="signal",
            required_bars=26,
        )

        assert spec.output_field == "signal"

    def test_indicator_spec_str_without_output_field(self) -> None:
        """Test IndicatorSpec string representation without output field."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="AAPL",
            source="close",
            params=(20,),
            output_key="sma_AAPL_close_20",
            output_field=None,
            required_bars=20,
        )

        result = str(spec)
        assert result == "sma(AAPL, close, (20,))"

    def test_indicator_spec_str_with_output_field(self) -> None:
        """Test IndicatorSpec string representation with output field."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="AAPL",
            source="close",
            params=(12, 26, 9),
            output_key="macd_AAPL_close_12_26_9_signal",
            output_field="signal",
            required_bars=26,
        )

        result = str(spec)
        assert result == "macd(AAPL, close, (12, 26, 9)):signal"

    def test_indicator_spec_is_frozen(self) -> None:
        """Test IndicatorSpec is immutable."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="AAPL",
            source="close",
            params=(20,),
            output_key="sma_AAPL_close_20",
            output_field=None,
            required_bars=20,
        )

        with pytest.raises(AttributeError):
            spec.params = (10,)

    def test_indicator_spec_hashable(self) -> None:
        """Test IndicatorSpec is hashable."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="AAPL",
            source="close",
            params=(20,),
            output_key="sma_AAPL_close_20",
            output_field=None,
            required_bars=20,
        )

        # Should be hashable
        assert hash(spec) is not None
        specs_set = {spec}
        assert spec in specs_set


class TestExtractIndicators:
    """Tests for extract_indicators function."""

    def test_extract_single_indicator_from_condition(self) -> None:
        """Test extracting a single indicator from If condition."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi AAPL 14) 70)
                (asset TLT :weight 100)
                (else (asset AAPL :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 1
        assert indicators[0].indicator_type == "rsi"
        assert indicators[0].symbol == "AAPL"
        assert indicators[0].params == (14,)

    def test_extract_multiple_indicators(self) -> None:
        """Test extracting multiple different indicators."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (and
                    (> (sma AAPL 10) (sma AAPL 20))
                    (< (rsi AAPL 14) 70))
                (asset AAPL :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 3
        indicator_types = {i.indicator_type for i in indicators}
        assert indicator_types == {"sma", "rsi"}

    def test_extract_deduplicates_identical(self) -> None:
        """Test that identical indicators are deduplicated."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (and
                    (> (rsi AAPL 14) 30)
                    (< (rsi AAPL 14) 70))
                (asset AAPL :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        # Same RSI used twice - should only appear once
        assert len(indicators) == 1

    def test_extract_different_params_not_deduplicated(self) -> None:
        """Test that indicators with different params are not deduplicated."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (> (sma AAPL 10) (sma AAPL 20))
                (asset AAPL :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 2
        params_set = {i.params for i in indicators}
        assert params_set == {(10,), (20,)}

    def test_extract_crossover_indicators(self) -> None:
        """Test extracting indicators from crossover condition."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (crosses-above (sma SPY 50) (sma SPY 200))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 2
        params_set = {i.params for i in indicators}
        assert params_set == {(50,), (200,)}

    def test_extract_from_simple_strategy_no_indicators(self) -> None:
        """Test extracting from strategy with no indicators."""
        sexpr = """
        (strategy "Simple"
            :benchmark SPY
            :rebalance monthly
            (weight :method equal
                (asset AAPL)
                (asset GOOGL)))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        assert len(indicators) == 0


class TestGetRequiredSymbols:
    """Tests for get_required_symbols function."""

    def test_get_symbols_from_assets(self) -> None:
        """Test getting symbols from asset declarations."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance monthly
            (weight :method equal
                (asset AAPL)
                (asset GOOGL)
                (asset MSFT)))
        """
        strategy = parse(sexpr)
        symbols = get_required_symbols(strategy)

        assert symbols == {"AAPL", "GOOGL", "MSFT"}

    def test_get_symbols_from_indicators(self) -> None:
        """Test getting symbols from indicator references."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi QQQ 14) 70)
                (asset TLT :weight 100)
                (else (asset SPY :weight 100))))
        """
        strategy = parse(sexpr)
        symbols = get_required_symbols(strategy)

        # Should include QQQ from indicator, plus assets
        assert "QQQ" in symbols
        assert "TLT" in symbols
        assert "SPY" in symbols

    def test_get_symbols_nested_blocks(self) -> None:
        """Test getting symbols from nested blocks."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance monthly
            (group "Tech"
                (asset AAPL)
                (group "Chips"
                    (asset NVDA)
                    (asset AMD))))
        """
        strategy = parse(sexpr)
        symbols = get_required_symbols(strategy)

        assert symbols == {"AAPL", "NVDA", "AMD"}


class TestGetMaxLookback:
    """Tests for get_max_lookback function."""

    def test_max_lookback_single(self) -> None:
        """Test max lookback with single indicator."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="AAPL",
                source="close",
                params=(20,),
                output_key="sma_AAPL_close_20",
                output_field=None,
                required_bars=20,
            ),
        ]

        assert get_max_lookback(indicators) == 20

    def test_max_lookback_multiple(self) -> None:
        """Test max lookback returns the maximum."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="AAPL",
                source="close",
                params=(10,),
                output_key="sma_AAPL_close_10",
                output_field=None,
                required_bars=10,
            ),
            IndicatorSpec(
                indicator_type="sma",
                symbol="AAPL",
                source="close",
                params=(50,),
                output_key="sma_AAPL_close_50",
                output_field=None,
                required_bars=50,
            ),
            IndicatorSpec(
                indicator_type="rsi",
                symbol="AAPL",
                source="close",
                params=(14,),
                output_key="rsi_AAPL_close_14",
                output_field=None,
                required_bars=15,
            ),
        ]

        assert get_max_lookback(indicators) == 50

    def test_max_lookback_empty(self) -> None:
        """Test max lookback with empty list returns 0."""
        assert get_max_lookback([]) == 0


class TestGetRequiredSources:
    """Tests for get_required_sources function."""

    def test_required_sources_close_only(self) -> None:
        """Test indicator that only needs close."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="AAPL",
                source="close",
                params=(20,),
                output_key="sma_AAPL_close_20",
                output_field=None,
                required_bars=20,
            ),
        ]

        sources = get_required_sources(indicators)
        assert sources == {"close"}

    def test_required_sources_atr_needs_hlc(self) -> None:
        """Test ATR requires high, low, close."""
        indicators = [
            IndicatorSpec(
                indicator_type="atr",
                symbol="AAPL",
                source="close",
                params=(14,),
                output_key="atr_AAPL_close_14",
                output_field=None,
                required_bars=15,
            ),
        ]

        sources = get_required_sources(indicators)
        assert sources == {"high", "low", "close"}

    def test_required_sources_obv_needs_volume(self) -> None:
        """Test OBV requires volume."""
        indicators = [
            IndicatorSpec(
                indicator_type="obv",
                symbol="AAPL",
                source="close",
                params=(),
                output_key="obv_AAPL_close",
                output_field=None,
                required_bars=2,
            ),
        ]

        sources = get_required_sources(indicators)
        assert "volume" in sources

    def test_required_sources_combined(self) -> None:
        """Test combined sources from multiple indicators."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="AAPL",
                source="close",
                params=(20,),
                output_key="sma_AAPL_close_20",
                output_field=None,
                required_bars=20,
            ),
            IndicatorSpec(
                indicator_type="atr",
                symbol="AAPL",
                source="close",
                params=(14,),
                output_key="atr_AAPL_close_14",
                output_field=None,
                required_bars=15,
            ),
            IndicatorSpec(
                indicator_type="obv",
                symbol="AAPL",
                source="close",
                params=(),
                output_key="obv_AAPL_close",
                output_field=None,
                required_bars=2,
            ),
        ]

        sources = get_required_sources(indicators)
        assert sources == {"high", "low", "close", "volume"}

    def test_required_sources_empty(self) -> None:
        """Test empty indicator list returns empty sources."""
        sources = get_required_sources([])
        assert sources == set()
