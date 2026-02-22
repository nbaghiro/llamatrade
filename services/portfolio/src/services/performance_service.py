"""Performance service."""

from datetime import datetime
from typing import Any
from uuid import UUID


class PerformanceService:
    """Service for performance analytics."""

    async def get_metrics(self, tenant_id: UUID, period: str) -> dict[str, Any]:
        """Get performance metrics."""
        return {
            "period": period,
            "total_return": 0,
            "total_return_percent": 0,
            "annualized_return": 0,
            "volatility": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "best_day": 0,
            "worst_day": 0,
            "avg_daily_return": 0,
        }

    async def get_equity_curve(
        self,
        tenant_id: UUID,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[dict[str, Any]]:
        """Get equity curve."""
        return []

    async def get_daily_returns(self, tenant_id: UUID, period: str) -> list[dict[str, Any]]:
        """Get daily returns."""
        return []


def get_performance_service() -> PerformanceService:
    return PerformanceService()
