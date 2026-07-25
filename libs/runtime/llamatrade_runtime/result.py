"""RunResult and metric assembly — the output of a completed run."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

import numpy as np

from llamatrade_runtime import metrics
from llamatrade_runtime.models import RejectedSignal, Trade


def _finite(value: float, default: float = 0.0) -> float:
    """Return ``value`` if finite, else ``default`` — keeps NaN/inf out of persisted metrics."""
    return value if math.isfinite(value) else default


def _empty_trade_list() -> list[Trade]:
    return []


def _empty_equity_curve() -> list[tuple[datetime, float]]:
    return []


def _empty_rejected_signals() -> list[RejectedSignal]:
    return []


def _empty_float_list() -> list[float]:
    return []


def _empty_monthly_returns() -> dict[str, float]:
    return {}


@dataclass
class RunResult:
    """Results from a run — trades, curves, and computed performance metrics."""

    trades: list[Trade] = field(default_factory=_empty_trade_list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=_empty_equity_curve)
    # Daily-resampled curve; all annualized metrics are computed on this grid.
    daily_equity_curve: list[tuple[datetime, float]] = field(default_factory=_empty_equity_curve)
    rejected_signals: list[RejectedSignal] = field(default_factory=_empty_rejected_signals)
    final_equity: float = 0
    total_return: float = 0
    annual_return: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    max_drawdown: float = 0
    max_drawdown_duration: int = 0  # In trading days
    win_rate: float = 0
    # None means undefined (no trades, or no losing trades) — see metrics module.
    profit_factor: float | None = None
    daily_returns: list[float] = field(default_factory=_empty_float_list)
    monthly_returns: dict[str, float] = field(default_factory=_empty_monthly_returns)
    exposure_time: float = 0  # Percentage of time with open positions
    # Benchmark comparison fields — populated by the caller (backtest service), not the runtime.
    benchmark_return: float = 0
    benchmark_equity_curve: list[tuple[datetime, float]] = field(
        default_factory=_empty_equity_curve
    )
    benchmark_symbol: str = ""
    alpha: float = 0
    beta: float = 0
    information_ratio: float = 0
    excess_return: float = 0


def assemble_result(
    initial_capital: float,
    equity_curve: list[tuple[datetime, float]],
    trades: list[Trade],
    rejected_signals: list[RejectedSignal],
    days_with_position: int,
    total_days: int,
    risk_free_rate: float = 0.02,
) -> RunResult:
    """Compute performance metrics from a run's equity curve and trades."""
    if not equity_curve:
        return RunResult(final_equity=initial_capital)

    # All annualized metrics use the daily grid so they are correct for any bar timeframe.
    daily_curve = metrics.resample_daily(equity_curve)
    daily_equities = np.array([e[1] for e in daily_curve])

    total_return, annual_return, daily_returns_list = metrics.calculate_returns(
        daily_equities, initial_capital, len(daily_equities)
    )
    daily_returns_arr = np.array(daily_returns_list)

    monthly_returns = metrics.calculate_monthly_returns(daily_curve, initial_capital)
    sharpe_ratio = metrics.calculate_sharpe_ratio(daily_returns_arr, risk_free_rate)
    sortino_ratio = metrics.calculate_sortino_ratio(daily_returns_arr, risk_free_rate)
    max_drawdown, max_dd_duration = metrics.calculate_max_drawdown(daily_equities)

    exposure_time = (days_with_position / total_days * 100) if total_days > 0 else 0

    trades_with_pnl = cast(list[metrics.TradeWithPnl], trades)
    win_rate, profit_factor = metrics.calculate_trade_statistics(trades_with_pnl)

    return RunResult(
        trades=trades,
        equity_curve=equity_curve,
        daily_equity_curve=daily_curve,
        rejected_signals=rejected_signals,
        final_equity=_finite(float(daily_equities[-1]), initial_capital),
        total_return=_finite(total_return),
        annual_return=_finite(annual_return),
        sharpe_ratio=_finite(sharpe_ratio),
        sortino_ratio=_finite(sortino_ratio),
        max_drawdown=_finite(max_drawdown),
        max_drawdown_duration=max_dd_duration,
        win_rate=_finite(win_rate),
        profit_factor=(
            profit_factor if (profit_factor is None or math.isfinite(profit_factor)) else None
        ),
        daily_returns=daily_returns_list,
        monthly_returns=monthly_returns,
        exposure_time=_finite(exposure_time),
    )
