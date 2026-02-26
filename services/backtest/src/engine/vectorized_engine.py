"""Vectorized backtest engine for high-performance backtesting.

This engine uses NumPy vectorization to achieve significantly faster
execution compared to the row-by-row engine. It's designed for:
- 1 symbol, 1 year: < 100ms
- 10 symbols, 5 years: < 2 seconds
- 100 symbols, 10 years: < 15 seconds
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

import numpy as np

from src.engine.backtester import BacktestConfig, BacktestResult, Trade


class VectorizedBarData(TypedDict):
    """Vectorized bar data for multiple symbols."""

    timestamps: np.ndarray  # Shape: (num_bars,) datetime64
    opens: np.ndarray  # Shape: (num_symbols, num_bars)
    highs: np.ndarray  # Shape: (num_symbols, num_bars)
    lows: np.ndarray  # Shape: (num_symbols, num_bars)
    closes: np.ndarray  # Shape: (num_symbols, num_bars)
    volumes: np.ndarray  # Shape: (num_symbols, num_bars)


SignalFn = Callable[["VectorizedBarData", dict[str, np.ndarray]], np.ndarray]


@dataclass
class CompiledStrategy:
    """Pre-compiled strategy for vectorized execution."""

    # Entry condition as a callable that returns boolean array
    entry_fn: SignalFn
    # Exit condition as a callable that returns boolean array
    exit_fn: SignalFn
    # Pre-computed indicators as dict of arrays
    indicators: dict[str, np.ndarray] = field(default_factory=dict)
    # Position sizing (fraction of equity)
    position_size_pct: float = 10.0
    # Risk parameters
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None


class VectorizedBacktestEngine:
    """High-performance vectorized backtest engine."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(
        self,
        bars: VectorizedBarData,
        strategy: CompiledStrategy,
        symbols: list[str],
    ) -> BacktestResult:
        """Run a vectorized backtest.

        Args:
            bars: Vectorized bar data (OHLCV arrays)
            strategy: Pre-compiled strategy with indicator arrays
            symbols: List of symbol names

        Returns:
            BacktestResult with metrics and trades
        """
        num_symbols = len(symbols)
        num_bars = len(bars["timestamps"])
        timestamps = bars["timestamps"]
        closes = bars["closes"]

        # Initialize tracking arrays
        positions = np.zeros((num_symbols, num_bars), dtype=np.float64)  # Quantity held
        entry_prices = np.zeros((num_symbols, num_bars), dtype=np.float64)
        equity = np.zeros(num_bars, dtype=np.float64)

        # Get entry/exit signals as boolean arrays (num_symbols, num_bars)
        entry_signals = strategy.entry_fn(bars, strategy.indicators)
        exit_signals = strategy.exit_fn(bars, strategy.indicators)

        # Apply risk exits if configured
        if strategy.stop_loss_pct or strategy.take_profit_pct:
            exit_signals = self._apply_risk_exits(
                exit_signals,
                closes,
                entry_prices,
                positions,
                strategy.stop_loss_pct,
                strategy.take_profit_pct,
            )

        # Track trades
        trades: list[Trade] = []

        # Simulate bar by bar (vectorized within each bar across symbols)
        current_positions = np.zeros(num_symbols)
        current_entry_prices = np.zeros(num_symbols)
        current_entry_bars = np.zeros(num_symbols, dtype=np.int64)
        current_cash = self.config.initial_capital
        days_with_position = 0

        for bar_idx in range(num_bars):
            bar_close = closes[:, bar_idx]

            # Process exits first
            exit_mask = exit_signals[:, bar_idx] & (current_positions > 0)
            if np.any(exit_mask):
                for sym_idx in np.where(exit_mask)[0]:
                    # Record trade
                    trade = Trade(
                        entry_date=self._idx_to_datetime(
                            timestamps, int(current_entry_bars[sym_idx])
                        ),
                        exit_date=self._idx_to_datetime(timestamps, bar_idx),
                        symbol=symbols[sym_idx],
                        side="long",
                        entry_price=current_entry_prices[sym_idx],
                        exit_price=bar_close[sym_idx],
                        quantity=current_positions[sym_idx],
                        commission=self.config.commission_rate * 2,
                    )
                    trades.append(trade)

                    # Update cash
                    current_cash += (
                        bar_close[sym_idx] * current_positions[sym_idx]
                        - self.config.commission_rate
                    )
                    current_positions[sym_idx] = 0
                    current_entry_prices[sym_idx] = 0

            # Process entries (only if not already in position)
            entry_mask = entry_signals[:, bar_idx] & (current_positions == 0)
            if np.any(entry_mask):
                for sym_idx in np.where(entry_mask)[0]:
                    # Calculate position size
                    equity_now = current_cash + np.sum(current_positions * bar_close)
                    position_value = equity_now * strategy.position_size_pct / 100
                    quantity = position_value / bar_close[sym_idx]

                    if position_value + self.config.commission_rate <= current_cash:
                        current_cash -= position_value + self.config.commission_rate
                        current_positions[sym_idx] = quantity
                        current_entry_prices[sym_idx] = bar_close[sym_idx]
                        current_entry_bars[sym_idx] = bar_idx

            # Track days with position
            if np.any(current_positions > 0):
                days_with_position += 1

            # Calculate equity
            position_value = np.sum(current_positions * bar_close)
            equity[bar_idx] = current_cash + position_value

        # Close remaining positions at end
        final_close = closes[:, -1]
        for sym_idx in range(num_symbols):
            if current_positions[sym_idx] > 0:
                trade = Trade(
                    entry_date=self._idx_to_datetime(timestamps, int(current_entry_bars[sym_idx])),
                    exit_date=self._idx_to_datetime(timestamps, num_bars - 1),
                    symbol=symbols[sym_idx],
                    side="long",
                    entry_price=current_entry_prices[sym_idx],
                    exit_price=final_close[sym_idx],
                    quantity=current_positions[sym_idx],
                    commission=self.config.commission_rate * 2,
                )
                trades.append(trade)

        # Build equity curve
        equity_curve = [
            (self._idx_to_datetime(timestamps, i), float(equity[i])) for i in range(num_bars)
        ]

        # Calculate metrics
        return self._calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            equity=equity,
            initial_capital=self.config.initial_capital,
            days_with_position=days_with_position,
            total_days=num_bars,
            risk_free_rate=self.config.risk_free_rate,
        )

    def _apply_risk_exits(
        self,
        exit_signals: np.ndarray,
        closes: np.ndarray,
        entry_prices: np.ndarray,
        positions: np.ndarray,
        stop_loss_pct: float | None,
        take_profit_pct: float | None,
    ) -> np.ndarray:
        """Apply stop-loss and take-profit exits vectorized."""
        result = exit_signals.copy()

        if stop_loss_pct is not None:
            # Calculate PnL percentage
            with np.errstate(divide="ignore", invalid="ignore"):
                pnl_pct = np.where(
                    entry_prices > 0,
                    (closes - entry_prices) / entry_prices * 100,
                    0,
                )
            result |= (pnl_pct <= -stop_loss_pct) & (positions > 0)

        if take_profit_pct is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                pnl_pct = np.where(
                    entry_prices > 0,
                    (closes - entry_prices) / entry_prices * 100,
                    0,
                )
            result |= (pnl_pct >= take_profit_pct) & (positions > 0)

        return result

    def _idx_to_datetime(self, timestamps: np.ndarray, idx: int) -> datetime:
        """Convert numpy datetime64 to Python datetime."""
        ts = timestamps[idx]
        if isinstance(ts, np.datetime64):
            # Convert numpy datetime64 to Python datetime
            unix_epoch = np.datetime64(0, "s")
            one_second = np.timedelta64(1, "s")
            seconds_since_epoch = (ts - unix_epoch) / one_second
            return datetime.fromtimestamp(float(seconds_since_epoch))
        if isinstance(ts, datetime):
            return ts
        return datetime.fromtimestamp(float(ts))

    def _calculate_metrics(
        self,
        trades: list[Trade],
        equity_curve: list[tuple[datetime, float]],
        equity: np.ndarray,
        initial_capital: float,
        days_with_position: int,
        total_days: int,
        risk_free_rate: float,
    ) -> BacktestResult:
        """Calculate backtest metrics using vectorized operations."""
        if len(equity) == 0:
            return BacktestResult()

        final_equity = float(equity[-1])
        total_return = (final_equity - initial_capital) / initial_capital

        # Annual return
        num_days = len(equity)
        annual_return = ((1 + total_return) ** (252 / max(num_days, 1))) - 1 if num_days > 0 else 0

        # Daily returns
        daily_returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
        daily_returns_list = daily_returns.tolist()

        # Monthly returns
        monthly_returns = self._compute_monthly_returns(equity_curve, initial_capital)

        # Sharpe ratio
        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            excess_returns = daily_returns - risk_free_rate / 252
            sharpe_ratio = float(np.sqrt(252) * np.mean(excess_returns) / np.std(daily_returns))
        else:
            sharpe_ratio = 0.0

        # Sortino ratio
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0 and np.std(negative_returns) > 0:
            sortino_ratio = float(np.sqrt(252) * np.mean(daily_returns) / np.std(negative_returns))
        else:
            sortino_ratio = 0.0

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_drawdown = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0

        # Max drawdown duration
        max_dd_duration = 0
        current_duration = 0
        for dd in drawdown:
            if dd > 0:
                current_duration += 1
                max_dd_duration = max(max_dd_duration, current_duration)
            else:
                current_duration = 0

        # Exposure time
        exposure_time = (days_with_position / total_days * 100) if total_days > 0 else 0

        # Trade statistics
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) if trades else 0

        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            final_equity=final_equity,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            win_rate=win_rate,
            profit_factor=profit_factor,
            daily_returns=daily_returns_list,
            monthly_returns=monthly_returns,
            exposure_time=exposure_time,
        )

    def _compute_monthly_returns(
        self,
        equity_curve: list[tuple[datetime, float]],
        initial_capital: float,
    ) -> dict[str, float]:
        """Compute monthly returns from equity curve."""
        if not equity_curve:
            return {}

        monthly_returns: dict[str, float] = {}
        month_equities: dict[str, list[tuple[datetime, float]]] = {}

        for dt, eq in equity_curve:
            month_key = dt.strftime("%Y-%m")
            if month_key not in month_equities:
                month_equities[month_key] = []
            month_equities[month_key].append((dt, eq))

        sorted_months = sorted(month_equities.keys())
        prev_month_end_equity = initial_capital

        for month in sorted_months:
            month_data = month_equities[month]
            month_end_equity = month_data[-1][1]
            month_return = (month_end_equity - prev_month_end_equity) / prev_month_end_equity
            monthly_returns[month] = month_return
            prev_month_end_equity = month_end_equity

        return monthly_returns


def prepare_vectorized_bars(
    bars: dict[str, list[dict]],
    symbols: list[str],
) -> tuple[VectorizedBarData, np.ndarray]:
    """Convert row-based bars to vectorized format.

    Args:
        bars: Dictionary mapping symbol to list of bar dicts
        symbols: List of symbol names in desired order

    Returns:
        Tuple of (VectorizedBarData, timestamps array)
    """
    # Get all unique timestamps
    all_timestamps = set()
    for symbol_bars in bars.values():
        for bar in symbol_bars:
            all_timestamps.add(bar["timestamp"])

    timestamps = np.array(sorted(all_timestamps))
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
