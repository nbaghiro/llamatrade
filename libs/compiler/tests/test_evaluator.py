"""Tests for llamatrade_compiler.evaluator module."""

from datetime import UTC, datetime

import numpy as np
import pytest

from llamatrade_compiler.evaluator import (
    EvaluationError,
    evaluate_condition,
    evaluate_condition_safe,
)
from llamatrade_compiler.state import EvaluationState
from llamatrade_compiler.types import Bar
from llamatrade_dsl import Comparison, Crossover, Indicator, LogicalOp, NumericLiteral, Price


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        open=100.0,
        high=105.0,
        low=98.0,
        close=103.0,
        volume=1000000,
    )


@pytest.fixture
def prev_bar() -> Bar:
    """Create a previous bar."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 10, 29, tzinfo=UTC),
        open=99.0,
        high=102.0,
        low=97.0,
        close=100.0,
        volume=800000,
    )


@pytest.fixture
def sample_indicators() -> dict[str, float | np.ndarray]:
    """Create sample indicator data."""
    return {
        "sma_AAPL_close_20": np.array([98.0, 99.0, 100.0, 101.0, 102.0]),
        "sma_AAPL_close_10": np.array([100.0, 101.0, 102.0, 103.0, 104.0]),
        "rsi_AAPL_close_14": np.array([45.0, 48.0, 52.0, 55.0, 65.0]),
    }


@pytest.fixture
def basic_state(
    sample_bar: Bar, prev_bar: Bar, sample_indicators: dict[str, float | np.ndarray]
) -> EvaluationState:
    """Create a basic evaluation state."""
    return EvaluationState(
        current_bars={"AAPL": sample_bar},
        prev_bars={"AAPL": prev_bar},
        indicators=sample_indicators,
    )


class TestComparisonOperators:
    """Tests for comparison operators."""

    def test_greater_than_true(self, basic_state: EvaluationState) -> None:
        """Test > operator when true."""
        # close (103) > 100
        condition = Comparison(
            operator=">",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=100),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_greater_than_false(self, basic_state: EvaluationState) -> None:
        """Test > operator when false."""
        # close (103) > 110
        condition = Comparison(
            operator=">",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=110),
        )

        assert evaluate_condition(condition, basic_state) is False

    def test_less_than_true(self, basic_state: EvaluationState) -> None:
        """Test < operator when true."""
        # close (103) < 110
        condition = Comparison(
            operator="<",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=110),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_less_than_indicator(self, basic_state: EvaluationState) -> None:
        """Test < operator with indicator."""
        # rsi (65) < 70
        condition = Comparison(
            operator="<",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=70),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_greater_than_equal_true(self, basic_state: EvaluationState) -> None:
        """Test >= operator when equal."""
        # close (103) >= 103
        condition = Comparison(
            operator=">=",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=103),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_less_than_equal_true(self, basic_state: EvaluationState) -> None:
        """Test <= operator when equal."""
        # close (103) <= 103
        condition = Comparison(
            operator="<=",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=103),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_equal_true(self, basic_state: EvaluationState) -> None:
        """Test = operator when true."""
        # close (103) = 103
        condition = Comparison(
            operator="=",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=103),
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_not_equal_true(self, basic_state: EvaluationState) -> None:
        """Test != operator when true."""
        # close (103) != 100
        condition = Comparison(
            operator="!=",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=100),
        )

        assert evaluate_condition(condition, basic_state) is True


class TestLogicalOperators:
    """Tests for logical operators."""

    def test_and_all_true(self, basic_state: EvaluationState) -> None:
        """Test 'and' when all conditions true."""
        # close (103) > 100 AND close < 110
        condition = LogicalOp(
            operator="and",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
                Comparison(
                    operator="<",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=110),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_and_one_false(self, basic_state: EvaluationState) -> None:
        """Test 'and' when one condition false."""
        # close (103) > 100 AND close > 110
        condition = LogicalOp(
            operator="and",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=110),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is False

    def test_or_one_true(self, basic_state: EvaluationState) -> None:
        """Test 'or' when one condition true."""
        # close (103) < 100 OR close < 110
        condition = LogicalOp(
            operator="or",
            operands=[
                Comparison(
                    operator="<",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
                Comparison(
                    operator="<",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=110),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_or_all_false(self, basic_state: EvaluationState) -> None:
        """Test 'or' when all conditions false."""
        # close (103) < 100 OR close > 110
        condition = LogicalOp(
            operator="or",
            operands=[
                Comparison(
                    operator="<",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=110),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is False

    def test_not_inverts_true(self, basic_state: EvaluationState) -> None:
        """Test 'not' inverts true to false."""
        # NOT (close > 100) -> NOT true -> false
        condition = LogicalOp(
            operator="not",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is False

    def test_not_inverts_false(self, basic_state: EvaluationState) -> None:
        """Test 'not' inverts false to true."""
        # NOT (close > 110) -> NOT false -> true
        condition = LogicalOp(
            operator="not",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=110),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is True

    def test_nested_logical(self, basic_state: EvaluationState) -> None:
        """Test nested logical operators."""
        # (close > 100 AND close < 110) OR (close > 120)
        condition = LogicalOp(
            operator="or",
            operands=[
                LogicalOp(
                    operator="and",
                    operands=[
                        Comparison(
                            operator=">",
                            left=Price(symbol="AAPL", field="close"),
                            right=NumericLiteral(value=100),
                        ),
                        Comparison(
                            operator="<",
                            left=Price(symbol="AAPL", field="close"),
                            right=NumericLiteral(value=110),
                        ),
                    ],
                ),
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=120),
                ),
            ],
        )

        assert evaluate_condition(condition, basic_state) is True


class TestCrossoverOperators:
    """Tests for crossover operators."""

    def test_cross_above_triggers(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crosses-above triggers when crossing up."""
        # SMA 10 crosses above SMA 20
        indicators = {
            "sma_AAPL_close_10": np.array([99.0, 100.0, 101.0, 102.0, 105.0]),  # last=105
            "sma_AAPL_close_20": np.array([100.0, 101.0, 102.0, 103.0, 104.0]),  # last=104
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="above",
            fast=Indicator(name="sma", symbol="AAPL", params=(10,)),
            slow=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # sma10[-1]=105 > sma20[-1]=104, sma10[-2]=102 <= sma20[-2]=103
        assert evaluate_condition(condition, state) is True

    def test_cross_above_no_trigger_already_above(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crosses-above doesn't trigger when already above."""
        indicators = {
            "sma_AAPL_close_10": np.array([101.0, 102.0, 103.0, 105.0, 106.0]),  # Always above
            "sma_AAPL_close_20": np.array([99.0, 100.0, 101.0, 102.0, 103.0]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="above",
            fast=Indicator(name="sma", symbol="AAPL", params=(10,)),
            slow=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # prev sma10=105 > prev sma20=102, so no cross
        assert evaluate_condition(condition, state) is False

    def test_cross_below_triggers(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crosses-below triggers when crossing down."""
        indicators = {
            "sma_AAPL_close_10": np.array([101.0, 102.0, 103.0, 103.0, 100.0]),  # last=100
            "sma_AAPL_close_20": np.array([99.0, 100.0, 101.0, 102.0, 102.0]),  # last=102
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="below",
            fast=Indicator(name="sma", symbol="AAPL", params=(10,)),
            slow=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # sma10[-1]=100 < sma20[-1]=102, sma10[-2]=103 >= sma20[-2]=102
        assert evaluate_condition(condition, state) is True

    def test_cross_above_with_literal(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crosses-above with literal threshold."""
        # RSI crosses above 50
        indicators = {
            "rsi_AAPL_close_14": np.array([45.0, 46.0, 48.0, 49.0, 55.0]),  # last=55, prev=49
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="above",
            fast=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            slow=NumericLiteral(value=50),
        )

        # rsi[-1]=55 > 50, rsi[-2]=49 <= 50
        assert evaluate_condition(condition, state) is True


class TestIndicatorReferences:
    """Tests for indicator reference resolution."""

    def test_indicator_from_cache(self, basic_state: EvaluationState) -> None:
        """Test indicator value is retrieved from cache."""
        condition = Comparison(
            operator=">",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=60),
        )

        # rsi_AAPL_close_14 last value is 65, > 60
        assert evaluate_condition(condition, basic_state) is True

    def test_indicator_comparison_two_indicators(self, basic_state: EvaluationState) -> None:
        """Test comparing two indicators."""
        condition = Comparison(
            operator=">",
            left=Indicator(name="sma", symbol="AAPL", params=(10,)),
            right=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # sma10 last=104, sma20 last=102
        assert evaluate_condition(condition, basic_state) is True

    def test_indicator_not_found_raises(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test missing indicator raises EvaluationError."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},  # Empty indicators
        )

        condition = Comparison(
            operator=">",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=50),
        )

        with pytest.raises(KeyError, match="Indicator not computed"):
            evaluate_condition(condition, state)


class TestEvaluateConditionSafe:
    """Tests for evaluate_condition_safe function."""

    def test_evaluate_safe_returns_true(self, basic_state: EvaluationState) -> None:
        """Test evaluate_condition_safe returns True when condition met."""
        condition = Comparison(
            operator=">",
            left=Price(symbol="AAPL", field="close"),
            right=NumericLiteral(value=100),
        )

        assert evaluate_condition_safe(condition, basic_state) is True

    def test_evaluate_safe_returns_false_on_error(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test evaluate_condition_safe returns False on evaluation error."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},  # Missing indicator will cause error
        )

        condition = Comparison(
            operator=">",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=50),
        )

        # Should return False instead of raising
        assert evaluate_condition_safe(condition, state) is False


class TestEvaluationError:
    """Tests for EvaluationError exception."""

    def test_evaluation_error_message(self) -> None:
        """Test EvaluationError has correct message."""
        error = EvaluationError("Test error message")
        assert str(error) == "Test error message"


class TestEdgeCases:
    """Tests for edge cases in condition evaluation."""

    def test_comparison_with_nan_indicator(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test comparison when indicator value is NaN."""
        indicators = {
            "rsi_AAPL_close_14": np.array([45.0, 48.0, 52.0, 55.0, np.nan]),  # Last is NaN
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Comparison(
            operator=">",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=50),
        )

        # NaN comparisons should return False
        result = evaluate_condition(condition, state)
        # NaN > 50 is False in Python
        assert result is False

    def test_comparison_nan_equals_nan(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test that NaN != NaN in comparisons."""
        indicators = {
            "sma_AAPL_close_10": np.array([np.nan, np.nan, np.nan, np.nan, np.nan]),
            "sma_AAPL_close_20": np.array([np.nan, np.nan, np.nan, np.nan, np.nan]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Comparison(
            operator="=",
            left=Indicator(name="sma", symbol="AAPL", params=(10,)),
            right=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # NaN == NaN is False in IEEE floating point
        assert evaluate_condition(condition, state) is False

    def test_crossover_with_nan_values(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crossover when values contain NaN."""
        indicators = {
            "sma_AAPL_close_10": np.array([99.0, 100.0, 101.0, np.nan, 105.0]),
            "sma_AAPL_close_20": np.array([100.0, 101.0, 102.0, np.nan, 104.0]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="above",
            fast=Indicator(name="sma", symbol="AAPL", params=(10,)),
            slow=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # Previous values are NaN, comparison fails
        result = evaluate_condition(condition, state)
        # NaN <= NaN is False, so crossover logic may behave unexpectedly
        # This tests that it doesn't crash
        assert isinstance(result, bool)

    def test_missing_symbol_in_price_data(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test accessing price for non-existent symbol."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},  # Only AAPL
            prev_bars={"AAPL": prev_bar},
            indicators={},
        )

        condition = Comparison(
            operator=">",
            left=Price(symbol="MSFT", field="close"),  # MSFT not in state
            right=NumericLiteral(value=100),
        )

        with pytest.raises(KeyError):
            evaluate_condition(condition, state)

    def test_evaluate_safe_missing_symbol(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test evaluate_condition_safe returns False for missing symbol."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},
        )

        condition = Comparison(
            operator=">",
            left=Price(symbol="MSFT", field="close"),
            right=NumericLiteral(value=100),
        )

        # Should return False, not raise
        assert evaluate_condition_safe(condition, state) is False

    def test_logical_and_short_circuit(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test logical AND short-circuits on first false."""
        # First condition is false, second would raise if evaluated
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},  # Missing indicator - would raise
        )

        condition = LogicalOp(
            operator="and",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=200),  # False: 103 > 200
                ),
                Comparison(
                    operator=">",
                    left=Indicator(name="rsi", symbol="AAPL", params=(14,)),  # Would raise
                    right=NumericLiteral(value=50),
                ),
            ],
        )

        # Should short-circuit and return False without evaluating second condition
        assert evaluate_condition(condition, state) is False

    def test_logical_or_short_circuit(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test logical OR short-circuits on first true."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},  # Missing indicator - would raise
        )

        condition = LogicalOp(
            operator="or",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),  # True: 103 > 100
                ),
                Comparison(
                    operator=">",
                    left=Indicator(name="rsi", symbol="AAPL", params=(14,)),  # Would raise
                    right=NumericLiteral(value=50),
                ),
            ],
        )

        # Should short-circuit and return True without evaluating second condition
        assert evaluate_condition(condition, state) is True

    def test_not_with_wrong_operand_count(self, basic_state: EvaluationState) -> None:
        """Test 'not' with wrong number of operands raises error."""
        condition = LogicalOp(
            operator="not",
            operands=[
                Comparison(
                    operator=">",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=100),
                ),
                Comparison(  # Extra operand
                    operator="<",
                    left=Price(symbol="AAPL", field="close"),
                    right=NumericLiteral(value=200),
                ),
            ],
        )

        with pytest.raises(EvaluationError, match="exactly 1 operand"):
            evaluate_condition(condition, basic_state)

    def test_single_element_indicator_array(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test indicator with single-element array."""
        indicators = {
            "rsi_AAPL_close_14": np.array([65.0]),  # Single value
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Comparison(
            operator=">",
            left=Indicator(name="rsi", symbol="AAPL", params=(14,)),
            right=NumericLiteral(value=50),
        )

        # Should work with single element
        assert evaluate_condition(condition, state) is True

    def test_crossover_single_element_array(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test crossover with single-element indicator arrays."""
        indicators = {
            "sma_AAPL_close_10": np.array([105.0]),  # Single value
            "sma_AAPL_close_20": np.array([100.0]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Crossover(
            direction="above",
            fast=Indicator(name="sma", symbol="AAPL", params=(10,)),
            slow=Indicator(name="sma", symbol="AAPL", params=(20,)),
        )

        # Single element means no "previous" value for crossover
        # Should handle gracefully (may raise or return False)
        try:
            result = evaluate_condition(condition, state)
            assert isinstance(result, bool)
        except IndexError, EvaluationError:
            pass  # Acceptable to raise for insufficient data

    def test_empty_logical_and(self, basic_state: EvaluationState) -> None:
        """Test empty 'and' operands list."""
        condition = LogicalOp(
            operator="and",
            operands=[],
        )

        # Empty AND should return True (identity element)
        assert evaluate_condition(condition, basic_state) is True

    def test_empty_logical_or(self, basic_state: EvaluationState) -> None:
        """Test empty 'or' operands list."""
        condition = LogicalOp(
            operator="or",
            operands=[],
        )

        # Empty OR should return False (identity element)
        assert evaluate_condition(condition, basic_state) is False

    def test_very_large_numeric_comparison(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test comparison with very large numbers."""
        indicators = {
            "obv_AAPL_close": np.array([1e15, 1.1e15, 1.2e15, 1.3e15, 1.5e15]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        condition = Comparison(
            operator=">",
            left=Indicator(name="obv", symbol="AAPL", params=()),
            right=NumericLiteral(value=1e14),
        )

        assert evaluate_condition(condition, state) is True

    def test_very_small_numeric_comparison(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test comparison with very small numbers."""
        indicators = {
            "custom_AAPL": np.array([1e-10, 1e-9, 1e-8, 1e-7, 1e-6]),
        }

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=indicators,
        )

        # Access the custom indicator directly
        condition = Comparison(
            operator=">",
            left=NumericLiteral(value=1e-6),
            right=NumericLiteral(value=1e-10),
        )

        assert evaluate_condition(condition, state) is True

    def test_equality_with_floating_point_precision(self, basic_state: EvaluationState) -> None:
        """Test equality comparison with floating point values."""
        # This tests floating point equality issues
        condition = Comparison(
            operator="=",
            left=NumericLiteral(value=0.1 + 0.2),  # 0.30000000000000004 in IEEE 754
            right=NumericLiteral(value=0.3),
        )

        # This may fail due to floating point precision
        # The result depends on the implementation
        result = evaluate_condition(condition, basic_state)
        # Just verify it doesn't crash
        assert isinstance(result, bool)


class TestSafeDivideAndNormalize:
    """Tests for safe_divide and normalize_weights helper functions."""

    def test_safe_divide_normal(self) -> None:
        """Test safe_divide with normal values."""
        from llamatrade_compiler.evaluator import safe_divide

        assert safe_divide(10.0, 2.0) == 5.0
        assert safe_divide(0.0, 5.0) == 0.0

    def test_safe_divide_by_zero(self) -> None:
        """Test safe_divide returns default on division by zero."""
        from llamatrade_compiler.evaluator import safe_divide

        assert safe_divide(10.0, 0.0) == 0.0
        assert safe_divide(10.0, 0.0, default=1.0) == 1.0

    def test_safe_divide_nan_numerator(self) -> None:
        """Test safe_divide returns default with NaN numerator."""
        from llamatrade_compiler.evaluator import safe_divide

        assert safe_divide(np.nan, 2.0) == 0.0

    def test_safe_divide_nan_denominator(self) -> None:
        """Test safe_divide returns default with NaN denominator."""
        from llamatrade_compiler.evaluator import safe_divide

        assert safe_divide(10.0, np.nan) == 0.0

    def test_safe_divide_inf_result(self) -> None:
        """Test safe_divide handles infinity result."""
        from llamatrade_compiler.evaluator import safe_divide

        # Very small denominator that would cause overflow
        result = safe_divide(1e308, 1e-308)
        # Should return default if result is inf
        assert result == 0.0 or np.isfinite(result)

    def test_normalize_weights_normal(self) -> None:
        """Test normalize_weights with normal values."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 60.0, "B": 40.0}
        result = normalize_weights(weights)
        assert result["A"] == pytest.approx(60.0)
        assert result["B"] == pytest.approx(40.0)

    def test_normalize_weights_not_100(self) -> None:
        """Test normalize_weights scales to 100%."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 30.0, "B": 20.0}  # Sum = 50
        result = normalize_weights(weights)
        assert result["A"] == pytest.approx(60.0)  # 30/50 * 100
        assert result["B"] == pytest.approx(40.0)  # 20/50 * 100

    def test_normalize_weights_all_zero(self) -> None:
        """Test normalize_weights with all zero weights."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 0.0, "B": 0.0}
        result = normalize_weights(weights)
        # Should fallback to equal weights
        assert result["A"] == pytest.approx(50.0)
        assert result["B"] == pytest.approx(50.0)

    def test_normalize_weights_empty(self) -> None:
        """Test normalize_weights with empty dict."""
        from llamatrade_compiler.evaluator import normalize_weights

        result = normalize_weights({})
        assert result == {}

    def test_normalize_weights_with_nan(self) -> None:
        """Test normalize_weights filters out NaN values."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 60.0, "B": np.nan, "C": 40.0}
        result = normalize_weights(weights)
        # B should be filtered out, A and C normalized
        assert "A" in result
        assert "C" in result
        assert result["A"] + result["C"] == pytest.approx(100.0)

    def test_normalize_weights_with_negative(self) -> None:
        """Test normalize_weights filters out negative values."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 60.0, "B": -10.0, "C": 40.0}
        result = normalize_weights(weights)
        # B should be filtered out
        assert result["A"] == pytest.approx(60.0)
        assert result["C"] == pytest.approx(40.0)

    def test_normalize_weights_all_nan(self) -> None:
        """Test normalize_weights with all NaN values."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": np.nan, "B": np.nan}
        result = normalize_weights(weights)
        # Should fallback to equal weights for original keys
        assert result["A"] == pytest.approx(50.0)
        assert result["B"] == pytest.approx(50.0)

    def test_normalize_weights_no_fallback(self) -> None:
        """Test normalize_weights without fallback to equal weights."""
        from llamatrade_compiler.evaluator import normalize_weights

        weights = {"A": 0.0, "B": 0.0}
        result = normalize_weights(weights, fallback_to_equal=False)
        assert result["A"] == 0.0
        assert result["B"] == 0.0
