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

    async def aclose(self) -> None:
        """Release the request-scoped DB session (trading-hardening 13A)."""
        await self.db.close()

    async def open_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: Decimal,
        entry_price: Decimal,
    ) -> Position:
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
            qty=qty,
            avg_entry_price=entry_price,
            current_price=entry_price,
            market_value=cost_basis,
            cost_basis=cost_basis,
            unrealized_pl=Decimal("0"),
            unrealized_plpc=Decimal("0"),
            realized_pl=Decimal("0"),
            is_open=True,
            opened_at=datetime.now(UTC),
        )
        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)

        return position

    async def close_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        exit_price: Decimal,
    ) -> Position | None:
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

        # Calculate realized P&L (exact Decimal)
        if position.side == POSITION_SIDE_LONG:
            realized_pl = (exit_price - position.avg_entry_price) * position.qty
        else:
            realized_pl = (position.avg_entry_price - exit_price) * position.qty

        position.is_open = False
        position.realized_pl = realized_pl
        position.current_price = exit_price
        position.market_value = position.qty * exit_price
        position.unrealized_pl = Decimal("0")
        position.unrealized_plpc = Decimal("0")
        position.closed_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(position)

        return position

    async def get_position(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
    ) -> Position | None:
        """Get a specific position.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID
            symbol: Stock symbol

        Returns:
            The position, or None if not found
        """
        position = await self._get_open_position(tenant_id, session_id, symbol.upper())
        return position

    async def list_open_positions(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> list[Position]:
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

        return list(positions)

    async def list_all_positions(
        self,
        tenant_id: UUID,
        session_id: UUID,
        include_closed: bool = True,
    ) -> list[Position]:
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

        return list(positions)

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

            price = Decimal(str(prices[pos.symbol]))  # market-data feed is float

            pos.current_price = price
            pos.market_value = pos.qty * price

            if pos.side == POSITION_SIDE_LONG:
                unrealized_pl = (price - pos.avg_entry_price) * pos.qty
            else:
                unrealized_pl = (pos.avg_entry_price - price) * pos.qty

            pos.unrealized_pl = unrealized_pl

            if pos.cost_basis != 0:
                pos.unrealized_plpc = unrealized_pl / pos.cost_basis
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


async def get_position_service(
    db: AsyncSession = Depends(get_db),
    market_data: MarketDataClient = Depends(get_market_data_client),
) -> PositionService:
    """Dependency to get position service."""
    return PositionService(db=db, market_data=market_data)


async def create_position_service(tenant_id: UUID | None = None) -> PositionService:
    """Create position service with a request-scoped DB session.

    Used by the gRPC servicer where FastAPI DI is not available. The caller MUST
    ``await service.aclose()`` when done (trading-hardening 13A). When a
    ``tenant_id`` is given, the session is bound to it for Postgres RLS.
    """
    from llamatrade_db import get_session_maker, set_tenant_guc

    db = get_session_maker()()
    if tenant_id is not None:
        await set_tenant_guc(db, tenant_id)
    market_data = get_market_data_client()
    return PositionService(db=db, market_data=market_data)
