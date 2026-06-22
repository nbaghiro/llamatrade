"""Condition evaluator for allocation strategy rules.

Evaluates Condition AST nodes against the current evaluation state,
returning boolean results for If block branch selection.
"""

import logging

import numpy as np

from llamatrade_compiler.evaluation.state import EvaluationState
from llamatrade_dsl import (
    Comparison,
    Condition,
    Crossover,
    Indicator,
    LogicalOp,
    NumericLiteral,
    Price,
    Value,
)

logger = logging.getLogger(__name__)


class EvaluationError(Exception):
    """Error during condition evaluation."""

    pass


def _record_degraded(state: EvaluationState, reason: str) -> None:
    """Record a condition that could not be meaningfully evaluated.

    The condition is treated as False (fail-safe: take no action) but the event
    is surfaced — counted on the state and logged — so a stale indicator, a NaN
    during warm-up, or a missing bar does not masquerade silently as a
    legitimate "no signal". The per-run total is exposed via
    ``StrategySession.degraded_eval_count`` for the service to emit as a metric.
    """
    state.degraded_evaluations += 1
    logger.debug("condition evaluation degraded (%s); treating as False", reason)


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

    # value is Metric (the only remaining type in the Value union)
    return state.get_metric_value(value)


def _get_prev_value(value: Value, state: EvaluationState) -> float:
    """Get the previous bar's value for a Value node."""
    if isinstance(value, NumericLiteral):
        return float(value.value)

    if isinstance(value, Price):
        return state.get_prev_price(value.symbol, value.field)

    if isinstance(value, Indicator):
        return state.get_prev_indicator_value(value)

    # value is Metric - metrics typically don't have prev value, use current
    return state.get_metric_value(value)


def _evaluate_comparison(comparison: Comparison, state: EvaluationState) -> bool:
    """Evaluate a Comparison condition."""
    left_val = _resolve_value(comparison.left, state)
    right_val = _resolve_value(comparison.right, state)

    # A NaN operand (e.g. an indicator still warming up) makes every IEEE
    # comparison silently False. Surface it instead of failing quietly.
    if np.isnan(left_val) or np.isnan(right_val):
        _record_degraded(state, f"NaN operand in '{comparison.operator}' comparison")
        return False

    op = comparison.operator
    if op == ">":
        return left_val > right_val
    if op == "<":
        return left_val < right_val
    if op == ">=":
        return left_val >= right_val
    if op == "<=":
        return left_val <= right_val
    if op == "=":
        return left_val == right_val
    # op must be "!=" at this point
    return left_val != right_val


def _evaluate_crossover(crossover: Crossover, state: EvaluationState) -> bool:
    """Evaluate a Crossover condition.

    cross-above: fast was <= slow, now fast > slow
    cross-below: fast was >= slow, now fast < slow
    """
    fast_curr = _resolve_value(crossover.fast, state)
    slow_curr = _resolve_value(crossover.slow, state)
    fast_prev = _get_prev_value(crossover.fast, state)
    slow_prev = _get_prev_value(crossover.slow, state)

    # A NaN on either side (current or previous) can't be a real crossing.
    if any(np.isnan(v) for v in (fast_curr, slow_curr, fast_prev, slow_prev)):
        _record_degraded(state, f"NaN operand in '{crossover.direction}' crossover")
        return False

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

    # condition is LogicalOp (the only remaining type in the Condition union)
    return _evaluate_logical(condition, state)


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
    except EvaluationError as e:
        _record_degraded(state, f"evaluation error: {e}")
        return False
    except (KeyError, ValueError, IndexError) as e:
        _record_degraded(state, f"missing/invalid data: {e}")
        return False
