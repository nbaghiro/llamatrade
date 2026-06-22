"""Shared metrics calculation functions for backtesting.

This module is the single source of truth for backtest metric math.
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
    # Guard against a non-positive peak (equity that started at/below zero):
    # (peak - equity) / peak would be inf/nan and poison np.max (7A).
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak > 0, (peak - equity) / peak, 0.0)
    drawdown = np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0)
    max_drawdown = float(np.max(drawdown)) if drawdown.size else 0.0

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
) -> tuple[float, float | None]:
    """Calculate win rate and profit factor from trades.

    Profit factor convention: None means "undefined" — either no trades at
    all, or no losing trades (which would otherwise divide by zero). Callers
    must surface undefined as missing, not as 0.

    Args:
        trades: List of Trade objects

    Returns:
        Tuple of (win_rate, profit_factor)
    """
    if not trades:
        return 0.0, None

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades)

    total_wins = sum(t.pnl for t in wins)
    total_losses = abs(sum(t.pnl for t in losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else None

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
    total_return = (final - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    # Annual return (assuming 252 trading days). When the portfolio is wiped out
    # (final equity <= 0, i.e. 1 + total_return <= 0) a fractional power of a
    # negative base is complex/nan, so clamp to -100% annualized (7A).
    if num_days <= 0:
        annual_return = 0.0
    elif 1 + total_return > 0:
        annual_return = ((1 + total_return) ** (252 / num_days)) - 1
    else:
        annual_return = -1.0

    # Daily returns. Skip non-positive prior-equity denominators so a zero/
    # negative equity point never yields inf/nan (7A).
    daily_returns_list: list[float]
    if len(equity) > 1:
        prev = equity[:-1]
        with np.errstate(divide="ignore", invalid="ignore"):
            daily_returns_arr = np.where(prev > 0, np.diff(equity) / prev, 0.0)
        daily_returns_arr = np.nan_to_num(daily_returns_arr, nan=0.0, posinf=0.0, neginf=0.0)
        daily_returns_list = cast(list[float], daily_returns_arr.tolist())
    else:
        daily_returns_list = []

    return total_return, annual_return, daily_returns_list


def resample_daily(
    equity_curve: list[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """Resample an equity curve to one point per calendar day.

    Keeps the LAST point of each day, so for daily bars this is the identity
    transform. All annualized metrics (Sharpe, Sortino, annual return,
    drawdown duration) must be computed on this daily grid — computing them
    on raw intraday bars with a 252-period annualization factor inflates them
    by roughly sqrt(bars per day).

    Args:
        equity_curve: Chronological list of (timestamp, equity) tuples

    Returns:
        Daily-resampled (timestamp, equity) tuples (last point per day)
    """
    if not equity_curve:
        return []

    daily: list[tuple[datetime, float]] = []
    for dt, eq in equity_curve:
        if daily and daily[-1][0].date() == dt.date():
            daily[-1] = (dt, eq)
        else:
            daily.append((dt, eq))
    return daily
