"""Evaluation state for strategy condition evaluation."""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from llamatrade_compiler.types import Bar


@dataclass(frozen=True)
class Position:
    """Represents a trading position."""

    symbol: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    entry_time: datetime


@dataclass
class EvaluationState:
    """
    Runtime state for evaluating strategy conditions.

    Contains all the data needed to evaluate entry/exit conditions:
    - Current and previous bar data
    - Pre-computed indicator values
    - Current position (if any)
    - Historical bar data for lookbacks
    """

    current_bar: Bar
    prev_bar: Bar
    indicators: dict[str, float | np.ndarray]
    position: Position | None = None
    bar_history: list[Bar] = field(default_factory=list)

    def get_value(self, name: str) -> float:
        """
        Get a named value (price field or indicator).

        Args:
            name: The value name (close, open, high, low, volume, or indicator key)

        Returns:
            The current value as a float
        """
        # Price fields
        if name == "close":
            return self.current_bar.close
        if name == "open":
            return self.current_bar.open
        if name == "high":
            return self.current_bar.high
        if name == "low":
            return self.current_bar.low
        if name == "volume":
            return float(self.current_bar.volume)
        if name == "timestamp":
            return float(self.current_bar.timestamp.timestamp())

        # Check indicators
        if name in self.indicators:
            value = self.indicators[name]
            if isinstance(value, np.ndarray):
                return float(value[-1])
            return float(value)

        raise KeyError(f"Unknown value: {name}")

    def get_prev_value(self, name: str) -> float:
        """
        Get the previous bar's value for a named field.

        Args:
            name: The value name

        Returns:
            The previous value as a float
        """
        # Price fields
        if name == "close":
            return self.prev_bar.close
        if name == "open":
            return self.prev_bar.open
        if name == "high":
            return self.prev_bar.high
        if name == "low":
            return self.prev_bar.low
        if name == "volume":
            return float(self.prev_bar.volume)

        # Check indicators (get second-to-last value)
        if name in self.indicators:
            value = self.indicators[name]
            if isinstance(value, np.ndarray) and len(value) > 1:
                return float(value[-2])
            return float(value) if not isinstance(value, np.ndarray) else float(value[-1])

        raise KeyError(f"Unknown value: {name}")

    def get_value_at_offset(self, name: str, offset: int) -> float:
        """
        Get a value at a historical offset.

        Args:
            name: The value name
            offset: Number of bars back (1 = previous bar, 2 = two bars ago)

        Returns:
            The value at the offset
        """
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        if offset == 0:
            return self.get_value(name)

        # For price fields, use bar history
        if name in ("close", "open", "high", "low", "volume"):
            if offset >= len(self.bar_history):
                raise IndexError(f"Not enough history for offset {offset}")
            bar = self.bar_history[-(offset + 1)]
            if name == "volume":
                return float(bar.volume)
            return float(getattr(bar, name))

        # For indicators, get from array
        if name in self.indicators:
            value = self.indicators[name]
            if isinstance(value, np.ndarray):
                if offset >= len(value):
                    raise IndexError(f"Not enough indicator history for offset {offset}")
                return float(value[-(offset + 1)])
            return float(value)

        raise KeyError(f"Unknown value: {name}")

    def get_indicator(self, key: str) -> float:
        """
        Get a pre-computed indicator value by its cache key.

        Args:
            key: The indicator cache key (e.g., "sma_close_20")

        Returns:
            The current indicator value
        """
        if key not in self.indicators:
            raise KeyError(f"Indicator not found: {key}")

        value = self.indicators[key]
        if isinstance(value, np.ndarray):
            return float(value[-1])
        return float(value)

    def get_indicator_array(self, key: str) -> np.ndarray:
        """
        Get the full indicator array for a key.

        Args:
            key: The indicator cache key

        Returns:
            The indicator array
        """
        if key not in self.indicators:
            raise KeyError(f"Indicator not found: {key}")

        value = self.indicators[key]
        if isinstance(value, np.ndarray):
            return value
        return np.array([value])

    def has_position(self) -> bool:
        """Check if there is a current position."""
        return self.position is not None

    def position_side(self) -> str | None:
        """Get the current position side or None."""
        return self.position.side if self.position else None

    def position_pnl_pct(self) -> float | None:
        """
        Calculate current position P&L percentage.

        Returns:
            P&L as a percentage, or None if no position
        """
        if self.position is None:
            return None

        current_price = self.current_bar.close
        entry_price = self.position.entry_price

        if self.position.side == "long":
            return ((current_price - entry_price) / entry_price) * 100
        else:  # short
            return ((entry_price - current_price) / entry_price) * 100
