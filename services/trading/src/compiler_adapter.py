"""Adapter to use CompiledStrategy with StrategyRunner.

Bridges the llamatrade-compiler library's CompiledStrategy with the
trading service's StrategyRunner protocol.
"""

import logging

from llamatrade_compiler import Bar, compile_strategy
from llamatrade_dsl import parse_strategy

from src.runner.bar_stream import BarData
from src.runner.runner import Position, Signal

logger = logging.getLogger(__name__)


class StrategyAdapter:
    """Adapts CompiledStrategy to StrategyRunner's StrategyFunction protocol.

    The StrategyRunner expects a callable with signature:
        (symbol: str, bars: list[BarData], position: Position | None, equity: float) -> Signal | None

    This adapter wraps a CompiledStrategy to match that interface.
    """

    def __init__(self, strategy_sexpr: str):
        """Initialize with strategy S-expression.

        Args:
            strategy_sexpr: Strategy definition in S-expression format
        """
        self.ast = parse_strategy(strategy_sexpr)
        self.compiled = compile_strategy(self.ast)
        self._initialized = False

    def __call__(
        self,
        symbol: str,
        bars: list[BarData],
        position: Position | None,
        equity: float,
    ) -> Signal | None:
        """Evaluate strategy and return signal if any.

        Args:
            symbol: The trading symbol
            bars: List of BarData from the bar stream
            position: Current position (if any)
            equity: Current equity/buying power

        Returns:
            A Signal if entry/exit conditions are met, None otherwise
        """
        if not bars:
            return None

        # Convert BarData to compiler's Bar format
        # Only process the latest bar (runner handles history accumulation)
        latest_bar = bars[-1]
        compiler_bar = Bar(
            timestamp=latest_bar.timestamp,
            open=latest_bar.open,
            high=latest_bar.high,
            low=latest_bar.low,
            close=latest_bar.close,
            volume=latest_bar.volume,
        )

        # Sync position state with compiled strategy
        if position:
            from llamatrade_compiler.state import Position as CompilerPosition

            self.compiled.set_position(
                CompilerPosition(
                    symbol=position.symbol,
                    side=position.side,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    entry_time=position.entry_date,
                )
            )
        else:
            self.compiled.close_position()

        # If this is the first call, we need to warm up with historical bars
        if not self._initialized:
            # Add all historical bars to compiled strategy
            for bar_data in bars[:-1]:
                hist_bar = Bar(
                    timestamp=bar_data.timestamp,
                    open=bar_data.open,
                    high=bar_data.high,
                    low=bar_data.low,
                    close=bar_data.close,
                    volume=bar_data.volume,
                )
                self.compiled.add_bar(hist_bar)
            self._initialized = True

        # Evaluate the strategy with the new bar
        signals = self.compiled.evaluate(compiler_bar)

        if not signals:
            return None

        # Convert first signal to runner's Signal format
        sig = signals[0]
        signal_type = sig.type.value  # "buy", "sell", "close_long", "close_short"

        # Calculate quantity based on equity and position sizing
        quantity_percent = sig.quantity_percent
        current_price = latest_bar.close

        if signal_type in ("buy", "sell"):
            # Entry signal - calculate quantity
            position_value = equity * (quantity_percent / 100)
            quantity = position_value / current_price if current_price > 0 else 0
        else:
            # Exit signal - use position quantity
            quantity = position.quantity if position else 0

        return Signal(
            type=signal_type,
            symbol=symbol,
            quantity=quantity,
            price=current_price,
        )

    def reset(self) -> None:
        """Reset the strategy state."""
        self.compiled.reset()
        self._initialized = False

    @property
    def name(self) -> str:
        """Get strategy name."""
        return str(self.compiled.name)

    @property
    def min_bars(self) -> int:
        """Get minimum bars required for evaluation."""
        return int(self.compiled.min_bars)


def load_strategy_adapter(strategy_sexpr: str) -> StrategyAdapter:
    """Factory function to create a strategy adapter.

    Args:
        strategy_sexpr: Strategy definition in S-expression format

    Returns:
        A StrategyAdapter ready for use with StrategyRunner
    """
    return StrategyAdapter(strategy_sexpr)


async def fetch_strategy_and_create_adapter(
    strategy_id: str,
    version: int | None = None,
) -> StrategyAdapter | None:
    """Fetch strategy from database and create an adapter.

    This is a helper function that would be used by the session service
    to load a strategy for execution.

    Args:
        strategy_id: UUID of the strategy
        version: Strategy version (None for current version)

    Returns:
        StrategyAdapter or None if strategy not found
    """
    # Note: This would need a database session to actually work.
    # This is a placeholder showing the intended interface.
    # In production, this would:
    # 1. Fetch StrategyVersion from database
    # 2. Get the S-expression from strategy_version.definition_sexpr
    # 3. Create and return the adapter
    logger.warning("fetch_strategy_and_create_adapter requires database session - placeholder only")
    return None
