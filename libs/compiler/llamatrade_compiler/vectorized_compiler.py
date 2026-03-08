"""Strategy compiler for vectorized backtest engine.

Compiles allocation DSL strategies into NumPy operations for fast vectorized execution.
Uses the shared indicator implementations from pipeline.py.
"""

from collections.abc import Callable
from typing import cast

import numpy as np

from llamatrade_compiler.pipeline import (
    adx,
    atr,
    bollinger_bands,
    cci,
    donchian,
    ema,
    keltner,
    macd,
    mfi,
    momentum,
    obv,
    rsi,
    sma,
    stddev,
    stochastic,
    vwap,
    williams_r,
)
from llamatrade_compiler.vectorized import VectorizedBarData, VectorizedCompiledStrategy
from llamatrade_dsl import (
    Asset,
    Block,
    Comparison,
    Condition,
    Crossover,
    Filter,
    Group,
    If,
    Indicator,
    NumericLiteral,
    ParseError,
    Price,
    Strategy,
    Value,
    Weight,
    parse,
    validate,
)


def compile_vectorized_strategy(config_sexpr: str) -> VectorizedCompiledStrategy:
    """Compile a DSL strategy into a vectorized executable format.

    Args:
        config_sexpr: The strategy S-expression

    Returns:
        VectorizedCompiledStrategy ready for vectorized execution
    """
    # Parse and validate
    try:
        strategy = parse(config_sexpr)
    except ParseError as e:
        raise ValueError(f"Invalid strategy: {e}") from e

    validation = validate(strategy)
    if not validation.valid:
        errors = "; ".join(str(e) for e in validation.errors)
        raise ValueError(f"Invalid strategy: {errors}")

    # Compile allocation function
    allocation_fn = _compile_allocation(strategy)

    return VectorizedCompiledStrategy(
        allocation_fn=allocation_fn,
        strategy_name=strategy.name,
        rebalance_frequency=strategy.rebalance,
        benchmark=strategy.benchmark,
    )


def _compile_allocation(
    strategy: Strategy,
) -> Callable[[VectorizedBarData, dict[str, np.ndarray]], dict[str, np.ndarray]]:
    """Compile strategy into a vectorized allocation function.

    Returns a function that takes (bars, indicators) and returns
    a dict mapping symbol -> weight array of shape (num_bars,).
    """

    def allocation_fn(
        bars: VectorizedBarData,
        indicators: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        # Compute required indicators
        computed_indicators = _compute_all_indicators(strategy, bars)
        indicators.update(computed_indicators)

        # Evaluate allocation from strategy tree
        num_bars = bars["closes"].shape[1]
        return _evaluate_block_vectorized(strategy, bars, indicators, num_bars)

    return allocation_fn


def _compute_all_indicators(
    strategy: Strategy,
    bars: VectorizedBarData,
) -> dict[str, np.ndarray]:
    """Recursively extract and compute all indicators from a strategy."""
    indicators: dict[str, np.ndarray] = {}
    _extract_indicators_from_block(strategy, bars, indicators)
    return indicators


def _extract_indicators_from_block(
    block: Block,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> None:
    """Recursively extract indicators from a block."""
    if isinstance(block, Strategy):
        for child in block.children:
            _extract_indicators_from_block(child, bars, indicators)

    elif isinstance(block, Group):
        for child in block.children:
            _extract_indicators_from_block(child, bars, indicators)

    elif isinstance(block, Weight):
        for child in block.children:
            _extract_indicators_from_block(child, bars, indicators)

    elif isinstance(block, If):
        _extract_indicators_from_condition(block.condition, bars, indicators)
        _extract_indicators_from_block(block.then_block, bars, indicators)
        if block.else_block:
            _extract_indicators_from_block(block.else_block, bars, indicators)

    elif isinstance(block, Filter):
        for child in block.children:
            _extract_indicators_from_block(child, bars, indicators)


def _extract_indicators_from_condition(
    condition: Condition,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> None:
    """Extract indicators from a condition."""
    if isinstance(condition, Comparison):
        _extract_indicators_from_value(condition.left, bars, indicators)
        _extract_indicators_from_value(condition.right, bars, indicators)

    elif isinstance(condition, Crossover):
        _extract_indicators_from_value(condition.fast, bars, indicators)
        _extract_indicators_from_value(condition.slow, bars, indicators)

    else:
        # condition is LogicalOp (the only remaining type in the Condition union)
        for operand in condition.operands:
            _extract_indicators_from_condition(operand, bars, indicators)


def _extract_indicators_from_value(
    value: Value,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> None:
    """Extract and compute indicators from a value."""
    if not isinstance(value, Indicator):
        return

    key = _build_indicator_key(value)
    if key in indicators:
        return

    # Get symbol index (assuming single symbol for now, or symbol mapping needed)
    closes = bars["closes"][0]  # First symbol
    highs = bars["highs"][0]
    lows = bars["lows"][0]
    volumes = bars["volumes"][0]

    result = _compute_single_indicator(
        value.name,
        closes,
        highs,
        lows,
        closes,
        volumes,
        list(value.params),
        value.output,
    )
    indicators[key] = result


def _compute_single_indicator(
    indicator_type: str,
    source_data: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    params: list[int | float],
    output_field: str | None,
) -> np.ndarray:
    """Compute a single indicator using shared pipeline functions."""
    period = int(params[0]) if params else 14

    if indicator_type == "sma":
        return sma(source_data, period)

    elif indicator_type == "ema":
        return ema(source_data, period)

    elif indicator_type == "rsi":
        return rsi(source_data, period)

    elif indicator_type == "stddev":
        return stddev(source_data, period)

    elif indicator_type == "momentum":
        return momentum(source_data, period)

    elif indicator_type == "macd":
        fast = int(params[0]) if len(params) > 0 else 12
        slow = int(params[1]) if len(params) > 1 else 26
        signal = int(params[2]) if len(params) > 2 else 9
        macd_line, signal_line, histogram = macd(source_data, fast, slow, signal)
        if output_field == "signal":
            return signal_line
        elif output_field == "histogram":
            return histogram
        return macd_line

    elif indicator_type == "bbands":
        num_std = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = bollinger_bands(source_data, period, num_std)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        return middle

    elif indicator_type == "atr":
        return atr(highs, lows, closes, period)

    elif indicator_type == "adx":
        adx_val, plus_di, minus_di = adx(highs, lows, closes, period)
        if output_field == "plus_di":
            return plus_di
        elif output_field == "minus_di":
            return minus_di
        return adx_val

    elif indicator_type == "stoch":
        k_period = int(params[0]) if len(params) > 0 else 14
        d_period = int(params[1]) if len(params) > 1 else 3
        smooth = int(params[2]) if len(params) > 2 else 3
        k, d = stochastic(highs, lows, closes, k_period, d_period, smooth)
        if output_field == "d":
            return d
        return k

    elif indicator_type == "cci":
        return cci(highs, lows, closes, period)

    elif indicator_type == "williams-r":
        return williams_r(highs, lows, closes, period)

    elif indicator_type == "obv":
        return obv(closes, volumes)

    elif indicator_type == "mfi":
        return mfi(highs, lows, closes, volumes, period)

    elif indicator_type == "vwap":
        return vwap(highs, lows, closes, volumes)

    elif indicator_type == "keltner":
        multiplier = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = keltner(highs, lows, closes, period, multiplier)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        return middle

    elif indicator_type == "donchian":
        upper, lower = donchian(highs, lows, period)
        if output_field == "lower":
            return lower
        return upper

    else:
        return sma(source_data, period)


def _build_indicator_key(indicator: Indicator) -> str:
    """Build indicator cache key."""
    parts = [indicator.name, indicator.symbol, "close"]
    parts.extend(str(p) for p in indicator.params)
    if indicator.output:
        parts.append(indicator.output)
    return "_".join(parts)


def _evaluate_block_vectorized(
    block: Block,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
    num_bars: int,
) -> dict[str, np.ndarray]:
    """Evaluate a block and return vectorized allocation weights."""
    if isinstance(block, Strategy):
        return _evaluate_children_vectorized(block.children, bars, indicators, num_bars)

    if isinstance(block, Group):
        return _evaluate_children_vectorized(block.children, bars, indicators, num_bars)

    if isinstance(block, Weight):
        return _evaluate_weight_vectorized(block, bars, indicators, num_bars)

    if isinstance(block, Asset):
        # Static weight for all bars
        weight = block.weight or 0
        return {block.symbol: np.full(num_bars, weight)}

    if isinstance(block, If):
        return _evaluate_if_vectorized(block, bars, indicators, num_bars)

    # block is Filter (the only remaining type in the Block union)
    return _evaluate_filter_vectorized(block, bars, indicators, num_bars)


def _evaluate_children_vectorized(
    children: list[Block],
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
    num_bars: int,
) -> dict[str, np.ndarray]:
    """Evaluate multiple children and combine weights."""
    combined: dict[str, np.ndarray] = {}

    for child in children:
        child_weights = _evaluate_block_vectorized(child, bars, indicators, num_bars)
        for symbol, weights in child_weights.items():
            if symbol in combined:
                combined[symbol] = combined[symbol] + weights
            else:
                combined[symbol] = weights

    return combined


def _evaluate_weight_vectorized(
    weight: Weight,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
    num_bars: int,
) -> dict[str, np.ndarray]:
    """Evaluate a Weight block with vectorized computation."""
    # Get child weights
    child_weights: dict[str, np.ndarray] = {}
    for child in weight.children:
        weights = _evaluate_block_vectorized(child, bars, indicators, num_bars)
        child_weights.update(weights)

    if not child_weights:
        return {}

    symbols = list(child_weights.keys())
    method = weight.method

    if method == "specified":
        return child_weights

    if method == "equal":
        equal_weight = 100.0 / len(symbols)
        return {s: np.full(num_bars, equal_weight) for s in symbols}

    # For dynamic methods, return equal weights as fallback
    # (full implementation would compute time-varying weights)
    equal_weight = 100.0 / len(symbols)
    return {s: np.full(num_bars, equal_weight) for s in symbols}


def _evaluate_if_vectorized(
    if_block: If,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
    num_bars: int,
) -> dict[str, np.ndarray]:
    """Evaluate an If block with vectorized condition."""
    # Evaluate condition for all bars
    condition_mask = _evaluate_condition_vectorized(if_block.condition, bars, indicators)

    # Get then and else weights
    then_weights = _evaluate_block_vectorized(if_block.then_block, bars, indicators, num_bars)

    if if_block.else_block:
        else_weights = _evaluate_block_vectorized(if_block.else_block, bars, indicators, num_bars)
    else:
        else_weights = {}

    # Combine based on condition
    all_symbols = set(then_weights.keys()) | set(else_weights.keys())
    result: dict[str, np.ndarray] = {}

    for symbol in all_symbols:
        then_w = then_weights.get(symbol, np.zeros(num_bars))
        else_w = else_weights.get(symbol, np.zeros(num_bars))
        result[symbol] = np.where(condition_mask, then_w, else_w)

    return result


def _evaluate_filter_vectorized(
    filter_block: Filter,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
    num_bars: int,
) -> dict[str, np.ndarray]:
    """Evaluate a Filter block (simplified - returns child weights)."""
    # For simplicity, just return child weights without filtering
    # Full implementation would rank and select at each bar
    return _evaluate_children_vectorized(filter_block.children, bars, indicators, num_bars)


def _evaluate_condition_vectorized(
    condition: Condition,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> np.ndarray:
    """Evaluate a condition in vectorized form.

    Returns boolean array of shape (num_bars,).
    """
    num_bars = bars["closes"].shape[1]

    if isinstance(condition, Comparison):
        left = _get_vectorized_value(condition.left, bars, indicators)
        right = _get_vectorized_value(condition.right, bars, indicators)

        op = condition.operator
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == "=":
            return left == right
        # op must be "!=" at this point
        return left != right

    if isinstance(condition, Crossover):
        fast = _get_vectorized_value(condition.fast, bars, indicators)
        slow = _get_vectorized_value(condition.slow, bars, indicators)

        prev_fast = np.roll(fast, 1)
        prev_slow = np.roll(slow, 1)
        prev_fast[0] = np.nan
        prev_slow[0] = np.nan

        if condition.direction == "above":
            return (prev_fast <= prev_slow) & (fast > slow)
        else:
            return (prev_fast >= prev_slow) & (fast < slow)

    # condition is LogicalOp (the only remaining type in the Condition union)
    if condition.operator == "and":
        result = np.ones(num_bars, dtype=bool)
        for operand in condition.operands:
            result &= _evaluate_condition_vectorized(operand, bars, indicators)
        return result

    if condition.operator == "or":
        result = np.zeros(num_bars, dtype=bool)
        for operand in condition.operands:
            result |= _evaluate_condition_vectorized(operand, bars, indicators)
        return result

    # condition.operator is "not"
    return ~_evaluate_condition_vectorized(condition.operands[0], bars, indicators)


def _get_vectorized_value(
    value: Value,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> np.ndarray:
    """Get vectorized value array."""
    num_bars = bars["closes"].shape[1]

    if isinstance(value, NumericLiteral):
        return cast(np.ndarray, np.full(num_bars, value.value, dtype=np.float64))

    if isinstance(value, Price):
        # For now, use first symbol (would need symbol mapping for multi-symbol)
        if value.field == "close":
            return bars["closes"][0]
        if value.field == "open":
            return bars["opens"][0]
        if value.field == "high":
            return bars["highs"][0]
        if value.field == "low":
            return bars["lows"][0]
        if value.field == "volume":
            return bars["volumes"][0]
        return bars["closes"][0]

    if isinstance(value, Indicator):
        key = _build_indicator_key(value)
        if key in indicators:
            return indicators[key]
        return cast(np.ndarray, np.zeros(num_bars, dtype=np.float64))

    # value is Metric (the only remaining type in the Value union)
    return cast(np.ndarray, np.zeros(num_bars, dtype=np.float64))
