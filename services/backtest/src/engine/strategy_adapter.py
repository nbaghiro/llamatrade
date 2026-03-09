"""Strategy adapter for backtest engine.

Adapts compiled DSL strategies to work with the bar-by-bar BacktestEngine,
converting allocation weights to SignalData format for position management.

This module uses the shared indicator implementations from llamatrade_compiler.pipeline.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

# Import from allocation-based compiler
from llamatrade_compiler import Bar, CompiledStrategy, compile_strategy
from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_symbols,
)
from llamatrade_dsl import RebalanceFrequency, parse_strategy, validate_strategy

from src.engine.backtester import BacktestEngine, BarData, SignalData

__all__ = [
    "create_strategy_function",
    "create_multi_symbol_strategy",
    "AllocationState",
    "IndicatorSpec",
    "should_rebalance",
]


def should_rebalance(
    current_date: date,
    last_rebalance: date | None,
    frequency: RebalanceFrequency | None,
) -> bool:
    """Determine if rebalancing should occur based on frequency.

    Args:
        current_date: The current trading date
        last_rebalance: Date of the last rebalance (None if never)
        frequency: Rebalance frequency (daily, weekly, monthly, quarterly, annually)

    Returns:
        True if rebalancing should occur, False otherwise
    """
    # First bar always triggers rebalance
    if last_rebalance is None:
        return True

    # Same day never triggers rebalance
    if current_date == last_rebalance:
        return False

    # Default to daily if not specified
    freq = frequency or "daily"

    match freq:
        case "daily":
            # Rebalance every trading day
            return current_date > last_rebalance

        case "weekly":
            # Rebalance on Monday (weekday 0) or if more than 7 days passed
            is_monday = current_date.weekday() == 0
            days_passed = (current_date - last_rebalance).days
            return is_monday and days_passed >= 1

        case "monthly":
            # Rebalance when month changes
            return (
                current_date.month != last_rebalance.month
                or current_date.year != last_rebalance.year
            )

        case "quarterly":
            # Rebalance when quarter changes (months 1,4,7,10)
            current_quarter = (current_date.month - 1) // 3
            last_quarter = (last_rebalance.month - 1) // 3
            return current_quarter != last_quarter or current_date.year != last_rebalance.year

        case "annually":
            # Rebalance when year changes
            return current_date.year != last_rebalance.year


def _empty_float_dict() -> dict[str, float]:
    """Factory for empty string-to-float dict."""
    return {}


@dataclass
class AllocationState:
    """Mutable state for allocation-based strategy evaluation."""

    current_weights: dict[str, float] = field(default_factory=_empty_float_dict)
    target_weights: dict[str, float] = field(default_factory=_empty_float_dict)
    last_rebalance: date | None = None
    rebalance_frequency: RebalanceFrequency | None = None


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

    Respects the rebalance frequency defined in the strategy - signals are only
    generated on rebalance days.

    Args:
        config_sexpr: The strategy S-expression in allocation format

    Returns:
        Tuple of (strategy function, minimum required bars)

    Example S-expression:
        (strategy "My Strategy"
            :benchmark SPY
            :rebalance monthly
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

    # Get rebalance frequency from strategy
    rebalance_frequency = ast.rebalance

    # Get required symbols
    get_required_symbols(ast)

    # Create compiled strategy per symbol for state management
    compiled_strategies: dict[str, CompiledStrategy] = {}
    # Single shared state for rebalancing across all symbols
    shared_state = AllocationState(rebalance_frequency=rebalance_frequency)

    def strategy_fn(engine: BacktestEngine, symbol: str, bar: BarData) -> list[SignalData]:
        """Evaluate strategy and return signals based on allocation changes.

        Only generates signals when rebalancing is due according to frequency.
        """
        # Get current date from bar timestamp
        current_date = bar["timestamp"].date()

        # Check if we should rebalance
        if not should_rebalance(
            current_date, shared_state.last_rebalance, shared_state.rebalance_frequency
        ):
            # Not a rebalance day - no signals
            return []

        # Get or create compiled strategy for this evaluation context
        # We use a single compiled strategy that handles all symbols
        if "main" not in compiled_strategies:
            compiled_strategies["main"] = compile_strategy(ast)

        compiled = compiled_strategies["main"]

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
        shared_state.current_weights.get(symbol, 0.0)

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
        shared_state.current_weights[symbol] = target_weight
        shared_state.target_weights = allocation["weights"].copy()
        shared_state.last_rebalance = current_date

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


# Type alias for multi-symbol strategy function
# Signature: (engine, bars_dict) -> list[SignalData]
# where bars_dict is {symbol: BarData} for all symbols on current date
MultiSymbolStrategyFn = Callable[[BacktestEngine, dict[str, BarData]], list[SignalData]]


def create_multi_symbol_strategy(
    config_sexpr: str,
) -> tuple[MultiSymbolStrategyFn, set[str], int]:
    """Create a multi-symbol strategy function from an allocation-based S-expression.

    Unlike create_strategy_function which is called per-symbol, this function
    receives ALL symbols' bars at once, enabling proper cross-symbol comparisons
    for portfolio-level allocation decisions (e.g., momentum weighting, risk parity).

    This is the recommended approach for multi-asset allocation strategies.

    Args:
        config_sexpr: The strategy S-expression in allocation format

    Returns:
        Tuple of (strategy function, required symbols, minimum required bars)

    Example:
        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        # In backtest loop:
        bars_today = {sym: get_bar(sym, date) for sym in symbols}
        signals = strategy_fn(engine, bars_today)
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

    # Get rebalance frequency and required symbols from strategy
    rebalance_frequency = ast.rebalance
    required_symbols = get_required_symbols(ast)

    # Create compiled strategy (shared across all evaluations)
    compiled_strategy = compile_strategy(ast)

    # Shared state for rebalancing
    shared_state = AllocationState(rebalance_frequency=rebalance_frequency)

    def multi_symbol_strategy_fn(
        engine: BacktestEngine, bars_dict: dict[str, BarData]
    ) -> list[SignalData]:
        """Evaluate strategy with all symbols' bars simultaneously.

        Args:
            engine: The backtest engine instance
            bars_dict: Dictionary of symbol -> BarData for current date

        Returns:
            List of signals for all symbols that need position changes
        """
        if not bars_dict:
            return []

        # Get current date from any bar
        first_bar = next(iter(bars_dict.values()))
        current_date = first_bar["timestamp"].date()

        # Check if we should rebalance
        if not should_rebalance(
            current_date, shared_state.last_rebalance, shared_state.rebalance_frequency
        ):
            return []

        # Convert all bars to compiler format
        compiler_bars: dict[str, Bar] = {
            symbol: _convert_bar(bar) for symbol, bar in bars_dict.items()
        }

        # Compute allocation with all symbols' data
        allocation = compiled_strategy.compute_allocation(compiler_bars)

        # Check if we have valid weights
        if not allocation["weights"]:
            return []

        signals: list[SignalData] = []
        total_equity = engine.get_equity()

        # Generate signals for ALL symbols based on allocation
        for symbol, target_weight in allocation["weights"].items():
            # Skip if we don't have bar data for this symbol
            if symbol not in bars_dict:
                continue

            bar = bars_dict[symbol]
            current_weight = shared_state.current_weights.get(symbol, 0.0)
            has_position = engine.has_position(symbol)

            # Weight changed significantly - generate signal
            weight_change = abs(target_weight - current_weight)
            if weight_change < 0.1 and has_position == (target_weight > 0):
                # No significant change needed
                continue

            if target_weight > 0 and not has_position:
                # Need to buy
                position_value = total_equity * (target_weight / 100)
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
                # Need to sell
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

            elif target_weight > 0 and has_position:
                # Rebalance existing position
                pos = engine.get_position(symbol)
                if pos:
                    current_value = pos.quantity * bar["close"]
                    target_value = total_equity * (target_weight / 100)
                    value_diff = target_value - current_value

                    # Only rebalance if difference is significant (>5% of target)
                    if abs(value_diff) > target_value * 0.05:
                        quantity_diff = abs(value_diff) / bar["close"]
                        if value_diff > 0:
                            # Need to buy more
                            signals.append(
                                {
                                    "type": "buy",
                                    "symbol": symbol,
                                    "quantity": quantity_diff,
                                    "price": bar["close"],
                                }
                            )
                        else:
                            # Need to sell some
                            quantity_to_sell = min(quantity_diff, pos.quantity)
                            signals.append(
                                {
                                    "type": "sell",
                                    "symbol": symbol,
                                    "quantity": quantity_to_sell,
                                    "price": bar["close"],
                                }
                            )

        # Update state
        shared_state.target_weights = allocation["weights"].copy()
        shared_state.current_weights = allocation["weights"].copy()
        shared_state.last_rebalance = current_date

        return signals

    return multi_symbol_strategy_fn, required_symbols, min_bars
