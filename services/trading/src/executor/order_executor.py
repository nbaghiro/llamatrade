"""Order executor - handles order submission and lifecycle."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from src.alpaca_client import AlpacaTradingClient
from src.models import OrderCreate, OrderStatus
from src.risk.risk_manager import RiskManager


class OrderExecutor:
    """Handles order submission, risk checks, and order lifecycle."""

    def __init__(
        self,
        alpaca_client: AlpacaTradingClient,
        risk_manager: RiskManager,
    ):
        self.alpaca = alpaca_client
        self.risk = risk_manager

    async def submit_order(
        self,
        tenant_id: UUID,
        session_id: UUID | None,
        order: OrderCreate,
    ) -> dict[str, Any]:
        """Submit an order after risk checks."""
        # Run risk checks
        risk_result = await self.risk.check_order(
            tenant_id=tenant_id,
            symbol=order.symbol,
            side=order.side.value,
            qty=order.qty,
            order_type=order.order_type.value,
        )

        if not risk_result.passed:
            raise ValueError(f"Risk check failed: {', '.join(risk_result.violations)}")

        # Submit to Alpaca
        order_id = uuid4()
        now = datetime.now(UTC)

        # In production, submit to Alpaca API
        # alpaca_order = await self.alpaca.submit_order(...)

        return {
            "id": order_id,
            "alpaca_order_id": None,  # Would come from Alpaca
            "symbol": order.symbol.upper(),
            "side": order.side,
            "qty": order.qty,
            "order_type": order.order_type,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "status": OrderStatus.SUBMITTED,
            "filled_qty": 0,
            "filled_avg_price": None,
            "submitted_at": now,
            "filled_at": None,
        }

    async def get_order(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get order by ID."""
        # In production, fetch from database
        return None

    async def list_orders(
        self,
        tenant_id: UUID,
        session_id: UUID | None = None,
        status: OrderStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List orders for tenant."""
        # In production, fetch from database
        return [], 0

    async def cancel_order(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Cancel an order."""
        # In production, cancel via Alpaca API
        return False

    async def sync_order_status(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Sync order status with Alpaca."""
        # In production, fetch from Alpaca and update local DB
        return None


def get_order_executor() -> OrderExecutor:
    """Dependency to get order executor."""
    from src.alpaca_client import get_alpaca_trading_client
    from src.risk.risk_manager import get_risk_manager

    return OrderExecutor(
        alpaca_client=get_alpaca_trading_client(),
        risk_manager=get_risk_manager(),
    )
