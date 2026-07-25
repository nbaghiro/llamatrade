"""Benchmark calculations for strategy comparison.

Provides reference benchmarks and relative performance metrics:
- SPY Buy & Hold
- Alpha, Beta, Information Ratio
"""

from datetime import date as date_type
from datetime import datetime
from typing import TypedDict

import numpy as np


class BenchmarkBarData(TypedDict):
    """Bar data for benchmark calculation."""

    timestamp: datetime
    close: float


def align_daily_returns(
    strategy_daily_curve: list[tuple[datetime, float]],
    benchmark_bars: list[BenchmarkBarData],
) -> tuple[np.ndarray, np.ndarray]:
    """Date-join strategy and benchmark day-over-day returns.

    Both series are resampled to one point per calendar day (last value),
    day-over-day returns are computed per series, and only dates present in
    BOTH series are kept. This replaces positional alignment, which skews
    alpha/beta whenever either series is missing a date.

    Args:
        strategy_daily_curve: Strategy (timestamp, equity) points, chronological
        benchmark_bars: Benchmark bars, chronological

    Returns:
        Tuple of (strategy_returns, benchmark_returns) aligned by date
    """

    def daily_returns_by_date(points: list[tuple[datetime, float]]) -> dict[date_type, float]:
        # Last value per calendar day
        daily: list[tuple[date_type, float]] = []
        for dt, val in points:
            d = dt.date()
            if daily and daily[-1][0] == d:
                daily[-1] = (d, val)
            else:
                daily.append((d, val))

        returns: dict[date_type, float] = {}
        for (_, prev_val), (d, val) in zip(daily, daily[1:], strict=False):
            if prev_val > 0:
                returns[d] = (val - prev_val) / prev_val
        return returns

    strategy_returns = daily_returns_by_date(strategy_daily_curve)
    benchmark_returns = daily_returns_by_date(
        [(b["timestamp"], b["close"]) for b in benchmark_bars]
    )

    common_dates = sorted(set(strategy_returns) & set(benchmark_returns))
    return (
        np.array([strategy_returns[d] for d in common_dates]),
        np.array([benchmark_returns[d] for d in common_dates]),
    )


class BenchmarkCalculator:
    """Calculate benchmark returns and relative metrics."""

    def __init__(
        self,
        risk_free_rate: float = 0.02,  # Annual rate (default 2%)
    ):
        self.risk_free_rate = risk_free_rate

    def calculate_spy_buy_hold(
        self,
        spy_bars: list[BenchmarkBarData],
        initial_capital: float,
    ) -> tuple[float, list[tuple[datetime, float]]]:
        """Calculate SPY buy & hold returns.

        Args:
            spy_bars: Historical SPY bar data
            initial_capital: Starting capital

        Returns:
            Tuple of (total_return, equity_curve)
        """
        if not spy_bars:
            return 0.0, []

        # Buy at first price
        first_price = spy_bars[0]["close"]
        shares = initial_capital / first_price

        # Track equity
        equity_curve = [(bar["timestamp"], shares * bar["close"]) for bar in spy_bars]

        # Calculate total return
        final_equity = shares * spy_bars[-1]["close"]
        total_return = (final_equity - initial_capital) / initial_capital

        return total_return, equity_curve

    def calculate_alpha_beta(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        risk_free_rate: float | None = None,
    ) -> tuple[float | None, float | None]:
        """Calculate alpha and beta vs benchmark.

        Alpha = strategy_return - (rf + beta * (benchmark_return - rf))
        Beta = cov(strategy, benchmark) / var(benchmark)

        Returns ``(None, None)`` when alpha/beta are genuinely undefined — fewer
        than two joined points, or a benchmark with zero variance (beta would be
        a 0/0). None means "undefined", which a 0.0 would silently misrepresent
        as "market-neutral" (8A; matches the profit_factor convention).

        Args:
            strategy_returns: Daily strategy returns
            benchmark_returns: Daily benchmark returns
            risk_free_rate: Annual risk-free rate (uses class default if None)

        Returns:
            Tuple of (alpha, beta), each None when undefined
        """
        if len(strategy_returns) < 2 or len(benchmark_returns) < 2:
            return None, None

        # Ensure same length
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strategy_returns = strategy_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        rf = risk_free_rate if risk_free_rate is not None else self.risk_free_rate

        # Calculate beta
        covariance = np.cov(strategy_returns, benchmark_returns)[0, 1]
        variance = np.var(benchmark_returns)

        if variance <= 0:
            # A flat benchmark has no variance: beta (and thus alpha) are
            # undefined, not zero.
            return None, None

        beta = covariance / variance

        # Calculate alpha (annualized)
        strategy_annual = np.mean(strategy_returns) * 252
        benchmark_annual = np.mean(benchmark_returns) * 252

        alpha = strategy_annual - (rf + beta * (benchmark_annual - rf))

        return float(alpha), float(beta)

    def calculate_information_ratio(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
    ) -> float | None:
        """Calculate Information Ratio.

        IR = (strategy - benchmark) / tracking_error
        Tracking error = std(strategy - benchmark)

        Returns ``None`` when IR is undefined — fewer than two joined points, or
        zero tracking error (a 0/0 when the strategy perfectly tracks the
        benchmark) — rather than a misleading 0.0 (8A).

        Args:
            strategy_returns: Daily strategy returns
            benchmark_returns: Daily benchmark returns

        Returns:
            Information ratio, or None when undefined
        """
        if len(strategy_returns) < 2 or len(benchmark_returns) < 2:
            return None

        # Ensure same length
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strategy_returns = strategy_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        # Active returns
        active_returns = strategy_returns - benchmark_returns

        # Tracking error
        tracking_error = np.std(active_returns)

        if tracking_error <= 0:
            return None

        # Annualized
        return float(np.sqrt(252) * np.mean(active_returns) / tracking_error)
