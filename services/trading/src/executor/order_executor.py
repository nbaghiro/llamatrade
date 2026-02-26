"""Order executor - handles order submission and lifecycle with database persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.trading import Order
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.alpaca_client import AlpacaOrderResponse, AlpacaTradingClient, get_alpaca_trading_client
from src.models import OrderCreate, OrderResponse, OrderStatus
from src.risk.risk_manager import RiskManager, get_risk_manager


class OrderExecutor:
    """Handles order submission, risk checks, and order lifecycle."""

    def __init__(
        self,
        db: AsyncSession,
        alpaca_client: AlpacaTradingClient,
        risk_manager: RiskManager,
    ):
        self.db = db
        self.alpaca = alpaca_client
        self.risk = risk_manager

    async def submit_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
    ) -> OrderResponse:
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

        # Generate client order ID
        client_order_id = str(uuid4())
        now = datetime.now(UTC)

        # Create order record in pending state
        db_order = Order(
            tenant_id=tenant_id,
            session_id=session_id,
            client_order_id=client_order_id,
            symbol=order.symbol.upper(),
            side=order.side.value,
            order_type=order.order_type.value,
            time_in_force=order.time_in_force.value,
            qty=Decimal(str(order.qty)),
            limit_price=Decimal(str(order.limit_price)) if order.limit_price else None,
            stop_price=Decimal(str(order.stop_price)) if order.stop_price else None,
            status="pending",
            filled_qty=Decimal("0"),
        )
        self.db.add(db_order)
        await self.db.commit()
        await self.db.refresh(db_order)

        # Submit to Alpaca
        try:
            alpaca_order = await self.alpaca.submit_order(
                symbol=order.symbol,
                qty=order.qty,
                side=order.side.value,
                order_type=order.order_type.value,
                time_in_force=order.time_in_force.value,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )

            # Update order with Alpaca response
            db_order.alpaca_order_id = alpaca_order.get("id")
            db_order.status = self._map_alpaca_status(alpaca_order.get("status", "new"))
            db_order.submitted_at = now
            await self.db.commit()
            await self.db.refresh(db_order)

        except Exception as e:
            # Mark order as failed
            db_order.status = "rejected"
            db_order.failed_at = now
            db_order.metadata_ = {"error": str(e)}
            await self.db.commit()
            raise ValueError(f"Failed to submit order to Alpaca: {e}")

        return self._to_response(db_order)

    async def get_order(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> OrderResponse | None:
        """Get order by ID."""
        order = await self._get_order_by_id(tenant_id, order_id)
        return self._to_response(order) if order else None

    async def list_orders(
        self,
        tenant_id: UUID,
        session_id: UUID | None = None,
        status: OrderStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OrderResponse], int]:
        """List orders for tenant."""
        stmt = select(Order).where(Order.tenant_id == tenant_id)

        if session_id:
            stmt = stmt.where(Order.session_id == session_id)
        if status:
            stmt = stmt.where(Order.status == status.value)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginate
        stmt = stmt.order_by(Order.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        return [self._to_response(o) for o in orders], total

    async def cancel_order(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Cancel an order."""
        order = await self._get_order_by_id(tenant_id, order_id)
        if not order:
            return False

        if order.status in ("filled", "cancelled", "rejected", "expired"):
            return False

        # Cancel via Alpaca if we have an Alpaca order ID
        if order.alpaca_order_id:
            cancelled = await self.alpaca.cancel_order(order.alpaca_order_id)
            if not cancelled:
                return False

        order.status = "cancelled"
        order.canceled_at = datetime.now(UTC)
        await self.db.commit()

        return True

    async def sync_order_status(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> OrderResponse | None:
        """Sync order status with Alpaca."""
        order = await self._get_order_by_id(tenant_id, order_id)
        if not order or not order.alpaca_order_id:
            return None

        alpaca_order = await self.alpaca.get_order(order.alpaca_order_id)
        if not alpaca_order:
            return self._to_response(order)

        # Update from Alpaca response
        self._update_from_alpaca(order, alpaca_order)
        await self.db.commit()
        await self.db.refresh(order)

        return self._to_response(order)

    async def sync_all_pending_orders(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> int:
        """Sync all pending orders for a session. Returns count of updated orders."""
        stmt = (
            select(Order)
            .where(Order.tenant_id == tenant_id)
            .where(Order.session_id == session_id)
            .where(Order.status.in_(["pending", "submitted", "accepted", "partial"]))
            .where(Order.alpaca_order_id.isnot(None))
        )

        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        updated = 0
        for order in orders:
            if order.alpaca_order_id:
                alpaca_order = await self.alpaca.get_order(order.alpaca_order_id)
                if alpaca_order:
                    old_status = order.status
                    self._update_from_alpaca(order, alpaca_order)
                    if order.status != old_status:
                        updated += 1

        await self.db.commit()
        return updated

    # ===================
    # Private helpers
    # ===================

    async def _get_order_by_id(self, tenant_id: UUID, order_id: UUID) -> Order | None:
        """Get order ensuring tenant isolation."""
        stmt = select(Order).where(Order.id == order_id).where(Order.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _map_alpaca_status(self, alpaca_status: str) -> str:
        """Map Alpaca status to our status."""
        mapping = {
            "new": "submitted",
            "accepted": "accepted",
            "pending_new": "pending",
            "accepted_for_bidding": "accepted",
            "stopped": "stopped",
            "rejected": "rejected",
            "suspended": "suspended",
            "calculated": "calculated",
            "partially_filled": "partial",
            "filled": "filled",
            "done_for_day": "expired",
            "canceled": "cancelled",
            "expired": "expired",
            "replaced": "replaced",
            "pending_cancel": "pending",
            "pending_replace": "pending",
        }
        return mapping.get(alpaca_status.lower(), alpaca_status.lower())

    def _update_from_alpaca(self, order: Order, alpaca_order: AlpacaOrderResponse) -> None:
        """Update order from Alpaca response."""
        order.status = self._map_alpaca_status(alpaca_order.get("status", "new"))

        filled_qty = alpaca_order.get("filled_qty")
        if filled_qty:
            order.filled_qty = Decimal(filled_qty)

        filled_avg_price = alpaca_order.get("filled_avg_price")
        if filled_avg_price:
            order.filled_avg_price = Decimal(filled_avg_price)

        filled_at = alpaca_order.get("filled_at")
        if filled_at:
            order.filled_at = datetime.fromisoformat(filled_at.replace("Z", "+00:00"))

    def _to_response(self, o: Order) -> OrderResponse:
        """Convert order to response."""
        return OrderResponse(
            id=o.id,
            alpaca_order_id=o.alpaca_order_id,
            symbol=o.symbol,
            side=o.side,
            qty=float(o.qty),
            order_type=o.order_type,
            limit_price=float(o.limit_price) if o.limit_price else None,
            stop_price=float(o.stop_price) if o.stop_price else None,
            status=OrderStatus(o.status)
            if o.status in OrderStatus.__members__.values()
            else OrderStatus.PENDING,
            filled_qty=float(o.filled_qty),
            filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None,
            submitted_at=o.submitted_at or o.created_at,
            filled_at=o.filled_at,
        )


async def get_order_executor(
    db: AsyncSession = Depends(get_db),
    alpaca: AlpacaTradingClient = Depends(get_alpaca_trading_client),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> OrderExecutor:
    """Dependency to get order executor."""
    return OrderExecutor(db=db, alpaca_client=alpaca, risk_manager=risk_manager)
