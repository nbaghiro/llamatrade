"""Portfolio service - portfolio summary and positions with database persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.portfolio import PortfolioSummary as PortfolioSummaryModel

from src.clients.market_data import MarketDataClient, get_market_data_client
from src.models import PortfolioSummary, PositionResponse


def _safe_float(val: object, default: float = 0.0) -> float:
    """Safely convert object to float."""
    if val is None:
        return default
    try:
        return float(val)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return default


class PortfolioService:
    """Service for portfolio operations with database persistence."""

    def __init__(self, db: AsyncSession, market_data: MarketDataClient | None = None):
        self.db = db
        self.market_data = market_data

    async def get_summary(self, tenant_id: UUID) -> PortfolioSummary:
        """Get portfolio summary including all positions and P&L.

        Args:
            tenant_id: Tenant ID for isolation

        Returns:
            Portfolio summary with current values and P&L
        """
        # Query portfolio summary from database
        stmt = select(PortfolioSummaryModel).where(PortfolioSummaryModel.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()

        if not summary:
            # Return default empty portfolio if no summary exists
            return PortfolioSummary(
                total_equity=0.0,
                cash=0.0,
                market_value=0.0,
                total_unrealized_pnl=0.0,
                total_realized_pnl=0.0,
                day_pnl=0.0,
                day_pnl_percent=0.0,
                total_pnl_percent=0.0,
                positions_count=0,
                updated_at=datetime.now(UTC),
            )

        # Get positions and enrich with current prices
        # JSONB columns return untyped objects, cast to expected structure
        positions: list[dict[str, object]] = cast(list[dict[str, object]], summary.positions or [])
        enriched_positions = await self._enrich_positions_with_prices(positions)

        # Calculate aggregated P&L from positions
        total_unrealized_pnl = sum(p.unrealized_pnl for p in enriched_positions)
        total_market_value = sum(p.market_value for p in enriched_positions)

        return PortfolioSummary(
            total_equity=float(summary.equity),
            cash=float(summary.cash),
            market_value=total_market_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=float(summary.total_pl),
            day_pnl=float(summary.daily_pl),
            day_pnl_percent=float(summary.daily_pl_percent) * 100,
            total_pnl_percent=float(summary.total_pl_percent) * 100,
            positions_count=summary.position_count,
            updated_at=summary.updated_at or datetime.now(UTC),
        )

    async def list_positions(self, tenant_id: UUID) -> list[PositionResponse]:
        """List all current positions with current prices.

        Args:
            tenant_id: Tenant ID for isolation

        Returns:
            List of positions with current market values
        """
        # Query portfolio summary to get positions JSONB
        stmt = select(PortfolioSummaryModel).where(PortfolioSummaryModel.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()

        # JSONB columns return untyped objects, cast to expected structure
        if not summary or not summary.positions:
            return []

        positions: list[dict[str, object]] = cast(list[dict[str, object]], summary.positions)
        return await self._enrich_positions_with_prices(positions)

    async def get_position(self, tenant_id: UUID, symbol: str) -> PositionResponse | None:
        """Get position for a specific symbol.

        Args:
            tenant_id: Tenant ID for isolation
            symbol: Stock symbol

        Returns:
            Position details or None if not found
        """
        positions = await self.list_positions(tenant_id)
        symbol_upper = symbol.upper()

        for pos in positions:
            if pos.symbol == symbol_upper:
                return pos

        return None

    async def _enrich_positions_with_prices(
        self, positions: list[dict[str, object]]
    ) -> list[PositionResponse]:
        """Enrich position data with current market prices.

        Args:
            positions: List of position dictionaries from JSONB

        Returns:
            List of PositionResponse with current prices and P&L
        """
        if not positions:
            return []

        # Get symbols and fetch current prices
        symbols: list[str] = [str(p.get("symbol", "")) for p in positions if p.get("symbol")]
        current_prices: dict[str, float] = {}

        if self.market_data and symbols:
            decimal_prices = await self.market_data.get_prices(symbols)
            current_prices = {k: float(v) for k, v in decimal_prices.items()}

        result: list[PositionResponse] = []
        for pos in positions:
            symbol: str = str(pos.get("symbol", ""))
            qty = _safe_float(pos.get("qty", 0))
            side: str = str(pos.get("side", "long"))
            avg_entry_price = _safe_float(pos.get("avg_entry_price", 0))
            cost_val = pos.get("cost_basis")
            cost_basis = _safe_float(cost_val) if cost_val is not None else qty * avg_entry_price

            # Use fetched price or fallback to stored price
            current_price_val = pos.get("current_price")
            fallback_price = (
                _safe_float(current_price_val) if current_price_val is not None else avg_entry_price
            )
            current_price = current_prices.get(symbol, fallback_price)

            # Calculate current market value
            market_value = qty * current_price

            # Calculate unrealized P&L based on side
            unrealized_pnl = self._calculate_unrealized_pnl(
                side=side,
                qty=qty,
                entry_price=avg_entry_price,
                current_price=current_price,
            )

            # Calculate unrealized P&L percent
            unrealized_pnl_percent = 0.0
            if cost_basis != 0:
                unrealized_pnl_percent = (unrealized_pnl / cost_basis) * 100

            result.append(
                PositionResponse(
                    symbol=symbol,
                    qty=qty,
                    side=side,
                    cost_basis=cost_basis,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percent=unrealized_pnl_percent,
                    current_price=current_price,
                    avg_entry_price=avg_entry_price,
                )
            )

        return result

    def _calculate_unrealized_pnl(
        self,
        side: str,
        qty: float,
        entry_price: float,
        current_price: float,
    ) -> float:
        """Calculate unrealized P&L based on position side.

        Args:
            side: Position side ("long" or "short")
            qty: Position quantity
            entry_price: Average entry price
            current_price: Current market price

        Returns:
            Unrealized P&L value
        """
        if side == "long":
            return (current_price - entry_price) * qty
        else:  # short
            return (entry_price - current_price) * qty

    async def update_summary(
        self,
        tenant_id: UUID,
        equity: float,
        cash: float,
        buying_power: float,
        portfolio_value: float,
        positions: list[dict[str, object]],
    ) -> PortfolioSummaryModel:
        """Update or create portfolio summary.

        Args:
            tenant_id: Tenant ID
            equity: Total account equity
            cash: Available cash
            buying_power: Buying power
            portfolio_value: Total portfolio value
            positions: List of position dictionaries

        Returns:
            Updated portfolio summary model
        """
        stmt = select(PortfolioSummaryModel).where(PortfolioSummaryModel.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()

        if summary:
            # Update existing
            summary.equity = Decimal(str(equity))
            summary.cash = Decimal(str(cash))
            summary.buying_power = Decimal(str(buying_power))
            summary.portfolio_value = Decimal(str(portfolio_value))
            summary.positions = positions
            summary.position_count = len(positions)
            summary.last_synced_at = datetime.now(UTC)
        else:
            # Create new
            summary = PortfolioSummaryModel(
                tenant_id=tenant_id,
                equity=Decimal(str(equity)),
                cash=Decimal(str(cash)),
                buying_power=Decimal(str(buying_power)),
                portfolio_value=Decimal(str(portfolio_value)),
                positions=positions,
                position_count=len(positions),
                last_synced_at=datetime.now(UTC),
            )
            self.db.add(summary)

        await self.db.commit()
        await self.db.refresh(summary)
        return summary


async def get_portfolio_service(
    db: AsyncSession = Depends(get_db),
    market_data: MarketDataClient = Depends(get_market_data_client),
) -> PortfolioService:
    """Dependency to get portfolio service."""
    return PortfolioService(db=db, market_data=market_data)
