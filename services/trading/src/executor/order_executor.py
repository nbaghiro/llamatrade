"""Order executor - handles order submission and lifecycle with database persistence."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_alpaca import AlpacaError, OrderNotFoundError, TradingClient, get_trading_client
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_db import get_db
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_STOP_LIMIT,
    TIME_IN_FORCE_GTC,
)

from src.executor.base import OrderSubmissionMixin
from src.metrics import (
    ORDER_SYNC_DURATION,
    ORDERS_SYNCED_TOTAL,
    record_bracket_oco_conflict,
    record_bracket_order_submitted,
    record_bracket_order_triggered,
)
from src.models import (
    BracketOrderInfo,
    BracketType,
    OrderCreate,
    OrderResponse,
    order_side_to_str,
    order_type_to_str,
    time_in_force_to_str,
)
from src.risk.risk_manager import RiskManager, get_risk_manager
from src.services.alert_service import AlertService, get_alert_service
from src.streaming import TradingEventPublisher, get_trading_event_publisher

logger = logging.getLogger(__name__)


class OrderExecutor(OrderSubmissionMixin):
    """Handles order submission, risk checks, and order lifecycle."""

    def __init__(
        self,
        db: AsyncSession,
        alpaca_client: TradingClient,
        risk_manager: RiskManager,
        alert_service: AlertService | None = None,
        event_publisher: TradingEventPublisher | None = None,
    ):
        self.db = db
        self.alpaca = alpaca_client
        self.risk = risk_manager
        self.alerts = alert_service
        self.publisher = event_publisher

    async def submit_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
    ) -> OrderResponse:
        """Submit an order after risk checks."""
        start_time = time.perf_counter()

        # Run risk checks (using mixin method)
        risk_result = await self._run_risk_check(
            tenant_id=tenant_id,
            order=order,
            session_id=session_id,
        )

        if not risk_result.passed:
            # Handle rejection with metrics and alerts (using mixin method)
            await self._handle_risk_rejection(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
                violations=risk_result.violations,
                start_time=start_time,
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
            side=order.side,  # Already int from Pydantic model
            order_type=order.order_type,  # Already int from Pydantic model
            time_in_force=order.time_in_force,  # Already int from Pydantic model
            qty=Decimal(str(order.qty)),
            limit_price=Decimal(str(order.limit_price)) if order.limit_price else None,
            stop_price=Decimal(str(order.stop_price)) if order.stop_price else None,
            status=ORDER_STATUS_PENDING,  # Use proto constant (int)
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
            db_order.metadata_ = {"bracket_tif": order.bracket_time_in_force}
        self.db.add(db_order)
        await self.db.commit()
        await self.db.refresh(db_order)

        # Submit to Alpaca (using mixin method)
        try:
            result = await self._submit_to_alpaca(order=order)

            # Update order with Alpaca response
            db_order.alpaca_order_id = result.alpaca_order_id
            db_order.status = self._map_alpaca_status(result.status)
            db_order.submitted_at = now
            await self.db.commit()
            await self.db.refresh(db_order)

            # Record success metric (using mixin method)
            self._record_submission_success(order=order, start_time=start_time)

            # Publish order submitted event
            if self.publisher:
                await self.publisher.publish_order_submitted(
                    session_id=session_id,
                    order_id=db_order.id,
                    alpaca_order_id=result.alpaca_order_id,
                    symbol=order.symbol,
                    side=order_side_to_str(order.side),
                    qty=order.qty,
                    order_type=order_type_to_str(order.order_type),
                )

        except Exception as e:
            # Handle API rejection with metrics and alerts (using mixin method)
            await self._handle_alpaca_rejection(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
                error=e,
                start_time=start_time,
            )
            # Mark order as failed
            db_order.status = ORDER_STATUS_REJECTED
            db_order.failed_at = now
            db_order.metadata_ = {"error": str(e)}
            await self.db.commit()
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
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OrderResponse], int]:
        """List orders for tenant.

        Args:
            status: Proto OrderStatus constant (e.g., ORDER_STATUS_FILLED = 5)
        """
        stmt = select(Order).where(Order.tenant_id == tenant_id)

        if session_id:
            stmt = stmt.where(Order.session_id == session_id)
        if status:
            stmt = stmt.where(Order.status == status)

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

        if order.status in (
            ORDER_STATUS_FILLED,
            ORDER_STATUS_CANCELLED,
            ORDER_STATUS_REJECTED,
            ORDER_STATUS_EXPIRED,
        ):
            return False

        # Cancel via Alpaca if we have an Alpaca order ID
        if order.alpaca_order_id:
            try:
                await self.alpaca.cancel_order(order.alpaca_order_id)
            except OrderNotFoundError:
                # Order doesn't exist at Alpaca - may have already been filled/cancelled
                logger.warning(f"Order {order.alpaca_order_id} not found at Alpaca during cancel")
            except AlpacaError as e:
                logger.error(f"Failed to cancel order {order.alpaca_order_id}: {e}")
                return False

        order.status = ORDER_STATUS_CANCELLED
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
        elif order.status == ORDER_STATUS_CANCELLED and old_status != ORDER_STATUS_CANCELLED:
            ORDERS_SYNCED_TOTAL.labels(status_change="cancelled").inc()
        elif order.status == ORDER_STATUS_PARTIAL and old_status != ORDER_STATUS_PARTIAL:
            ORDERS_SYNCED_TOTAL.labels(status_change="partial").inc()
        else:
            ORDERS_SYNCED_TOTAL.labels(status_change="no_change").inc()

        # Handle fill events
        if just_filled:
            filled_price = float(order.filled_avg_price or 0)

            # Publish order filled event
            if self.publisher:
                await self.publisher.publish_order_filled(
                    session_id=order.session_id,
                    order_id=order.id,
                    alpaca_order_id=order.alpaca_order_id,
                    symbol=order.symbol,
                    side=order_side_to_str(order.side),
                    qty=float(order.qty),
                    order_type=order_type_to_str(order.order_type),
                    filled_qty=float(order.filled_qty),
                    filled_avg_price=filled_price,
                )

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
        """Sync all pending orders for a session. Returns count of updated orders.

        Uses asyncio.gather() to fetch all Alpaca orders in parallel for better
        performance when syncing many orders.
        """
        stmt = (
            select(Order)
            .where(Order.tenant_id == tenant_id)
            .where(Order.session_id == session_id)
            .where(
                Order.status.in_(
                    [
                        ORDER_STATUS_PENDING,
                        ORDER_STATUS_SUBMITTED,
                        ORDER_STATUS_ACCEPTED,
                        ORDER_STATUS_PARTIAL,
                    ]
                )
            )
            .where(Order.alpaca_order_id.isnot(None))
        )

        result = await self.db.execute(stmt)
        orders = list(result.scalars().all())

        if not orders:
            return 0

        updated = 0
        orders_to_handle_fill: list[tuple[Order, float]] = []
        bracket_orders_filled: list[Order] = []

        # Fetch all Alpaca orders in parallel
        # Filter to only orders with alpaca_order_id (should all have it due to query)
        orders_with_ids = [
            (order, order.alpaca_order_id) for order in orders if order.alpaca_order_id
        ]

        if not orders_with_ids:
            return 0

        # Create tasks for parallel fetch
        tasks = [self.alpaca.get_order(alpaca_id) for _, alpaca_id in orders_with_ids]

        # Fetch all in parallel, capturing exceptions per-order
        alpaca_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for (order, _), alpaca_order in zip(orders_with_ids, alpaca_results, strict=False):
            # Skip if fetch failed (exception returned)
            if isinstance(alpaca_order, BaseException):
                continue
            if not alpaca_order:
                continue

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
        """Submit stop-loss and take-profit orders atomically after main order fills.

        If either bracket order fails to submit to Alpaca, both are rolled back.
        The main order still proceeds - we alert the user to set manual stop-loss.

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
        exit_side = ORDER_SIDE_SELL if parent_order.side == ORDER_SIDE_BUY else ORDER_SIDE_BUY

        # Get bracket TIF from metadata, default to GTC
        bracket_tif = TIME_IN_FORCE_GTC
        metadata = parent_order.metadata_
        if metadata and "bracket_tif" in metadata:
            bracket_tif = int(metadata["bracket_tif"])  # Proto enum value

        # Track successfully submitted Alpaca order IDs for rollback
        submitted_alpaca_ids: list[str] = []

        try:
            # Phase 1: Create both orders in DB first (no Alpaca submission yet)
            if parent_order.stop_loss_price:
                sl_order = await self._create_bracket_order_in_db(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    parent_order=parent_order,
                    bracket_type=BracketType.STOP_LOSS,
                    exit_side=exit_side,
                    trigger_price=float(parent_order.stop_loss_price),
                    time_in_force=bracket_tif,
                )

            if parent_order.take_profit_price:
                tp_order = await self._create_bracket_order_in_db(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    parent_order=parent_order,
                    bracket_type=BracketType.TAKE_PROFIT,
                    exit_side=exit_side,
                    trigger_price=float(parent_order.take_profit_price),
                    time_in_force=bracket_tif,
                )

            await self.db.commit()

            # Phase 2: Submit to Alpaca - if any fails, rollback all
            if sl_order:
                sl_alpaca_id = await self._submit_bracket_to_alpaca(sl_order)
                if sl_alpaca_id:
                    submitted_alpaca_ids.append(sl_alpaca_id)
                record_bracket_order_submitted("stop_loss")

            if tp_order:
                tp_alpaca_id = await self._submit_bracket_to_alpaca(tp_order)
                if tp_alpaca_id:
                    submitted_alpaca_ids.append(tp_alpaca_id)
                record_bracket_order_submitted("take_profit")

            await self.db.commit()
            return sl_order, tp_order

        except Exception as e:
            # Rollback: cancel any orders that were submitted to Alpaca
            await self._rollback_bracket_orders(submitted_alpaca_ids)

            # Mark DB orders as failed
            now = datetime.now(UTC)
            if sl_order:
                sl_order.status = ORDER_STATUS_REJECTED
                sl_order.failed_at = now
                sl_order.metadata_ = {"error": str(e), "rollback": True}
            if tp_order:
                tp_order.status = ORDER_STATUS_REJECTED
                tp_order.failed_at = now
                tp_order.metadata_ = {"error": str(e), "rollback": True}

            await self.db.commit()

            # Alert user - bracket orders failed (but main order still proceeded)
            import logging

            logging.getLogger(__name__).error(
                f"Bracket orders failed for {parent_order.symbol}: {e}"
            )
            if self.alerts:
                await self.alerts.on_strategy_error(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    error=f"CRITICAL: Bracket orders failed for {parent_order.symbol}. "
                    f"Position may be unprotected. Please set manual stop-loss. Error: {e}",
                )

            # Return None for failed brackets - main order still proceeds
            return None, None

    async def _create_bracket_order_in_db(
        self,
        tenant_id: UUID,
        session_id: UUID,
        parent_order: Order,
        bracket_type: BracketType,
        exit_side: int,
        trigger_price: float,
        time_in_force: int,
    ) -> Order:
        """Create a bracket order record in DB without submitting to Alpaca.

        This is phase 1 of atomic bracket submission.
        """
        client_order_id = str(uuid4())

        # Determine order type and prices
        if bracket_type == BracketType.STOP_LOSS:
            # Use stop-limit for SL to control slippage
            slippage_buffer = 0.001  # 0.1% slippage allowance
            if exit_side == ORDER_SIDE_SELL:
                limit_price = trigger_price * (1 - slippage_buffer)
            else:
                limit_price = trigger_price * (1 + slippage_buffer)

            db_order_type = ORDER_TYPE_STOP_LIMIT
            stop_price = Decimal(str(trigger_price))
            limit_price_decimal = Decimal(str(round(limit_price, 2)))
        else:
            # Use limit order for TP
            db_order_type = ORDER_TYPE_LIMIT
            stop_price = None
            limit_price_decimal = Decimal(str(trigger_price))

        # Create bracket order record in pending state
        db_order = Order(
            tenant_id=tenant_id,
            session_id=session_id,
            client_order_id=client_order_id,
            symbol=parent_order.symbol,
            side=exit_side,
            order_type=db_order_type,
            time_in_force=time_in_force,
            qty=parent_order.qty,
            limit_price=limit_price_decimal,
            stop_price=stop_price,
            status=ORDER_STATUS_PENDING,
            filled_qty=Decimal("0"),
            parent_order_id=parent_order.id,
            bracket_type=bracket_type,  # BracketType is IntEnum, no conversion needed
        )
        self.db.add(db_order)
        await self.db.flush()
        await self.db.refresh(db_order)

        return db_order

    async def _submit_bracket_to_alpaca(self, order: Order) -> str | None:
        """Submit a bracket order to Alpaca and update DB record.

        This is phase 2 of atomic bracket submission.

        Returns:
            Alpaca order ID if successful, None otherwise

        Raises:
            Exception: If Alpaca submission fails (triggers rollback)
        """
        now = datetime.now(UTC)

        alpaca_order = await self.alpaca.submit_order(
            symbol=order.symbol,
            qty=float(order.qty),
            side=order_side_to_str(order.side),
            order_type=order_type_to_str(order.order_type),
            time_in_force=time_in_force_to_str(order.time_in_force),
            limit_price=float(order.limit_price) if order.limit_price else None,
            stop_price=float(order.stop_price) if order.stop_price else None,
        )

        order.alpaca_order_id = alpaca_order.id
        order.status = self._map_alpaca_status(alpaca_order.status.value)
        order.submitted_at = now

        return alpaca_order.id

    async def _rollback_bracket_orders(self, alpaca_order_ids: list[str]) -> None:
        """Cancel bracket orders that were submitted to Alpaca.

        Called when bracket order submission partially fails.
        """
        for order_id in alpaca_order_ids:
            try:
                await self.alpaca.cancel_order(order_id)
                logger.info(f"Rolled back bracket order: {order_id}")
            except Exception as e:
                # Log but don't raise - we're already in error handling
                logger.error(f"Failed to rollback bracket order {order_id}: {e}")

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

        Race condition handling:
        - Uses SELECT FOR UPDATE to acquire exclusive lock on sibling orders
        - Checks if sibling already filled (both orders filled simultaneously)
        - Idempotent: safe to call multiple times for same fill
        """
        if not filled_bracket.parent_order_id:
            return

        # Record bracket order triggered metric
        if filled_bracket.bracket_type == BracketType.STOP_LOSS:
            record_bracket_order_triggered("stop_loss")
        elif filled_bracket.bracket_type == BracketType.TAKE_PROFIT:
            record_bracket_order_triggered("take_profit")

        # Send alert for bracket fill
        if self.alerts:
            filled_price = float(filled_bracket.filled_avg_price or 0)
            qty = float(filled_bracket.qty)

            if filled_bracket.bracket_type == BracketType.STOP_LOSS:
                await self.alerts.on_stop_loss_hit(
                    tenant_id=filled_bracket.tenant_id,
                    session_id=filled_bracket.session_id,
                    symbol=filled_bracket.symbol,
                    qty=qty,
                    stop_price=float(filled_bracket.stop_price or 0),
                    filled_price=filled_price,
                )
            elif filled_bracket.bracket_type == BracketType.TAKE_PROFIT:
                await self.alerts.on_take_profit_hit(
                    tenant_id=filled_bracket.tenant_id,
                    session_id=filled_bracket.session_id,
                    symbol=filled_bracket.symbol,
                    qty=qty,
                    target_price=float(filled_bracket.limit_price or 0),
                    filled_price=filled_price,
                )

        # Acquire exclusive lock on sibling orders to prevent race conditions
        # This prevents concurrent _handle_bracket_fill calls from conflicting
        stmt = (
            select(Order)
            .where(Order.parent_order_id == filled_bracket.parent_order_id)
            .where(Order.id != filled_bracket.id)
            .with_for_update()  # Exclusive lock - blocks concurrent access
        )
        result = await self.db.execute(stmt)
        siblings = result.scalars().all()

        # Process each sibling order
        now = datetime.now(UTC)
        for sibling in siblings:
            # Check if sibling already filled (both bracket orders hit simultaneously)
            if sibling.status == ORDER_STATUS_FILLED:
                logger.warning(
                    f"OCO conflict: both bracket orders filled for parent "
                    f"{filled_bracket.parent_order_id}. This order: {filled_bracket.id}, "
                    f"sibling: {sibling.id}. Both fills are valid."
                )
                record_bracket_oco_conflict("both_filled")
                continue

            # Check if sibling already cancelled (idempotent handling)
            if sibling.status == ORDER_STATUS_CANCELLED:
                logger.debug(f"Sibling bracket {sibling.id} already cancelled, skipping")
                record_bracket_oco_conflict("cancelled_already")
                continue

            # Only cancel if sibling is still in cancellable state
            if sibling.status not in (
                ORDER_STATUS_PENDING,
                ORDER_STATUS_SUBMITTED,
                ORDER_STATUS_ACCEPTED,
                ORDER_STATUS_PARTIAL,
            ):
                logger.debug(
                    f"Sibling bracket {sibling.id} in non-cancellable state "
                    f"{sibling.status}, skipping"
                )
                continue

            # Cancel via Alpaca if we have an order ID
            if sibling.alpaca_order_id:
                try:
                    await self.alpaca.cancel_order(sibling.alpaca_order_id)
                except OrderNotFoundError:
                    # Order no longer exists at Alpaca - sync status from broker
                    logger.info(
                        f"Sibling bracket {sibling.alpaca_order_id} not found at "
                        f"Alpaca during OCO cancel, syncing status"
                    )
                    # Let the sync_order_status handle updating the correct status
                    await self._sync_single_order_status(sibling)
                    continue
                except AlpacaError as e:
                    logger.warning(
                        f"Failed to cancel sibling bracket {sibling.alpaca_order_id}: {e}"
                    )
                    # Continue anyway - mark as cancelled locally
                    # The periodic sync will correct if needed

            # Update local state
            sibling.status = ORDER_STATUS_CANCELLED
            sibling.canceled_at = now
            sibling_metadata = sibling.metadata_
            if sibling_metadata is None:
                sibling_metadata = {}
            sibling_metadata["cancelled_reason"] = "oco_triggered"
            sibling_metadata["cancelled_by_order"] = str(filled_bracket.id)
            sibling.metadata_ = sibling_metadata

        await self.db.commit()

    async def _sync_single_order_status(self, order: Order) -> None:
        """Sync a single order's status from Alpaca.

        Used during OCO handling when we discover an order no longer exists.
        """
        if not order.alpaca_order_id:
            return

        try:
            alpaca_order = await self.alpaca.get_order(order.alpaca_order_id)
            if alpaca_order:
                new_status = self._map_alpaca_status(alpaca_order.status.value)
                if new_status != order.status:
                    logger.info(
                        f"Synced order {order.id} status from {order.status} "
                        f"to {new_status} during OCO handling"
                    )
                    order.status = new_status
                    if new_status == ORDER_STATUS_FILLED:
                        order.filled_qty = Decimal(str(alpaca_order.filled_qty))
                        if alpaca_order.filled_avg_price:
                            order.filled_avg_price = Decimal(str(alpaca_order.filled_avg_price))
                        if alpaca_order.filled_at:
                            order.filled_at = alpaca_order.filled_at
        except Exception as e:
            logger.warning(f"Failed to sync order {order.id} during OCO: {e}")

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
            .where(
                Order.status.in_(
                    [
                        ORDER_STATUS_PENDING,
                        ORDER_STATUS_SUBMITTED,
                        ORDER_STATUS_ACCEPTED,
                        ORDER_STATUS_PARTIAL,
                    ]
                )
            )
        )
        result = await self.db.execute(stmt)
        bracket_orders = result.scalars().all()

        cancelled_count = 0
        now = datetime.now(UTC)

        for bracket_order in bracket_orders:
            if bracket_order.alpaca_order_id:
                try:
                    await self.alpaca.cancel_order(bracket_order.alpaca_order_id)
                except OrderNotFoundError:
                    logger.info(
                        f"Bracket order {bracket_order.alpaca_order_id} not found at Alpaca"
                    )
                except AlpacaError as e:
                    logger.warning(
                        f"Failed to cancel bracket order {bracket_order.alpaca_order_id}: {e}"
                    )
            bracket_order.status = ORDER_STATUS_CANCELLED
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
            if order.bracket_type == BracketType.STOP_LOSS:
                sl_order = order
            elif order.bracket_type == BracketType.TAKE_PROFIT:
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

    # Note: _map_alpaca_status is now inherited from OrderSubmissionMixin

    def _update_from_alpaca(self, order: Order, alpaca_order: AlpacaOrder) -> bool:
        """Update order from Alpaca response.

        Returns:
            True if the order transitioned to filled status
        """
        old_status = order.status
        order.status = self._map_alpaca_status(alpaca_order.status.value)

        if alpaca_order.filled_qty:
            order.filled_qty = Decimal(str(alpaca_order.filled_qty))

        if alpaca_order.filled_avg_price:
            order.filled_avg_price = Decimal(str(alpaca_order.filled_avg_price))

        if alpaca_order.filled_at:
            order.filled_at = alpaca_order.filled_at

        # Return True if order just became filled
        return old_status != ORDER_STATUS_FILLED and order.status == ORDER_STATUS_FILLED

    def _to_response(self, o: Order, bracket_info: BracketOrderInfo | None = None) -> OrderResponse:
        """Convert order to response."""
        return OrderResponse(
            id=o.id,
            client_order_id=o.client_order_id,
            alpaca_order_id=o.alpaca_order_id,
            symbol=o.symbol,
            side=o.side,  # Already int (proto enum value)
            qty=float(o.qty),
            order_type=o.order_type,  # Already int (proto enum value)
            limit_price=float(o.limit_price) if o.limit_price else None,
            stop_price=float(o.stop_price) if o.stop_price else None,
            status=o.status,  # Already int (proto enum value)
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
    alpaca: TradingClient = Depends(get_trading_client),
    risk_manager: RiskManager = Depends(get_risk_manager),
    alert_service: AlertService = Depends(get_alert_service),
) -> OrderExecutor:
    """Dependency to get order executor."""
    return OrderExecutor(
        db=db,
        alpaca_client=alpaca,
        risk_manager=risk_manager,
        alert_service=alert_service,
        event_publisher=get_trading_event_publisher(),
    )


async def create_order_executor() -> OrderExecutor:
    """Create order executor without dependency injection.

    Used by gRPC servicer where FastAPI DI is not available.
    """
    from llamatrade_alpaca import get_trading_client
    from llamatrade_db import get_db

    from src.risk.risk_manager import get_risk_manager

    db = await anext(get_db())
    alpaca = get_trading_client()
    risk_manager = get_risk_manager()

    return OrderExecutor(
        db=db,
        alpaca_client=alpaca,
        risk_manager=risk_manager,
        alert_service=None,  # Alert service requires async init, optional for gRPC
        event_publisher=get_trading_event_publisher(),
    )
