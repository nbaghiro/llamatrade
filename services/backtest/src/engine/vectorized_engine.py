"""Vectorized backtest engine for high-performance backtesting.

This engine uses NumPy vectorization to achieve significantly faster
execution compared to the bar-by-bar engine. It's designed for:
- 1 symbol, 1 year: < 100ms
- 10 symbols, 5 years: < 2 seconds
- 100 symbols, 10 years: < 15 seconds

## Key Differences from Bar-by-Bar Engine (backtester.py)

1. **Position Types**: Only supports long positions. Use bar-by-bar engine for shorts.

2. **Signal Rejection**: Silently skips entries when insufficient cash (no tracking).
   Bar-by-bar engine tracks rejected signals in BacktestResult.rejected_signals.

3. **Commission Handling**: Applies commission_rate * 2 on exit only.
   Bar-by-bar engine deducts commission on both entry and exit.

4. **Risk Exits**: Stop-loss and take-profit are computed during simulation loop
   using actual entry prices (not pre-computed).

5. **Strategy Interface**: Requires VectorizedCompiledStrategy with entry_fn/exit_fn
   that return boolean arrays. Bar-by-bar engine uses callable(engine, symbol, bar).

Choose this engine for:
- Large-scale parameter optimization
- Multi-asset universes (100+ symbols)
- Long-only strategies without complex position management

Choose bar-by-bar engine for:
- Short selling
- Position sizing based on current equity
- Debugging rejected signals
- Maximum accuracy in commission/slippage modeling
"""

from datetime import datetime

import numpy as np

# Import vectorized types from shared library
from llamatrade_compiler import (
    VectorizedBarData,
    VectorizedCompiledStrategy,
)

from src.engine.backtester import BacktestConfig, BacktestResult, Trade

__all__ = [
    "VectorizedBacktestEngine",
    "VectorizedBarData",
]


class VectorizedBacktestEngine:
    """High-performance vectorized backtest engine."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(
        self,
        bars: VectorizedBarData,
        strategy: VectorizedCompiledStrategy,
        symbols: list[str],
    ) -> BacktestResult:
        """Run a vectorized backtest.

        Args:
            bars: Vectorized bar data (OHLCV arrays)
            strategy: Pre-compiled strategy with indicator arrays
            symbols: List of symbol names

        Returns:
            BacktestResult with metrics and trades

        Raises:
            ValueError: If bars data is missing required keys or is empty.
        """
        # Validate required keys exist
        required_keys = ["timestamps", "closes", "opens", "highs", "lows", "volumes"]
        missing_keys = [k for k in required_keys if k not in bars]
        if missing_keys:
            raise ValueError(f"bars data missing required keys: {missing_keys}")

        # Validate arrays are not empty
        if len(bars["timestamps"]) == 0:
            return BacktestResult(
                final_equity=self.config.initial_capital,
                total_return=0.0,
                annual_return=0.0,
            )

        # Validate symbols list
        if not symbols:
            raise ValueError("symbols list cannot be empty")

        num_symbols = len(symbols)
        num_bars = len(bars["timestamps"])
        timestamps = bars["timestamps"]
        closes = bars["closes"]

        # Validate array shapes match
        if closes.shape[0] != num_symbols:
            raise ValueError(
                f"closes array has {closes.shape[0]} symbols but {num_symbols} symbols provided"
            )

        # Initialize tracking arrays
        _positions = np.zeros((num_symbols, num_bars), dtype=np.float64)  # Quantity held (TODO)
        _entry_prices = np.zeros((num_symbols, num_bars), dtype=np.float64)  # TODO
        equity = np.zeros(num_bars, dtype=np.float64)

        # This engine requires signal functions; validate before use
        entry_fn = strategy.entry_fn
        exit_fn = strategy.exit_fn
        if entry_fn is None or exit_fn is None:
            raise ValueError("VectorizedBacktestEngine requires strategy with entry_fn and exit_fn")

        # Get entry/exit signals as boolean arrays (num_symbols, num_bars)
        entry_signals = entry_fn(bars, strategy.indicators)
        exit_signals = exit_fn(bars, strategy.indicators)

        # Note: Risk exits (stop-loss/take-profit) are applied during the simulation loop
        # below, where we have actual entry prices. Pre-computing them here would use
        # uninitialized entry_prices (all zeros) which produces incorrect results.

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

            # Process exits first (strategy signals + risk exits)
            exit_mask = exit_signals[:, bar_idx] & (current_positions > 0)

            # Apply risk exits (stop-loss / take-profit) for positions with real entry prices
            if strategy.stop_loss_pct or strategy.take_profit_pct:
                in_position_mask = current_positions > 0
                if np.any(in_position_mask):
                    # Calculate P&L percentage for positions
                    with np.errstate(divide="ignore", invalid="ignore"):
                        pnl_pct = np.where(
                            current_entry_prices > 0,
                            (bar_close - current_entry_prices) / current_entry_prices * 100,
                            0,
                        )
                    if strategy.stop_loss_pct is not None:
                        exit_mask |= (pnl_pct <= -strategy.stop_loss_pct) & in_position_mask
                    if strategy.take_profit_pct is not None:
                        exit_mask |= (pnl_pct >= strategy.take_profit_pct) & in_position_mask
            if np.any(exit_mask):
                for sym_idx_np in np.where(exit_mask)[0]:
                    sym_idx = int(sym_idx_np)
                    # Record trade
                    symbol: str = symbols[sym_idx]
                    trade = Trade(
                        entry_date=self._idx_to_datetime(
                            timestamps, int(current_entry_bars[sym_idx])
                        ),
                        exit_date=self._idx_to_datetime(timestamps, bar_idx),
                        symbol=symbol,
                        side="long",
                        entry_price=float(current_entry_prices[sym_idx]),
                        exit_price=float(bar_close[sym_idx]),
                        quantity=float(current_positions[sym_idx]),
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
                for sym_idx_np in np.where(entry_mask)[0]:
                    sym_idx = int(sym_idx_np)
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

    def _idx_to_datetime(self, timestamps: np.ndarray, idx: int) -> datetime:
        """Convert numpy datetime64 to Python datetime.

        Args:
            timestamps: Array of timestamps
            idx: Index into the array (must be valid)

        Returns:
            Python datetime object

        Raises:
            IndexError: If idx is out of bounds
        """
        if len(timestamps) == 0:
            raise IndexError("Cannot index into empty timestamps array")
        if idx < 0 or idx >= len(timestamps):
            raise IndexError(
                f"Index {idx} out of bounds for timestamps array of length {len(timestamps)}"
            )

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
