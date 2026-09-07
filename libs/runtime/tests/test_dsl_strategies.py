"""End-to-end tests for DSL-defined allocation strategies.

Tests the full pipeline: parse -> extract -> compile -> evaluate
using realistic portfolio allocation strategies defined in s-expressions.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_dsl import parse
from llamatrade_runtime.evaluation.compiled import CompiledStrategy, compile_strategy
from llamatrade_runtime.types import Bar

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
# End-to-End Strategy Tests
# =============================================================================


class TestEndToEndStrategies:
    """End-to-end tests for allocation strategies."""

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


NESTED_SEXPR = """
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


class TestComplexStrategies:
    """Tests for complex multi-component strategies."""

    @staticmethod
    def _final_weights(spy_closes: list[float]) -> dict[str, float]:
        compiled = compile_strategy(parse(NESTED_SEXPR))
        spy_bars = generate_bars_with_pattern(spy_closes)
        tlt_bars = generate_bars_with_pattern([50.0] * len(spy_closes))
        weights: dict[str, float] = {}
        for spy_bar, tlt_bar in zip(spy_bars, tlt_bars, strict=True):
            weights = compiled.compute_allocation({"SPY": spy_bar, "TLT": tlt_bar})["weights"]
        return weights

    def test_nested_conditional_outer_branch_on_high_rsi(self) -> None:
        # Strictly rising closes -> no losses -> RSI 100 > 70 -> TLT.
        weights = self._final_weights([100.0 + i for i in range(25)])
        assert weights == {"TLT": pytest.approx(100.0)}

    def test_nested_conditional_inner_then_branch_on_low_rsi(self) -> None:
        # Strictly falling closes -> no gains -> RSI 0 < 30 -> SPY.
        weights = self._final_weights([100.0 - i for i in range(25)])
        assert weights == {"SPY": pytest.approx(100.0)}

    def test_nested_conditional_inner_else_branch_on_neutral_rsi(self) -> None:
        # Alternating equal-size moves keep RSI near 50 (inside 30..70) -> equal split.
        closes = [100.0 + (i % 2) for i in range(25)]
        weights = self._final_weights(closes)
        assert weights["SPY"] == pytest.approx(50.0)
        assert weights["TLT"] == pytest.approx(50.0)

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
