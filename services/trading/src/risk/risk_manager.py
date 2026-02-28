"""Risk manager - enforces trading limits and risk rules with database persistence."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.audit import DailyPnL, RiskConfig
from llamatrade_db.models.trading import Order, Position
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.market_data import MarketDataClient, get_market_data_client
from src.metrics import record_risk_check, update_daily_pnl, update_drawdown
from src.models import RiskCheckResult, RiskLimits


class RiskManager:
    """Manages risk limits and validates orders against them."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        market_data: MarketDataClient | None = None,
    ):
        self.db = db
        self.market_data = market_data
        # Default risk limits (used when no DB or no config found)
        self._default_limits = RiskLimits(
            max_position_size=10000,
            max_daily_loss=1000,
            max_order_value=5000,
        )
        # Price cache for fallback (symbol -> last known price)
        self._price_cache: dict[str, float] = {}

    async def get_limits(
        self,
        tenant_id: UUID,
        session_id: UUID | None = None,
    ) -> RiskLimits:
        """Get risk limits for a tenant/session."""
        if not self.db:
            return self._default_limits

        # Try session-specific config first
        if session_id:
            config = await self._get_config(tenant_id, session_id)
            if config:
                return self._config_to_limits(config)

        # Fall back to tenant-wide config
        config = await self._get_config(tenant_id, None)
        if config:
            return self._config_to_limits(config)

        return self._default_limits

    async def check_order(
        self,
        tenant_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        limit_price: float | None = None,
        session_id: UUID | None = None,
    ) -> RiskCheckResult:
        """Check if an order passes all risk limits."""
        start_time = time.perf_counter()
        violations = []
        limits = await self.get_limits(tenant_id, session_id)

        # Estimate order value
        estimated_price = limit_price or await self._get_current_price(symbol)
        order_value = qty * estimated_price

        # 1. Check max order value
        if limits.max_order_value and order_value > limits.max_order_value:
            violations.append(
                f"Order value ${order_value:.2f} exceeds limit ${limits.max_order_value:.2f}"
            )

        # 2. Check allowed symbols
        if limits.allowed_symbols and symbol.upper() not in limits.allowed_symbols:
            violations.append(f"Symbol {symbol} is not in allowed list")

        # 3. Check position size (if we have DB access)
        if self.db and limits.max_position_size and session_id:
            position_check = await self._check_position_size(
                tenant_id, session_id, symbol, qty, side, limits.max_position_size
            )
            if not position_check:
                violations.append(f"Position would exceed max size ${limits.max_position_size:.2f}")

        # 4. Check daily loss (if we have DB access)
        if self.db and limits.max_daily_loss and session_id:
            loss_check = await self._check_daily_loss(tenant_id, session_id, limits.max_daily_loss)
            if not loss_check:
                violations.append(f"Daily loss limit ${limits.max_daily_loss:.2f} exceeded")

        # 5. Check order rate limit (if we have DB access)
        if self.db and session_id:
            rate_check = await self._check_rate_limit(tenant_id, session_id)
            if not rate_check:
                violations.append("Order rate limit exceeded (max 10 orders/minute)")

        # Record risk check metrics
        duration = time.perf_counter() - start_time
        passed = len(violations) == 0
        record_risk_check(passed=passed, violations=violations, duration=duration)

        return RiskCheckResult(
            passed=passed,
            violations=violations,
        )

    async def check_daily_loss(
        self,
        tenant_id: UUID,
        session_id: UUID | None = None,
    ) -> bool:
        """Check if daily loss limit has been exceeded."""
        limits = await self.get_limits(tenant_id, session_id)
        if not limits.max_daily_loss:
            return True

        if not self.db or not session_id:
            return True

        daily_pnl = await self._get_daily_pnl(tenant_id, session_id)
        return daily_pnl > -limits.max_daily_loss

    async def update_limits(
        self,
        tenant_id: UUID,
        limits: RiskLimits,
        session_id: UUID | None = None,
    ) -> RiskLimits:
        """Update risk limits for a tenant/session."""
        if not self.db:
            return limits

        # Check if config exists
        existing = await self._get_config(tenant_id, session_id)

        if existing:
            # Update existing config
            existing.max_position_value = limits.max_position_size
            existing.max_daily_loss_value = limits.max_daily_loss
            existing.max_order_value = limits.max_order_value
            existing.allowed_symbols = limits.allowed_symbols
        else:
            # Create new config
            config = RiskConfig(
                tenant_id=tenant_id,
                session_id=session_id,
                max_position_value=limits.max_position_size,
                max_daily_loss_value=limits.max_daily_loss,
                max_order_value=limits.max_order_value,
                allowed_symbols=limits.allowed_symbols,
            )
            self.db.add(config)

        await self.db.commit()
        return limits

    async def get_current_drawdown(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> float:
        """Get current drawdown percentage for a session."""
        if not self.db:
            return 0.0

        today = datetime.now(UTC).date()
        stmt = (
            select(DailyPnL)
            .where(DailyPnL.tenant_id == tenant_id)
            .where(DailyPnL.session_id == session_id)
            .where(func.date(DailyPnL.date) == today)
        )
        result = await self.db.execute(stmt)
        daily = result.scalar_one_or_none()

        if not daily:
            return 0.0

        return float(daily.max_drawdown_pct)

    async def update_daily_pnl(
        self,
        tenant_id: UUID,
        session_id: UUID,
        realized_pnl: float,
        unrealized_pnl: float,
        equity: float,
    ) -> None:
        """Update daily P&L tracking."""
        if not self.db:
            return

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Get or create today's record
        stmt = (
            select(DailyPnL)
            .where(DailyPnL.tenant_id == tenant_id)
            .where(DailyPnL.session_id == session_id)
            .where(DailyPnL.date == today)
        )
        result = await self.db.execute(stmt)
        daily = result.scalar_one_or_none()

        total_pnl = realized_pnl + unrealized_pnl

        if daily:
            # Update existing record
            daily.realized_pnl = realized_pnl
            daily.unrealized_pnl = unrealized_pnl
            daily.total_pnl = total_pnl
            daily.equity_end = equity

            # Update high/low
            if equity > daily.equity_high:
                daily.equity_high = equity
            if equity < daily.equity_low:
                daily.equity_low = equity

            # Calculate drawdown from high
            if daily.equity_high > 0:
                drawdown = ((daily.equity_high - equity) / daily.equity_high) * 100
                daily.max_drawdown_pct = max(daily.max_drawdown_pct, drawdown)
        else:
            # Create new record
            daily = DailyPnL(
                tenant_id=tenant_id,
                session_id=session_id,
                date=today,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                total_pnl=total_pnl,
                equity_start=equity,
                equity_high=equity,
                equity_low=equity,
                equity_end=equity,
                max_drawdown_pct=0.0,
            )
            self.db.add(daily)

        await self.db.commit()

        # Update Prometheus metrics
        update_daily_pnl(str(tenant_id), str(session_id), total_pnl)
        update_drawdown(str(tenant_id), str(session_id), float(daily.max_drawdown_pct))

    async def record_trade(
        self,
        tenant_id: UUID,
        session_id: UUID,
        is_win: bool,
    ) -> None:
        """Record a completed trade for statistics."""
        if not self.db:
            return

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        stmt = (
            select(DailyPnL)
            .where(DailyPnL.tenant_id == tenant_id)
            .where(DailyPnL.session_id == session_id)
            .where(DailyPnL.date == today)
        )
        result = await self.db.execute(stmt)
        daily = result.scalar_one_or_none()

        if daily:
            daily.trades_count += 1
            if is_win:
                daily.winning_trades += 1
            else:
                daily.losing_trades += 1
            await self.db.commit()

    # ===================
    # Private helpers
    # ===================

    async def _get_config(
        self,
        tenant_id: UUID,
        session_id: UUID | None,
    ) -> RiskConfig | None:
        """Get risk config from database."""
        if not self.db:
            return None

        stmt = (
            select(RiskConfig)
            .where(RiskConfig.tenant_id == tenant_id)
            .where(RiskConfig.is_active == True)  # noqa: E712
        )

        if session_id:
            stmt = stmt.where(RiskConfig.session_id == session_id)
        else:
            stmt = stmt.where(RiskConfig.session_id.is_(None))

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _config_to_limits(self, config: RiskConfig) -> RiskLimits:
        """Convert database config to RiskLimits."""
        return RiskLimits(
            max_position_size=config.max_position_value,
            max_daily_loss=config.max_daily_loss_value,
            max_order_value=config.max_order_value,
            allowed_symbols=config.allowed_symbols,
        )

    async def _get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol from market data service."""
        symbol = symbol.upper()

        # Try to fetch from market data service
        if self.market_data:
            price = await self.market_data.get_latest_price(symbol)
            if price is not None and price > 0:
                self._price_cache[symbol] = price
                return price

        # Fall back to cached price
        if symbol in self._price_cache:
            return self._price_cache[symbol]

        # If we have DB, try to get last known price from position
        if self.db:
            stmt = (
                select(Position.current_price)
                .where(Position.symbol == symbol)
                .where(Position.current_price.isnot(None))
                .order_by(Position.updated_at.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            cached_price = result.scalar_one_or_none()
            if cached_price:
                return float(cached_price)

        # Last resort fallback (should rarely be used)
        return 100.0

    async def _check_position_size(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty: float,
        side: str,
        max_size: float,
    ) -> bool:
        """Check if order would exceed position size limit."""
        if not self.db:
            return True

        # Get current position
        stmt = (
            select(Position)
            .where(Position.tenant_id == tenant_id)
            .where(Position.session_id == session_id)
            .where(Position.symbol == symbol)
            .where(Position.is_open == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()

        current_qty = float(position.qty) if position else 0.0
        current_price = (
            float(position.current_price) if position and position.current_price else 100.0
        )

        # Calculate new position size
        if side in ("buy", "cover"):
            new_qty = current_qty + qty
        else:
            new_qty = abs(current_qty - qty)

        new_value = new_qty * current_price
        return new_value <= max_size

    async def _check_daily_loss(
        self,
        tenant_id: UUID,
        session_id: UUID,
        max_loss: float,
    ) -> bool:
        """Check if daily loss limit has been exceeded."""
        daily_pnl = await self._get_daily_pnl(tenant_id, session_id)
        return daily_pnl > -max_loss

    async def _get_daily_pnl(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> float:
        """Get today's P&L for a session."""
        if not self.db:
            return 0.0

        today = datetime.now(UTC).date()
        stmt = (
            select(DailyPnL)
            .where(DailyPnL.tenant_id == tenant_id)
            .where(DailyPnL.session_id == session_id)
            .where(func.date(DailyPnL.date) == today)
        )
        result = await self.db.execute(stmt)
        daily = result.scalar_one_or_none()

        return daily.total_pnl if daily else 0.0

    async def _check_rate_limit(
        self,
        tenant_id: UUID,
        session_id: UUID,
        max_per_minute: int = 10,
    ) -> bool:
        """Check if order rate limit has been exceeded."""
        if not self.db:
            return True

        one_minute_ago = datetime.now(UTC) - timedelta(minutes=1)

        stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.tenant_id == tenant_id)
            .where(Order.session_id == session_id)
            .where(Order.created_at >= one_minute_ago)
        )
        result = await self.db.execute(stmt)
        count = result.scalar() or 0

        return count < max_per_minute


# Singleton for non-DB usage
_manager: RiskManager | None = None


def get_risk_manager() -> RiskManager:
    """Dependency to get risk manager (without DB)."""
    global _manager
    if _manager is None:
        _manager = RiskManager(market_data=get_market_data_client())
    return _manager


async def get_risk_manager_with_db(
    db: AsyncSession = Depends(get_db),
    market_data: MarketDataClient = Depends(get_market_data_client),
) -> RiskManager:
    """Dependency to get risk manager with database and market data access."""
    return RiskManager(db=db, market_data=market_data)
