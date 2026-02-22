"""Backtesting engine - runs historical simulations."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np


@dataclass
class Trade:
    """Represents a completed trade."""

    entry_date: datetime
    exit_date: datetime
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: float
    quantity: float
    commission: float = 0

    @property
    def pnl(self) -> float:
        """Calculate P&L for this trade."""
        if self.side == "long":
            gross_pnl = (self.exit_price - self.entry_price) * self.quantity
        else:
            gross_pnl = (self.entry_price - self.exit_price) * self.quantity
        return gross_pnl - self.commission

    @property
    def pnl_percent(self) -> float:
        """Calculate P&L percentage."""
        return (self.pnl / (self.entry_price * self.quantity)) * 100


@dataclass
class Position:
    """Represents an open position."""

    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_date: datetime


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    initial_capital: float = 100000
    commission_rate: float = 0  # Per trade
    slippage_rate: float = 0  # Percentage
    risk_free_rate: float = 0.02  # For Sharpe ratio


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    final_equity: float = 0
    total_return: float = 0
    annual_return: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    max_drawdown: float = 0
    max_drawdown_duration: int = 0
    win_rate: float = 0
    profit_factor: float = 0


class BacktestEngine:
    """Engine for running historical backtests."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.cash = self.config.initial_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, float]] = []
        self._current_date: datetime | None = None

    def reset(self):
        """Reset the engine state."""
        self.cash = self.config.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self._current_date = None

    def run(
        self,
        bars: dict[str, list[dict[str, Any]]],
        strategy_fn: Callable,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestResult:
        """Run a backtest.

        Args:
            bars: Historical bar data by symbol
            strategy_fn: Strategy function that takes (engine, symbol, bar) and returns signals
            start_date: Start date for the backtest
            end_date: End date for the backtest

        Returns:
            BacktestResult with metrics and trades
        """
        self.reset()

        # Get all dates in range
        all_dates = set()
        for symbol_bars in bars.values():
            for b in symbol_bars:
                bar_date = b["timestamp"]
                if start_date <= bar_date <= end_date:
                    all_dates.add(bar_date)

        # Sort dates
        sorted_dates = sorted(all_dates)

        # Process each date
        for date in sorted_dates:
            self._current_date = date

            # Process each symbol
            for symbol, symbol_bars in bars.items():
                # Find bar for this date
                bar: dict[str, Any] | None = None
                for b in symbol_bars:
                    if b["timestamp"] == date:
                        bar = b
                        break

                if bar:
                    # Get signals from strategy
                    signals = strategy_fn(self, symbol, bar)

                    # Process signals
                    for signal in signals:
                        self._process_signal(signal, bar)

            # Record equity
            equity = self._calculate_equity(bars, date)
            self.equity_curve.append((date, equity))

        # Close all remaining positions at the end
        self._close_all_positions(bars, end_date)

        # Calculate metrics
        return self._calculate_results()

    def _process_signal(self, signal: dict[str, Any], bar: dict[str, Any]):
        """Process a trading signal."""
        signal_type = signal.get("type")
        symbol: str | None = signal.get("symbol")
        quantity = signal.get("quantity", 0)
        price = bar["close"]

        if symbol is None:
            return

        # Apply slippage
        if self.config.slippage_rate > 0:
            if signal_type in ("buy", "cover"):
                price *= 1 + self.config.slippage_rate
            elif signal_type in ("sell", "short"):
                price *= 1 - self.config.slippage_rate

        if signal_type == "buy":
            self._open_position(symbol, "long", price, quantity)
        elif signal_type == "sell":
            if symbol in self.positions:
                self._close_position(symbol, price)
        elif signal_type == "short":
            self._open_position(symbol, "short", price, quantity)
        elif signal_type == "cover":
            if symbol in self.positions:
                self._close_position(symbol, price)

    def _open_position(self, symbol: str, side: str, price: float, quantity: float):
        """Open a new position."""
        if self._current_date is None:
            return

        cost = price * quantity
        commission = self.config.commission_rate

        if cost + commission > self.cash:
            return  # Not enough cash

        self.cash -= cost + commission
        self.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            entry_price=price,
            quantity=quantity,
            entry_date=self._current_date,
        )

    def _close_position(self, symbol: str, price: float):
        """Close an existing position."""
        if symbol not in self.positions or self._current_date is None:
            return

        pos = self.positions.pop(symbol)
        commission = self.config.commission_rate

        trade = Trade(
            entry_date=pos.entry_date,
            exit_date=self._current_date,
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=price,
            quantity=pos.quantity,
            commission=commission * 2,  # Entry + exit
        )

        self.trades.append(trade)
        self.cash += price * pos.quantity - commission

    def _close_all_positions(self, bars: dict[str, list[dict[str, Any]]], date: datetime):
        """Close all open positions."""
        for symbol in list(self.positions.keys()):
            # Find last price
            price = None
            for bar in reversed(bars.get(symbol, [])):
                if bar["timestamp"] <= date:
                    price = bar["close"]
                    break

            if price:
                self._close_position(symbol, price)

    def _calculate_equity(self, bars: dict[str, list[dict[str, Any]]], date: datetime) -> float:
        """Calculate current equity."""
        equity = self.cash

        for symbol, pos in self.positions.items():
            # Find current price
            price = pos.entry_price
            for bar in reversed(bars.get(symbol, [])):
                if bar["timestamp"] <= date:
                    price = bar["close"]
                    break

            if pos.side == "long":
                equity += pos.quantity * price
            else:
                # Short position
                equity += pos.quantity * (2 * pos.entry_price - price)

        return equity

    def _calculate_results(self) -> BacktestResult:
        """Calculate backtest metrics."""
        if not self.equity_curve:
            return BacktestResult()

        equities = np.array([e[1] for e in self.equity_curve])
        initial = self.config.initial_capital
        final = equities[-1]

        # Total return
        total_return = (final - initial) / initial

        # Annual return (assuming 252 trading days)
        num_days = len(equities)
        annual_return = ((1 + total_return) ** (252 / max(num_days, 1))) - 1 if num_days > 0 else 0

        # Daily returns
        daily_returns = np.diff(equities) / equities[:-1] if len(equities) > 1 else np.array([])

        # Sharpe ratio
        if len(daily_returns) > 0 and np.std(daily_returns) > 0:
            excess_returns = daily_returns - self.config.risk_free_rate / 252
            sharpe_ratio = np.sqrt(252) * np.mean(excess_returns) / np.std(daily_returns)
        else:
            sharpe_ratio = 0

        # Sortino ratio (downside deviation)
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 0 and np.std(negative_returns) > 0:
            sortino_ratio = np.sqrt(252) * np.mean(daily_returns) / np.std(negative_returns)
        else:
            sortino_ratio = 0

        # Max drawdown
        peak = np.maximum.accumulate(equities)
        drawdown = (peak - equities) / peak
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

        # Max drawdown duration
        max_dd_duration = 0
        current_duration = 0
        for dd in drawdown:
            if dd > 0:
                current_duration += 1
                max_dd_duration = max(max_dd_duration, current_duration)
            else:
                current_duration = 0

        # Trade statistics
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        win_rate = len(wins) / len(self.trades) if self.trades else 0

        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

        return BacktestResult(
            trades=self.trades,
            equity_curve=self.equity_curve,
            final_equity=final,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            win_rate=win_rate,
            profit_factor=profit_factor if profit_factor != float("inf") else 0,
        )

    # Convenience methods for strategies
    def get_position(self, symbol: str) -> Position | None:
        """Get current position for a symbol."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol."""
        return symbol in self.positions

    def get_cash(self) -> float:
        """Get available cash."""
        return self.cash

    def get_equity(self) -> float:
        """Get current equity (approximate)."""
        if self.equity_curve:
            return self.equity_curve[-1][1]
        return self.cash
