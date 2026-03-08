"""Vectorized strategy types and utilities for high-performance backtesting.

This module provides types and utilities for vectorized allocation strategy execution,
designed for efficient backtesting across multiple symbols and time periods.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray


class BarDict(TypedDict):
    """Type for bar data dictionary."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class VectorizedBarData(TypedDict):
    """Vectorized bar data for multiple symbols.

    All arrays (except timestamps) have shape (num_symbols, num_bars).
    Timestamps has shape (num_bars,) since it's shared across symbols.
    """

    timestamps: NDArray[np.datetime64]  # Shape: (num_bars,) datetime64
    opens: NDArray[np.float64]  # Shape: (num_symbols, num_bars)
    highs: NDArray[np.float64]  # Shape: (num_symbols, num_bars)
    lows: NDArray[np.float64]  # Shape: (num_symbols, num_bars)
    closes: NDArray[np.float64]  # Shape: (num_symbols, num_bars)
    volumes: NDArray[np.float64]  # Shape: (num_symbols, num_bars)


# Type alias for vectorized allocation functions
# Takes (bars, indicators) and returns dict mapping symbol -> weight array
AllocationFn = Callable[
    [VectorizedBarData, dict[str, NDArray[np.float64]]],
    dict[str, NDArray[np.float64]],
]

# Type alias for entry/exit signal functions
# Takes (bars, indicators) and returns boolean array of shape (num_symbols, num_bars)
SignalFn = Callable[
    [VectorizedBarData, dict[str, NDArray[np.float64]]],
    NDArray[np.bool_],
]


def _empty_indicator_dict() -> dict[str, NDArray[np.float64]]:
    """Factory for empty indicator dict."""
    return {}


@dataclass
class VectorizedCompiledStrategy:
    """Pre-compiled allocation strategy for vectorized execution.

    Unlike the bar-by-bar CompiledStrategy, this version stores functions
    that operate on entire arrays of data for high-performance backtesting.

    Attributes:
        allocation_fn: Callable that returns weight arrays for each symbol
        indicators: Pre-computed indicator arrays (cached during execution)
        strategy_name: Name of the strategy
        rebalance_frequency: How often to rebalance (daily, weekly, monthly, etc.)
        benchmark: Benchmark symbol for comparison
        entry_fn: Optional signal function for entries (for signal-based strategies)
        exit_fn: Optional signal function for exits (for signal-based strategies)
        stop_loss_pct: Stop loss percentage (e.g., 5.0 for 5%)
        take_profit_pct: Take profit percentage (e.g., 10.0 for 10%)
        position_size_pct: Position size as percentage of equity (e.g., 10.0 for 10%)
    """

    allocation_fn: AllocationFn
    indicators: dict[str, NDArray[np.float64]] = field(default_factory=_empty_indicator_dict)
    strategy_name: str = ""
    rebalance_frequency: str | None = None
    benchmark: str | None = None
    # Signal-based strategy functions
    entry_fn: SignalFn | None = None
    exit_fn: SignalFn | None = None
    # Risk management
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    position_size_pct: float = 10.0  # Default 10% of equity per position

    def compute_weights(
        self,
        bars: VectorizedBarData,
    ) -> dict[str, NDArray[np.float64]]:
        """Compute allocation weights for all bars.

        Args:
            bars: Vectorized bar data for all symbols

        Returns:
            Dict mapping symbol to weight array of shape (num_bars,)
        """
        return self.allocation_fn(bars, self.indicators)


def prepare_vectorized_bars(
    bars: dict[str, list[BarDict]],
    symbols: list[str],
) -> tuple[VectorizedBarData, NDArray[np.datetime64]]:
    """Convert row-based bars to vectorized format.

    Args:
        bars: Dictionary mapping symbol to list of bar dicts.
              Each bar dict must have: timestamp, open, high, low, close, volume
        symbols: List of symbol names in desired order

    Returns:
        Tuple of (VectorizedBarData, timestamps array)
    """
    # Get all unique timestamps
    all_timestamps: set[datetime] = set()
    for symbol_bars in bars.values():
        for bar in symbol_bars:
            all_timestamps.add(bar["timestamp"])

    timestamps: NDArray[np.datetime64] = np.array(sorted(all_timestamps))
    num_bars = len(timestamps)
    num_symbols = len(symbols)

    # Create timestamp index for fast lookup
    ts_to_idx = {ts: i for i, ts in enumerate(timestamps)}

    # Pre-allocate arrays
    opens = np.full((num_symbols, num_bars), np.nan, dtype=np.float64)
    highs = np.full((num_symbols, num_bars), np.nan, dtype=np.float64)
    lows = np.full((num_symbols, num_bars), np.nan, dtype=np.float64)
    closes = np.full((num_symbols, num_bars), np.nan, dtype=np.float64)
    volumes = np.zeros((num_symbols, num_bars), dtype=np.float64)

    # Fill arrays
    for sym_idx, symbol in enumerate(symbols):
        symbol_bars = bars.get(symbol, [])
        for bar in symbol_bars:
            bar_idx = ts_to_idx.get(bar["timestamp"])
            if bar_idx is not None:
                opens[sym_idx, bar_idx] = bar["open"]
                highs[sym_idx, bar_idx] = bar["high"]
                lows[sym_idx, bar_idx] = bar["low"]
                closes[sym_idx, bar_idx] = bar["close"]
                volumes[sym_idx, bar_idx] = bar["volume"]

    # Forward-fill NaN values for closes (for missing days)
    for sym_idx in range(num_symbols):
        mask = np.isnan(closes[sym_idx])
        if np.any(mask):
            idx = np.where(~mask, np.arange(num_bars), 0)
            np.maximum.accumulate(idx, out=idx)
            closes[sym_idx, mask] = closes[sym_idx, idx[mask]]

    return {
        "timestamps": timestamps,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "volumes": volumes,
    }, timestamps


def should_use_vectorized_engine(
    num_symbols: int,
    num_bars: int,
    threshold: int = 10000,
) -> bool:
    """Determine whether to use the vectorized engine based on data size.

    The vectorized engine has some overhead for small datasets but provides
    significant speedups for larger ones. This function provides a heuristic
    for when to use it.

    Args:
        num_symbols: Number of symbols
        num_bars: Number of bars per symbol
        threshold: Minimum total bars for vectorized engine (default 10000)

    Returns:
        True if vectorized engine should be used
    """
    total_bars = num_symbols * num_bars
    return total_bars > threshold
