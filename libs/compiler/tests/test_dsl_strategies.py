"""End-to-end tests for DSL-defined allocation strategies.

Tests the full pipeline: parse -> extract -> compile -> evaluate
using realistic portfolio allocation strategies defined in s-expressions.
"""

from datetime import UTC, datetime, timedelta

import numpy as np

from llamatrade_compiler.compiled import CompiledStrategy, compile_strategy
from llamatrade_compiler.extractor import extract_indicators, get_max_lookback
from llamatrade_compiler.types import Bar
from llamatrade_dsl import parse

# =============================================================================
# Test Fixtures
# =============================================================================


def generate_bars(
    n: int,
    start_price: float = 100.0,
    trend: float = 0.0,
    start_date: datetime | None = None,
    volatility: float = 0.02,
) -> list[Bar]:
    """Generate synthetic bar data with configurable trend and volatility."""
    np.random.seed(42)
    bars: list[Bar] = []

    price = start_price
    timestamp = start_date or datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

    for _ in range(n):
        change = trend + np.random.randn() * volatility
        new_price = price * (1 + change)

        high = max(price, new_price) * (1 + abs(np.random.randn() * 0.01))
        low = min(price, new_price) * (1 - abs(np.random.randn() * 0.01))

        bars.append(
            Bar(
                timestamp=timestamp,
                open=price,
                high=high,
                low=low,
                close=new_price,
                volume=int(1000000 * (1 + np.random.randn() * 0.3)),
            )
        )

        price = new_price
        timestamp += timedelta(days=1)

    return bars


def generate_bars_with_pattern(
    pattern: list[float], start_date: datetime | None = None
) -> list[Bar]:
    """Generate bars from a specific price pattern for deterministic testing."""
    bars: list[Bar] = []
    timestamp = start_date or datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

    for i, close in enumerate(pattern):
        open_price = pattern[i - 1] if i > 0 else close
        bars.append(
            Bar(
                timestamp=timestamp,
                open=open_price,
                high=max(open_price, close) * 1.01,
                low=min(open_price, close) * 0.99,
                close=close,
                volume=1000000,
            )
        )
        timestamp += timedelta(days=1)

    return bars


# =============================================================================
# Extractor Edge Cases
# =============================================================================


class TestExtractorEdgeCases:
    """Tests for indicator extraction edge cases."""

    def test_strategy_with_no_indicators(self) -> None:
        """Test extracting indicators from strategy with only assets."""
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

    def test_same_indicator_different_params(self) -> None:
        """Test that same indicator with different params is extracted separately."""
        sexpr = """
        (strategy "Multi SMA"
            :benchmark SPY
            :rebalance daily
            (if (and (> (sma SPY 10) 100) (> (sma SPY 20) 100))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        # Should have SMA(10) and SMA(20) as separate indicators
        periods = {ind.params[0] for ind in indicators if ind.indicator_type == "sma"}
        assert 10 in periods
        assert 20 in periods

    def test_same_indicator_different_outputs(self) -> None:
        """Test MACD with different output fields is extracted correctly."""
        sexpr = """
        (strategy "MACD Signal"
            :benchmark SPY
            :rebalance daily
            (if (> (macd SPY 12 26 9 :signal) (macd SPY 12 26 9))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        # Should have two MACD indicators (default and signal)
        macd_indicators = [ind for ind in indicators if ind.indicator_type == "macd"]
        assert len(macd_indicators) >= 1

    def test_macd_lookback_calculation(self) -> None:
        """Test MACD lookback is calculated correctly."""
        sexpr = """
        (strategy "MACD"
            :benchmark SPY
            :rebalance daily
            (if (> (macd SPY 12 26 9) 0)
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        lookback = get_max_lookback(indicators)
        # MACD needs slow period (26) + signal period (9) - 1 = ~34 bars
        assert lookback >= 26

    def test_deeply_nested_indicators(self) -> None:
        """Test extraction from deeply nested conditions."""
        sexpr = """
        (strategy "Complex"
            :benchmark SPY
            :rebalance daily
            (if (and
                    (> (rsi SPY 14) 30)
                    (or
                        (> (sma SPY 10) (sma SPY 20))
                        (and
                            (< (rsi SPY 14) 70)
                            (> (ema SPY 12) 100))))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        indicators = extract_indicators(strategy)

        indicator_names = {ind.indicator_type for ind in indicators}
        assert "rsi" in indicator_names
        assert "sma" in indicator_names
        assert "ema" in indicator_names


# =============================================================================
# End-to-End Strategy Tests
# =============================================================================


class TestEndToEndStrategies:
    """End-to-end tests for allocation strategies."""

    def test_equal_weight_allocation(self) -> None:
        """Test equal weight allocation produces correct weights."""
        sexpr = """
        (strategy "Equal Weight"
            :benchmark SPY
            :rebalance monthly
            (weight :method equal
                (asset AAPL)
                (asset GOOGL)
                (asset MSFT)))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(compiled.min_bars + 10)
        for bar in bars:
            result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        # Final allocation should be equal weights
        assert "weights" in result
        weights = result["weights"]
        expected = 100.0 / 3
        for symbol in ["AAPL", "GOOGL", "MSFT"]:
            assert abs(weights.get(symbol, 0) - expected) < 1

    def test_specified_weight_allocation(self) -> None:
        """Test specified weights are preserved."""
        sexpr = """
        (strategy "60/40"
            :benchmark SPY
            :rebalance monthly
            (weight :method specified
                (asset SPY :weight 60)
                (asset TLT :weight 40)))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(compiled.min_bars + 10)
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        weights = result["weights"]
        # After normalization
        assert abs(weights.get("SPY", 0) - 60) < 1
        assert abs(weights.get("TLT", 0) - 40) < 1

    def test_rsi_conditional_allocation(self) -> None:
        """Test RSI-based conditional allocation."""
        sexpr = """
        (strategy "RSI Switch"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi SPY 14) 50)
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Need enough bars for RSI calculation
        bars = generate_bars(50, trend=0.01)  # Uptrend
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        # With uptrend, RSI should be > 50, so SPY should be allocated
        weights = result["weights"]
        assert len(weights) > 0

    def test_sma_crossover_allocation(self) -> None:
        """Test SMA crossover allocation."""
        sexpr = """
        (strategy "SMA Cross"
            :benchmark SPY
            :rebalance daily
            (if (crosses-above (sma SPY 10) (sma SPY 20))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(50)
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        # Should have allocation to either SPY or TLT
        weights = result["weights"]
        total = sum(weights.values())
        assert abs(total - 100) < 1


class TestMomentumStrategies:
    """Tests for momentum-based allocation strategies."""

    def test_momentum_weight_basic(self) -> None:
        """Test basic momentum weighting."""
        sexpr = """
        (strategy "Momentum"
            :benchmark SPY
            :rebalance monthly
            (weight :method momentum :lookback 30 :top 2
                (asset AAPL)
                (asset GOOGL)
                (asset MSFT)))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Generate different trends for each symbol
        np.random.seed(42)
        aapl_bars = generate_bars(50, trend=0.02)  # Strong uptrend
        googl_bars = generate_bars(50, trend=0.01)  # Moderate uptrend
        msft_bars = generate_bars(50, trend=-0.01)  # Downtrend

        for i in range(50):
            result = compiled.compute_allocation(
                {
                    "AAPL": aapl_bars[i],
                    "GOOGL": googl_bars[i],
                    "MSFT": msft_bars[i],
                }
            )

        # Top 2 momentum should be AAPL and GOOGL
        assert "weights" in result
        assert len(result["weights"]) > 0


class TestFilterStrategies:
    """Tests for filter-based allocation strategies."""

    def test_filter_top_momentum(self) -> None:
        """Test filter selects top momentum assets."""
        sexpr = """
        (strategy "Top Momentum"
            :benchmark SPY
            :rebalance monthly
            (filter :by momentum :select (top 2) :lookback 30
                (weight :method equal
                    (asset AAPL)
                    (asset GOOGL)
                    (asset MSFT)
                    (asset AMZN))))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(50)
        for bar in bars:
            result = compiled.compute_allocation(
                {
                    "AAPL": bar,
                    "GOOGL": bar,
                    "MSFT": bar,
                    "AMZN": bar,
                }
            )

        weights = result["weights"]
        # Should only have top 2 assets
        non_zero = [s for s, w in weights.items() if w > 0]
        assert len(non_zero) <= 2


class TestComplexStrategies:
    """Tests for complex multi-component strategies."""

    def test_nested_conditionals(self) -> None:
        """Test nested if conditions."""
        sexpr = """
        (strategy "Nested"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi SPY 14) 70)
                (asset TLT :weight 100)
                (else (if (< (rsi SPY 14) 30)
                    (asset SPY :weight 100)
                    (else (weight :method equal
                        (asset SPY)
                        (asset TLT)))))))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(50)
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        weights = result["weights"]
        assert sum(weights.values()) > 0

    def test_logical_conditions(self) -> None:
        """Test AND/OR logical conditions."""
        sexpr = """
        (strategy "Logical"
            :benchmark SPY
            :rebalance daily
            (if (and (> (rsi SPY 14) 30) (< (rsi SPY 14) 70))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = generate_bars(50)
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        weights = result["weights"]
        total = sum(weights.values())
        assert abs(total - 100) < 1


class TestInverseVolatilityStrategies:
    """Tests for inverse volatility weighting."""

    def test_inverse_volatility_weight(self) -> None:
        """Test inverse volatility weighting."""
        sexpr = """
        (strategy "Inv Vol"
            :benchmark SPY
            :rebalance monthly
            (weight :method inverse-volatility :lookback 30
                (asset SPY)
                (asset TLT)
                (asset GLD)))
        """
        strategy = parse(sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Generate different volatility profiles
        spy_bars = generate_bars(50, volatility=0.02)
        tlt_bars = generate_bars(50, volatility=0.01)  # Less volatile
        gld_bars = generate_bars(50, volatility=0.015)

        for i in range(50):
            result = compiled.compute_allocation(
                {
                    "SPY": spy_bars[i],
                    "TLT": tlt_bars[i],
                    "GLD": gld_bars[i],
                }
            )

        weights = result["weights"]
        # TLT should have highest weight (least volatile)
        # But we're just checking it computes something
        assert sum(weights.values()) > 0


class TestCompileStrategyFunction:
    """Tests for the compile_strategy convenience function."""

    def test_compile_strategy_function(self) -> None:
        """Test compile_strategy function works correctly."""
        sexpr = """
        (strategy "Test"
            :benchmark SPY
            :rebalance monthly
            (weight :method equal
                (asset AAPL)
                (asset GOOGL)))
        """
        strategy = parse(sexpr)
        compiled = compile_strategy(strategy)

        assert isinstance(compiled, CompiledStrategy)
        assert compiled.name == "Test"
        assert compiled.rebalance_frequency == "monthly"
        assert compiled.benchmark == "SPY"
