"""Extract indicator specifications from allocation strategy AST."""

from dataclasses import dataclass

from llamatrade_dsl import (
    INDICATORS,
    Block,
    Comparison,
    Condition,
    Crossover,
    Filter,
    Group,
    If,
    Indicator,
    Metric,
    Price,
    Strategy,
    Value,
    Weight,
)


@dataclass(frozen=True)
class IndicatorSpec:
    """Specification for a single indicator to compute.

    Attributes:
        indicator_type: The indicator function name (sma, ema, rsi, etc.)
        symbol: The asset symbol to compute for
        source: The price field to use (close, high, low, open, volume)
        params: Tuple of numeric parameters (period, fast, slow, signal, etc.)
        output_key: Unique cache key for storing results
        output_field: For multi-output indicators, the specific output
        required_bars: Minimum number of historical bars needed to compute
    """

    indicator_type: str
    symbol: str
    source: str
    params: tuple[int | float, ...]
    output_key: str
    output_field: str | None
    required_bars: int

    def __str__(self) -> str:
        field_suffix = f":{self.output_field}" if self.output_field else ""
        return f"{self.indicator_type}({self.symbol}, {self.source}, {self.params}){field_suffix}"


# Lookback requirements for each indicator type
INDICATOR_LOOKBACKS: dict[str, int] = {
    "sma": 0,
    "ema": 2,
    "rsi": 1,
    "macd": 0,
    "bbands": 0,
    "atr": 1,
    "adx": 1,
    "stoch": 0,
    "cci": 0,
    "williams-r": 0,
    "obv": 1,
    "mfi": 1,
    "vwap": 1,
    "keltner": 0,
    "donchian": 0,
    "stddev": 0,
    "momentum": 0,
}


def _calculate_required_bars(indicator_type: str, params: tuple[int | float, ...]) -> int:
    """Calculate minimum bars required for an indicator."""
    base_warmup = INDICATOR_LOOKBACKS.get(indicator_type, 0)

    if indicator_type in ("sma", "ema", "rsi", "atr", "adx", "cci", "mfi", "stddev", "momentum"):
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup

    if indicator_type == "macd":
        if len(params) >= 3:
            return int(max(params[0], params[1], params[2])) + base_warmup
        return 26 + base_warmup

    if indicator_type == "bbands":
        if params:
            return int(params[0]) + base_warmup
        return 20 + base_warmup

    if indicator_type == "stoch":
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup

    if indicator_type in ("williams-r", "donchian"):
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup

    if indicator_type == "keltner":
        if params:
            return int(params[0]) + base_warmup
        return 20 + base_warmup

    if indicator_type in ("obv", "vwap"):
        return 1 + base_warmup

    if params:
        return int(params[0]) + base_warmup
    return 14 + base_warmup


def _generate_output_key(
    indicator_type: str,
    symbol: str,
    source: str,
    params: tuple[int | float, ...],
    output_field: str | None,
) -> str:
    """Generate a unique cache key for an indicator."""
    parts = [indicator_type, symbol, source]
    parts.extend(str(p) for p in params)
    if output_field:
        parts.append(output_field)
    return "_".join(parts)


def _extract_from_value(
    value: Value,
    indicators: dict[str, IndicatorSpec],
) -> None:
    """Extract indicator specs from a Value node."""
    if isinstance(value, Indicator):
        indicator_type = value.name
        if indicator_type not in INDICATORS:
            return

        symbol = value.symbol
        source = "close"  # Default source
        params = value.params
        output_field = value.output

        output_key = _generate_output_key(indicator_type, symbol, source, params, output_field)

        if output_key not in indicators:
            required_bars = _calculate_required_bars(indicator_type, params)
            spec = IndicatorSpec(
                indicator_type=indicator_type,
                symbol=symbol,
                source=source,
                params=params,
                output_key=output_key,
                output_field=output_field,
                required_bars=required_bars,
            )
            indicators[output_key] = spec


def _extract_from_condition(
    condition: Condition,
    indicators: dict[str, IndicatorSpec],
) -> None:
    """Extract indicator specs from a Condition node."""
    if isinstance(condition, Comparison):
        _extract_from_value(condition.left, indicators)
        _extract_from_value(condition.right, indicators)

    elif isinstance(condition, Crossover):
        _extract_from_value(condition.fast, indicators)
        _extract_from_value(condition.slow, indicators)

    else:
        # condition is LogicalOp (the only remaining type in the Condition union)
        for operand in condition.operands:
            _extract_from_condition(operand, indicators)


def _extract_from_block(
    block: Block,
    indicators: dict[str, IndicatorSpec],
) -> None:
    """Extract indicator specs from a Block node."""
    if isinstance(block, Strategy):
        for child in block.children:
            _extract_from_block(child, indicators)

    elif isinstance(block, Group):
        for child in block.children:
            _extract_from_block(child, indicators)

    elif isinstance(block, Weight):
        for child in block.children:
            _extract_from_block(child, indicators)

    elif isinstance(block, If):
        _extract_from_condition(block.condition, indicators)
        _extract_from_block(block.then_block, indicators)
        if block.else_block:
            _extract_from_block(block.else_block, indicators)

    elif isinstance(block, Filter):
        for child in block.children:
            _extract_from_block(child, indicators)

    # else: block is Asset - assets don't contain indicators


def extract_indicators(strategy: Strategy) -> list[IndicatorSpec]:
    """Extract all indicator specifications from an allocation strategy.

    Walks the strategy tree, collecting all indicator references from
    conditions in If blocks.

    Args:
        strategy: The parsed allocation strategy AST

    Returns:
        List of IndicatorSpec objects, deduplicated by output_key
    """
    indicators: dict[str, IndicatorSpec] = {}
    _extract_from_block(strategy, indicators)
    return list(indicators.values())


def get_max_lookback(indicators: list[IndicatorSpec]) -> int:
    """Get the maximum lookback period needed across all indicators.

    Args:
        indicators: List of indicator specifications

    Returns:
        Maximum required_bars value, or 0 if empty
    """
    if not indicators:
        return 0
    return max(spec.required_bars for spec in indicators)


def get_required_symbols(strategy: Strategy) -> set[str]:
    """Get all symbols required by the strategy.

    Extracts symbols from:
    - Asset blocks
    - Indicators in conditions
    - Price references in conditions
    - Metrics in conditions

    Args:
        strategy: The parsed allocation strategy

    Returns:
        Set of symbol names
    """
    symbols: set[str] = set()
    _extract_symbols_from_block(strategy, symbols)
    return symbols


def _extract_symbols_from_block(block: Block, symbols: set[str]) -> None:
    """Recursively extract symbols from a block."""
    if isinstance(block, Strategy):
        for child in block.children:
            _extract_symbols_from_block(child, symbols)

    elif isinstance(block, Group):
        for child in block.children:
            _extract_symbols_from_block(child, symbols)

    elif isinstance(block, Weight):
        for child in block.children:
            _extract_symbols_from_block(child, symbols)

    elif isinstance(block, If):
        _extract_symbols_from_condition(block.condition, symbols)
        _extract_symbols_from_block(block.then_block, symbols)
        if block.else_block:
            _extract_symbols_from_block(block.else_block, symbols)

    elif isinstance(block, Filter):
        for child in block.children:
            _extract_symbols_from_block(child, symbols)

    else:
        # block is Asset (the only remaining type in the Block union)
        symbols.add(block.symbol)


def _extract_symbols_from_condition(condition: Condition, symbols: set[str]) -> None:
    """Recursively extract symbols from a condition."""
    if isinstance(condition, Comparison):
        _extract_symbols_from_value(condition.left, symbols)
        _extract_symbols_from_value(condition.right, symbols)

    elif isinstance(condition, Crossover):
        _extract_symbols_from_value(condition.fast, symbols)
        _extract_symbols_from_value(condition.slow, symbols)

    else:
        # condition is LogicalOp (the only remaining type in the Condition union)
        for operand in condition.operands:
            _extract_symbols_from_condition(operand, symbols)


def _extract_symbols_from_value(value: Value, symbols: set[str]) -> None:
    """Extract symbols from a value."""
    if isinstance(value, Indicator):
        symbols.add(value.symbol)
    elif isinstance(value, Price):
        symbols.add(value.symbol)
    elif isinstance(value, Metric):
        symbols.add(value.symbol)


def get_required_sources(indicators: list[IndicatorSpec]) -> set[str]:
    """Get all price/volume sources required by indicators.

    Args:
        indicators: List of indicator specifications

    Returns:
        Set of source field names (close, high, low, open, volume)
    """
    sources: set[str] = set()
    for spec in indicators:
        if spec.source in ("close", "open", "high", "low", "volume"):
            sources.add(spec.source)
        # Add additional sources needed by specific indicators
        if spec.indicator_type in ("atr", "stoch", "williams-r", "cci"):
            sources.update({"high", "low", "close"})
        if spec.indicator_type in ("obv", "mfi", "vwap"):
            sources.add("volume")
    return sources
