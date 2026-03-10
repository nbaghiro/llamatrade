"""Position service - local position tracking with database persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.trading import Position
from llamatrade_proto.generated.trading_pb2 import (
    POSITION_SIDE_LONG,
)

from src.clients.market_data import MarketDataClient, get_market_data_client
from src.models import PositionResponse, position_side_to_str


class PositionService:
    """Manages position tracking with database persistence.

    This service tracks positions locally in the database, separate from
    Alpaca's position tracking. This allows:
    - Session-specific position tracking
    - Historical position data
    - Custom P&L calculations
    """

    def __init__(self, db: AsyncSession, market_data: MarketDataClient | None = None):
        self.db = db
        self.market_data = market_data

    async def open_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
    ) -> PositionResponse:
        """Open a new position.

        Args:
            tenant_id: Tenant ID for isolation
            session_id: Trading session ID
            symbol: Stock symbol
            side: "long" or "short"
            qty: Position quantity
            entry_price: Entry price

        Returns:
            The created position
        """
        symbol = symbol.upper()
        cost_basis = qty * entry_price

        position = Position(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol=symbol,
            side=side,
            qty=Decimal(str(qty)),
            avg_entry_price=Decimal(str(entry_price)),
            current_price=Decimal(str(entry_price)),
            market_value=Decimal(str(cost_basis)),
            cost_basis=Decimal(str(cost_basis)),
            unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"),
            realized_pl=Decimal("0"),
            is_open=True,
            opened_at=datetime.now(UTC),
        )
        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)

        return self._to_response(position)

    async def close_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        exit_price: float,
    ) -> PositionResponse | None:
        """Close an existing position.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID
            symbol: Stock symbol
            exit_price: Exit price

        Returns:
            The closed position, or None if not found
        """
        position = await self._get_open_position(tenant_id, session_id, symbol.upper())
        if not position:
            return None

        # Calculate realized P&L
        qty = float(position.qty)
        entry_price = float(position.avg_entry_price)

        if position.side == POSITION_SIDE_LONG:
            realized_pl = (exit_price - entry_price) * qty
        else:
            realized_pl = (entry_price - exit_price) * qty

        position.is_open = False
        position.realized_pl = Decimal(str(realized_pl))
        position.current_price = Decimal(str(exit_price))
        position.market_value = Decimal(str(qty * exit_price))
        position.unrealized_pl = Decimal("0")
        position.unrealized_plpc = Decimal("0")
        position.closed_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(position)

        return self._to_response(position)

    async def get_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
    ) -> PositionResponse | None:
        """Get a specific position.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID
            symbol: Stock symbol

        Returns:
            The position, or None if not found
        """
        position = await self._get_open_position(tenant_id, session_id, symbol.upper())
        return self._to_response(position) if position else None

    async def list_open_positions(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> list[PositionResponse]:
        """List all open positions for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID

        Returns:
            List of open positions
        """
        stmt = (
            select(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open.is_(True))
            .order_by(Position.opened_at)
        )
        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        return [self._to_response(p) for p in positions]

    async def list_all_positions(
        self,
        tenant_id: UUID,
        session_id: UUID,
        include_closed: bool = True,
    ) -> list[PositionResponse]:
        """List all positions for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID
            include_closed: Whether to include closed positions

        Returns:
            List of positions
        """
        stmt = (
            select(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
        )

        if not include_closed:
            stmt = stmt.where(Position.is_open.is_(True))

        stmt = stmt.order_by(Position.opened_at)

        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        return [self._to_response(p) for p in positions]

    async def update_prices(
        self,
        tenant_id: UUID,
        session_id: UUID,
        prices: dict[str, float] | None = None,
    ) -> int:
        """Update current prices and unrealized P&L for all open positions.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID
            prices: Optional dict of symbol -> price. If None, fetches from market data.

        Returns:
            Number of positions updated
        """
        positions = await self._get_open_positions_raw(tenant_id, session_id)
        if not positions:
            return 0

        # Fetch prices from market data if not provided
        if prices is None and self.market_data:
            symbols = [p.symbol for p in positions]
            prices = await self.market_data.get_prices(symbols)

        if not prices:
            return 0

        updated = 0
        for pos in positions:
            if pos.symbol not in prices:
                continue

            price = prices[pos.symbol]
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)

            pos.current_price = Decimal(str(price))
            pos.market_value = Decimal(str(qty * price))

            if pos.side == POSITION_SIDE_LONG:
                unrealized_pl = (price - entry_price) * qty
            else:
                unrealized_pl = (entry_price - price) * qty

            pos.unrealized_pl = Decimal(str(unrealized_pl))

            cost_basis = float(pos.cost_basis)
            if cost_basis != 0:
                pos.unrealized_plpc = Decimal(str(unrealized_pl / cost_basis))
            else:
                pos.unrealized_plpc = Decimal("0")

            updated += 1

        await self.db.commit()
        return updated

    async def get_session_pnl(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> tuple[float, float]:
        """Calculate realized and unrealized P&L for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID

        Returns:
            Tuple of (realized_pnl, unrealized_pnl)
        """
        # Sum realized P&L from all positions (open and closed)
        realized_stmt = (
            select(func.sum(Position.realized_pl))
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
        )
        realized_result = await self.db.execute(realized_stmt)
        realized_pnl = realized_result.scalar() or Decimal("0")

        # Sum unrealized P&L from open positions
        unrealized_stmt = (
            select(func.sum(Position.unrealized_pl))
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open.is_(True))
        )
        unrealized_result = await self.db.execute(unrealized_stmt)
        unrealized_pnl = unrealized_result.scalar() or Decimal("0")

        return float(realized_pnl), float(unrealized_pnl)

    async def count_trades(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> int:
        """Count total trades (closed positions) for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID

        Returns:
            Number of closed positions (trades)
        """
        stmt = (
            select(func.count())
            .select_from(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open.is_(False))
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ===================
    # Private helpers
    # ===================

    async def _get_open_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
    ) -> Position | None:
        """Get an open position by symbol."""
        stmt = (
            select(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.symbol == symbol)
            .where(Position.is_open.is_(True))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_open_positions_raw(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> list[Position]:
        """Get all open positions (raw ORM objects)."""
        stmt = (
            select(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open.is_(True))
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _to_response(self, p: Position) -> PositionResponse:
        """Convert Position ORM object to response."""
        return PositionResponse(
            symbol=p.symbol,
            qty=float(p.qty),
            side=position_side_to_str(p.side),
            cost_basis=float(p.cost_basis),
            market_value=float(p.market_value) if p.market_value else 0.0,
            unrealized_pnl=float(p.unrealized_pl) if p.unrealized_pl else 0.0,
            unrealized_pnl_percent=float(p.unrealized_plpc) * 100 if p.unrealized_plpc else 0.0,
            current_price=float(p.current_price) if p.current_price else 0.0,
        )


async def get_position_service(
    db: AsyncSession = Depends(get_db),
    market_data: MarketDataClient = Depends(get_market_data_client),
) -> PositionService:
    """Dependency to get position service."""
    return PositionService(db=db, market_data=market_data)


async def create_position_service() -> PositionService:
    """Create position service without dependency injection.

    Used by gRPC servicer where FastAPI DI is not available.
    """
    db = await anext(get_db())
    market_data = get_market_data_client()
    return PositionService(db=db, market_data=market_data)
