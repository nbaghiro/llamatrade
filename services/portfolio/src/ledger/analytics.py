"""Pure performance analytics over an equity series (read-side kernel).

Self-contained math for the ledger read path: position P&L, and the
return/risk metrics (Sharpe, Sortino, max drawdown, benchmark alpha/beta) the
performance API exposes. Kept dependency-free of the legacy ``domain.py`` /
``performance_service.py`` so those can be deleted later without touching
the ledger reads. Inputs are plain values (no DB/IO) so every metric is
directly unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------- position P&L


def unrealized_pnl(side: str, qty: float, entry_price: float, current_price: float) -> float:
    """Unrealized P&L for a position (long: (cur−entry)·qty; short: (entry−cur)·qty)."""
    if side == "short":
        return (entry_price - current_price) * qty
    return (current_price - entry_price) * qty


def pnl_percent(pnl: float, cost_basis: float) -> float:
    """P&L as a percent of cost basis (0 when cost basis is 0)."""
    if cost_basis == 0:
        return 0.0
    return (pnl / cost_basis) * 100


# ----------------------------------------------------------------- risk ratios


def sharpe_ratio(daily_returns: NDArray[np.float64], risk_free_rate: float = 0.02) -> float:
    """Annualized Sharpe (0 if no data or zero volatility)."""
    if len(daily_returns) == 0:
        return 0.0
    std = float(np.std(daily_returns))
    if std == 0:
        return 0.0
    excess = daily_returns - risk_free_rate / 252
    return float(np.sqrt(252) * np.mean(excess) / std)


def sortino_ratio(daily_returns: NDArray[np.float64], risk_free_rate: float = 0.02) -> float:
    """Annualized Sortino (0 if no downside or zero downside deviation)."""
    if len(daily_returns) == 0:
        return 0.0
    negative = daily_returns[daily_returns < 0]
    if len(negative) == 0:
        return 0.0
    downside_std = float(np.std(negative))
    if downside_std == 0:
        return 0.0
    excess = float(np.mean(daily_returns)) - risk_free_rate / 252
    return float(np.sqrt(252) * excess / downside_std)


def max_drawdown(equities: NDArray[np.float64]) -> float:
    """Maximum drawdown as a percent (peak-to-trough)."""
    if len(equities) == 0:
        return 0.0
    peak = np.maximum.accumulate(equities)
    drawdown = (peak - equities) / peak
    return float(np.max(drawdown) * 100) if len(drawdown) > 0 else 0.0


def benchmark_metrics(
    dates: list[date],
    equities: NDArray[np.float64],
    bench_closes: dict[date, float],
) -> tuple[float, float, float]:
    """``(beta, alpha %, benchmark_return %)`` over the overlapping window.

    Population normalization (ddof=0) so a 1:1 tracker yields beta == 1.0.
    Zeros when there is insufficient overlapping data.
    """
    port_rets: list[float] = []
    bench_rets: list[float] = []
    for i in range(1, len(dates)):
        b0 = bench_closes.get(dates[i - 1])
        b1 = bench_closes.get(dates[i])
        if b0 and b1 and equities[i - 1] != 0:
            port_rets.append(float(equities[i] / equities[i - 1] - 1))
            bench_rets.append(b1 / b0 - 1)
    if len(bench_rets) < 2:
        return 0.0, 0.0, 0.0
    p = np.array(port_rets)
    b = np.array(bench_rets)
    var_b = float(np.var(b))
    beta = float(np.cov(p, b, ddof=0)[0][1] / var_b) if var_b > 0 else 0.0
    rf_daily = 0.02 / 252
    alpha_daily = float(np.mean(p)) - (rf_daily + beta * (float(np.mean(b)) - rf_daily))
    alpha = alpha_daily * 252 * 100
    benchmark_return = (float(np.prod(1 + b)) - 1) * 100
    return beta, alpha, benchmark_return


# --------------------------------------------------------- equity-series bundle


@dataclass(frozen=True)
class EquityMetrics:
    """Return/risk metrics derived from an equity series."""

    total_return: float
    total_return_percent: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    best_day: float
    worst_day: float
    avg_daily_return: float


def equity_metrics(equities: NDArray[np.float64]) -> EquityMetrics:
    """Compute the full metric bundle from a (≥2-point) equity series.

    Returns all-zero metrics for a series too short to derive returns from.
    """
    if len(equities) < 2:
        return EquityMetrics(*([0.0] * 12))

    daily_returns = np.diff(equities) / equities[:-1]
    initial, final = float(equities[0]), float(equities[-1])
    total_return = final - initial
    total_return_percent = (total_return / initial) * 100 if initial != 0 else 0.0

    num_days = len(equities)
    annualized = (
        (((1 + total_return / initial) ** (252 / max(num_days, 1))) - 1) * 100
        if num_days > 0 and initial != 0
        else 0.0
    )
    volatility = float(np.std(daily_returns) * np.sqrt(252) * 100) if len(daily_returns) else 0.0
    best = float(np.max(daily_returns) * 100) if len(daily_returns) else 0.0
    worst = float(np.min(daily_returns) * 100) if len(daily_returns) else 0.0
    avg = float(np.mean(daily_returns) * 100) if len(daily_returns) else 0.0

    total_days = len(daily_returns)
    win_rate = float(np.sum(daily_returns > 0) / total_days * 100) if total_days else 0.0
    gains = daily_returns[daily_returns > 0]
    losses = daily_returns[daily_returns < 0]
    total_gains = float(np.sum(gains)) if len(gains) else 0.0
    total_losses = float(abs(np.sum(losses))) if len(losses) else 0.0
    profit_factor = total_gains / total_losses if total_losses > 0 else 0.0

    return EquityMetrics(
        total_return=total_return,
        total_return_percent=total_return_percent,
        annualized_return=annualized,
        volatility=volatility,
        sharpe_ratio=sharpe_ratio(daily_returns),
        sortino_ratio=sortino_ratio(daily_returns),
        max_drawdown=max_drawdown(equities),
        win_rate=win_rate,
        profit_factor=profit_factor,
        best_day=best,
        worst_day=worst,
        avg_daily_return=avg,
    )
