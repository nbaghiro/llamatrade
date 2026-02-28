"""Extract indicator specifications from strategy AST."""

from collections.abc import Callable
from dataclasses import dataclass

from llamatrade_dsl import INDICATORS
from llamatrade_dsl.ast import ASTNode, FunctionCall, Keyword, Literal, Strategy, Symbol


@dataclass(frozen=True)
class IndicatorSpec:
    """Specification for a single indicator to compute.

    Attributes:
        indicator_type: The indicator function name (sma, ema, rsi, etc.)
        source: The price field to use (close, high, low, open, volume)
        params: Tuple of numeric parameters (period, fast, slow, signal, etc.)
        output_key: Unique cache key for storing results (e.g., "sma_close_20")
        output_field: For multi-output indicators, the specific output (line, signal, upper, etc.)
        required_bars: Minimum number of historical bars needed to compute
    """

    indicator_type: str
    source: str
    params: tuple[int | float, ...]
    output_key: str
    output_field: str | None
    required_bars: int

    def __str__(self) -> str:
        field_suffix = f":{self.output_field}" if self.output_field else ""
        return f"{self.indicator_type}({self.source}, {self.params}){field_suffix}"


# Lookback requirements for each indicator type
# Formula: required_bars = max_period + warm_up_bars
INDICATOR_LOOKBACKS: dict[str, int] = {
    "sma": 0,  # period + 0 warm-up
    "ema": 2,  # period + 2 warm-up for EMA convergence
    "rsi": 1,  # period + 1 for initial calculation
    "macd": 0,  # Uses max(fast, slow, signal)
    "bbands": 0,  # period + 0
    "atr": 1,  # period + 1 for true range
    "adx": 1,  # period + 1
    "stoch": 0,  # Uses k_period
    "cci": 0,  # period
    "williams-r": 0,  # period
    "obv": 1,  # Needs at least 1 bar of history
    "mfi": 1,  # period + 1
    "vwap": 1,  # Needs at least 1 bar
    "keltner": 0,  # ema_period
    "donchian": 0,  # period
    "stddev": 0,  # period
    "momentum": 0,  # period
}


def _extract_source(args: tuple[ASTNode, ...]) -> str:
    """Extract the source field from indicator arguments.

    The first positional argument should be a price Symbol or another indicator.
    """
    for arg in args:
        if isinstance(arg, Symbol):
            return str(arg.name)
        if isinstance(arg, FunctionCall):
            # Nested indicator - use the nested indicator's output
            return str(arg.name)
    return "close"  # Default to close


def _extract_params(args: tuple[ASTNode, ...]) -> tuple[int | float, ...]:
    """Extract numeric parameters from indicator arguments."""
    params: list[int | float] = []
    for arg in args:
        if isinstance(arg, Literal):
            if isinstance(arg.value, (int, float)) and not isinstance(arg.value, bool):
                params.append(arg.value)
    return tuple(params)


def _extract_output_field(args: tuple[ASTNode, ...]) -> str | None:
    """Extract output field selector from indicator arguments."""
    for arg in args:
        if isinstance(arg, Keyword):
            return str(arg.name)
    return None


def _calculate_required_bars(indicator_type: str, params: tuple[int | float, ...]) -> int:
    """Calculate minimum bars required for an indicator.

    Args:
        indicator_type: The indicator function name
        params: The indicator parameters

    Returns:
        Minimum number of historical bars needed
    """
    base_warmup = INDICATOR_LOOKBACKS.get(indicator_type, 0)

    if indicator_type in ("sma", "ema", "rsi", "atr", "adx", "cci", "mfi", "stddev", "momentum"):
        # Single period indicators: (source, period)
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup  # Default period

    if indicator_type == "macd":
        # MACD: (source, fast, slow, signal)
        if len(params) >= 3:
            return int(max(params[0], params[1], params[2])) + base_warmup
        return 26 + base_warmup  # Default slow period

    if indicator_type == "bbands":
        # Bollinger Bands: (source, period, std_dev)
        if params:
            return int(params[0]) + base_warmup
        return 20 + base_warmup

    if indicator_type == "stoch":
        # Stochastic: (source, k_period, d_period, smooth)
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup

    if indicator_type in ("williams-r", "donchian"):
        # Williams %R, Donchian: (source, period)
        if params:
            return int(params[0]) + base_warmup
        return 14 + base_warmup

    if indicator_type == "keltner":
        # Keltner: (source, ema_period, atr_mult)
        if params:
            return int(params[0]) + base_warmup
        return 20 + base_warmup

    if indicator_type in ("obv", "vwap"):
        # Volume indicators - minimal lookback
        return 1 + base_warmup

    # Default: assume first param is period
    if params:
        return int(params[0]) + base_warmup
    return 14 + base_warmup


def _generate_output_key(
    indicator_type: str,
    source: str,
    params: tuple[int | float, ...],
    output_field: str | None,
) -> str:
    """Generate a unique cache key for an indicator.

    Examples:
        sma(close, 20) -> "sma_close_20"
        macd(close, 12, 26, 9):signal -> "macd_close_12_26_9_signal"
        bbands(close, 20, 2):upper -> "bbands_close_20_2_upper"
    """
    parts = [indicator_type, source]
    parts.extend(str(p) for p in params)
    if output_field:
        parts.append(output_field)
    return "_".join(parts)


def _walk_ast(node: ASTNode, visitor: Callable[[ASTNode], None]) -> None:
    """Walk the AST and call visitor for each node."""
    visitor(node)
    if isinstance(node, FunctionCall):
        for arg in node.args:
            _walk_ast(arg, visitor)


def _extract_from_node(
    node: ASTNode,
    indicators: dict[str, IndicatorSpec],
) -> None:
    """Extract indicator specs from a single AST node."""
    if not isinstance(node, FunctionCall):
        return

    if node.name not in INDICATORS:
        return

    indicator_type = node.name
    source = _extract_source(node.args)
    params = _extract_params(node.args)
    output_field = _extract_output_field(node.args)

    # Generate the output key
    output_key = _generate_output_key(indicator_type, source, params, output_field)

    # Skip if we already have this indicator
    if output_key in indicators:
        return

    required_bars = _calculate_required_bars(indicator_type, params)

    spec = IndicatorSpec(
        indicator_type=indicator_type,
        source=source,
        params=params,
        output_key=output_key,
        output_field=output_field,
        required_bars=required_bars,
    )
    indicators[output_key] = spec


def extract_indicators(strategy: Strategy) -> list[IndicatorSpec]:
    """Extract all indicator specifications from a strategy.

    Walks the entry and exit conditions, collecting all indicator
    function calls and their parameters.

    Args:
        strategy: The parsed strategy AST

    Returns:
        List of IndicatorSpec objects, deduplicated by output_key
    """
    indicators: dict[str, IndicatorSpec] = {}

    # Walk entry condition
    _walk_ast(strategy.entry, lambda node: _extract_from_node(node, indicators))

    # Walk exit condition
    _walk_ast(strategy.exit, lambda node: _extract_from_node(node, indicators))

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


def get_required_sources(indicators: list[IndicatorSpec]) -> set[str]:
    """Get all price/volume sources required by indicators.

    Args:
        indicators: List of indicator specifications

    Returns:
        Set of source field names (close, high, low, open, volume)
    """
    sources: set[str] = set()
    for spec in indicators:
        # Direct price sources
        if spec.source in ("close", "open", "high", "low", "volume"):
            sources.add(spec.source)
        # Add any additional sources needed by specific indicators
        if spec.indicator_type in ("atr", "stoch", "williams-r", "cci"):
            # These need high, low, close
            sources.update({"high", "low", "close"})
        if spec.indicator_type in ("obv", "mfi", "vwap"):
            # These need volume
            sources.add("volume")
    return sources
