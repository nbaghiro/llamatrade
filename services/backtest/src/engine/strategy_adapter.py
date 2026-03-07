"""Strategy adapter for backtest engine.

Adapts compiled DSL strategies to work with the bar-by-bar BacktestEngine,
converting allocation weights to SignalData format for position management.

This module uses the shared indicator implementations from llamatrade_compiler.pipeline.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

# Import from allocation-based compiler
from llamatrade_compiler import Bar, CompiledStrategy, compile_strategy
from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_symbols,
)
from llamatrade_dsl import parse_strategy, validate_strategy

from src.engine.backtester import BacktestEngine, BarData, SignalData

# Re-export for backward compatibility
__all__ = [
    "create_strategy_function",
    "AllocationState",
    "IndicatorSpec",
]


@dataclass
class AllocationState:
    """Mutable state for allocation-based strategy evaluation."""

    current_weights: dict[str, float] = field(default_factory=dict)
    target_weights: dict[str, float] = field(default_factory=dict)


def _convert_bar(bar: BarData) -> Bar:
    """Convert backtest BarData to compiler Bar format."""
    return Bar(
        timestamp=bar["timestamp"],
        open=bar["open"],
        high=bar["high"],
        low=bar["low"],
        close=bar["close"],
        volume=bar["volume"],
    )


def create_strategy_function(
    config_sexpr: str,
) -> tuple[Callable[[BacktestEngine, str, BarData], list[SignalData]], int]:
    """Create a strategy function from an allocation-based S-expression config.

    This function adapts the allocation-based DSL to the signal-based backtest engine.
    When target allocation for a symbol increases from 0, it generates a buy signal.
    When target allocation decreases to 0, it generates a sell signal.

    Args:
        config_sexpr: The strategy S-expression in allocation format

    Returns:
        Tuple of (strategy function, minimum required bars)

    Example S-expression:
        (strategy "My Strategy"
            :benchmark SPY
            :rebalance daily
            (if (> (rsi SPY 14) 70)
                (asset TLT :weight 100)
                (else (asset SPY :weight 100))))
    """
    # Parse and validate
    ast = parse_strategy(config_sexpr)
    validation = validate_strategy(ast)
    if not validation.valid:
        errors = "; ".join(str(e) for e in validation.errors)
        raise ValueError(f"Invalid strategy: {errors}")

    # Extract indicators and calculate minimum bars
    indicators = extract_indicators(ast)
    min_bars = get_max_lookback(indicators)
    min_bars = max(min_bars, 2)  # At least 2 for crossovers

    # Get required symbols
    get_required_symbols(ast)

    # Create compiled strategy per symbol for state management
    compiled_strategies: dict[str, CompiledStrategy] = {}
    allocation_states: dict[str, AllocationState] = {}

    def strategy_fn(engine: BacktestEngine, symbol: str, bar: BarData) -> list[SignalData]:
        """Evaluate strategy and return signals based on allocation changes."""
        # Get or create compiled strategy for this evaluation context
        # We use a single compiled strategy that handles all symbols
        if "main" not in compiled_strategies:
            compiled_strategies["main"] = compile_strategy(ast)

        compiled = compiled_strategies["main"]

        # Get or create allocation state
        if symbol not in allocation_states:
            allocation_states[symbol] = AllocationState()
        state = allocation_states[symbol]

        # Convert bar to compiler format
        compiler_bar = _convert_bar(bar)

        # Build bars dict for all symbols we've seen
        # For simplicity, we use the same bar for all symbols in this single-symbol call
        bars_dict = {symbol: compiler_bar}

        # Compute allocation
        allocation = compiled.compute_allocation(bars_dict)

        # Check if we have valid weights
        if not allocation["weights"]:
            return []

        # Get target weight for this symbol
        target_weight = allocation["weights"].get(symbol, 0.0)
        state.current_weights.get(symbol, 0.0)

        signals: list[SignalData] = []

        # Generate signals based on weight changes
        has_position = engine.has_position(symbol)

        if target_weight > 0 and not has_position:
            # Target allocation increased - buy signal
            equity = engine.get_equity()
            position_value = equity * (target_weight / 100)
            quantity = position_value / bar["close"] if bar["close"] > 0 else 0.0

            if quantity > 0:
                signals.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": bar["close"],
                    }
                )

        elif target_weight == 0 and has_position:
            # Target allocation is zero - sell signal
            pos = engine.get_position(symbol)
            if pos:
                signals.append(
                    {
                        "type": "sell",
                        "symbol": symbol,
                        "quantity": pos.quantity,
                        "price": bar["close"],
                    }
                )

        # Update state
        state.current_weights[symbol] = target_weight
        state.target_weights = allocation["weights"].copy()

        return signals

    return strategy_fn, min_bars


def create_allocation_strategy(
    config_sexpr: str,
) -> tuple[CompiledStrategy, set[str], int]:
    """Create a compiled allocation strategy.

    This is the preferred way to use allocation-based strategies.
    Returns the compiled strategy directly for use with allocation-aware engines.

    Args:
        config_sexpr: The strategy S-expression

    Returns:
        Tuple of (compiled strategy, required symbols, minimum bars)
    """
    ast = parse_strategy(config_sexpr)
    validation = validate_strategy(ast)
    if not validation.valid:
        errors = "; ".join(str(e) for e in validation.errors)
        raise ValueError(f"Invalid strategy: {errors}")

    compiled = compile_strategy(ast)
    symbols = get_required_symbols(ast)
    min_bars = compiled.min_bars

    return compiled, symbols, min_bars
