"""Compiled strategy for efficient execution.

CompiledStrategy wraps a Strategy AST and provides efficient evaluation
of entry/exit conditions against market data.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from llamatrade_compiler import Bar, Signal, SignalType
from llamatrade_dsl.ast import Strategy

from src.compiler.evaluator import evaluate_entry, evaluate_exit
from src.compiler.extractor import IndicatorSpec, extract_indicators, get_max_lookback
from src.compiler.pipeline import PriceData, compute_all_indicators
from src.compiler.state import EvaluationState, Position


@dataclass
class CompiledStrategy:
    """A compiled strategy ready for execution.

    Takes a Strategy AST and prepares it for efficient bar-by-bar evaluation.

    Attributes:
        strategy: The original strategy AST
        indicators: Extracted indicator specifications
        min_bars: Minimum historical bars needed before evaluation
        _bar_history: Internal bar history for lookbacks
        _position: Current position (if any)
        _indicator_cache: Cached indicator values
    """

    strategy: Strategy
    indicators: list[IndicatorSpec] = field(default_factory=list)
    min_bars: int = 0
    _bar_history: list[Bar] = field(default_factory=list, repr=False)
    _position: Position | None = field(default=None, repr=False)
    _indicator_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    @classmethod
    def compile(cls, strategy: Strategy) -> "CompiledStrategy":
        """Compile a strategy AST into an executable form.

        Args:
            strategy: The parsed strategy AST

        Returns:
            A CompiledStrategy ready for evaluation
        """
        indicators = extract_indicators(strategy)
        min_bars = get_max_lookback(indicators)

        # Need at least 2 bars for crossover detection
        min_bars = max(min_bars, 2)

        return cls(
            strategy=strategy,
            indicators=indicators,
            min_bars=min_bars,
        )

    def reset(self) -> None:
        """Reset strategy state for a new evaluation run."""
        self._bar_history = []
        self._position = None
        self._indicator_cache = {}

    def add_bar(self, bar: Bar) -> None:
        """Add a bar to history.

        Args:
            bar: The OHLCV bar to add
        """
        self._bar_history.append(bar)

    def has_enough_history(self) -> bool:
        """Check if we have enough bars for evaluation."""
        return len(self._bar_history) >= self.min_bars

    def set_position(self, position: Position | None) -> None:
        """Set the current position.

        Args:
            position: The position or None if flat
        """
        self._position = position

    def open_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        entry_time: datetime,
    ) -> None:
        """Open a new position.

        Args:
            symbol: The symbol
            side: "long" or "short"
            quantity: Position size
            entry_price: Entry price
            entry_time: Entry timestamp
        """
        self._position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_time,
        )

    def close_position(self) -> None:
        """Close the current position."""
        self._position = None

    def _compute_indicators(self) -> dict[str, np.ndarray]:
        """Compute all indicators from current bar history."""
        if not self._bar_history:
            return {}

        # Build price data from history
        prices = PriceData(
            open=np.array([b.open for b in self._bar_history]),
            high=np.array([b.high for b in self._bar_history]),
            low=np.array([b.low for b in self._bar_history]),
            close=np.array([b.close for b in self._bar_history]),
            volume=np.array([b.volume for b in self._bar_history]),
        )

        return compute_all_indicators(self.indicators, prices)

    def _build_state(self) -> EvaluationState:
        """Build evaluation state from current history."""
        if len(self._bar_history) < 2:
            raise ValueError("Need at least 2 bars for evaluation")

        indicators = self._compute_indicators()

        # Convert float values to arrays for consistency
        indicator_dict: dict[str, float | np.ndarray] = {}
        for key, value in indicators.items():
            indicator_dict[key] = value

        return EvaluationState(
            current_bar=self._bar_history[-1],
            prev_bar=self._bar_history[-2],
            indicators=indicator_dict,
            position=self._position,
            bar_history=self._bar_history,
        )

    def evaluate(self, bar: Bar) -> list[Signal]:
        """Evaluate the strategy with a new bar.

        Args:
            bar: The new OHLCV bar

        Returns:
            List of signals (may be empty)
        """
        # Add bar to history
        self.add_bar(bar)

        # Check if we have enough history
        if not self.has_enough_history():
            return []

        # Build evaluation state
        state = self._build_state()

        signals: list[Signal] = []

        # Check entry condition (only if not in position)
        if not state.has_position():
            if evaluate_entry(state, self.strategy.entry):
                signal = self._create_entry_signal(bar)
                signals.append(signal)

        # Check exit condition (only if in position)
        else:
            if evaluate_exit(state, self.strategy.exit):
                signal = self._create_exit_signal(bar)
                signals.append(signal)

            # Also check risk-based exits
            risk_signal = self._check_risk_exits(state, bar)
            if risk_signal:
                signals.append(risk_signal)

        return signals

    def _create_entry_signal(self, bar: Bar) -> Signal:
        """Create an entry signal based on strategy config."""
        # Determine signal type from strategy type
        signal_type = SignalType.BUY

        if self.strategy.strategy_type == "mean_reversion":
            # Mean reversion might short at tops
            signal_type = SignalType.BUY
        else:
            signal_type = SignalType.BUY

        # Calculate position sizing
        sizing = self.strategy.sizing
        quantity_pct = sizing.get("value", 10)

        # Calculate stop loss and take profit
        stop_loss = None
        take_profit = None

        risk = self.strategy.risk
        if risk.get("stop_loss_pct"):
            stop_loss = bar.close * (1 - risk["stop_loss_pct"] / 100)
        if risk.get("take_profit_pct"):
            take_profit = bar.close * (1 + risk["take_profit_pct"] / 100)

        return Signal(
            type=signal_type,
            symbol=self.strategy.symbols[0] if self.strategy.symbols else "",
            price=bar.close,
            timestamp=bar.timestamp,
            quantity_percent=quantity_pct,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                "strategy_name": self.strategy.name,
                "strategy_type": self.strategy.strategy_type,
            },
        )

    def _create_exit_signal(self, bar: Bar) -> Signal:
        """Create an exit signal."""
        side = self._position.side if self._position else "long"

        signal_type = SignalType.CLOSE_LONG if side == "long" else SignalType.CLOSE_SHORT

        return Signal(
            type=signal_type,
            symbol=self.strategy.symbols[0] if self.strategy.symbols else "",
            price=bar.close,
            timestamp=bar.timestamp,
            quantity_percent=100.0,  # Close full position
            metadata={
                "strategy_name": self.strategy.name,
                "exit_reason": "condition",
            },
        )

    def _check_risk_exits(self, state: EvaluationState, bar: Bar) -> Signal | None:
        """Check for risk-based exit conditions."""
        if not self._position:
            return None

        risk = self.strategy.risk
        pnl_pct = state.position_pnl_pct()

        if pnl_pct is None:
            return None

        # Stop loss check
        stop_loss_pct = risk.get("stop_loss_pct")
        if stop_loss_pct and pnl_pct <= -stop_loss_pct:
            return Signal(
                type=SignalType.CLOSE_LONG
                if self._position.side == "long"
                else SignalType.CLOSE_SHORT,
                symbol=self._position.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                quantity_percent=100.0,
                metadata={
                    "strategy_name": self.strategy.name,
                    "exit_reason": "stop_loss",
                    "pnl_pct": pnl_pct,
                },
            )

        # Take profit check
        take_profit_pct = risk.get("take_profit_pct")
        if take_profit_pct and pnl_pct >= take_profit_pct:
            return Signal(
                type=SignalType.CLOSE_LONG
                if self._position.side == "long"
                else SignalType.CLOSE_SHORT,
                symbol=self._position.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                quantity_percent=100.0,
                metadata={
                    "strategy_name": self.strategy.name,
                    "exit_reason": "take_profit",
                    "pnl_pct": pnl_pct,
                },
            )

        return None

    def backtest_bars(self, bars: list[Bar]) -> list[Signal]:
        """Run backtest over a series of bars.

        Args:
            bars: List of OHLCV bars in chronological order

        Returns:
            All signals generated during the backtest
        """
        self.reset()
        all_signals: list[Signal] = []

        for bar in bars:
            signals = self.evaluate(bar)

            # Update position based on signals
            for signal in signals:
                if signal.type == SignalType.BUY:
                    self.open_position(
                        symbol=signal.symbol,
                        side="long",
                        quantity=1.0,  # Simplified for backtest
                        entry_price=signal.price,
                        entry_time=signal.timestamp,
                    )
                elif signal.type in (SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT):
                    self.close_position()

            all_signals.extend(signals)

        return all_signals

    @property
    def name(self) -> str:
        """Strategy name."""
        return str(self.strategy.name)

    @property
    def symbols(self) -> list[str]:
        """Strategy symbols."""
        return list(self.strategy.symbols)

    @property
    def timeframe(self) -> str:
        """Strategy timeframe."""
        return str(self.strategy.timeframe)

    def __repr__(self) -> str:
        return (
            f"CompiledStrategy(name={self.name!r}, "
            f"symbols={self.symbols}, "
            f"indicators={len(self.indicators)}, "
            f"min_bars={self.min_bars})"
        )


def compile_strategy(strategy: Strategy) -> CompiledStrategy:
    """Compile a strategy AST into an executable form.

    This is the main entry point for strategy compilation.

    Args:
        strategy: The parsed strategy AST

    Returns:
        A CompiledStrategy ready for evaluation
    """
    return CompiledStrategy.compile(strategy)
