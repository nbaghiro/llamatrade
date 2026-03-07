"""Shared metrics calculation functions for backtesting engines.

This module provides a single source of truth for calculating
backtest metrics, used by both bar-by-bar and vectorized engines.
"""

from datetime import datetime
from typing import Protocol, cast

import numpy as np


class TradeWithPnl(Protocol):
    """Protocol for trade objects that have a pnl attribute."""

    @property
    def pnl(self) -> float:
        """Profit/loss of the trade."""
        ...


def calculate_sharpe_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02,
) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        daily_returns: Array of daily returns
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        Annualized Sharpe ratio
    """
    if len(daily_returns) == 0 or np.std(daily_returns) == 0:
        return 0.0

    daily_rf = risk_free_rate / 252
    excess_returns = daily_returns - daily_rf
    return float(np.sqrt(252) * np.mean(excess_returns) / np.std(daily_returns))


def calculate_sortino_ratio(
    daily_returns: np.ndarray,
    risk_free_rate: float = 0.02,
) -> float:
    """Calculate annualized Sortino ratio (downside deviation).

    Args:
        daily_returns: Array of daily returns
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        Annualized Sortino ratio
    """
    if len(daily_returns) == 0:
        return 0.0

    negative_returns = daily_returns[daily_returns < 0]
    if len(negative_returns) == 0 or np.std(negative_returns) == 0:
        return 0.0

    return float(np.sqrt(252) * np.mean(daily_returns) / np.std(negative_returns))


def calculate_max_drawdown(equity: np.ndarray) -> tuple[float, int]:
    """Calculate maximum drawdown and its duration.

    Args:
        equity: Array of equity values

    Returns:
        Tuple of (max_drawdown_percentage, max_drawdown_duration_in_bars)
    """
    if len(equity) == 0:
        return 0.0, 0

    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_drawdown = float(np.max(drawdown))

    # Calculate duration
    max_dd_duration = 0
    current_duration = 0
    for dd in drawdown:
        if dd > 0:
            current_duration += 1
            max_dd_duration = max(max_dd_duration, current_duration)
        else:
            current_duration = 0

    return max_drawdown, max_dd_duration


def calculate_monthly_returns(
    equity_curve: list[tuple[datetime, float]],
    initial_capital: float,
) -> dict[str, float]:
    """Calculate monthly returns from equity curve.

    Args:
        equity_curve: List of (datetime, equity) tuples
        initial_capital: Starting capital

    Returns:
        Dict mapping "YYYY-MM" to monthly return
    """
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
        if prev_month_end_equity > 0:
            month_return = (month_end_equity - prev_month_end_equity) / prev_month_end_equity
        else:
            month_return = 0.0
        monthly_returns[month] = month_return
        prev_month_end_equity = month_end_equity

    return monthly_returns


def calculate_trade_statistics(
    trades: list[TradeWithPnl],
) -> tuple[float, float]:
    """Calculate win rate and profit factor from trades.

    Args:
        trades: List of Trade objects

    Returns:
        Tuple of (win_rate, profit_factor)
    """
    if not trades:
        return 0.0, 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades)

    total_wins = sum(t.pnl for t in wins)
    total_losses = abs(sum(t.pnl for t in losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else 0.0

    return win_rate, profit_factor


def calculate_returns(
    equity: np.ndarray,
    initial_capital: float,
    num_days: int,
) -> tuple[float, float, list[float]]:
    """Calculate total return, annual return, and daily returns.

    Args:
        equity: Array of equity values
        initial_capital: Starting capital
        num_days: Number of trading days

    Returns:
        Tuple of (total_return, annual_return, daily_returns_list)
    """
    if len(equity) == 0:
        return 0.0, 0.0, []

    final = float(equity[-1])
    total_return = (final - initial_capital) / initial_capital

    # Annual return (assuming 252 trading days)
    if num_days > 0:
        annual_return = ((1 + total_return) ** (252 / num_days)) - 1
    else:
        annual_return = 0.0

    # Daily returns
    daily_returns_list: list[float]
    if len(equity) > 1:
        daily_returns_arr = np.diff(equity) / equity[:-1]
        daily_returns_list = cast(list[float], daily_returns_arr.tolist())
    else:
        daily_returns_list = []

    return total_return, annual_return, daily_returns_list
