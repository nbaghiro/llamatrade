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
