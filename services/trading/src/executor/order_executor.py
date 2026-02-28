"""Order executor - handles order submission and lifecycle with database persistence."""

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.trading import Order
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.alpaca_client import AlpacaOrderResponse, AlpacaTradingClient, get_alpaca_trading_client
from src.metrics import (
    ORDER_SYNC_DURATION,
    ORDERS_SYNCED_TOTAL,
    record_bracket_order_submitted,
    record_bracket_order_triggered,
    record_order_submission,
)
from src.models import (
    BracketOrderInfo,
    BracketType,
    OrderCreate,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.risk.risk_manager import RiskManager, get_risk_manager
from src.services.alert_service import AlertService, get_alert_service


class OrderExecutor:
    """Handles order submission, risk checks, and order lifecycle."""

    def __init__(
        self,
        db: AsyncSession,
        alpaca_client: AlpacaTradingClient,
        risk_manager: RiskManager,
        alert_service: AlertService | None = None,
    ):
        self.db = db
        self.alpaca = alpaca_client
        self.risk = risk_manager
        self.alerts = alert_service

    async def submit_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
    ) -> OrderResponse:
        """Submit an order after risk checks."""
        start_time = time.perf_counter()

        # Run risk checks
        risk_result = await self.risk.check_order(
            tenant_id=tenant_id,
            symbol=order.symbol,
            side=order.side.value,
            qty=order.qty,
            order_type=order.order_type.value,
        )

        if not risk_result.passed:
            # Record rejection metric
            duration = time.perf_counter() - start_time
            record_order_submission(
                side=order.side.value,
                order_type=order.order_type.value,
                status="rejected_risk",
                duration=duration,
            )
            # Send rejection alert
            if self.alerts:
                await self.alerts.on_order_rejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    qty=order.qty,
                    reason=", ".join(risk_result.violations),
                )
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
            # Store bracket order prices on parent order
            stop_loss_price=(
                Decimal(str(order.stop_loss_price)) if order.stop_loss_price else None
            ),
            take_profit_price=(
                Decimal(str(order.take_profit_price)) if order.take_profit_price else None
            ),
        )
        # Store bracket TIF in metadata if specified
        if order.stop_loss_price or order.take_profit_price:
            db_order.metadata_ = {"bracket_tif": order.bracket_time_in_force.value}
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

            # Record success metric
            duration = time.perf_counter() - start_time
            record_order_submission(
                side=order.side.value,
                order_type=order.order_type.value,
                status="success",
                duration=duration,
            )

        except Exception as e:
            # Record API error metric
            duration = time.perf_counter() - start_time
            record_order_submission(
                side=order.side.value,
                order_type=order.order_type.value,
                status="rejected_api",
                duration=duration,
            )
            # Mark order as failed
            db_order.status = "rejected"
            db_order.failed_at = now
            db_order.metadata_ = {"error": str(e)}
            await self.db.commit()
            # Send rejection alert
            if self.alerts:
                await self.alerts.on_order_rejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    qty=order.qty,
                    reason=f"Alpaca API error: {e}",
                )
            raise ValueError(f"Failed to submit order to Alpaca: {e}")

        return self._to_response(db_order)

    async def get_order(
        self,
        order_id: UUID,
        tenant_id: UUID,
        include_bracket_info: bool = False,
    ) -> OrderResponse | None:
        """Get order by ID."""
        order = await self._get_order_by_id(tenant_id, order_id)
        if not order:
            return None

        bracket_info = None
        if include_bracket_info and (order.stop_loss_price or order.take_profit_price):
            sl_order, tp_order = await self._get_bracket_orders(order.id)
            bracket_info = BracketOrderInfo(
                stop_loss_order_id=sl_order.id if sl_order else None,
                take_profit_order_id=tp_order.id if tp_order else None,
            )

        return self._to_response(order, bracket_info)

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
        """Cancel an order and its bracket orders if any."""
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

        # If this is a parent order, cancel all bracket orders
        if order.stop_loss_price or order.take_profit_price:
            await self.cancel_bracket_orders(order.id, tenant_id)

        await self.db.commit()

        return True

    async def sync_order_status(
        self,
        order_id: UUID,
        tenant_id: UUID,
    ) -> OrderResponse | None:
        """Sync order status with Alpaca."""
        start_time = time.perf_counter()

        order = await self._get_order_by_id(tenant_id, order_id)
        if not order or not order.alpaca_order_id:
            return None

        alpaca_order = await self.alpaca.get_order(order.alpaca_order_id)
        if not alpaca_order:
            # Record sync metric
            duration = time.perf_counter() - start_time
            ORDER_SYNC_DURATION.observe(duration)
            ORDERS_SYNCED_TOTAL.labels(status_change="no_change").inc()
            return self._to_response(order)

        old_status = order.status

        # Update from Alpaca response
        just_filled = self._update_from_alpaca(order, alpaca_order)
        await self.db.commit()
        await self.db.refresh(order)

        # Record sync metric
        duration = time.perf_counter() - start_time
        ORDER_SYNC_DURATION.observe(duration)
        if just_filled:
            ORDERS_SYNCED_TOTAL.labels(status_change="filled").inc()
        elif order.status == "cancelled" and old_status != "cancelled":
            ORDERS_SYNCED_TOTAL.labels(status_change="cancelled").inc()
        elif order.status == "partial" and old_status != "partial":
            ORDERS_SYNCED_TOTAL.labels(status_change="partial").inc()
        else:
            ORDERS_SYNCED_TOTAL.labels(status_change="no_change").inc()

        # Handle fill events
        if just_filled:
            filled_price = float(order.filled_avg_price or 0)
            if order.parent_order_id:
                # Bracket order filled - cancel sibling (OCO) and send alert
                await self._handle_bracket_fill(order)
            else:
                # Parent order filled - send alert and submit bracket orders
                if self.alerts:
                    await self.alerts.on_order_filled(
                        tenant_id=order.tenant_id,
                        session_id=order.session_id,
                        order=self._to_response(order),
                    )
                await self._handle_order_fill(order, filled_price)

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
        orders_to_handle_fill: list[tuple[Order, float]] = []
        bracket_orders_filled: list[Order] = []

        for order in orders:
            if order.alpaca_order_id:
                alpaca_order = await self.alpaca.get_order(order.alpaca_order_id)
                if alpaca_order:
                    old_status = order.status
                    just_filled = self._update_from_alpaca(order, alpaca_order)
                    if just_filled:
                        updated += 1
                        filled_price = float(order.filled_avg_price or 0)
                        if order.parent_order_id:
                            # This is a bracket order that filled
                            bracket_orders_filled.append(order)
                        else:
                            # This is a parent order that filled
                            orders_to_handle_fill.append((order, filled_price))
                    elif order.status != old_status:
                        # Status changed but not to filled
                        updated += 1

        await self.db.commit()

        # Handle parent order fills - send alert and submit bracket orders
        for order, filled_price in orders_to_handle_fill:
            if self.alerts:
                await self.alerts.on_order_filled(
                    tenant_id=order.tenant_id,
                    session_id=order.session_id,
                    order=self._to_response(order),
                )
            await self._handle_order_fill(order, filled_price)

        # Handle bracket order fills - cancel sibling (OCO behavior) with alerts
        for bracket_order in bracket_orders_filled:
            await self._handle_bracket_fill(bracket_order)

        return updated

    # ===================
    # Bracket order methods
    # ===================

    async def _submit_bracket_orders(
        self,
        tenant_id: UUID,
        session_id: UUID,
        parent_order: Order,
        filled_price: float,
    ) -> tuple[Order | None, Order | None]:
        """Submit stop-loss and take-profit orders after main order fills.

        Args:
            tenant_id: Tenant ID for order
            session_id: Trading session ID
            parent_order: The filled parent order
            filled_price: The filled average price of the parent order

        Returns:
            Tuple of (stop_loss_order, take_profit_order), either can be None
        """
        sl_order: Order | None = None
        tp_order: Order | None = None

        # Determine exit side (opposite of entry)
        exit_side = OrderSide.SELL if parent_order.side == "buy" else OrderSide.BUY

        # Get bracket TIF from metadata, default to GTC
        bracket_tif = TimeInForce.GTC
        if parent_order.metadata_ and "bracket_tif" in parent_order.metadata_:
            bracket_tif = TimeInForce(parent_order.metadata_["bracket_tif"])

        # Submit stop-loss order if configured
        if parent_order.stop_loss_price:
            sl_order = await self._create_bracket_order(
                tenant_id=tenant_id,
                session_id=session_id,
                parent_order=parent_order,
                bracket_type=BracketType.STOP_LOSS,
                exit_side=exit_side,
                trigger_price=float(parent_order.stop_loss_price),
                time_in_force=bracket_tif,
            )
            record_bracket_order_submitted("stop_loss")

        # Submit take-profit order if configured
        if parent_order.take_profit_price:
            tp_order = await self._create_bracket_order(
                tenant_id=tenant_id,
                session_id=session_id,
                parent_order=parent_order,
                bracket_type=BracketType.TAKE_PROFIT,
                exit_side=exit_side,
                trigger_price=float(parent_order.take_profit_price),
                time_in_force=bracket_tif,
            )
            record_bracket_order_submitted("take_profit")

        await self.db.commit()
        return sl_order, tp_order

    async def _create_bracket_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        parent_order: Order,
        bracket_type: BracketType,
        exit_side: OrderSide,
        trigger_price: float,
        time_in_force: TimeInForce,
    ) -> Order:
        """Create and submit a single bracket order (SL or TP).

        For stop-loss: Uses stop-limit order to avoid slippage
        For take-profit: Uses limit order
        """
        client_order_id = str(uuid4())
        now = datetime.now(UTC)

        # Determine order type and prices
        if bracket_type == BracketType.STOP_LOSS:
            # Use stop-limit for SL to control slippage
            # Set limit slightly worse than stop to ensure fill
            slippage_buffer = 0.001  # 0.1% slippage allowance
            if exit_side == OrderSide.SELL:
                limit_price = trigger_price * (1 - slippage_buffer)
            else:
                limit_price = trigger_price * (1 + slippage_buffer)

            order_type = OrderType.STOP_LIMIT
            stop_price = Decimal(str(trigger_price))
            limit_price_decimal = Decimal(str(round(limit_price, 2)))
        else:
            # Use limit order for TP
            order_type = OrderType.LIMIT
            stop_price = None
            limit_price_decimal = Decimal(str(trigger_price))

        # Create bracket order record
        db_order = Order(
            tenant_id=tenant_id,
            session_id=session_id,
            client_order_id=client_order_id,
            symbol=parent_order.symbol,
            side=exit_side.value,
            order_type=order_type.value,
            time_in_force=time_in_force.value,
            qty=parent_order.qty,
            limit_price=limit_price_decimal,
            stop_price=stop_price,
            status="pending",
            filled_qty=Decimal("0"),
            parent_order_id=parent_order.id,
            bracket_type=bracket_type.value,
        )
        self.db.add(db_order)
        await self.db.commit()
        await self.db.refresh(db_order)

        # Submit to Alpaca
        try:
            alpaca_order = await self.alpaca.submit_order(
                symbol=parent_order.symbol,
                qty=float(parent_order.qty),
                side=exit_side.value,
                order_type=order_type.value,
                time_in_force=time_in_force.value,
                limit_price=float(limit_price_decimal),
                stop_price=float(stop_price) if stop_price else None,
            )

            db_order.alpaca_order_id = alpaca_order.get("id")
            db_order.status = self._map_alpaca_status(alpaca_order.get("status", "new"))
            db_order.submitted_at = now
            await self.db.commit()
            await self.db.refresh(db_order)

        except Exception as e:
            db_order.status = "rejected"
            db_order.failed_at = now
            db_order.metadata_ = {"error": str(e)}
            await self.db.commit()
            # Don't raise - bracket order failure shouldn't fail the main order
            # Log would go here in production

        return db_order

    async def _handle_order_fill(
        self,
        order: Order,
        filled_price: float,
    ) -> None:
        """Called when order fills - submits bracket orders if configured."""
        # Only submit brackets for parent orders (not bracket orders themselves)
        if order.parent_order_id:
            return

        # Check if this order has bracket configuration
        if not order.stop_loss_price and not order.take_profit_price:
            return

        # Submit the bracket orders
        await self._submit_bracket_orders(
            tenant_id=order.tenant_id,
            session_id=order.session_id,
            parent_order=order,
            filled_price=filled_price,
        )

    async def _handle_bracket_fill(
        self,
        filled_bracket: Order,
    ) -> None:
        """Handle OCO behavior when a bracket order fills.

        When stop-loss fills, cancel take-profit and vice versa.
        Also sends alert for stop-loss/take-profit hit.
        """
        if not filled_bracket.parent_order_id:
            return

        # Record bracket order triggered metric
        if filled_bracket.bracket_type == BracketType.STOP_LOSS.value:
            record_bracket_order_triggered("stop_loss")
        elif filled_bracket.bracket_type == BracketType.TAKE_PROFIT.value:
            record_bracket_order_triggered("take_profit")

        # Send alert for bracket fill
        if self.alerts:
            filled_price = float(filled_bracket.filled_avg_price or 0)
            qty = float(filled_bracket.qty)

            if filled_bracket.bracket_type == BracketType.STOP_LOSS.value:
                await self.alerts.on_stop_loss_hit(
                    tenant_id=filled_bracket.tenant_id,
                    session_id=filled_bracket.session_id,
                    symbol=filled_bracket.symbol,
                    qty=qty,
                    stop_price=float(filled_bracket.stop_price or 0),
                    filled_price=filled_price,
                )
            elif filled_bracket.bracket_type == BracketType.TAKE_PROFIT.value:
                await self.alerts.on_take_profit_hit(
                    tenant_id=filled_bracket.tenant_id,
                    session_id=filled_bracket.session_id,
                    symbol=filled_bracket.symbol,
                    qty=qty,
                    target_price=float(filled_bracket.limit_price or 0),
                    filled_price=filled_price,
                )

        # Get sibling bracket orders
        stmt = (
            select(Order)
            .where(Order.parent_order_id == filled_bracket.parent_order_id)
            .where(Order.id != filled_bracket.id)
            .where(Order.status.in_(["pending", "submitted", "accepted", "partial"]))
        )
        result = await self.db.execute(stmt)
        siblings = result.scalars().all()

        # Cancel sibling bracket orders (OCO behavior)
        for sibling in siblings:
            if sibling.alpaca_order_id:
                await self.alpaca.cancel_order(sibling.alpaca_order_id)
            sibling.status = "cancelled"
            sibling.canceled_at = datetime.now(UTC)
            sibling.metadata_ = sibling.metadata_ or {}
            sibling.metadata_["cancelled_reason"] = "oco_triggered"

        await self.db.commit()

    async def cancel_bracket_orders(
        self,
        parent_order_id: UUID,
        tenant_id: UUID,
    ) -> int:
        """Cancel all bracket orders for a parent order.

        Args:
            parent_order_id: ID of the parent order
            tenant_id: Tenant ID for isolation

        Returns:
            Count of orders cancelled
        """
        stmt = (
            select(Order)
            .where(Order.parent_order_id == parent_order_id)
            .where(Order.tenant_id == tenant_id)
            .where(Order.status.in_(["pending", "submitted", "accepted", "partial"]))
        )
        result = await self.db.execute(stmt)
        bracket_orders = result.scalars().all()

        cancelled_count = 0
        now = datetime.now(UTC)

        for bracket_order in bracket_orders:
            if bracket_order.alpaca_order_id:
                await self.alpaca.cancel_order(bracket_order.alpaca_order_id)
            bracket_order.status = "cancelled"
            bracket_order.canceled_at = now
            cancelled_count += 1

        await self.db.commit()
        return cancelled_count

    async def _get_bracket_orders(
        self,
        parent_order_id: UUID,
    ) -> tuple[Order | None, Order | None]:
        """Get bracket orders for a parent order.

        Returns:
            Tuple of (stop_loss_order, take_profit_order)
        """
        stmt = select(Order).where(Order.parent_order_id == parent_order_id)
        result = await self.db.execute(stmt)
        bracket_orders = result.scalars().all()

        sl_order: Order | None = None
        tp_order: Order | None = None

        for order in bracket_orders:
            if order.bracket_type == BracketType.STOP_LOSS.value:
                sl_order = order
            elif order.bracket_type == BracketType.TAKE_PROFIT.value:
                tp_order = order

        return sl_order, tp_order

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

    def _update_from_alpaca(self, order: Order, alpaca_order: AlpacaOrderResponse) -> bool:
        """Update order from Alpaca response.

        Returns:
            True if the order transitioned to filled status
        """
        old_status = order.status
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

        # Return True if order just became filled
        return str(old_status) != "filled" and str(order.status) == "filled"

    def _to_response(self, o: Order, bracket_info: BracketOrderInfo | None = None) -> OrderResponse:
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
            # Bracket order fields
            parent_order_id=o.parent_order_id,
            bracket_type=BracketType(o.bracket_type) if o.bracket_type else None,
            stop_loss_price=float(o.stop_loss_price) if o.stop_loss_price else None,
            take_profit_price=float(o.take_profit_price) if o.take_profit_price else None,
            bracket_orders=bracket_info,
        )


async def get_order_executor(
    db: AsyncSession = Depends(get_db),
    alpaca: AlpacaTradingClient = Depends(get_alpaca_trading_client),
    risk_manager: RiskManager = Depends(get_risk_manager),
    alert_service: AlertService = Depends(get_alert_service),
) -> OrderExecutor:
    """Dependency to get order executor."""
    return OrderExecutor(
        db=db,
        alpaca_client=alpaca,
        risk_manager=risk_manager,
        alert_service=alert_service,
    )
