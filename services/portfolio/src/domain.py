"""Pure portfolio analytics — no I/O, deterministic, fully unit-testable.

This module is the single source of truth for the portfolio service's financial
math. Functions here take plain values (never a DB session or network client) so
they can be tested directly with zero third-party dependencies, and are intended
to be reused by both the current read services and the ledger-projection read
layer.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from numpy.typing import NDArray


def unrealized_pnl(side: str, qty: float, entry_price: float, current_price: float) -> float:
    """Unrealized P&L for a position.

    Long:  (current - entry) * qty
    Short: (entry - current) * qty
    """
    if side == "short":
        return (entry_price - current_price) * qty
    return (current_price - entry_price) * qty


def pnl_percent(pnl: float, cost_basis: float) -> float:
    """P&L as a percent of cost basis (0 when cost basis is 0)."""
    if cost_basis == 0:
        return 0.0
    return (pnl / cost_basis) * 100


def benchmark_metrics(
    dates: list[date],
    equities: NDArray[np.float64],
    bench_closes: dict[date, float],
) -> tuple[float, float, float]:
    """Compute ``(beta, alpha %, benchmark_return %)`` versus a benchmark.

    Aligns portfolio and benchmark returns over the intervals where both have
    data, then computes:
    - beta  = cov(portfolio, benchmark) / var(benchmark)  (population, ddof=0)
    - alpha = annualized Jensen's alpha (2% risk-free), in percent
    - benchmark_return = compounded benchmark return over the aligned window

    Returns zeros if there is insufficient overlapping data.
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
    # Population normalization (ddof=0) for both covariance and variance so a
    # portfolio that tracks the benchmark 1:1 yields beta == 1.0.
    var_b = float(np.var(b))
    beta = float(np.cov(p, b, ddof=0)[0][1] / var_b) if var_b > 0 else 0.0

    rf_daily = 0.02 / 252
    alpha_daily = float(np.mean(p)) - (rf_daily + beta * (float(np.mean(b)) - rf_daily))
    alpha = alpha_daily * 252 * 100

    benchmark_return = (float(np.prod(1 + b)) - 1) * 100

    return beta, alpha, benchmark_return
