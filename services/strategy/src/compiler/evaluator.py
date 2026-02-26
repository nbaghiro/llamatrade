"""Condition evaluator for strategy entry/exit rules.

Evaluates AST condition trees against the current evaluation state,
returning boolean results for entry/exit signals.
"""

from datetime import datetime

from llamatrade_dsl.ast import ASTNode, FunctionCall, Keyword, Literal, Symbol
from llamatrade_dsl.validator import (
    ARITHMETIC_OPS,
    COMPARATORS,
    CROSSOVER_OPS,
    INDICATORS,
    LOGICAL_OPS,
    SPECIAL_OPS,
)

from src.compiler.state import EvaluationState


class EvaluationError(Exception):
    """Error during condition evaluation."""

    pass


def _resolve_value(node: ASTNode, state: EvaluationState) -> float:
    """Resolve an AST node to a numeric value.

    Args:
        node: AST node to resolve
        state: Current evaluation state

    Returns:
        The numeric value

    Raises:
        EvaluationError: If the node cannot be resolved
    """
    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return 1.0 if node.value else 0.0
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise EvaluationError(f"Cannot convert literal to number: {node.value}")

    if isinstance(node, Symbol):
        return state.get_value(node.name)

    if isinstance(node, FunctionCall):
        return _evaluate_numeric(node, state)

    if isinstance(node, Keyword):
        raise EvaluationError(f"Unexpected keyword in numeric context: {node.name}")

    raise EvaluationError(f"Unknown node type: {type(node)}")


def _evaluate_numeric(call: FunctionCall, state: EvaluationState) -> float:
    """Evaluate a function call that returns a number.

    Args:
        call: The function call node
        state: Current evaluation state

    Returns:
        The numeric result
    """
    name = call.name
    args = call.args

    # Indicator calls
    if name in INDICATORS:
        return _evaluate_indicator(call, state)

    # Arithmetic operations
    if name in ARITHMETIC_OPS:
        return _evaluate_arithmetic(name, args, state)

    # Special functions that return numbers
    if name == "prev":
        return _evaluate_prev(args, state)

    if name == "position-pnl-pct":
        pnl = state.position_pnl_pct()
        return pnl if pnl is not None else 0.0

    raise EvaluationError(f"Function {name} does not return a number")


def _evaluate_indicator(call: FunctionCall, state: EvaluationState) -> float:
    """Evaluate an indicator reference.

    Looks up the indicator value from pre-computed state.
    """
    # Build the cache key from the call
    parts = [call.name]

    # Extract source and params
    source = "close"
    params: list[str] = []
    output_field: str | None = None

    for arg in call.args:
        if isinstance(arg, Symbol):
            source = arg.name
        elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
            params.append(str(arg.value))
        elif isinstance(arg, Keyword):
            output_field = arg.name

    parts.append(source)
    parts.extend(params)
    if output_field:
        parts.append(output_field)

    key = "_".join(parts)

    try:
        return state.get_indicator(key)
    except KeyError:
        # Try without output field for single-output indicators
        if output_field:
            key_without_field = "_".join(parts[:-1])
            try:
                return state.get_indicator(key_without_field)
            except KeyError:
                pass
        raise EvaluationError(f"Indicator not found: {key}")


def _evaluate_arithmetic(name: str, args: tuple[ASTNode, ...], state: EvaluationState) -> float:
    """Evaluate arithmetic operations."""
    if name == "abs":
        if len(args) != 1:
            raise EvaluationError("abs requires exactly 1 argument")
        return abs(_resolve_value(args[0], state))

    values = [_resolve_value(arg, state) for arg in args]

    if name == "+":
        return sum(values)

    if name == "-":
        if len(values) != 2:
            raise EvaluationError("- requires exactly 2 arguments")
        return values[0] - values[1]

    if name == "*":
        result = 1.0
        for v in values:
            result *= v
        return result

    if name == "/":
        if len(values) != 2:
            raise EvaluationError("/ requires exactly 2 arguments")
        if values[1] == 0:
            raise EvaluationError("Division by zero")
        return values[0] / values[1]

    if name == "min":
        return min(values)

    if name == "max":
        return max(values)

    raise EvaluationError(f"Unknown arithmetic operation: {name}")


def _evaluate_prev(args: tuple[ASTNode, ...], state: EvaluationState) -> float:
    """Evaluate (prev expr n) - get value n bars ago."""
    if len(args) != 2:
        raise EvaluationError("prev requires exactly 2 arguments")

    offset_node = args[1]
    if not isinstance(offset_node, Literal) or not isinstance(offset_node.value, int):
        raise EvaluationError("prev offset must be an integer literal")

    offset = offset_node.value
    expr = args[0]

    # For symbols, use state's offset method
    if isinstance(expr, Symbol):
        return state.get_value_at_offset(expr.name, offset)

    # For indicators, get from array
    if isinstance(expr, FunctionCall) and expr.name in INDICATORS:
        key = _build_indicator_key(expr)
        arr = state.get_indicator_array(key)
        if offset >= len(arr):
            raise EvaluationError(f"Not enough history for offset {offset}")
        return float(arr[-(offset + 1)])

    raise EvaluationError(f"prev not supported for: {type(expr)}")


def _build_indicator_key(call: FunctionCall) -> str:
    """Build a cache key for an indicator call."""
    parts = [call.name]
    source = "close"
    params: list[str] = []
    output_field: str | None = None

    for arg in call.args:
        if isinstance(arg, Symbol):
            source = arg.name
        elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
            params.append(str(arg.value))
        elif isinstance(arg, Keyword):
            output_field = arg.name

    parts.append(source)
    parts.extend(params)
    if output_field:
        parts.append(output_field)

    return "_".join(parts)


def _evaluate_comparison(op: str, left: ASTNode, right: ASTNode, state: EvaluationState) -> bool:
    """Evaluate a comparison operation."""
    left_val = _resolve_value(left, state)
    right_val = _resolve_value(right, state)

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


def _evaluate_crossover(name: str, left: ASTNode, right: ASTNode, state: EvaluationState) -> bool:
    """Evaluate crossover operations.

    cross-above: left was <= right, now left > right
    cross-below: left was >= right, now left < right
    """
    # Current values
    left_curr = _resolve_value(left, state)
    right_curr = _resolve_value(right, state)

    # Previous values
    left_prev = _get_prev_value(left, state)
    right_prev = _get_prev_value(right, state)

    if name == "cross-above":
        return left_prev <= right_prev and left_curr > right_curr

    if name == "cross-below":
        return left_prev >= right_prev and left_curr < right_curr

    raise EvaluationError(f"Unknown crossover operator: {name}")


def _get_prev_value(node: ASTNode, state: EvaluationState) -> float:
    """Get the previous bar's value for a node."""
    if isinstance(node, Literal):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise EvaluationError(f"Cannot get previous value of: {node.value}")

    if isinstance(node, Symbol):
        return state.get_prev_value(node.name)

    if isinstance(node, FunctionCall):
        if node.name in INDICATORS:
            key = _build_indicator_key(node)
            arr = state.get_indicator_array(key)
            if len(arr) < 2:
                raise EvaluationError("Not enough history for previous value")
            return float(arr[-2])

        # For arithmetic, recursively compute with prev values
        if node.name in ARITHMETIC_OPS:
            # This is complex - for now, raise an error
            raise EvaluationError(f"Crossover with arithmetic not fully supported: {node.name}")

    raise EvaluationError(f"Cannot get previous value of: {type(node)}")


def _evaluate_logical(name: str, args: tuple[ASTNode, ...], state: EvaluationState) -> bool:
    """Evaluate logical operations."""
    if name == "and":
        return all(evaluate_condition(arg, state) for arg in args)

    if name == "or":
        return any(evaluate_condition(arg, state) for arg in args)

    if name == "not":
        if len(args) != 1:
            raise EvaluationError("not requires exactly 1 argument")
        return not evaluate_condition(args[0], state)

    raise EvaluationError(f"Unknown logical operator: {name}")


def _evaluate_special(name: str, args: tuple[ASTNode, ...], state: EvaluationState) -> bool:
    """Evaluate special boolean functions."""
    if name == "has-position":
        return state.has_position()

    if name == "market-hours":
        # For now, always return True - can be enhanced with market calendar
        return True

    if name == "time-between":
        # (time-between "09:30" "16:00")
        if len(args) != 2:
            raise EvaluationError("time-between requires exactly 2 arguments")

        start_str = args[0].value if isinstance(args[0], Literal) else ""
        end_str = args[1].value if isinstance(args[1], Literal) else ""

        if not isinstance(start_str, str) or not isinstance(end_str, str):
            raise EvaluationError("time-between requires string arguments")

        current_time = state.current_bar.timestamp.time()
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()

        return bool(start_time <= current_time <= end_time)

    if name == "day-of-week":
        # (day-of-week 1 2 3 4 5) - weekday numbers (0=Monday)
        days = []
        for arg in args:
            if isinstance(arg, Literal) and isinstance(arg.value, int):
                days.append(arg.value)

        current_day = state.current_bar.timestamp.weekday()
        return current_day in days

    raise EvaluationError(f"Unknown special function: {name}")


def evaluate_condition(node: ASTNode, state: EvaluationState) -> bool:
    """Evaluate an AST condition node.

    Args:
        node: The condition AST node
        state: Current evaluation state

    Returns:
        True if condition is met, False otherwise

    Raises:
        EvaluationError: If condition cannot be evaluated
    """
    if isinstance(node, Literal):
        if isinstance(node.value, bool):
            return node.value
        raise EvaluationError(f"Non-boolean literal in condition context: {node.value}")

    if isinstance(node, FunctionCall):
        name = node.name
        args = node.args

        # Comparison operators
        if name in COMPARATORS:
            if len(args) != 2:
                raise EvaluationError(f"Comparator {name} requires exactly 2 arguments")
            return _evaluate_comparison(name, args[0], args[1], state)

        # Logical operators
        if name in LOGICAL_OPS:
            return _evaluate_logical(name, args, state)

        # Crossover operators
        if name in CROSSOVER_OPS:
            if len(args) != 2:
                raise EvaluationError(f"Crossover {name} requires exactly 2 arguments")
            return _evaluate_crossover(name, args[0], args[1], state)

        # Special functions
        if name in SPECIAL_OPS:
            return _evaluate_special(name, args, state)

        raise EvaluationError(f"Function {name} does not return boolean")

    raise EvaluationError(f"Cannot evaluate as condition: {type(node)}")


def evaluate_entry(state: EvaluationState, entry_condition: ASTNode) -> bool:
    """Evaluate entry condition.

    Args:
        state: Current evaluation state
        entry_condition: The entry condition AST

    Returns:
        True if entry signal should be generated
    """
    try:
        return evaluate_condition(entry_condition, state)
    except EvaluationError:
        return False


def evaluate_exit(state: EvaluationState, exit_condition: ASTNode) -> bool:
    """Evaluate exit condition.

    Args:
        state: Current evaluation state
        exit_condition: The exit condition AST

    Returns:
        True if exit signal should be generated
    """
    try:
        return evaluate_condition(exit_condition, state)
    except EvaluationError:
        return False
