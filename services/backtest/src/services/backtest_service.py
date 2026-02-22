"""Backtest service - manages backtest runs."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.models import BacktestStatus


class BacktestService:
    """Service for managing backtest runs."""

    async def create_backtest(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
        strategy_version: int | None,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        symbols: list[str] | None,
        commission: float,
        slippage: float,
    ) -> dict[str, Any]:
        """Create and queue a new backtest."""
        if end_date <= start_date:
            raise ValueError("End date must be after start date")

        backtest_id = uuid4()
        now = datetime.now(UTC)

        # In production, save to database and enqueue task
        return {
            "id": backtest_id,
            "tenant_id": tenant_id,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version or 1,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "status": BacktestStatus.PENDING,
            "progress": 0,
            "error_message": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
        }

    async def get_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get backtest by ID."""
        return None

    async def list_backtests(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        status: BacktestStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List backtests for tenant."""
        return [], 0

    async def get_results(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get backtest results."""
        return None

    async def cancel_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Cancel a backtest."""
        return False

    async def retry_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Retry a failed backtest."""
        return None


def get_backtest_service() -> BacktestService:
    """Dependency to get backtest service."""
    return BacktestService()
