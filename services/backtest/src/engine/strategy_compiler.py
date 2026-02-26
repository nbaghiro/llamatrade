"""Strategy compiler for vectorized backtest engine.

Compiles DSL strategies into NumPy operations for fast vectorized execution.
"""

from collections.abc import Callable

import numpy as np
from llamatrade_dsl import parse_strategy, validate_strategy
from llamatrade_dsl.ast import ASTNode, FunctionCall, Keyword, Literal, Symbol
from llamatrade_dsl.validator import INDICATORS

from src.engine.strategy_adapter import (
    _compute_adx,
    _compute_atr,
    _compute_bbands,
    _compute_cci,
    _compute_donchian,
    _compute_ema,
    _compute_keltner,
    _compute_macd,
    _compute_mfi,
    _compute_momentum,
    _compute_obv,
    _compute_rsi,
    _compute_sma,
    _compute_stddev,
    _compute_stochastic,
    _compute_vwap,
    _compute_williams_r,
)
from src.engine.vectorized_engine import CompiledStrategy, VectorizedBarData


def compile_strategy(config_sexpr: str) -> CompiledStrategy:
    """Compile a DSL strategy into a vectorized executable format.

    Args:
        config_sexpr: The strategy S-expression

    Returns:
        CompiledStrategy ready for vectorized execution
    """
    # Parse and validate
    strategy = parse_strategy(config_sexpr)
    validation = validate_strategy(strategy)
    if not validation.valid:
        errors = "; ".join(str(e) for e in validation.errors)
        raise ValueError(f"Invalid strategy: {errors}")

    # Extract risk and sizing parameters
    stop_loss_pct = strategy.risk.get("stop_loss_pct")
    take_profit_pct = strategy.risk.get("take_profit_pct")
    position_size_pct = strategy.sizing.get("value", 10.0)

    # Compile entry and exit conditions
    entry_fn = _compile_condition(strategy.entry, is_entry=True)
    exit_fn = _compile_condition(strategy.exit, is_entry=False)

    return CompiledStrategy(
        entry_fn=entry_fn,
        exit_fn=exit_fn,
        position_size_pct=position_size_pct,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )


def _compile_condition(
    node: ASTNode,
    is_entry: bool,
) -> Callable[[VectorizedBarData, dict[str, np.ndarray]], np.ndarray]:
    """Compile a condition AST node into a vectorized function.

    Returns a function that takes (bars, indicators) and returns
    a boolean array of shape (num_symbols, num_bars).
    """

    def condition_fn(
        bars: VectorizedBarData,
        indicators: dict[str, np.ndarray],
    ) -> np.ndarray:
        # Compute required indicators
        computed_indicators = _compute_all_indicators(node, bars)
        indicators.update(computed_indicators)

        # Evaluate condition
        return _evaluate_vectorized(node, bars, indicators)

    return condition_fn


def _compute_all_indicators(
    node: ASTNode,
    bars: VectorizedBarData,
) -> dict[str, np.ndarray]:
    """Recursively extract and compute all indicators from an AST node."""
    indicators: dict[str, np.ndarray] = {}

    if not isinstance(node, FunctionCall):
        return indicators

    closes = bars["closes"]
    highs = bars["highs"]
    lows = bars["lows"]
    volumes = bars["volumes"]
    num_symbols, num_bars = closes.shape

    if node.name in INDICATORS:
        # Extract parameters
        source = "close"
        params: list[int | float] = []
        output_field: str | None = None

        for arg in node.args:
            if isinstance(arg, Symbol):
                source = arg.name
            elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
                params.append(arg.value)
            elif isinstance(arg, Keyword):
                output_field = arg.name

        # Build key
        key = _build_indicator_key(node.name, source, params, output_field)

        if key not in indicators:
            # Compute for each symbol
            result = np.zeros((num_symbols, num_bars))

            for sym_idx in range(num_symbols):
                sym_closes = closes[sym_idx]
                sym_highs = highs[sym_idx]
                sym_lows = lows[sym_idx]
                sym_volumes = volumes[sym_idx]

                # Get source data
                if source == "high":
                    source_data = sym_highs
                elif source == "low":
                    source_data = sym_lows
                elif source == "volume":
                    source_data = sym_volumes
                else:
                    source_data = sym_closes

                # Compute indicator
                result[sym_idx] = _compute_single_indicator(
                    node.name,
                    source_data,
                    sym_highs,
                    sym_lows,
                    sym_closes,
                    sym_volumes,
                    params,
                    output_field,
                )

            indicators[key] = result

    # Recurse into arguments
    for arg in node.args:
        child_indicators = _compute_all_indicators(arg, bars)
        indicators.update(child_indicators)

    return indicators


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
    """Compute a single indicator for one symbol."""
    period = int(params[0]) if params else 14

    if indicator_type == "sma":
        return _compute_sma(source_data, period)
    elif indicator_type == "ema":
        return _compute_ema(source_data, period)
    elif indicator_type == "rsi":
        return _compute_rsi(source_data, period)
    elif indicator_type == "stddev":
        return _compute_stddev(source_data, period)
    elif indicator_type == "momentum":
        return _compute_momentum(source_data, period)
    elif indicator_type == "macd":
        fast = int(params[0]) if len(params) > 0 else 12
        slow = int(params[1]) if len(params) > 1 else 26
        signal = int(params[2]) if len(params) > 2 else 9
        macd_line, signal_line, histogram = _compute_macd(source_data, fast, slow, signal)
        if output_field == "signal":
            return signal_line
        elif output_field == "histogram":
            return histogram
        return macd_line
    elif indicator_type == "bbands":
        num_std = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = _compute_bbands(source_data, period, num_std)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        return middle
    elif indicator_type == "atr":
        return _compute_atr(highs, lows, closes, period)
    elif indicator_type == "adx":
        adx, plus_di, minus_di = _compute_adx(highs, lows, closes, period)
        if output_field == "plus_di":
            return plus_di
        elif output_field == "minus_di":
            return minus_di
        return adx
    elif indicator_type == "stoch":
        k_period = int(params[0]) if len(params) > 0 else 14
        d_period = int(params[1]) if len(params) > 1 else 3
        k, d = _compute_stochastic(highs, lows, closes, k_period, d_period)
        if output_field == "d":
            return d
        return k
    elif indicator_type == "cci":
        return _compute_cci(highs, lows, closes, period)
    elif indicator_type == "williams-r":
        return _compute_williams_r(highs, lows, closes, period)
    elif indicator_type == "obv":
        return _compute_obv(closes, volumes)
    elif indicator_type == "mfi":
        return _compute_mfi(highs, lows, closes, volumes, period)
    elif indicator_type == "vwap":
        return _compute_vwap(highs, lows, closes, volumes)
    elif indicator_type == "keltner":
        multiplier = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = _compute_keltner(highs, lows, closes, period, multiplier)
        if output_field == "upper":
            return upper
        elif output_field == "lower":
            return lower
        return middle
    elif indicator_type == "donchian":
        upper, lower = _compute_donchian(highs, lows, period)
        if output_field == "lower":
            return lower
        return upper
    else:
        return _compute_sma(source_data, period)


def _build_indicator_key(
    name: str,
    source: str,
    params: list[int | float],
    output_field: str | None,
) -> str:
    """Build indicator cache key."""
    parts = [name, source] + [str(p) for p in params]
    if output_field:
        parts.append(output_field)
    return "_".join(parts)


def _evaluate_vectorized(
    node: ASTNode,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> np.ndarray:
    """Evaluate a condition AST node on vectorized data.

    Returns boolean array of shape (num_symbols, num_bars).
    """
    num_symbols, num_bars = bars["closes"].shape

    if isinstance(node, Literal):
        return np.full((num_symbols, num_bars), bool(node.value))

    if isinstance(node, FunctionCall):
        name = node.name
        args = node.args

        # Logical operators
        if name == "and":
            result = np.ones((num_symbols, num_bars), dtype=bool)
            for arg in args:
                result &= _evaluate_vectorized(arg, bars, indicators)
            return result

        if name == "or":
            result = np.zeros((num_symbols, num_bars), dtype=bool)
            for arg in args:
                result |= _evaluate_vectorized(arg, bars, indicators)
            return result

        if name == "not":
            return ~_evaluate_vectorized(args[0], bars, indicators)

        # Comparisons
        if name in (">", "<", ">=", "<=", "=", "!="):
            left = _get_vectorized_value(args[0], bars, indicators)
            right = _get_vectorized_value(args[1], bars, indicators)
            if name == ">":
                return left > right
            if name == "<":
                return left < right
            if name == ">=":
                return left >= right
            if name == "<=":
                return left <= right
            if name == "=":
                return np.asarray(left == right)
            if name == "!=":
                return np.asarray(left != right)

        # Crossovers
        if name in ("cross-above", "cross-below"):
            left = _get_vectorized_value(args[0], bars, indicators)
            right = _get_vectorized_value(args[1], bars, indicators)

            # Shift for previous values
            prev_left = np.roll(left, 1, axis=1)
            prev_right = np.roll(right, 1, axis=1)
            prev_left[:, 0] = np.nan
            prev_right[:, 0] = np.nan

            if name == "cross-above":
                return (prev_left <= prev_right) & (left > right)
            else:
                return (prev_left >= prev_right) & (left < right)

        # Special functions
        if name == "has-position":
            # This is handled at runtime
            return np.zeros((num_symbols, num_bars), dtype=bool)

    return np.zeros((num_symbols, num_bars), dtype=bool)


def _get_vectorized_value(
    node: ASTNode,
    bars: VectorizedBarData,
    indicators: dict[str, np.ndarray],
) -> np.ndarray:
    """Get the numeric value of an AST node as a vectorized array.

    Returns array of shape (num_symbols, num_bars).
    """
    num_symbols, num_bars = bars["closes"].shape

    if isinstance(node, Literal):
        # Literal.value can be various types but for numeric operations we need float
        value = node.value
        if isinstance(value, (int, float)):
            return np.full((num_symbols, num_bars), float(value))
        elif isinstance(value, bool):
            return np.full((num_symbols, num_bars), float(value))
        else:
            return np.zeros((num_symbols, num_bars))

    if isinstance(node, Symbol):
        if node.name == "close":
            return bars["closes"]
        if node.name == "open":
            return bars["opens"]
        if node.name == "high":
            return bars["highs"]
        if node.name == "low":
            return bars["lows"]
        if node.name == "volume":
            return bars["volumes"].astype(float)
        return np.zeros((num_symbols, num_bars))

    if isinstance(node, FunctionCall):
        if node.name in INDICATORS:
            # Extract parameters to build key
            source = "close"
            params: list[int | float] = []
            output_field: str | None = None

            for arg in node.args:
                if isinstance(arg, Symbol):
                    source = arg.name
                elif isinstance(arg, Literal) and isinstance(arg.value, (int, float)):
                    params.append(arg.value)
                elif isinstance(arg, Keyword):
                    output_field = arg.name

            key = _build_indicator_key(node.name, source, params, output_field)
            if key in indicators:
                return indicators[key]

    return np.zeros((num_symbols, num_bars))


def should_use_vectorized_engine(
    num_symbols: int,
    num_bars: int,
    threshold: int = 10000,
) -> bool:
    """Determine whether to use the vectorized engine based on data size.

    Args:
        num_symbols: Number of symbols
        num_bars: Number of bars per symbol
        threshold: Minimum total bars for vectorized engine

    Returns:
        True if vectorized engine should be used
    """
    total_bars = num_symbols * num_bars
    return total_bars > threshold
