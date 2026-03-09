"""Benchmark calculations for strategy comparison.

Provides reference benchmarks and relative performance metrics:
- SPY Buy & Hold
- 60/40 Portfolio (stocks/bonds)
- Risk-Free Rate
- Alpha, Beta, Information Ratio
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

import numpy as np

if TYPE_CHECKING:
    from src.services.backtest_service import MarketDataFetcher


class BenchmarkBarData(TypedDict):
    """Bar data for benchmark calculation."""

    timestamp: datetime
    close: float


@dataclass
class BenchmarkMetrics:
    """Metrics comparing strategy to benchmarks."""

    # Benchmark returns
    spy_return: float = 0.0
    portfolio_60_40_return: float = 0.0
    risk_free_return: float = 0.0

    # Relative metrics
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0

    # Excess returns
    excess_return_vs_spy: float = 0.0
    excess_return_vs_60_40: float = 0.0
    excess_return_vs_rf: float = 0.0


class BenchmarkCalculator:
    """Calculate benchmark returns and relative metrics."""

    def __init__(
        self,
        risk_free_rate: float = 0.02,  # Annual rate (default 2%)
        portfolio_weights: tuple[float, float] = (0.6, 0.4),  # 60% stocks, 40% bonds
        rebalance_frequency: str = "quarterly",  # quarterly, monthly, none
    ):
        self.risk_free_rate = risk_free_rate
        self.stock_weight, self.bond_weight = portfolio_weights
        self.rebalance_frequency = rebalance_frequency

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

    def calculate_60_40_portfolio(
        self,
        spy_bars: list[BenchmarkBarData],
        bond_bars: list[BenchmarkBarData] | None,
        initial_capital: float,
    ) -> tuple[float, list[tuple[datetime, float]]]:
        """Calculate 60/40 portfolio returns with rebalancing.

        Uses SPY for stocks and BND/AGG for bonds.
        If bond data unavailable, uses risk-free rate for bond portion.

        Args:
            spy_bars: Historical SPY bar data
            bond_bars: Historical bond ETF data (BND/AGG) or None
            initial_capital: Starting capital

        Returns:
            Tuple of (total_return, equity_curve)
        """
        if not spy_bars:
            return 0.0, []

        # Initial allocation
        stock_capital = initial_capital * self.stock_weight
        bond_capital = initial_capital * self.bond_weight

        stock_shares = stock_capital / spy_bars[0]["close"]

        # Handle bonds
        daily_rf_rate = 0.0  # Default, only used when use_bond_etf is False
        if bond_bars and len(bond_bars) == len(spy_bars):
            bond_shares = bond_capital / bond_bars[0]["close"]
            use_bond_etf = True
        else:
            # Use risk-free rate for bond portion
            bond_shares = 0
            use_bond_etf = False
            daily_rf_rate = (1 + self.risk_free_rate) ** (1 / 252) - 1

        equity_curve: list[tuple[datetime, float]] = []
        last_rebalance_month = spy_bars[0]["timestamp"].month
        last_rebalance_quarter = (spy_bars[0]["timestamp"].month - 1) // 3

        for i, bar in enumerate(spy_bars):
            # Calculate current values
            stock_value = stock_shares * bar["close"]

            if use_bond_etf and bond_bars:
                bond_value = bond_shares * bond_bars[i]["close"]
            else:
                # Compound bond portion at risk-free rate
                days_elapsed = i
                bond_value = bond_capital * (1 + daily_rf_rate) ** days_elapsed

            total_equity = stock_value + bond_value
            equity_curve.append((bar["timestamp"], total_equity))

            # Check for rebalancing
            should_rebalance = False
            current_month = bar["timestamp"].month
            current_quarter = (bar["timestamp"].month - 1) // 3

            if self.rebalance_frequency == "monthly":
                if current_month != last_rebalance_month:
                    should_rebalance = True
                    last_rebalance_month = current_month
            elif self.rebalance_frequency == "quarterly":
                if current_quarter != last_rebalance_quarter:
                    should_rebalance = True
                    last_rebalance_quarter = current_quarter

            # Rebalance
            if should_rebalance and i < len(spy_bars) - 1:
                target_stock_value = total_equity * self.stock_weight
                target_bond_value = total_equity * self.bond_weight

                stock_shares = target_stock_value / bar["close"]

                if use_bond_etf and bond_bars:
                    bond_shares = target_bond_value / bond_bars[i]["close"]
                else:
                    bond_capital = target_bond_value

        # Calculate total return
        final_equity = equity_curve[-1][1] if equity_curve else initial_capital
        total_return = (final_equity - initial_capital) / initial_capital

        return total_return, equity_curve

    def calculate_risk_free_return(
        self,
        num_days: int,
        initial_capital: float,
    ) -> tuple[float, list[float]]:
        """Calculate risk-free return over period.

        Args:
            num_days: Number of trading days
            initial_capital: Starting capital

        Returns:
            Tuple of (total_return, equity_values)
        """
        if num_days <= 0:
            return 0.0, [initial_capital]

        # Daily compounding
        daily_rate = (1 + self.risk_free_rate) ** (1 / 252) - 1

        equity_values = [initial_capital * (1 + daily_rate) ** i for i in range(num_days)]

        total_return = (equity_values[-1] - initial_capital) / initial_capital
        return total_return, equity_values

    def calculate_alpha_beta(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        risk_free_rate: float | None = None,
    ) -> tuple[float, float]:
        """Calculate alpha and beta vs benchmark.

        Alpha = strategy_return - (rf + beta * (benchmark_return - rf))
        Beta = cov(strategy, benchmark) / var(benchmark)

        Args:
            strategy_returns: Daily strategy returns
            benchmark_returns: Daily benchmark returns
            risk_free_rate: Annual risk-free rate (uses class default if None)

        Returns:
            Tuple of (alpha, beta)
        """
        if len(strategy_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0, 0.0

        # Ensure same length
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strategy_returns = strategy_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        rf = risk_free_rate if risk_free_rate is not None else self.risk_free_rate

        # Calculate beta
        covariance = np.cov(strategy_returns, benchmark_returns)[0, 1]
        variance = np.var(benchmark_returns)

        if variance > 0:
            beta = covariance / variance
        else:
            beta = 0.0

        # Calculate alpha (annualized)
        strategy_annual = np.mean(strategy_returns) * 252
        benchmark_annual = np.mean(benchmark_returns) * 252

        alpha = strategy_annual - (rf + beta * (benchmark_annual - rf))

        return float(alpha), float(beta)

    def calculate_information_ratio(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
    ) -> float:
        """Calculate Information Ratio.

        IR = (strategy - benchmark) / tracking_error
        Tracking error = std(strategy - benchmark)

        Args:
            strategy_returns: Daily strategy returns
            benchmark_returns: Daily benchmark returns

        Returns:
            Information ratio
        """
        if len(strategy_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0

        # Ensure same length
        min_len = min(len(strategy_returns), len(benchmark_returns))
        strategy_returns = strategy_returns[:min_len]
        benchmark_returns = benchmark_returns[:min_len]

        # Active returns
        active_returns = strategy_returns - benchmark_returns

        # Tracking error
        tracking_error = np.std(active_returns)

        if tracking_error > 0:
            # Annualized
            ir = float(np.sqrt(252) * np.mean(active_returns) / tracking_error)
        else:
            ir = 0.0

        return ir

    def calculate_all_metrics(
        self,
        strategy_returns: np.ndarray,
        strategy_total_return: float,
        spy_bars: list[BenchmarkBarData],
        bond_bars: list[BenchmarkBarData] | None,
        initial_capital: float,
    ) -> BenchmarkMetrics:
        """Calculate all benchmark comparison metrics.

        Args:
            strategy_returns: Daily strategy returns
            strategy_total_return: Total strategy return
            spy_bars: Historical SPY data
            bond_bars: Historical bond ETF data or None
            initial_capital: Starting capital

        Returns:
            BenchmarkMetrics with all comparison data
        """
        num_days = len(spy_bars) if spy_bars else len(strategy_returns)

        # Calculate benchmark returns
        spy_return, _ = self.calculate_spy_buy_hold(spy_bars, initial_capital)
        portfolio_return, _ = self.calculate_60_40_portfolio(spy_bars, bond_bars, initial_capital)
        rf_return, _ = self.calculate_risk_free_return(num_days, initial_capital)

        # Calculate SPY daily returns for alpha/beta
        if spy_bars and len(spy_bars) > 1:
            spy_closes = np.array([b["close"] for b in spy_bars])
            spy_returns = np.diff(spy_closes) / spy_closes[:-1]
        else:
            spy_returns = np.array([])

        # Calculate alpha and beta
        alpha, beta = self.calculate_alpha_beta(strategy_returns, spy_returns)

        # Calculate information ratio
        ir = self.calculate_information_ratio(strategy_returns, spy_returns)

        return BenchmarkMetrics(
            spy_return=spy_return,
            portfolio_60_40_return=portfolio_return,
            risk_free_return=rf_return,
            alpha=alpha,
            beta=beta,
            information_ratio=ir,
            excess_return_vs_spy=strategy_total_return - spy_return,
            excess_return_vs_60_40=strategy_total_return - portfolio_return,
            excess_return_vs_rf=strategy_total_return - rf_return,
        )


async def fetch_benchmark_data(
    market_data_client: MarketDataFetcher,
    start_date: datetime,
    end_date: datetime,
    timeframe: str = "1D",
) -> tuple[list[BenchmarkBarData], list[BenchmarkBarData] | None, bool]:
    """Fetch benchmark data (SPY and BND) from market data service.

    Args:
        market_data_client: MarketDataClient instance
        start_date: Start date
        end_date: End date
        timeframe: Timeframe (default daily)

    Returns:
        Tuple of (spy_bars, bond_bars, benchmark_available).
        benchmark_available is True if SPY data was successfully fetched with at least one bar.
    """
    try:
        # Fetch SPY
        bars = await market_data_client.fetch_bars(
            symbols=["SPY", "BND"],
            timeframe=timeframe,
            start_date=start_date.date(),
            end_date=end_date.date(),
        )

        def _to_float(val: object) -> float:
            """Safely convert to float."""
            if val is None:
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return 0.0
            try:
                return float(val)  # type: ignore[arg-type]
            except TypeError, ValueError:
                return 0.0

        spy_bars: list[BenchmarkBarData] = []
        for b in bars.get("SPY", []):
            ts = b["timestamp"]
            spy_bars.append(
                {
                    "timestamp": ts
                    if isinstance(ts, datetime)
                    else datetime.fromisoformat(str(ts)),
                    "close": _to_float(b["close"]),
                }
            )

        bond_bars_list: list[BenchmarkBarData] = []
        for b in bars.get("BND", []):
            ts = b["timestamp"]
            bond_bars_list.append(
                {
                    "timestamp": ts
                    if isinstance(ts, datetime)
                    else datetime.fromisoformat(str(ts)),
                    "close": _to_float(b["close"]),
                }
            )

        # Benchmark is considered available if we have at least one SPY bar
        benchmark_available = len(spy_bars) > 0
        return spy_bars, bond_bars_list if bond_bars_list else None, benchmark_available

    except Exception:
        # On error, explicitly mark benchmark as unavailable
        return [], None, False
