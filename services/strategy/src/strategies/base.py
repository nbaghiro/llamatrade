"""Base strategy class for all trading strategies."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict

import numpy as np

# Import core types from the shared compiler library
from llamatrade_compiler import Bar, Signal


class StrategyConfigDict(TypedDict, total=False):
    """Strategy configuration dictionary."""

    symbols: list[str]
    timeframe: str
    risk: dict[str, float]


class BarDict(TypedDict):
    """Bar data as dictionary."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BaseStrategy(ABC):
    """Base class for all trading strategies.

    All strategies must implement:
    - name: Strategy name
    - description: Strategy description
    - on_bar: Process new bar data and return signals

    Optional overrides:
    - on_init: Initialize strategy state
    - on_order_filled: Handle order fill events
    - validate_config: Validate configuration
    """

    name: str = "Base Strategy"
    description: str = "Base strategy class"

    def __init__(self, config: StrategyConfigDict | None = None):
        """Initialize the strategy.

        Args:
            config: Strategy configuration dictionary
        """
        self.config: StrategyConfigDict = config or {}
        self.symbols: list[str] = self.config.get("symbols", [])
        self.timeframe: str = self.config.get("timeframe", "1D")
        self.risk_config: dict[str, float] = self.config.get("risk", {})

        # State
        self.indicators: dict[str, np.ndarray] = {}
        self.positions: dict[str, float] = {}  # symbol -> quantity
        self.bars: dict[str, list[Bar]] = {}  # symbol -> list of bars

        # Call initialization hook
        self.on_init()

    def on_init(self) -> None:
        """Initialize strategy state. Override in subclass if needed."""
        pass

    @abstractmethod
    def on_bar(self, symbol: str, bar: Bar) -> list[Signal]:
        """Process a new bar and generate signals.

        Args:
            symbol: The symbol for this bar
            bar: The OHLCV bar data

        Returns:
            List of signals to execute (may be empty)
        """
        pass

    def on_order_filled(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> None:
        """Handle order fill event. Override in subclass if needed.

        Args:
            symbol: The filled order's symbol
            side: 'buy' or 'sell'
            quantity: Filled quantity
            price: Fill price
        """
        # Update position tracking
        current = self.positions.get(symbol, 0)
        if side == "buy":
            self.positions[symbol] = current + quantity
        else:
            self.positions[symbol] = current - quantity

    def validate_config(self) -> list[str]:
        """Validate strategy configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.symbols:
            errors.append("At least one symbol is required")

        valid_timeframes = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
        if self.timeframe not in valid_timeframes:
            errors.append(f"Invalid timeframe: {self.timeframe}")

        return errors

    def add_bar(self, symbol: str, bar: Bar) -> None:
        """Add a bar to the strategy's history.

        Args:
            symbol: Symbol for the bar
            bar: Bar data to add
        """
        if symbol not in self.bars:
            self.bars[symbol] = []
        self.bars[symbol].append(bar)

    def get_prices(self, symbol: str, field: str = "close") -> np.ndarray:
        """Get price array for a symbol.

        Args:
            symbol: Symbol to get prices for
            field: Price field ('open', 'high', 'low', 'close')

        Returns:
            NumPy array of prices
        """
        if symbol not in self.bars:
            return np.array([])

        return np.array([getattr(bar, field) for bar in self.bars[symbol]])

    def get_volumes(self, symbol: str) -> np.ndarray:
        """Get volume array for a symbol.

        Args:
            symbol: Symbol to get volumes for

        Returns:
            NumPy array of volumes
        """
        if symbol not in self.bars:
            return np.array([])

        return np.array([bar.volume for bar in self.bars[symbol]])

    def calculate_stop_loss(self, price: float) -> float | None:
        """Calculate stop loss price based on risk config.

        Args:
            price: Entry price

        Returns:
            Stop loss price or None if not configured
        """
        stop_percent: float | None = self.risk_config.get("stop_loss_percent")
        if stop_percent is not None:
            return price * (1 - stop_percent / 100)
        return None

    def calculate_take_profit(self, price: float) -> float | None:
        """Calculate take profit price based on risk config.

        Args:
            price: Entry price

        Returns:
            Take profit price or None if not configured
        """
        tp_percent: float | None = self.risk_config.get("take_profit_percent")
        if tp_percent is not None:
            return price * (1 + tp_percent / 100)
        return None

    def get_position(self, symbol: str) -> float:
        """Get current position for a symbol.

        Args:
            symbol: Symbol to check

        Returns:
            Position quantity (0 if no position)
        """
        return self.positions.get(symbol, 0)

    def has_position(self, symbol: str) -> bool:
        """Check if strategy has a position in a symbol.

        Args:
            symbol: Symbol to check

        Returns:
            True if position exists
        """
        return self.get_position(symbol) != 0
