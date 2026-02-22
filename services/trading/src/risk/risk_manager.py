"""Risk manager - enforces trading limits and risk rules."""

from uuid import UUID

from src.models import RiskCheckResult, RiskLimits


class RiskManager:
    """Manages risk limits and validates orders against them."""

    default_limits: RiskLimits

    def __init__(self):
        # Default risk limits
        self.default_limits = RiskLimits(
            max_position_size=10000,
            max_daily_loss=1000,
            max_order_value=5000,
        )

    async def get_limits(self, tenant_id: UUID) -> RiskLimits:
        """Get risk limits for a tenant."""
        # In production, fetch from database
        return self.default_limits

    async def check_order(
        self,
        tenant_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> RiskCheckResult:
        """Check if an order passes risk limits."""
        violations = []
        limits = await self.get_limits(tenant_id)

        # Estimate order value
        # In production, fetch current price
        estimated_price = limit_price or 100  # Placeholder
        order_value = qty * estimated_price

        # Check max order value
        if limits.max_order_value and order_value > limits.max_order_value:
            violations.append(
                f"Order value ${order_value:.2f} exceeds limit ${limits.max_order_value:.2f}"
            )

        # Check allowed symbols
        if limits.allowed_symbols and symbol.upper() not in limits.allowed_symbols:
            violations.append(f"Symbol {symbol} is not in allowed list")

        # Check position size
        if limits.max_position_size:
            # In production, fetch current position and check total
            pass

        # Check daily loss
        if limits.max_daily_loss:
            # In production, check daily P&L
            pass

        return RiskCheckResult(
            passed=len(violations) == 0,
            violations=violations,
        )

    async def check_daily_loss(self, tenant_id: UUID) -> bool:
        """Check if daily loss limit has been exceeded."""
        limits = await self.get_limits(tenant_id)
        if not limits.max_daily_loss:
            return True

        # In production, calculate daily P&L
        daily_pnl = 0  # Placeholder
        return daily_pnl > -limits.max_daily_loss

    async def update_limits(
        self,
        tenant_id: UUID,
        limits: RiskLimits,
    ) -> RiskLimits:
        """Update risk limits for a tenant."""
        # In production, save to database
        return limits


_manager: RiskManager | None = None


def get_risk_manager() -> RiskManager:
    """Dependency to get risk manager."""
    global _manager
    if _manager is None:
        _manager = RiskManager()
    return _manager
