"""Condition evaluator for allocation strategy rules.

Evaluates Condition AST nodes against the current evaluation state,
returning boolean results for If block branch selection.
"""

import numpy as np

from llamatrade_compiler.state import EvaluationState
from llamatrade_dsl import (
    Comparison,
    Condition,
    Crossover,
    Indicator,
    LogicalOp,
    Metric,
    NumericLiteral,
    Price,
    Value,
)


class EvaluationError(Exception):
    """Error during condition evaluation."""

    pass


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default on division by zero or NaN.

    Args:
        numerator: The numerator
        denominator: The denominator
        default: Value to return if division is undefined

    Returns:
        Result of division or default value
    """
    if denominator == 0.0 or np.isnan(denominator) or np.isnan(numerator):
        return default
    result = numerator / denominator
    if np.isnan(result) or np.isinf(result):
        return default
    return result


def normalize_weights(
    weights: dict[str, float],
    fallback_to_equal: bool = True,
) -> dict[str, float]:
    """Normalize weights to sum to 100%, handling edge cases.

    Args:
        weights: Dictionary of symbol -> weight
        fallback_to_equal: If True, use equal weights when normalization fails

    Returns:
        Normalized weights summing to 100%

    Examples:
        >>> normalize_weights({"A": 60, "B": 40})
        {"A": 60.0, "B": 40.0}  # Already normalized

        >>> normalize_weights({"A": 30, "B": 30})
        {"A": 50.0, "B": 50.0}  # Scaled to 100%

        >>> normalize_weights({"A": 0, "B": 0})
        {"A": 50.0, "B": 50.0}  # Fallback to equal weights

        >>> normalize_weights({})
        {}  # Empty input returns empty
    """
    if not weights:
        return {}

    # Filter out NaN and negative weights
    valid_weights = {k: v for k, v in weights.items() if not np.isnan(v) and v >= 0}

    if not valid_weights:
        if fallback_to_equal:
            # Return equal weights for all original symbols
            equal_weight = 100.0 / len(weights)
            return {k: equal_weight for k in weights}
        return {k: 0.0 for k in weights}

    total = sum(valid_weights.values())

    if total == 0.0 or np.isnan(total):
        if fallback_to_equal:
            # Return equal weights
            equal_weight = 100.0 / len(valid_weights)
            return {k: equal_weight for k in valid_weights}
        return {k: 0.0 for k in valid_weights}

    # Normalize to 100%
    return {k: safe_divide(v * 100.0, total, 0.0) for k, v in valid_weights.items()}


def _resolve_value(value: Value, state: EvaluationState) -> float:
    """Resolve a Value node to a numeric value.

    Args:
        value: Value node to resolve
        state: Current evaluation state

    Returns:
        The numeric value

    Raises:
        EvaluationError: If the value cannot be resolved
    """
    if isinstance(value, NumericLiteral):
        return float(value.value)

    if isinstance(value, Price):
        return state.get_price(value.symbol, value.field)

    if isinstance(value, Indicator):
        return state.get_indicator_value(value)

    if isinstance(value, Metric):
        return state.get_metric_value(value)

    raise EvaluationError(f"Cannot resolve value: {type(value)}")


def _get_prev_value(value: Value, state: EvaluationState) -> float:
    """Get the previous bar's value for a Value node."""
    if isinstance(value, NumericLiteral):
        return float(value.value)

    if isinstance(value, Price):
        return state.get_prev_price(value.symbol, value.field)

    if isinstance(value, Indicator):
        return state.get_prev_indicator_value(value)

    if isinstance(value, Metric):
        # Metrics typically don't have prev value - use current
        return state.get_metric_value(value)

    raise EvaluationError(f"Cannot get previous value of: {type(value)}")


def _evaluate_comparison(comparison: Comparison, state: EvaluationState) -> bool:
    """Evaluate a Comparison condition."""
    left_val = _resolve_value(comparison.left, state)
    right_val = _resolve_value(comparison.right, state)

    op = comparison.operator
    if op == ">":
        return left_val > right_val
    if op == "<":
        return left_val < right_val
    if op == ">=":
        return left_val >= right_val
    if op == "<=":
        return left_val <= right_val
    if op == "=" or op == "==":
        return left_val == right_val
    if op == "!=":
        return left_val != right_val

    raise EvaluationError(f"Unknown comparison operator: {op}")


def _evaluate_crossover(crossover: Crossover, state: EvaluationState) -> bool:
    """Evaluate a Crossover condition.

    cross-above: fast was <= slow, now fast > slow
    cross-below: fast was >= slow, now fast < slow
    """
    fast_curr = _resolve_value(crossover.fast, state)
    slow_curr = _resolve_value(crossover.slow, state)
    fast_prev = _get_prev_value(crossover.fast, state)
    slow_prev = _get_prev_value(crossover.slow, state)

    if crossover.direction == "above":
        return fast_prev <= slow_prev and fast_curr > slow_curr

    if crossover.direction == "below":
        return fast_prev >= slow_prev and fast_curr < slow_curr

    raise EvaluationError(f"Unknown crossover direction: {crossover.direction}")


def _evaluate_logical(logical: LogicalOp, state: EvaluationState) -> bool:
    """Evaluate a LogicalOp condition."""
    op = logical.operator
    operands = logical.operands

    if op == "and":
        return all(evaluate_condition(operand, state) for operand in operands)

    if op == "or":
        return any(evaluate_condition(operand, state) for operand in operands)

    if op == "not":
        if len(operands) != 1:
            raise EvaluationError("'not' requires exactly 1 operand")
        return not evaluate_condition(operands[0], state)

    raise EvaluationError(f"Unknown logical operator: {op}")


def evaluate_condition(condition: Condition, state: EvaluationState) -> bool:
    """Evaluate a Condition AST node.

    Args:
        condition: The condition to evaluate
        state: Current evaluation state

    Returns:
        True if condition is met, False otherwise

    Raises:
        EvaluationError: If condition cannot be evaluated
    """
    if isinstance(condition, Comparison):
        return _evaluate_comparison(condition, state)

    if isinstance(condition, Crossover):
        return _evaluate_crossover(condition, state)

    if isinstance(condition, LogicalOp):
        return _evaluate_logical(condition, state)

    raise EvaluationError(f"Cannot evaluate condition: {type(condition)}")


def evaluate_condition_safe(condition: Condition, state: EvaluationState) -> bool:
    """Evaluate a condition, returning False on error.

    Args:
        condition: The condition to evaluate
        state: Current evaluation state

    Returns:
        True if condition is met, False if not met or on error
    """
    try:
        return evaluate_condition(condition, state)
    except EvaluationError:
        return False
    except KeyError, ValueError, IndexError:
        return False


def evaluate_condition_vectorized(
    condition: Condition,
    indicator_data: dict[str, np.ndarray],
    price_data: dict[str, dict[str, np.ndarray]],
) -> np.ndarray:
    """Evaluate a condition in vectorized form for backtesting.

    Args:
        condition: The condition to evaluate
        indicator_data: Dict mapping indicator keys to arrays
        price_data: Dict mapping symbol -> field -> price arrays

    Returns:
        Boolean array where True indicates condition is met
    """
    if isinstance(condition, Comparison):
        left = _get_vectorized_value(condition.left, indicator_data, price_data)
        right = _get_vectorized_value(condition.right, indicator_data, price_data)

        op = condition.operator
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == "=" or op == "==":
            return left == right
        if op == "!=":
            return left != right

    if isinstance(condition, Crossover):
        fast = _get_vectorized_value(condition.fast, indicator_data, price_data)
        slow = _get_vectorized_value(condition.slow, indicator_data, price_data)

        prev_fast = np.roll(fast, 1)
        prev_slow = np.roll(slow, 1)
        prev_fast[0] = np.nan
        prev_slow[0] = np.nan

        if condition.direction == "above":
            return (prev_fast <= prev_slow) & (fast > slow)
        else:
            return (prev_fast >= prev_slow) & (fast < slow)

    if isinstance(condition, LogicalOp):
        if condition.operator == "and":
            result = np.ones(len(price_data[next(iter(price_data))]["close"]), dtype=bool)
            for operand in condition.operands:
                result &= evaluate_condition_vectorized(operand, indicator_data, price_data)
            return result

        if condition.operator == "or":
            result = np.zeros(len(price_data[next(iter(price_data))]["close"]), dtype=bool)
            for operand in condition.operands:
                result |= evaluate_condition_vectorized(operand, indicator_data, price_data)
            return result

        if condition.operator == "not":
            return ~evaluate_condition_vectorized(condition.operands[0], indicator_data, price_data)

    raise EvaluationError(f"Cannot vectorize condition: {type(condition)}")


def _get_vectorized_value(
    value: Value,
    indicator_data: dict[str, np.ndarray],
    price_data: dict[str, dict[str, np.ndarray]],
) -> np.ndarray:
    """Get vectorized value for backtesting."""
    if isinstance(value, NumericLiteral):
        # Need to determine array length from available data
        for symbol_data in price_data.values():
            return np.full(len(symbol_data["close"]), value.value)
        return np.array([value.value])

    if isinstance(value, Price):
        return price_data[value.symbol][value.field]

    if isinstance(value, Indicator):
        key = _build_indicator_key(value)
        return indicator_data.get(key, np.array([]))

    raise EvaluationError(f"Cannot vectorize value: {type(value)}")


def _build_indicator_key(indicator: Indicator) -> str:
    """Build cache key for an indicator."""
    parts = [indicator.name, indicator.symbol, "close"]
    parts.extend(str(p) for p in indicator.params)
    if indicator.output:
        parts.append(indicator.output)
    return "_".join(parts)
