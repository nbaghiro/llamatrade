"""Event-sourced order executor with idempotent, durable order submission.

This executor uses event sourcing to ensure:
1. Idempotent order submission (same signal = same order, even after crash)
2. Durable state (replay events to recover state)
3. Full audit trail (every action is recorded as an event)
"""

import hashlib
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from llamatrade_alpaca import AlpacaError, OrderNotFoundError, TradingClient
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_FILLED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_STOP_LIMIT,
    TIME_IN_FORCE_GTC,
    OrderSide,
    TimeInForce,
)

from src.events.aggregates import SessionState
from src.events.store import EventStore
from src.events.trading_events import (
    BracketOrderAccepted,
    BracketOrderCancelled,
    BracketOrderCreated,
    BracketOrderTriggered,
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    PositionClosed,
    PositionIncreased,
    PositionOpened,
    PositionReduced,
    SignalGenerated,
    SignalRejected,
)
from src.executor.base import OrderSubmissionMixin
from src.metrics import (
    record_bracket_oco_conflict,
    record_bracket_order_submitted,
    record_bracket_order_triggered,
)
from src.models import (
    BracketType,
    OrderCreate,
    bracket_type_to_str,
    order_side_to_str,
    order_type_to_str,
    time_in_force_to_str,
)
from src.risk.risk_manager import RiskManager
from src.services.alert_service import AlertService
from src.streaming import TradingEventPublisher

logger = logging.getLogger(__name__)


def generate_deterministic_order_id(
    session_id: UUID,
    symbol: str,
    side: str,
    signal_timestamp: datetime,
) -> str:
    """Generate a deterministic client_order_id for idempotency.

    The same signal will always produce the same order ID, so if we
    crash and retry, Alpaca will return the existing order.

    Format: lt-{hash[:16]}
    """
    # Create deterministic hash from signal parameters
    data = f"{session_id}:{symbol}:{side}:{signal_timestamp.isoformat()}"
    hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"lt-{hash_digest}"


class EventSourcedOrderExecutor(OrderSubmissionMixin):
    """Order executor with event sourcing for durability and auditability.

    All order operations emit events to the event store. State is derived
    by replaying events. Order submission is idempotent via deterministic
    client_order_id generation.

    Usage:
        executor = EventSourcedOrderExecutor(
            event_store=store,
            alpaca_client=alpaca,
            risk_manager=risk,
        )

        # Submit order (idempotent)
        order_id = await executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=OrderCreate(...),
            signal_timestamp=signal.timestamp,
        )

        # Get current state by replaying events
        state = await executor.get_session_state(session_id, tenant_id)
    """

    def __init__(
        self,
        event_store: EventStore,
        alpaca_client: TradingClient,
        risk_manager: RiskManager,
        alert_service: AlertService | None = None,
        event_publisher: TradingEventPublisher | None = None,
    ):
        self.events = event_store
        self.alpaca = alpaca_client
        self.risk = risk_manager
        self.alerts = alert_service
        self.publisher = event_publisher

    async def submit_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
        signal_timestamp: datetime | None = None,
    ) -> UUID:
        """Submit an order with event sourcing and idempotency.

        Args:
            tenant_id: Tenant identifier.
            session_id: Trading session identifier.
            order: Order to submit.
            signal_timestamp: Timestamp of the signal that generated this order.
                Used for deterministic client_order_id generation.

        Returns:
            Order ID.

        Raises:
            ValueError: If risk check fails or order submission fails.
        """
        start_time = time.perf_counter()
        order_id = uuid4()
        now = signal_timestamp or datetime.now(UTC)

        # Generate deterministic client_order_id for idempotency
        client_order_id = generate_deterministic_order_id(
            session_id=session_id,
            symbol=order.symbol,
            side=order_side_to_str(order.side),
            signal_timestamp=now,
        )

        # 1. Check if we already have an order with this client_order_id
        #    (crash recovery - we may have submitted but crashed before recording)
        existing_order = await self.alpaca.get_order_by_client_id(client_order_id)
        if existing_order:
            logger.info(
                f"Found existing order for client_order_id={client_order_id}",
                extra={"alpaca_order_id": existing_order.id},
            )
            # Emit events we may have missed
            await self._emit_events_from_alpaca_order(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                client_order_id=client_order_id,
                order=order,
                alpaca_order=existing_order,
            )
            return order_id

        # 2. Run risk checks (using mixin method)
        risk_result = await self._run_risk_check(
            tenant_id=tenant_id,
            order=order,
            session_id=session_id,
        )

        if not risk_result.passed:
            # Emit SignalRejected event (event-sourced specific)
            await self.events.append(
                SignalRejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=order.symbol,
                    signal_type=order_side_to_str(order.side),
                    reason="risk_check_failed",
                    details={"violations": risk_result.violations},
                )
            )

            # Handle rejection with metrics and alerts (using mixin method)
            await self._handle_risk_rejection(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
                violations=risk_result.violations,
                start_time=start_time,
            )
            raise ValueError(f"Risk check failed: {', '.join(risk_result.violations)}")

        # 3. Emit OrderSubmitted event (our intent)
        await self.events.append(
            OrderSubmitted(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=order.symbol.upper(),
                side=order_side_to_str(order.side),
                qty=Decimal(str(order.qty)),
                order_type=order_type_to_str(order.order_type),
                time_in_force=time_in_force_to_str(order.time_in_force),
                limit_price=Decimal(str(order.limit_price)) if order.limit_price else None,
                stop_price=Decimal(str(order.stop_price)) if order.stop_price else None,
                stop_loss_price=(
                    Decimal(str(order.stop_loss_price)) if order.stop_loss_price else None
                ),
                take_profit_price=(
                    Decimal(str(order.take_profit_price)) if order.take_profit_price else None
                ),
            )
        )

        # 4. Submit to Alpaca (using mixin method, idempotent via client_order_id)
        try:
            result = await self._submit_to_alpaca(
                order=order,
                client_order_id=client_order_id,
            )

            # 5. Emit OrderAccepted event (event-sourced specific)
            await self.events.append(
                OrderAccepted(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    broker_order_id=result.alpaca_order_id,
                )
            )

            # Record success metric (using mixin method)
            self._record_submission_success(order=order, start_time=start_time)

            # Publish order submitted event
            if self.publisher:
                await self.publisher.publish_order_submitted(
                    session_id=session_id,
                    order_id=order_id,
                    alpaca_order_id=result.alpaca_order_id,
                    symbol=order.symbol,
                    side=order_side_to_str(order.side),
                    qty=order.qty,
                    order_type=order_type_to_str(order.order_type),
                )

            # Check if immediately filled (market orders)
            if result.status == "filled":
                await self._emit_fill_event(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    order=order,
                    alpaca_order=result.order,
                )

                # Publish order filled event
                if self.publisher:
                    filled_qty = float(result.order.filled_qty if result.order else 0)
                    filled_price = float(result.order.filled_avg_price or 0 if result.order else 0)
                    await self.publisher.publish_order_filled(
                        session_id=session_id,
                        order_id=order_id,
                        alpaca_order_id=result.alpaca_order_id,
                        symbol=order.symbol,
                        side=order_side_to_str(order.side),
                        qty=order.qty,
                        order_type=order_type_to_str(order.order_type),
                        filled_qty=filled_qty,
                        filled_avg_price=filled_price,
                    )

        except Exception as e:
            # Emit OrderRejected event (event-sourced specific)
            await self.events.append(
                OrderRejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    reason="broker_rejected",
                    broker_message=str(e),
                )
            )

            # Handle Alpaca rejection with metrics and alerts (using mixin method)
            await self._handle_alpaca_rejection(
                tenant_id=tenant_id,
                session_id=session_id,
                order=order,
                error=e,
                start_time=start_time,
            )
            raise ValueError(f"Failed to submit order to Alpaca: {e}")

        return order_id

    async def record_signal(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        signal_type: OrderSide.ValueType,
        price: Decimal,
        qty: Decimal,
        confidence: float = 1.0,
        indicators: dict[str, Any] | None = None,
    ) -> None:
        """Record a signal event for audit trail.

        Call this before submit_order to record the signal that
        generated the order.
        """
        await self.events.append(
            SignalGenerated(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
                signal_type=order_side_to_str(signal_type),
                price=price,
                qty=qty,
                confidence=confidence,
                indicators=indicators or {},
            )
        )

    async def sync_order_with_broker(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order_id: UUID,
        client_order_id: str,
        broker_order_id: str,
        order: OrderCreate,
    ) -> bool:
        """Sync order status with broker and emit events for any changes.

        Returns True if order is now filled.
        """
        alpaca_order = await self.alpaca.get_order(broker_order_id)
        if not alpaca_order:
            return False

        status = alpaca_order.status.value.lower()

        if status == "filled":
            await self._emit_fill_event(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                order=order,
                alpaca_order=alpaca_order,
            )
            return True

        elif status in ("canceled", "cancelled"):
            await self.events.append(
                OrderCancelled(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    reason="broker_cancelled",
                    filled_qty=Decimal(str(alpaca_order.filled_qty)),
                )
            )

        return False

    async def record_position_opened(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: Literal["long", "short"],
        qty: Decimal,
        entry_price: Decimal,
        order_id: UUID | None,
    ) -> None:
        """Record that a position was opened."""
        await self.events.append(
            PositionOpened(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=entry_price,
                order_id=order_id,
            )
        )

    async def record_position_increased(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty_added: Decimal,
        price: Decimal,
        new_total_qty: Decimal,
        new_avg_cost: Decimal,
        order_id: UUID,
    ) -> None:
        """Record that a position was increased."""
        await self.events.append(
            PositionIncreased(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
                qty_added=qty_added,
                price=price,
                new_total_qty=new_total_qty,
                new_avg_cost=new_avg_cost,
                order_id=order_id,
            )
        )

    async def record_position_reduced(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty_removed: Decimal,
        exit_price: Decimal,
        remaining_qty: Decimal,
        realized_pnl: Decimal,
        order_id: UUID,
    ) -> None:
        """Record that a position was reduced."""
        await self.events.append(
            PositionReduced(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
                qty_removed=qty_removed,
                exit_price=exit_price,
                remaining_qty=remaining_qty,
                realized_pnl=realized_pnl,
                order_id=order_id,
            )
        )

    async def record_position_closed(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        exit_price: Decimal,
        realized_pnl: Decimal,
        order_id: UUID | None,
    ) -> None:
        """Record that a position was closed."""
        await self.events.append(
            PositionClosed(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=symbol,
                exit_price=exit_price,
                realized_pnl=realized_pnl,
                order_id=order_id,
            )
        )

    async def get_session_state(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionState:
        """Get current session state by replaying events.

        This is the primary way to query state - it's always consistent
        with the events in the store.
        """
        return await SessionState.load(
            session_id=session_id,
            tenant_id=tenant_id,
            event_store=self.events,
        )

    async def recover_from_crash(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> SessionState:
        """Recover session state after a crash.

        Replays events and checks for any orders that were submitted
        but not confirmed (we crashed between submit and record).
        """
        state = await self.get_session_state(session_id, tenant_id)

        # Find orders that were submitted but not accepted/rejected
        # (we may have crashed before recording the broker response)
        for order_id, order_state in state.orders.items():
            if order_state.status == "submitted" and not order_state.broker_order_id:
                # Check if this order exists in Alpaca
                alpaca_order = await self.alpaca.get_order_by_client_id(order_state.client_order_id)
                if alpaca_order:
                    # Order was submitted - emit the events we missed
                    await self.events.append(
                        OrderAccepted(
                            tenant_id=tenant_id,
                            session_id=session_id,
                            order_id=order_id,
                            broker_order_id=alpaca_order.id,
                        )
                    )

                    # Check if filled
                    if alpaca_order.status.value == "filled":
                        filled_qty = Decimal(str(alpaca_order.filled_qty))
                        filled_price = Decimal(str(alpaca_order.filled_avg_price or 0))
                        await self.events.append(
                            OrderFilled(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                order_id=order_id,
                                symbol=order_state.symbol,
                                side=order_state.side,
                                filled_qty=filled_qty,
                                filled_avg_price=filled_price,
                            )
                        )

        # Reload state with recovered events
        return await self.get_session_state(session_id, tenant_id)

    # ===================
    # Bracket order methods
    # ===================

    async def submit_bracket_orders(
        self,
        tenant_id: UUID,
        session_id: UUID,
        parent_order_id: UUID,
        parent_client_order_id: str,
        symbol: str,
        entry_side: OrderSide.ValueType,
        qty: Decimal,
        filled_price: Decimal,
        stop_loss_price: Decimal | None = None,
        take_profit_price: Decimal | None = None,
        bracket_time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_GTC,
    ) -> tuple[UUID | None, UUID | None]:
        """Submit bracket orders (stop-loss and/or take-profit) after main order fills.

        Args:
            tenant_id: Tenant identifier.
            session_id: Trading session identifier.
            parent_order_id: ID of the filled parent order.
            parent_client_order_id: Client order ID of parent.
            symbol: Trading symbol.
            entry_side: Side of the entry order (BUY/SELL).
            qty: Quantity to protect.
            filled_price: Price at which parent order filled.
            stop_loss_price: Stop-loss trigger price.
            take_profit_price: Take-profit limit price.
            bracket_time_in_force: Time in force for bracket orders.

        Returns:
            Tuple of (stop_loss_order_id, take_profit_order_id), either can be None.
        """
        sl_order_id: UUID | None = None
        tp_order_id: UUID | None = None

        # Exit side is opposite of entry
        exit_side = ORDER_SIDE_SELL if entry_side == ORDER_SIDE_BUY else ORDER_SIDE_BUY

        # Submit stop-loss order if configured
        if stop_loss_price:
            sl_order_id = await self._submit_bracket_order(
                tenant_id=tenant_id,
                session_id=session_id,
                parent_order_id=parent_order_id,
                parent_client_order_id=parent_client_order_id,
                bracket_type=BracketType.STOP_LOSS,
                symbol=symbol,
                exit_side=exit_side,
                qty=qty,
                trigger_price=stop_loss_price,
                time_in_force=bracket_time_in_force,
            )
            if sl_order_id:
                record_bracket_order_submitted("stop_loss")

        # Submit take-profit order if configured
        if take_profit_price:
            tp_order_id = await self._submit_bracket_order(
                tenant_id=tenant_id,
                session_id=session_id,
                parent_order_id=parent_order_id,
                parent_client_order_id=parent_client_order_id,
                bracket_type=BracketType.TAKE_PROFIT,
                symbol=symbol,
                exit_side=exit_side,
                qty=qty,
                trigger_price=take_profit_price,
                time_in_force=bracket_time_in_force,
            )
            if tp_order_id:
                record_bracket_order_submitted("take_profit")

        return sl_order_id, tp_order_id

    async def _submit_bracket_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        parent_order_id: UUID,
        parent_client_order_id: str,
        bracket_type: int,
        symbol: str,
        exit_side: OrderSide.ValueType,
        qty: Decimal,
        trigger_price: Decimal,
        time_in_force: TimeInForce.ValueType,
    ) -> UUID | None:
        """Submit a single bracket order (SL or TP).

        Returns order ID if submitted, None if submission failed.
        """
        order_id = uuid4()

        # Generate deterministic client order ID for idempotency
        client_order_id = f"{parent_client_order_id}-{bracket_type_to_str(bracket_type)}"

        # Determine order type and prices
        if bracket_type == BracketType.STOP_LOSS:
            # Use stop-limit for SL to control slippage
            # Set limit slightly worse than stop to ensure fill
            slippage_buffer = Decimal("0.001")  # 0.1% slippage allowance
            if exit_side == ORDER_SIDE_SELL:
                limit_price = trigger_price * (1 - slippage_buffer)
            else:
                limit_price = trigger_price * (1 + slippage_buffer)
            order_type = ORDER_TYPE_STOP_LIMIT
            stop_price = trigger_price
        else:
            # Use limit order for TP
            order_type = ORDER_TYPE_LIMIT
            stop_price = None
            limit_price = trigger_price

        # Emit BracketOrderCreated event
        await self.events.append(
            BracketOrderCreated(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                parent_order_id=parent_order_id,
                bracket_type=bracket_type_to_str(bracket_type),
                symbol=symbol,
                side=order_side_to_str(exit_side),
                qty=qty,
                trigger_price=trigger_price,
                limit_price=limit_price,
            )
        )

        # Submit to Alpaca
        try:
            alpaca_order = await self.alpaca.submit_order(
                symbol=symbol,
                qty=float(qty),
                side=order_side_to_str(exit_side),
                order_type=order_type_to_str(order_type),
                time_in_force=time_in_force_to_str(time_in_force),
                limit_price=float(limit_price),
                stop_price=float(stop_price) if stop_price else None,
                client_order_id=client_order_id,
            )

            broker_order_id = alpaca_order.id

            # Emit BracketOrderAccepted event
            await self.events.append(
                BracketOrderAccepted(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    parent_order_id=parent_order_id,
                    bracket_type=bracket_type_to_str(bracket_type),
                    broker_order_id=broker_order_id,
                )
            )

            return order_id

        except Exception as e:
            logger.warning(
                f"Failed to submit {bracket_type_to_str(bracket_type)} bracket order: {e}",
                extra={
                    "parent_order_id": str(parent_order_id),
                    "symbol": symbol,
                    "error": str(e),
                },
            )
            # Don't raise - bracket order failure shouldn't fail the main flow
            return None

    async def handle_bracket_fill(
        self,
        tenant_id: UUID,
        session_id: UUID,
        filled_order_id: UUID,
        parent_order_id: UUID,
        bracket_type: int,
        symbol: str,
        filled_qty: Decimal,
        filled_price: Decimal,
        sibling_order_ids: list[UUID] | None = None,
        sibling_broker_order_ids: list[str] | None = None,
    ) -> None:
        """Handle OCO behavior when a bracket order fills.

        Cancels sibling bracket orders when one fills.

        Args:
            tenant_id: Tenant identifier.
            session_id: Trading session identifier.
            filled_order_id: ID of the bracket order that filled.
            parent_order_id: ID of the parent order.
            bracket_type: Type of bracket that filled (int constant).
            symbol: Trading symbol.
            filled_qty: Quantity that filled.
            filled_price: Average fill price.
            sibling_order_ids: IDs of sibling bracket orders to cancel.
            sibling_broker_order_ids: Broker IDs of siblings to cancel.
        """
        # Record metric
        record_bracket_order_triggered(bracket_type_to_str(bracket_type))

        # Emit BracketOrderTriggered event
        await self.events.append(
            BracketOrderTriggered(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=filled_order_id,
                parent_order_id=parent_order_id,
                bracket_type=bracket_type_to_str(bracket_type),
                symbol=symbol,
                filled_qty=filled_qty,
                filled_avg_price=filled_price,
            )
        )

        # Send alert for bracket fill
        if self.alerts:
            if bracket_type == BracketType.STOP_LOSS:
                await self.alerts.on_stop_loss_hit(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=symbol,
                    qty=float(filled_qty),
                    stop_price=float(filled_price),  # Using filled price as trigger
                    filled_price=float(filled_price),
                )
            elif bracket_type == BracketType.TAKE_PROFIT:
                await self.alerts.on_take_profit_hit(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=symbol,
                    qty=float(filled_qty),
                    target_price=float(filled_price),
                    filled_price=float(filled_price),
                )

        # Cancel sibling bracket orders (OCO behavior)
        # Race condition handling: If both brackets fill simultaneously,
        # one cancel will fail with NOT_FOUND. We check the actual state
        # from Alpaca to determine if it filled or was already cancelled.
        if sibling_order_ids and sibling_broker_order_ids:
            for sibling_id, broker_id in zip(
                sibling_order_ids, sibling_broker_order_ids, strict=False
            ):
                # Determine sibling bracket type (opposite of filled)
                sibling_type: Literal["stop_loss", "take_profit"] = (
                    "take_profit" if bracket_type == BracketType.STOP_LOSS else "stop_loss"
                )

                # Cancel with Alpaca
                try:
                    await self.alpaca.cancel_order(broker_id)
                    # Successfully cancelled - emit event
                    await self.events.append(
                        BracketOrderCancelled(
                            tenant_id=tenant_id,
                            session_id=session_id,
                            order_id=sibling_id,
                            parent_order_id=parent_order_id,
                            bracket_type=sibling_type,
                            reason="oco_triggered",
                        )
                    )
                except OrderNotFoundError:
                    # Order not found at Alpaca - it may have filled or been cancelled
                    # Check the actual status to determine what happened
                    logger.info(
                        f"Sibling bracket {broker_id} not found at Alpaca during OCO, "
                        f"checking actual status"
                    )
                    try:
                        alpaca_order = await self.alpaca.get_order(broker_id)
                        if alpaca_order and alpaca_order.status.value == "filled":
                            # Both brackets filled - this is valid (price gapped)
                            logger.warning(
                                f"OCO conflict: both bracket orders filled. "
                                f"Parent: {parent_order_id}, this: {filled_order_id}, "
                                f"sibling: {sibling_id}. Both fills are valid."
                            )
                            record_bracket_oco_conflict("both_filled")
                            # Don't emit cancel event - it actually filled
                        else:
                            # Order was already cancelled by another process
                            logger.debug(f"Sibling bracket {sibling_id} already cancelled")
                            record_bracket_oco_conflict("cancelled_already")
                            # Still emit cancel event for consistency in event stream
                            await self.events.append(
                                BracketOrderCancelled(
                                    tenant_id=tenant_id,
                                    session_id=session_id,
                                    order_id=sibling_id,
                                    parent_order_id=parent_order_id,
                                    bracket_type=sibling_type,
                                    reason="oco_triggered",
                                )
                            )
                    except Exception as e:
                        logger.warning(f"Failed to check sibling bracket status: {e}")
                        # Assume it was cancelled and emit event
                        await self.events.append(
                            BracketOrderCancelled(
                                tenant_id=tenant_id,
                                session_id=session_id,
                                order_id=sibling_id,
                                parent_order_id=parent_order_id,
                                bracket_type=sibling_type,
                                reason="oco_triggered",
                            )
                        )
                except AlpacaError as e:
                    # Other error - log but still emit cancel event
                    logger.warning(f"Failed to cancel sibling bracket order {broker_id}: {e}")
                    # Emit cancel event anyway - the periodic sync will correct if needed
                    await self.events.append(
                        BracketOrderCancelled(
                            tenant_id=tenant_id,
                            session_id=session_id,
                            order_id=sibling_id,
                            parent_order_id=parent_order_id,
                            bracket_type=sibling_type,
                            reason="oco_triggered",
                        )
                    )

    # ===================
    # Private helpers
    # ===================

    async def _emit_fill_event(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order_id: UUID,
        order: OrderCreate,
        alpaca_order: AlpacaOrder,
    ) -> None:
        """Emit OrderFilled event from Alpaca order data."""
        filled_qty = Decimal(str(alpaca_order.filled_qty))
        filled_price = Decimal(str(alpaca_order.filled_avg_price or 0))

        await self.events.append(
            OrderFilled(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                symbol=order.symbol.upper(),
                side=order_side_to_str(order.side),
                filled_qty=filled_qty,
                filled_avg_price=filled_price,
            )
        )

        if self.alerts:
            from src.models import OrderResponse

            await self.alerts.on_order_filled(
                tenant_id=tenant_id,
                session_id=session_id,
                order=OrderResponse(
                    id=order_id,
                    symbol=order.symbol,
                    side=order.side,  # Already int
                    qty=order.qty,
                    order_type=order.order_type,  # Already int
                    status=ORDER_STATUS_FILLED,
                    filled_qty=float(filled_qty),
                    filled_avg_price=float(filled_price),
                    submitted_at=datetime.now(UTC),
                ),
            )

    async def _emit_events_from_alpaca_order(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order_id: UUID,
        client_order_id: str,
        order: OrderCreate,
        alpaca_order: AlpacaOrder,
    ) -> None:
        """Emit events based on Alpaca order state (for crash recovery)."""
        # Emit OrderSubmitted if not already
        await self.events.append(
            OrderSubmitted(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=order.symbol.upper(),
                side=order_side_to_str(order.side),
                qty=Decimal(str(order.qty)),
                order_type=order_type_to_str(order.order_type),
                time_in_force=time_in_force_to_str(order.time_in_force),
                limit_price=Decimal(str(order.limit_price)) if order.limit_price else None,
                stop_price=Decimal(str(order.stop_price)) if order.stop_price else None,
            )
        )

        # Emit OrderAccepted
        await self.events.append(
            OrderAccepted(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                broker_order_id=alpaca_order.id,
            )
        )

        # Emit fill if applicable
        status = alpaca_order.status.value.lower()
        if status == "filled":
            await self._emit_fill_event(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                order=order,
                alpaca_order=alpaca_order,
            )
        elif status in ("canceled", "cancelled"):
            await self.events.append(
                OrderCancelled(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    reason="broker_cancelled",
                    filled_qty=Decimal(str(alpaca_order.filled_qty)),
                )
            )

    def _side_to_signal_type(self, side: int) -> Literal["buy", "sell", "short", "cover"]:
        """Convert order side int to signal type."""
        if side == ORDER_SIDE_BUY:
            return "buy"
        else:
            return "sell"
