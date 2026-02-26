"""Session service - trading session management with database persistence."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from llamatrade_db.models.trading import Position, TradingSession
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SessionResponse, SessionStatus, TradingMode


class SessionService:
    """Manages trading sessions with database persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_session(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int | None,
        name: str,
        mode: TradingMode,
        credentials_id: UUID,
        symbols: list[str] | None = None,
        config: dict | None = None,
    ) -> SessionResponse:
        """Start a new trading session."""
        # Verify strategy exists and belongs to tenant
        strategy = await self._get_strategy(tenant_id, strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Use current version if not specified
        version = strategy_version or strategy.current_version

        # Get strategy version for symbols
        strategy_ver = await self._get_strategy_version(strategy_id, version)
        if not strategy_ver:
            raise ValueError(f"Strategy version {version} not found")

        # Use symbols from strategy if not provided
        actual_symbols = symbols or strategy_ver.symbols or []
        if not actual_symbols:
            raise ValueError("No symbols specified")

        now = datetime.now(UTC)

        session = TradingSession(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            strategy_version=version,
            credentials_id=credentials_id,
            name=name,
            mode=mode.value,
            status="active",
            config=config or {},
            symbols=actual_symbols,
            started_at=now,
            created_by=user_id,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return self._to_response(session)

    async def get_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
        include_pnl: bool = True,
    ) -> SessionResponse | None:
        """Get session by ID.

        Args:
            session_id: The session ID
            tenant_id: Tenant ID for isolation
            include_pnl: If True, includes calculated P&L (default True)

        Returns:
            Session response or None if not found
        """
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return None

        if include_pnl:
            return await self._to_response_with_pnl(session)
        return self._to_response(session)

    async def list_sessions(
        self,
        tenant_id: UUID,
        status: SessionStatus | None = None,
        strategy_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SessionResponse], int]:
        """List sessions for tenant."""
        stmt = select(TradingSession).where(TradingSession.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(TradingSession.status == status.value)
        if strategy_id:
            stmt = stmt.where(TradingSession.strategy_id == strategy_id)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginate
        stmt = stmt.order_by(TradingSession.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        sessions = result.scalars().all()

        return [self._to_response(s) for s in sessions], total

    async def stop_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Stop a trading session."""
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return None

        if session.status == "stopped":
            return self._to_response(session)

        session.status = "stopped"
        session.stopped_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(session)

        return self._to_response(session)

    async def pause_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Pause a trading session."""
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return None

        if session.status != "active":
            raise ValueError("Only active sessions can be paused")

        session.status = "paused"
        await self.db.commit()
        await self.db.refresh(session)

        return self._to_response(session)

    async def resume_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionResponse | None:
        """Resume a paused session."""
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return None

        if session.status != "paused":
            raise ValueError("Only paused sessions can be resumed")

        session.status = "active"
        await self.db.commit()
        await self.db.refresh(session)

        return self._to_response(session)

    async def update_heartbeat(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Update session heartbeat timestamp."""
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return False

        session.last_heartbeat = datetime.now(UTC)
        await self.db.commit()
        return True

    async def set_error(
        self,
        session_id: UUID,
        tenant_id: UUID,
        error_message: str,
    ) -> SessionResponse | None:
        """Set error state on session."""
        session = await self._get_session_by_id(tenant_id, session_id)
        if not session:
            return None

        session.status = "error"
        session.error_message = error_message
        session.stopped_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(session)

        return self._to_response(session)

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
        realized_pnl = realized_result.scalar() or 0

        # Sum unrealized P&L from open positions
        unrealized_stmt = (
            select(func.sum(Position.unrealized_pl))
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open == True)  # noqa: E712
        )
        unrealized_result = await self.db.execute(unrealized_stmt)
        unrealized_pnl = unrealized_result.scalar() or 0

        return float(realized_pnl), float(unrealized_pnl)

    async def get_trades_count(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> int:
        """Count total completed trades for a session.

        Args:
            tenant_id: Tenant ID
            session_id: Trading session ID

        Returns:
            Number of closed positions (completed trades)
        """
        stmt = (
            select(func.count())
            .select_from(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.is_open == False)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ===================
    # Private helpers
    # ===================

    async def _get_session_by_id(self, tenant_id: UUID, session_id: UUID) -> TradingSession | None:
        """Get session ensuring tenant isolation."""
        stmt = (
            select(TradingSession)
            .where(TradingSession.id == session_id)
            .where(TradingSession.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_strategy(self, tenant_id: UUID, strategy_id: UUID) -> Strategy | None:
        """Get strategy ensuring tenant isolation."""
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_strategy_version(
        self, strategy_id: UUID, version: int
    ) -> StrategyVersion | None:
        """Get a specific strategy version."""
        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _to_response_with_pnl(self, s: TradingSession) -> SessionResponse:
        """Convert session to response with P&L calculation."""
        realized_pnl, unrealized_pnl = await self.get_session_pnl(s.tenant_id, s.id)
        trades_count = await self.get_trades_count(s.tenant_id, s.id)

        return SessionResponse(
            id=s.id,
            tenant_id=s.tenant_id,
            strategy_id=s.strategy_id,
            mode=TradingMode(s.mode),
            status=SessionStatus(s.status),
            started_at=s.started_at or s.created_at,
            stopped_at=s.stopped_at,
            pnl=realized_pnl + unrealized_pnl,
            trades_count=trades_count,
        )

    def _to_response(self, s: TradingSession) -> SessionResponse:
        """Convert session to response (without P&L for efficiency).

        Use _to_response_with_pnl for responses that need P&L data.
        """
        return SessionResponse(
            id=s.id,
            tenant_id=s.tenant_id,
            strategy_id=s.strategy_id,
            mode=TradingMode(s.mode),
            status=SessionStatus(s.status),
            started_at=s.started_at or s.created_at,
            stopped_at=s.stopped_at,
            pnl=0,  # Use _to_response_with_pnl for actual P&L
            trades_count=0,
        )


async def get_session_service(
    db: AsyncSession = Depends(get_db),
) -> SessionService:
    """Dependency to get session service."""
    return SessionService(db)
