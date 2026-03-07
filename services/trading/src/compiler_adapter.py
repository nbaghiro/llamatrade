"""Adapter to use CompiledStrategy with StrategyRunner.

Bridges the llamatrade-compiler library's allocation-based CompiledStrategy
with the trading service's StrategyRunner protocol by converting target
allocations to buy/sell signals.
"""

import logging
from collections.abc import Sequence

from llamatrade_compiler import Bar, CompiledStrategy, compile_strategy
from llamatrade_compiler.extractor import get_required_symbols
from llamatrade_dsl import Strategy, parse_strategy, validate_strategy

from src.runner.bar_stream import BarData
from src.runner.runner import Position, Signal

logger = logging.getLogger(__name__)


class StrategyAdapter:
    """Adapts allocation-based CompiledStrategy to StrategyRunner's signal protocol.

    The StrategyRunner expects a callable with signature:
        (symbol: str, bars: list[BarData], position: Position | None, equity: float) -> Signal | None

    This adapter wraps a CompiledStrategy and converts allocation weights to signals:
    - When target weight > 0 and no position: generates buy signal
    - When target weight = 0 and has position: generates sell signal

    For multi-symbol strategies, each symbol gets its own CompiledStrategy
    instance to maintain independent state (bar history, indicators, etc.).
    """

    def __init__(self, strategy_sexpr: str):
        """Initialize with strategy S-expression.

        Args:
            strategy_sexpr: Strategy definition in allocation-based S-expression format

        Raises:
            ValueError: If the strategy is invalid or cannot be compiled.

        Example S-expression:
            (strategy "RSI Switch"
                :benchmark SPY
                :rebalance daily
                (if (> (rsi SPY 14) 70)
                    (asset TLT :weight 100)
                    (else (asset SPY :weight 100))))
        """
        # Parse the strategy
        try:
            self._ast: Strategy = parse_strategy(strategy_sexpr)
        except Exception as e:
            raise ValueError(f"Failed to parse strategy: {e}") from e

        # Validate the strategy
        validation = validate_strategy(self._ast)
        if not validation.valid:
            errors = "; ".join(str(e) for e in validation.errors)
            raise ValueError(f"Invalid strategy: {errors}")

        # Compile the strategy (used as a template)
        try:
            self._template: CompiledStrategy = compile_strategy(self._ast)
        except Exception as e:
            raise ValueError(f"Failed to compile strategy: {e}") from e

        # Extract required symbols
        self._symbols: set[str] = get_required_symbols(self._ast)

        # Per-symbol compiled strategies (each symbol needs its own state)
        self._per_symbol: dict[str, CompiledStrategy] = {}
        self._initialized_symbols: set[str] = set()

        # Track current allocations per symbol
        self._current_weights: dict[str, float] = {}

        logger.info(
            f"Compiled strategy '{self._template.name}' with "
            f"{len(self._template.indicators)} indicators, "
            f"min_bars={self._template.min_bars}"
        )

    def __call__(
        self,
        symbol: str,
        bars: Sequence[BarData],
        position: Position | None,
        equity: float,
    ) -> Signal | None:
        """Evaluate strategy and return signal if any.

        Args:
            symbol: The trading symbol
            bars: Sequence of BarData from the bar stream
            position: Current position (if any)
            equity: Current equity/buying power

        Returns:
            A Signal if entry/exit conditions are met, None otherwise
        """
        if not bars:
            return None

        # Get or create per-symbol compiled strategy
        # Each symbol needs its own state (bar history, indicator cache, etc.)
        if symbol not in self._per_symbol:
            self._per_symbol[symbol] = compile_strategy(self._ast)
            logger.debug(f"Created compiled strategy instance for {symbol}")

        compiled = self._per_symbol[symbol]

        # Convert latest BarData to compiler's Bar format
        latest_bar = bars[-1]
        compiler_bar = self._convert_bar(latest_bar)

        # Initialize with historical bars on first call for this symbol
        if symbol not in self._initialized_symbols:
            # Add all historical bars except the last (will be added by compute_allocation)
            for bar_data in bars[:-1]:
                compiled.add_bars({symbol: self._convert_bar(bar_data)})
            self._initialized_symbols.add(symbol)
            logger.debug(f"Initialized {symbol} with {len(bars) - 1} historical bars")

        # Compute allocation
        try:
            allocation = compiled.compute_allocation({symbol: compiler_bar})
        except Exception as e:
            logger.error(f"Strategy evaluation error for {symbol}: {e}")
            return None

        # Check if we have valid weights
        if not allocation["weights"]:
            return None

        # Get target weight for this symbol
        target_weight = allocation["weights"].get(symbol, 0.0)
        self._current_weights.get(symbol, 0.0)
        current_price = latest_bar.close

        # Determine if we need to generate a signal
        has_position = position is not None

        if target_weight > 0 and not has_position:
            # Target allocation - generate buy signal
            position_value = equity * (target_weight / 100)
            quantity = position_value / current_price if current_price > 0 else 0.0

            if quantity > 0:
                self._current_weights[symbol] = target_weight
                return Signal(
                    type="buy",
                    symbol=symbol,
                    quantity=quantity,
                    price=current_price,
                )

        elif target_weight == 0 and has_position:
            # Zero allocation - generate sell signal
            self._current_weights[symbol] = 0.0
            return Signal(
                type="sell",
                symbol=symbol,
                quantity=position.quantity,
                price=current_price,
            )

        # Update weight tracking
        self._current_weights[symbol] = target_weight
        return None

    def _convert_bar(self, bar: BarData) -> Bar:
        """Convert runner BarData to compiler Bar."""
        return Bar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )

    def reset(self, symbol: str | None = None) -> None:
        """Reset strategy state.

        Args:
            symbol: If provided, reset only that symbol's state.
                   If None, reset all symbols.
        """
        if symbol:
            if symbol in self._per_symbol:
                self._per_symbol[symbol].reset()
                self._initialized_symbols.discard(symbol)
                self._current_weights.pop(symbol, None)
        else:
            for compiled in self._per_symbol.values():
                compiled.reset()
            self._per_symbol.clear()
            self._initialized_symbols.clear()
            self._current_weights.clear()

    @property
    def name(self) -> str:
        """Get strategy name."""
        return str(self._template.name)

    @property
    def min_bars(self) -> int:
        """Get minimum bars required for evaluation."""
        return int(self._template.min_bars)

    @property
    def symbols(self) -> list[str]:
        """Get strategy symbols from the definition."""
        return list(self._symbols)

    @property
    def rebalance_frequency(self) -> str | None:
        """Get strategy rebalance frequency."""
        return self._template.rebalance_frequency

    def get_indicator_values(self, symbol: str) -> dict[str, float]:
        """Get current indicator values for a symbol.

        Useful for debugging and display in UI.

        Args:
            symbol: The symbol to get indicators for.

        Returns:
            Dictionary of indicator name to current value.
        """
        if symbol not in self._per_symbol:
            return {}

        compiled = self._per_symbol[symbol]

        # Get indicator cache if available
        if not hasattr(compiled, "_indicator_cache"):
            return {}

        cache = compiled._indicator_cache

        # Get the last value from each indicator array
        result: dict[str, float] = {}
        for key, arr in cache.items():
            if len(arr) > 0:
                result[key] = float(arr[-1])

        return result

    def get_current_weights(self) -> dict[str, float]:
        """Get current target weights for all symbols."""
        return self._current_weights.copy()

    def __repr__(self) -> str:
        return (
            f"StrategyAdapter(name={self.name!r}, min_bars={self.min_bars}, symbols={self.symbols})"
        )


def load_strategy_adapter(strategy_sexpr: str) -> StrategyAdapter:
    """Factory function to create a strategy adapter.

    Args:
        strategy_sexpr: Strategy definition in S-expression format

    Returns:
        A StrategyAdapter ready for use with StrategyRunner

    Raises:
        ValueError: If the strategy is invalid or cannot be compiled.
    """
    return StrategyAdapter(strategy_sexpr)
