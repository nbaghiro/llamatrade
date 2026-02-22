"""Portfolio service."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID


class PortfolioService:
    """Service for portfolio operations."""

    async def get_summary(self, tenant_id: UUID) -> dict[str, Any]:
        """Get portfolio summary."""
        now = datetime.now(UTC)
        return {
            "total_equity": 100000,
            "cash": 50000,
            "market_value": 50000,
            "total_unrealized_pnl": 0,
            "total_realized_pnl": 0,
            "day_pnl": 0,
            "day_pnl_percent": 0,
            "total_pnl_percent": 0,
            "positions_count": 0,
            "updated_at": now,
        }

    async def list_positions(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """List positions."""
        return []

    async def get_position(self, tenant_id: UUID, symbol: str) -> dict[str, Any] | None:
        """Get position for symbol."""
        return None


def get_portfolio_service() -> PortfolioService:
    return PortfolioService()
