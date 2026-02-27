"""Tests for the condition evaluator module."""

from datetime import datetime

import numpy as np
import pytest
from llamatrade_compiler import Bar
from llamatrade_dsl import parse_strategy
from src.compiler.evaluator import (
    EvaluationError,
    evaluate_condition,
    evaluate_entry,
    evaluate_exit,
)
from src.compiler.state import EvaluationState, Position


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar for testing."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 10, 0),
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=1000000,
    )


@pytest.fixture
def prev_bar() -> Bar:
    """Create a previous bar for testing."""
    return Bar(
        timestamp=datetime(2024, 1, 14, 10, 0),
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=900000,
    )


@pytest.fixture
def state_with_indicators(sample_bar: Bar, prev_bar: Bar) -> EvaluationState:
    """Create evaluation state with sample indicators."""
    return EvaluationState(
        current_bar=sample_bar,
        prev_bar=prev_bar,
        indicators={
            "sma_close_20": np.array([98.0, 99.0, 100.0]),  # 3 values, last is current
            "sma_close_50": np.array([95.0, 96.0, 97.0]),
            "rsi_close_14": np.array([45.0, 55.0, 65.0]),
            "macd_close_12_26_9_line": np.array([0.5, 1.0, 1.5]),
            "macd_close_12_26_9_signal": np.array([0.3, 0.8, 1.2]),
            "bbands_close_20_2.0_upper": np.array([103.0, 104.0, 105.0]),
            "bbands_close_20_2.0_lower": np.array([97.0, 96.0, 95.0]),
        },
        position=None,
        bar_history=[prev_bar, sample_bar],
    )


class TestComparisonOperators:
    """Tests for comparison operators."""

    def test_greater_than_true(self, state_with_indicators: EvaluationState) -> None:
        """Test > operator returns True when condition met."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> close 100)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_greater_than_false(self, state_with_indicators: EvaluationState) -> None:
        """Test > operator returns False when condition not met."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> close 200)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is False

    def test_less_than(self, state_with_indicators: EvaluationState) -> None:
        """Test < operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (< close 102)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_greater_equal(self, state_with_indicators: EvaluationState) -> None:
        """Test >= operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (>= close 101)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_less_equal(self, state_with_indicators: EvaluationState) -> None:
        """Test <= operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (<= close 101)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_equal(self, state_with_indicators: EvaluationState) -> None:
        """Test = operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (= close 101)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_not_equal(self, state_with_indicators: EvaluationState) -> None:
        """Test != operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (!= close 100)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True


class TestLogicalOperators:
    """Tests for logical operators."""

    def test_and_true(self, state_with_indicators: EvaluationState) -> None:
        """Test AND with all conditions true."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (and (> close 100) (< close 102))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_and_false(self, state_with_indicators: EvaluationState) -> None:
        """Test AND with one condition false."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (and (> close 100) (< close 100))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is False

    def test_or_true(self, state_with_indicators: EvaluationState) -> None:
        """Test OR with one condition true."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (or (> close 200) (< close 102))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_or_false(self, state_with_indicators: EvaluationState) -> None:
        """Test OR with all conditions false."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (or (> close 200) (< close 50))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is False

    def test_not_true(self, state_with_indicators: EvaluationState) -> None:
        """Test NOT operator."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (not (< close 100))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_nested_logic(self, state_with_indicators: EvaluationState) -> None:
        """Test nested logical operators."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (and
            (or (> close 100) (< close 50))
            (not (> close 200)))
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True


class TestIndicatorComparisons:
    """Tests for indicator-based comparisons."""

    def test_indicator_vs_literal(self, state_with_indicators: EvaluationState) -> None:
        """Test comparing indicator to literal value."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (rsi close 14) 50)
          :exit (< (rsi close 14) 50))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True  # RSI is 65

    def test_indicator_vs_indicator(self, state_with_indicators: EvaluationState) -> None:
        """Test comparing two indicators."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (sma close 20) (sma close 50))
          :exit (< (sma close 20) (sma close 50)))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True  # SMA20=100, SMA50=97


class TestCrossoverOperators:
    """Tests for crossover operators."""

    def test_cross_above_true(self) -> None:
        """Test cross-above when crossover occurs."""
        bar1 = Bar(
            timestamp=datetime(2024, 1, 14),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000000,
        )
        bar2 = Bar(
            timestamp=datetime(2024, 1, 15),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1000000,
        )
        state = EvaluationState(
            current_bar=bar2,
            prev_bar=bar1,
            indicators={
                # SMA20 crosses above SMA50
                "sma_close_20": np.array([95.0, 99.0]),  # prev=95, curr=99
                "sma_close_50": np.array([97.0, 98.0]),  # prev=97, curr=98
            },
            position=None,
            bar_history=[bar1, bar2],
        )

        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (cross-above (sma close 20) (sma close 50))
          :exit (cross-below (sma close 20) (sma close 50)))
        """)
        result = evaluate_condition(strategy.entry, state)
        assert result is True

    def test_cross_above_false_no_cross(self) -> None:
        """Test cross-above when no crossover occurs."""
        bar1 = Bar(
            timestamp=datetime(2024, 1, 14),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000000,
        )
        bar2 = Bar(
            timestamp=datetime(2024, 1, 15),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1000000,
        )
        state = EvaluationState(
            current_bar=bar2,
            prev_bar=bar1,
            indicators={
                # SMA20 stays above SMA50 (no cross)
                "sma_close_20": np.array([99.0, 100.0]),
                "sma_close_50": np.array([95.0, 96.0]),
            },
            position=None,
            bar_history=[bar1, bar2],
        )

        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (cross-above (sma close 20) (sma close 50))
          :exit (cross-below (sma close 20) (sma close 50)))
        """)
        result = evaluate_condition(strategy.entry, state)
        assert result is False

    def test_cross_below(self) -> None:
        """Test cross-below operator."""
        bar1 = Bar(
            timestamp=datetime(2024, 1, 14),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000000,
        )
        bar2 = Bar(
            timestamp=datetime(2024, 1, 15),
            open=99,
            high=100,
            low=98,
            close=99,
            volume=1000000,
        )
        state = EvaluationState(
            current_bar=bar2,
            prev_bar=bar1,
            indicators={
                # SMA20 crosses below SMA50
                "sma_close_20": np.array([99.0, 97.0]),
                "sma_close_50": np.array([97.0, 98.0]),
            },
            position=None,
            bar_history=[bar1, bar2],
        )

        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (cross-above (sma close 20) (sma close 50))
          :exit (cross-below (sma close 20) (sma close 50)))
        """)
        result = evaluate_condition(strategy.exit, state)
        assert result is True


class TestSpecialFunctions:
    """Tests for special functions."""

    def test_has_position_false(self, state_with_indicators: EvaluationState) -> None:
        """Test has-position when no position."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (not (has-position))
          :exit (has-position))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True

    def test_has_position_true(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test has-position when position exists."""
        state = EvaluationState(
            current_bar=sample_bar,
            prev_bar=prev_bar,
            indicators={},
            position=Position(
                symbol="AAPL",
                side="long",
                quantity=100,
                entry_price=100.0,
                entry_time=datetime(2024, 1, 14),
            ),
            bar_history=[prev_bar, sample_bar],
        )

        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (not (has-position))
          :exit (has-position))
        """)
        result = evaluate_condition(strategy.exit, state)
        assert result is True


class TestArithmeticOperations:
    """Tests for arithmetic in conditions."""

    def test_addition(self, state_with_indicators: EvaluationState) -> None:
        """Test addition in condition."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (+ close 10) 110)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True  # 101 + 10 = 111 > 110

    def test_subtraction(self, state_with_indicators: EvaluationState) -> None:
        """Test subtraction in condition."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (- close 1) 99)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True  # 101 - 1 = 100 > 99

    def test_multiplication(self, state_with_indicators: EvaluationState) -> None:
        """Test multiplication in condition."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (* close 2) 200)
          :exit (< close 100))
        """)
        result = evaluate_condition(strategy.entry, state_with_indicators)
        assert result is True  # 101 * 2 = 202 > 200


class TestEvaluateEntryExit:
    """Tests for evaluate_entry and evaluate_exit helper functions."""

    def test_evaluate_entry_returns_false_on_error(
        self, state_with_indicators: EvaluationState
    ) -> None:
        """Test that evaluate_entry returns False on error."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (nonexistent-indicator) 100)
          :exit (< close 100))
        """)
        result = evaluate_entry(state_with_indicators, strategy.entry)
        assert result is False  # Should not raise, returns False

    def test_evaluate_exit_returns_false_on_error(
        self, state_with_indicators: EvaluationState
    ) -> None:
        """Test that evaluate_exit returns False on error."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> close 100)
          :exit (< (nonexistent-indicator) 100))
        """)
        result = evaluate_exit(state_with_indicators, strategy.exit)
        assert result is False  # Should not raise, returns False


class TestEvaluationErrors:
    """Tests for error handling."""

    def test_unknown_indicator_raises_error(self, state_with_indicators: EvaluationState) -> None:
        """Test that unknown indicator raises EvaluationError."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (sma close 999) 100)
          :exit (< close 100))
        """)
        with pytest.raises(EvaluationError, match="Indicator not found"):
            evaluate_condition(strategy.entry, state_with_indicators)

    def test_division_by_zero(self, state_with_indicators: EvaluationState) -> None:
        """Test division by zero raises error."""
        strategy = parse_strategy("""
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (/ close 0) 100)
          :exit (< close 100))
        """)
        with pytest.raises(EvaluationError, match="Division by zero"):
            evaluate_condition(strategy.entry, state_with_indicators)
