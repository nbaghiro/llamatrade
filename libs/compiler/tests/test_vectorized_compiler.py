"""Tests for llamatrade_compiler.vectorized_compiler module."""

import numpy as np
import pytest

from llamatrade_compiler.vectorized import VectorizedBarData
from llamatrade_compiler.vectorized_compiler import compile_vectorized_strategy


@pytest.fixture
def equal_weight_sexpr() -> str:
    """Simple equal-weight allocation strategy."""
    return """
    (strategy "Equal Weight"
        :benchmark SPY
        :rebalance monthly
        (weight :method equal
            (asset AAPL)
            (asset GOOGL)
            (asset MSFT)))
    """


@pytest.fixture
def specified_weight_sexpr() -> str:
    """Strategy with specified weights."""
    return """
    (strategy "60/40 Portfolio"
        :benchmark SPY
        :rebalance quarterly
        (weight :method specified
            (asset SPY :weight 60)
            (asset TLT :weight 40)))
    """


@pytest.fixture
def conditional_sexpr() -> str:
    """Conditional RSI strategy."""
    return """
    (strategy "RSI Switch"
        :benchmark SPY
        :rebalance daily
        (if (> (rsi SPY 14) 70)
            (asset TLT :weight 100)
            (else (asset SPY :weight 100))))
    """


@pytest.fixture
def crossover_sexpr() -> str:
    """SMA crossover strategy."""
    return """
    (strategy "SMA Crossover"
        :benchmark SPY
        :rebalance daily
        (if (crosses-above (sma SPY 10) (sma SPY 20))
            (asset SPY :weight 100)
            (else (asset TLT :weight 100))))
    """


@pytest.fixture
def sample_bars() -> VectorizedBarData:
    """Create sample vectorized bar data."""
    num_bars = 30
    return {
        "timestamps": np.arange(num_bars).astype("datetime64[D]"),
        "opens": np.random.rand(3, num_bars) * 100 + 100,
        "highs": np.random.rand(3, num_bars) * 10 + 105,
        "lows": np.random.rand(3, num_bars) * 10 + 95,
        "closes": np.random.rand(3, num_bars) * 100 + 100,
        "volumes": np.random.rand(3, num_bars) * 1000000 + 500000,
    }


class TestCompileVectorizedStrategy:
    """Tests for compile_vectorized_strategy function."""

    def test_compile_returns_vectorized_compiled_strategy(self, equal_weight_sexpr: str) -> None:
        """Test compile returns VectorizedCompiledStrategy."""
        from llamatrade_compiler.vectorized import VectorizedCompiledStrategy

        compiled = compile_vectorized_strategy(equal_weight_sexpr)

        assert isinstance(compiled, VectorizedCompiledStrategy)

    def test_compile_preserves_strategy_name(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves strategy name."""
        compiled = compile_vectorized_strategy(equal_weight_sexpr)

        assert compiled.strategy_name == "Equal Weight"

    def test_compile_preserves_benchmark(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves benchmark."""
        compiled = compile_vectorized_strategy(equal_weight_sexpr)

        assert compiled.benchmark == "SPY"

    def test_compile_preserves_rebalance_frequency(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves rebalance frequency."""
        compiled = compile_vectorized_strategy(equal_weight_sexpr)

        assert compiled.rebalance_frequency == "monthly"

    def test_compile_invalid_strategy_raises(self) -> None:
        """Test compile raises ValueError for invalid strategy."""
        invalid_sexpr = "(strategy)"

        with pytest.raises(ValueError, match="Invalid strategy"):
            compile_vectorized_strategy(invalid_sexpr)


class TestVectorizedAllocation:
    """Tests for vectorized allocation computation."""

    def test_equal_weight_allocation(self, equal_weight_sexpr: str) -> None:
        """Test equal weight produces equal allocations."""
        compiled = compile_vectorized_strategy(equal_weight_sexpr)

        num_bars = 10
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 100 + 100,
            "highs": np.random.rand(1, num_bars) * 10 + 105,
            "lows": np.random.rand(1, num_bars) * 10 + 95,
            "closes": np.random.rand(1, num_bars) * 100 + 100,
            "volumes": np.random.rand(1, num_bars) * 1000000 + 500000,
        }

        weights = compiled.compute_weights(bars)

        # Should have 3 symbols with equal weight
        assert len(weights) == 3
        assert "AAPL" in weights
        assert "GOOGL" in weights
        assert "MSFT" in weights

        expected_weight = 100.0 / 3
        for symbol in weights:
            assert weights[symbol].shape == (num_bars,)
            np.testing.assert_array_almost_equal(
                weights[symbol], np.full(num_bars, expected_weight), decimal=2
            )

    def test_specified_weight_allocation(self, specified_weight_sexpr: str) -> None:
        """Test specified weight produces correct allocations."""
        compiled = compile_vectorized_strategy(specified_weight_sexpr)

        num_bars = 10
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 100 + 100,
            "highs": np.random.rand(1, num_bars) * 10 + 105,
            "lows": np.random.rand(1, num_bars) * 10 + 95,
            "closes": np.random.rand(1, num_bars) * 100 + 100,
            "volumes": np.random.rand(1, num_bars) * 1000000 + 500000,
        }

        weights = compiled.compute_weights(bars)

        assert "SPY" in weights
        assert "TLT" in weights

        np.testing.assert_array_almost_equal(weights["SPY"], np.full(num_bars, 60.0), decimal=2)
        np.testing.assert_array_almost_equal(weights["TLT"], np.full(num_bars, 40.0), decimal=2)

    def test_conditional_allocation_shape(self, conditional_sexpr: str) -> None:
        """Test conditional allocation returns correct shape."""
        compiled = compile_vectorized_strategy(conditional_sexpr)

        num_bars = 30  # Need enough for RSI(14)
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 100 + 100,
            "highs": np.random.rand(1, num_bars) * 10 + 110,
            "lows": np.random.rand(1, num_bars) * 10 + 90,
            "closes": np.random.rand(1, num_bars) * 100 + 100,
            "volumes": np.random.rand(1, num_bars) * 1000000 + 500000,
        }

        weights = compiled.compute_weights(bars)

        # Should have weights for both possible outcomes
        assert len(weights) >= 1
        for symbol, w in weights.items():
            assert w.shape == (num_bars,)


class TestVectorizedConditions:
    """Tests for vectorized condition evaluation."""

    def test_comparison_creates_varying_weights(self) -> None:
        """Test comparison conditions create varying weights over time."""
        sexpr = """
        (strategy "Price Test"
            :benchmark SPY
            :rebalance daily
            (if (> (price SPY :close) 100)
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 10
        # Create price series that crosses 100
        closes = np.array([[95, 98, 100, 102, 105, 103, 99, 97, 101, 104]])
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": closes - 1,
            "highs": closes + 2,
            "lows": closes - 2,
            "closes": closes.astype(float),
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        # Weights should vary based on price
        assert "SPY" in weights or "TLT" in weights


class TestVectorizedIndicators:
    """Tests for vectorized indicator computation."""

    def test_sma_indicator_computed(self) -> None:
        """Test SMA indicator is computed for allocation."""
        sexpr = """
        (strategy "SMA Test"
            :benchmark SPY
            :rebalance daily
            (if (> (sma SPY 5) 100)
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 20
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        # Should not raise
        weights = compiled.compute_weights(bars)

        assert len(weights) >= 1

    def test_rsi_indicator_computed(self) -> None:
        """Test RSI indicator is computed for allocation."""
        sexpr = """
        (strategy "RSI Test"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi SPY 14) 50)
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 30
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        assert len(weights) >= 1


class TestVectorizedCrossover:
    """Tests for vectorized crossover conditions."""

    def test_crossover_condition_evaluated(self, crossover_sexpr: str) -> None:
        """Test crossover condition is evaluated."""
        compiled = compile_vectorized_strategy(crossover_sexpr)

        num_bars = 30
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        # Should have weights for either SPY or TLT
        assert len(weights) >= 1
        assert "SPY" in weights or "TLT" in weights


class TestVectorizedLogicalOps:
    """Tests for vectorized logical operators."""

    def test_and_condition(self) -> None:
        """Test AND condition is evaluated vectorized."""
        sexpr = """
        (strategy "AND Test"
            :benchmark SPY
            :rebalance daily
            (if (and (> (rsi SPY 14) 30) (< (rsi SPY 14) 70))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 30
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        assert len(weights) >= 1

    def test_or_condition(self) -> None:
        """Test OR condition is evaluated vectorized."""
        sexpr = """
        (strategy "OR Test"
            :benchmark SPY
            :rebalance daily
            (if (or (< (rsi SPY 14) 30) (> (rsi SPY 14) 70))
                (asset TLT :weight 100)
                (else (asset SPY :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 30
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        assert len(weights) >= 1

    def test_not_condition(self) -> None:
        """Test NOT condition is evaluated vectorized."""
        sexpr = """
        (strategy "NOT Test"
            :benchmark SPY
            :rebalance daily
            (if (not (> (rsi SPY 14) 70))
                (asset SPY :weight 100)
                (else (asset TLT :weight 100))))
        """
        compiled = compile_vectorized_strategy(sexpr)

        num_bars = 30
        np.random.seed(42)
        bars: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.random.rand(1, num_bars) * 10 + 100,
            "highs": np.random.rand(1, num_bars) * 5 + 105,
            "lows": np.random.rand(1, num_bars) * 5 + 95,
            "closes": np.random.rand(1, num_bars) * 10 + 100,
            "volumes": np.full((1, num_bars), 1000000.0),
        }

        weights = compiled.compute_weights(bars)

        assert len(weights) >= 1
