"""Performance service - performance analytics with database persistence."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import numpy as np
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.portfolio import PortfolioHistory

from src.models import EquityPoint, PerformanceMetrics


class PerformanceService:
    """Service for performance analytics with database persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_metrics(self, tenant_id: UUID, period: str) -> PerformanceMetrics:
        """Get performance metrics for a period.

        Args:
            tenant_id: Tenant ID for isolation
            period: Period string (1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL)

        Returns:
            Performance metrics for the period
        """
        start_date, end_date = self._get_period_dates(period)

        # Fetch portfolio history for the period
        history = await self._get_portfolio_history(tenant_id, start_date, end_date)

        if not history or len(history) < 2:
            return PerformanceMetrics(
                period=period,
                total_return=0.0,
                total_return_percent=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                best_day=0.0,
                worst_day=0.0,
                avg_daily_return=0.0,
            )

        # Extract equity values
        equities = np.array([float(h.equity) for h in history])

        # Calculate daily returns
        daily_returns = np.diff(equities) / equities[:-1]

        # Total return
        initial_equity = equities[0]
        final_equity = equities[-1]
        total_return = final_equity - initial_equity
        total_return_percent = (total_return / initial_equity) * 100 if initial_equity != 0 else 0

        # Annualized return (assuming 252 trading days)
        num_days = len(equities)
        annualized_return = (
            (((1 + total_return / initial_equity) ** (252 / max(num_days, 1))) - 1) * 100
            if num_days > 0 and initial_equity != 0
            else 0
        )

        # Volatility (annualized standard deviation)
        volatility = (
            float(np.std(daily_returns) * np.sqrt(252) * 100) if len(daily_returns) > 0 else 0
        )

        # Sharpe ratio (assuming 2% risk-free rate)
        risk_free_rate = 0.02
        sharpe_ratio = self._calc_sharpe_ratio(daily_returns, risk_free_rate)

        # Sortino ratio
        sortino_ratio = self._calc_sortino_ratio(daily_returns)

        # Max drawdown
        max_drawdown = self._calc_max_drawdown(equities)

        # Best and worst day
        best_day = float(np.max(daily_returns) * 100) if len(daily_returns) > 0 else 0
        worst_day = float(np.min(daily_returns) * 100) if len(daily_returns) > 0 else 0

        # Average daily return
        avg_daily_return = float(np.mean(daily_returns) * 100) if len(daily_returns) > 0 else 0

        # Win rate and profit factor - need transaction data for accurate calculation
        # For now, calculate from daily returns
        winning_days = np.sum(daily_returns > 0)
        total_days = len(daily_returns)
        win_rate = (winning_days / total_days * 100) if total_days > 0 else 0

        # Profit factor
        gains = daily_returns[daily_returns > 0]
        losses = daily_returns[daily_returns < 0]
        total_gains = float(np.sum(gains)) if len(gains) > 0 else 0
        total_losses = float(abs(np.sum(losses))) if len(losses) > 0 else 0
        profit_factor = total_gains / total_losses if total_losses > 0 else 0

        return PerformanceMetrics(
            period=period,
            total_return=total_return,
            total_return_percent=total_return_percent,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            best_day=best_day,
            worst_day=worst_day,
            avg_daily_return=avg_daily_return,
        )

    async def get_equity_curve(
        self,
        tenant_id: UUID,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[EquityPoint]:
        """Get historical equity curve.

        Args:
            tenant_id: Tenant ID for isolation
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of equity points
        """
        # Convert datetime to date if provided
        start = start_date.date() if start_date else None
        end = end_date.date() if end_date else None

        history = await self._get_portfolio_history(tenant_id, start, end)

        return [
            EquityPoint(
                timestamp=datetime.combine(h.snapshot_date, datetime.min.time(), tzinfo=UTC),
                equity=float(h.equity),
                cash=float(h.cash),
                market_value=float(h.portfolio_value),
            )
            for h in history
        ]

    async def get_daily_returns(
        self, tenant_id: UUID, period: str
    ) -> list[dict[str, float | datetime]]:
        """Get daily returns for a period.

        Args:
            tenant_id: Tenant ID for isolation
            period: Period string (1W, 1M, 3M, 6M, 1Y, YTD, ALL)

        Returns:
            List of daily return records
        """
        start_date, end_date = self._get_period_dates(period)
        history = await self._get_portfolio_history(tenant_id, start_date, end_date)

        if not history or len(history) < 2:
            return []

        result: list[dict[str, float | datetime]] = []
        for h in history:
            if h.daily_return is not None:
                result.append(
                    {
                        "date": datetime.combine(h.snapshot_date, datetime.min.time(), tzinfo=UTC),
                        "return": float(h.daily_return) * 100,
                        "cumulative_return": float(h.cumulative_return or 0) * 100,
                    }
                )

        return result

    async def _get_portfolio_history(
        self,
        tenant_id: UUID,
        start_date: date | None,
        end_date: date | None,
    ) -> list[PortfolioHistory]:
        """Fetch portfolio history from database.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            List of portfolio history records
        """
        stmt = (
            select(PortfolioHistory)
            .where(PortfolioHistory.tenant_id == tenant_id)
            .order_by(PortfolioHistory.snapshot_date)
        )

        if start_date:
            stmt = stmt.where(PortfolioHistory.snapshot_date >= start_date)
        if end_date:
            stmt = stmt.where(PortfolioHistory.snapshot_date <= end_date)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _get_period_dates(self, period: str) -> tuple[date, date]:
        """Convert period string to start and end dates.

        Args:
            period: Period string (1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL)

        Returns:
            Tuple of (start_date, end_date)
        """
        today = date.today()
        end_date = today

        if period == "1D":
            start_date = today - timedelta(days=1)
        elif period == "1W":
            start_date = today - timedelta(weeks=1)
        elif period == "1M":
            start_date = today - timedelta(days=30)
        elif period == "3M":
            start_date = today - timedelta(days=90)
        elif period == "6M":
            start_date = today - timedelta(days=180)
        elif period == "1Y":
            start_date = today - timedelta(days=365)
        elif period == "YTD":
            start_date = date(today.year, 1, 1)
        else:  # ALL
            start_date = date(2000, 1, 1)  # Far enough back

        return start_date, end_date

    def _calc_sharpe_ratio(self, daily_returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate annualized Sharpe ratio.

        Args:
            daily_returns: Array of daily returns
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Sharpe ratio
        """
        if len(daily_returns) == 0:
            return 0.0

        std = np.std(daily_returns)
        if std == 0:
            return 0.0

        excess_returns = daily_returns - risk_free_rate / 252
        return float(np.sqrt(252) * np.mean(excess_returns) / std)

    def _calc_sortino_ratio(self, daily_returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate annualized Sortino ratio.

        Args:
            daily_returns: Array of daily returns
            risk_free_rate: Annual risk-free rate (default 2%)

        Returns:
            Sortino ratio
        """
        if len(daily_returns) == 0:
            return 0.0

        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) == 0:
            return 0.0

        downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0.0

        excess_return = np.mean(daily_returns) - risk_free_rate / 252
        return float(np.sqrt(252) * excess_return / downside_std)

    def _calc_max_drawdown(self, equities: np.ndarray) -> float:
        """Calculate maximum drawdown percentage.

        Args:
            equities: Array of equity values

        Returns:
            Maximum drawdown as percentage
        """
        if len(equities) == 0:
            return 0.0

        peak = np.maximum.accumulate(equities)
        drawdown = (peak - equities) / peak
        return float(np.max(drawdown) * 100) if len(drawdown) > 0 else 0.0


async def get_performance_service(
    db: AsyncSession = Depends(get_db),
) -> PerformanceService:
    """Dependency to get performance service."""
    return PerformanceService(db=db)
