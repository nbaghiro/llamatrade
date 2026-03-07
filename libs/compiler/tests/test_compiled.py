"""Tests for llamatrade_compiler.compiled module."""

from datetime import UTC, datetime, timedelta

import pytest

from llamatrade_compiler.compiled import CompiledStrategy, compile_strategy
from llamatrade_compiler.types import Bar
from llamatrade_dsl import parse


@pytest.fixture
def equal_weight_sexpr() -> str:
    """Simple equal-weight strategy."""
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
def momentum_weight_sexpr() -> str:
    """Momentum-weighted strategy."""
    return """
    (strategy "Momentum"
        :benchmark SPY
        :rebalance monthly
        (weight :method momentum :lookback 90 :top 2
            (asset AAPL)
            (asset GOOGL)
            (asset MSFT)
            (asset AMZN)))
    """


def create_bars(num_bars: int, base_price: float = 100.0) -> list[Bar]:
    """Create a list of bars with random walk."""
    import numpy as np

    np.random.seed(42)
    base_time = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    bars = []

    price = base_price
    for i in range(num_bars):
        change = np.random.randn() * 0.02
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * 1.005
        low_price = min(open_price, close_price) * 0.995
        volume = int(np.random.randint(100000, 1000000))

        bars.append(
            Bar(
                timestamp=base_time + timedelta(days=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        price = close_price

    return bars


class TestCompile:
    """Tests for CompiledStrategy.compile() factory method."""

    def test_compile_creates_compiled_strategy(self, equal_weight_sexpr: str) -> None:
        """Test compile creates a CompiledStrategy."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert isinstance(compiled, CompiledStrategy)

    def test_compile_extracts_symbols(self, equal_weight_sexpr: str) -> None:
        """Test compile extracts required symbols."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.symbols == {"AAPL", "GOOGL", "MSFT"}

    def test_compile_sets_min_bars(self, conditional_sexpr: str) -> None:
        """Test compile sets minimum bars from indicator lookback."""
        strategy = parse(conditional_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # RSI 14 needs ~15 bars, minimum 2 for crossover
        assert compiled.min_bars >= 2

    def test_compile_preserves_strategy_name(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves strategy name."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.name == "Equal Weight"

    def test_compile_preserves_rebalance_frequency(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves rebalance frequency."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.rebalance_frequency == "monthly"

    def test_compile_preserves_benchmark(self, equal_weight_sexpr: str) -> None:
        """Test compile preserves benchmark."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.benchmark == "SPY"

    def test_compile_strategy_function(self, equal_weight_sexpr: str) -> None:
        """Test compile_strategy convenience function."""
        strategy = parse(equal_weight_sexpr)
        compiled = compile_strategy(strategy)

        assert isinstance(compiled, CompiledStrategy)


class TestStateManagement:
    """Tests for strategy state management."""

    def test_reset_clears_state(self, equal_weight_sexpr: str) -> None:
        """Test reset clears all state."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Add some bars
        bars_data = create_bars(10)
        for bar in bars_data:
            compiled.add_bars({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        compiled.reset()

        assert not compiled.has_enough_history()
        assert compiled._bar_history == {}
        assert compiled._indicator_cache == {}

    def test_add_bars_appends_to_history(self, equal_weight_sexpr: str) -> None:
        """Test add_bars appends to history."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bar = create_bars(1)[0]
        compiled.add_bars({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert len(compiled._bar_history["AAPL"]) == 1
        assert len(compiled._bar_history["GOOGL"]) == 1
        assert len(compiled._bar_history["MSFT"]) == 1

    def test_has_enough_history_false_initially(self, equal_weight_sexpr: str) -> None:
        """Test has_enough_history returns False initially."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert not compiled.has_enough_history()

    def test_has_enough_history_true_after_min_bars(self, equal_weight_sexpr: str) -> None:
        """Test has_enough_history returns True after min_bars."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)
        for bar in bars:
            compiled.add_bars({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert compiled.has_enough_history()


class TestComputeAllocation:
    """Tests for allocation computation."""

    def test_compute_allocation_returns_allocation_type(self, equal_weight_sexpr: str) -> None:
        """Test compute_allocation returns Allocation type."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)
        result = None
        for bar in bars:
            result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert result is not None
        assert "weights" in result
        assert "rebalance_needed" in result
        assert "metadata" in result

    def test_compute_allocation_insufficient_history(self, equal_weight_sexpr: str) -> None:
        """Test compute_allocation with insufficient history returns empty."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bar = create_bars(1)[0]
        result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert result["weights"] == {}
        assert result["rebalance_needed"] is False
        assert result["metadata"]["reason"] == "insufficient_history"

    def test_equal_weight_computes_equal_weights(self, equal_weight_sexpr: str) -> None:
        """Test equal weight method produces equal weights."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)
        result = None
        for bar in bars:
            result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert result is not None
        weights = result["weights"]

        # Should have 3 symbols with equal weight
        assert len(weights) == 3
        expected_weight = 100.0 / 3
        assert weights["AAPL"] == pytest.approx(expected_weight, rel=0.01)
        assert weights["GOOGL"] == pytest.approx(expected_weight, rel=0.01)
        assert weights["MSFT"] == pytest.approx(expected_weight, rel=0.01)

    def test_specified_weight_computes_specified_weights(self, specified_weight_sexpr: str) -> None:
        """Test specified weight method produces specified weights."""
        strategy = parse(specified_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)
        result = None
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        assert result is not None
        weights = result["weights"]

        # Should have 60/40 split
        assert len(weights) == 2
        assert weights["SPY"] == pytest.approx(60.0, rel=0.01)
        assert weights["TLT"] == pytest.approx(40.0, rel=0.01)

    def test_weights_sum_to_100(self, equal_weight_sexpr: str) -> None:
        """Test all weights sum to 100."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)
        result = None
        for bar in bars:
            result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        assert result is not None
        total_weight = sum(result["weights"].values())
        assert total_weight == pytest.approx(100.0, rel=0.01)


class TestConditionalAllocation:
    """Tests for conditional (If) allocation."""

    def test_conditional_evaluates_condition(self, conditional_sexpr: str) -> None:
        """Test conditional allocation evaluates condition."""
        strategy = parse(conditional_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Create enough bars with known values
        bars = create_bars(compiled.min_bars + 5)
        result = None
        for bar in bars:
            result = compiled.compute_allocation({"SPY": bar, "TLT": bar})

        assert result is not None
        # Result should have weights for either SPY or TLT
        weights = result["weights"]
        assert len(weights) >= 1


class TestRebalanceDetection:
    """Tests for rebalance detection."""

    def test_first_allocation_needs_rebalance(self, equal_weight_sexpr: str) -> None:
        """Test first allocation always needs rebalance."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 1)

        # Feed bars until we have enough history
        first_valid_result = None
        for bar in bars:
            result = compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})
            # The first valid result (with weights) should need rebalance
            if result["weights"] and first_valid_result is None:
                first_valid_result = result

        assert first_valid_result is not None
        assert first_valid_result["rebalance_needed"] is True

    def test_same_allocation_no_rebalance(self, equal_weight_sexpr: str) -> None:
        """Test same allocation doesn't need rebalance."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        bars = create_bars(compiled.min_bars + 2)

        # First pass to set initial allocation
        for bar in bars[:-1]:
            compiled.compute_allocation({"AAPL": bar, "GOOGL": bar, "MSFT": bar})

        # Second pass should not need rebalance (weights unchanged)
        last_bar = bars[-1]
        result = compiled.compute_allocation(
            {"AAPL": last_bar, "GOOGL": last_bar, "MSFT": last_bar}
        )

        # Equal weights stay the same, so no rebalance
        assert result["rebalance_needed"] is False


class TestMomentumWeighting:
    """Tests for momentum-based weighting."""

    def test_momentum_weight_selects_top_performers(self, momentum_weight_sexpr: str) -> None:
        """Test momentum weighting selects top performers."""
        strategy = parse(momentum_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        # Create bars - need 90 for lookback
        bars_aapl = create_bars(100, base_price=100.0)
        bars_googl = create_bars(100, base_price=90.0)  # Different starting prices
        bars_msft = create_bars(100, base_price=110.0)
        bars_amzn = create_bars(100, base_price=80.0)

        result = None
        for i in range(len(bars_aapl)):
            result = compiled.compute_allocation(
                {
                    "AAPL": bars_aapl[i],
                    "GOOGL": bars_googl[i],
                    "MSFT": bars_msft[i],
                    "AMZN": bars_amzn[i],
                }
            )

        assert result is not None
        # Should have weights for top 2 performers
        weights = result["weights"]
        non_zero_weights = {k: v for k, v in weights.items() if v > 0}
        assert len(non_zero_weights) == 2


class TestCompiledStrategyProperties:
    """Tests for CompiledStrategy properties."""

    def test_name_property(self, equal_weight_sexpr: str) -> None:
        """Test name property."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.name == "Equal Weight"

    def test_rebalance_frequency_property(self, equal_weight_sexpr: str) -> None:
        """Test rebalance_frequency property."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.rebalance_frequency == "monthly"

    def test_benchmark_property(self, equal_weight_sexpr: str) -> None:
        """Test benchmark property."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        assert compiled.benchmark == "SPY"

    def test_repr(self, equal_weight_sexpr: str) -> None:
        """Test __repr__ method."""
        strategy = parse(equal_weight_sexpr)
        compiled = CompiledStrategy.compile(strategy)

        repr_str = repr(compiled)

        assert "CompiledStrategy" in repr_str
        assert "Equal Weight" in repr_str
