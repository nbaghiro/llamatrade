"""Event-sourced order executor with idempotent, durable order submission.

This executor uses event sourcing to ensure:
1. Idempotent order submission (same signal = same order, even after crash)
2. Durable state (replay events to recover state)
3. Full audit trail (every action is recorded as an event)
"""

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID, uuid4

from src.alpaca_client import AlpacaOrderResponse, AlpacaTradingClient
from src.events.aggregates import SessionState
from src.events.store import EventStore
from src.events.trading_events import (
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
from src.models import OrderCreate, OrderSide
from src.risk.risk_manager import RiskManager
from src.services.alert_service import AlertService

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


class EventSourcedOrderExecutor:
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
        alpaca_client: AlpacaTradingClient,
        risk_manager: RiskManager,
        alert_service: AlertService | None = None,
    ):
        self.events = event_store
        self.alpaca = alpaca_client
        self.risk = risk_manager
        self.alerts = alert_service

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
        order_id = uuid4()
        now = signal_timestamp or datetime.now(UTC)

        # Generate deterministic client_order_id for idempotency
        client_order_id = generate_deterministic_order_id(
            session_id=session_id,
            symbol=order.symbol,
            side=order.side.value,
            signal_timestamp=now,
        )

        # 1. Check if we already have an order with this client_order_id
        #    (crash recovery - we may have submitted but crashed before recording)
        existing_order = await self.alpaca.get_order_by_client_id(client_order_id)
        if existing_order:
            logger.info(
                f"Found existing order for client_order_id={client_order_id}",
                extra={"alpaca_order_id": existing_order.get("id")},
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

        # 2. Run risk checks
        risk_result = await self.risk.check_order(
            tenant_id=tenant_id,
            symbol=order.symbol,
            side=order.side.value,
            qty=order.qty,
            order_type=order.order_type.value,
        )

        if not risk_result.passed:
            # Emit SignalRejected event
            await self.events.append(
                SignalRejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    symbol=order.symbol,
                    signal_type=self._side_to_signal_type(order.side),
                    reason="risk_check_failed",
                    details={"violations": risk_result.violations},
                )
            )

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

        # 3. Emit OrderSubmitted event (our intent)
        await self.events.append(
            OrderSubmitted(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=order.symbol.upper(),
                side=order.side.value,
                qty=Decimal(str(order.qty)),
                order_type=cast(
                    Literal["market", "limit", "stop", "stop_limit"], order.order_type.value
                ),
                time_in_force=order.time_in_force.value,
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

        # 4. Submit to Alpaca (idempotent via client_order_id)
        try:
            alpaca_order = await self.alpaca.submit_order(
                symbol=order.symbol,
                qty=order.qty,
                side=order.side.value,
                order_type=order.order_type.value,
                time_in_force=order.time_in_force.value,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                client_order_id=client_order_id,  # Idempotency key
            )

            # 5. Emit OrderAccepted event
            await self.events.append(
                OrderAccepted(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    broker_order_id=alpaca_order.get("id", ""),
                )
            )

            # Check if immediately filled (market orders)
            if alpaca_order.get("status") == "filled":
                await self._emit_fill_event(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    order=order,
                    alpaca_order=alpaca_order,
                )

        except Exception as e:
            # Emit OrderRejected event
            await self.events.append(
                OrderRejected(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    order_id=order_id,
                    reason="broker_rejected",
                    broker_message=str(e),
                )
            )

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

        return order_id

    async def record_signal(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        signal_type: Literal["buy", "sell", "short", "cover"],
        price: Decimal,
        qty: Decimal,
        confidence: float = 1.0,
        indicators: dict | None = None,
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
                signal_type=signal_type,
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

        status = alpaca_order.get("status", "").lower()

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
                    filled_qty=Decimal(alpaca_order.get("filled_qty", "0")),
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
        order_id: UUID,
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
        order_id: UUID,
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
                            broker_order_id=alpaca_order.get("id", ""),
                        )
                    )

                    # Check if filled
                    if alpaca_order.get("status") == "filled":
                        filled_qty = Decimal(alpaca_order.get("filled_qty", "0"))
                        filled_price = Decimal(alpaca_order.get("filled_avg_price") or "0")
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
    # Private helpers
    # ===================

    async def _emit_fill_event(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order_id: UUID,
        order: OrderCreate,
        alpaca_order: AlpacaOrderResponse,
    ) -> None:
        """Emit OrderFilled event from Alpaca order data."""
        filled_qty = Decimal(alpaca_order.get("filled_qty", "0"))
        filled_price = Decimal(alpaca_order.get("filled_avg_price") or "0")

        await self.events.append(
            OrderFilled(
                tenant_id=tenant_id,
                session_id=session_id,
                order_id=order_id,
                symbol=order.symbol.upper(),
                side=order.side.value,
                filled_qty=filled_qty,
                filled_avg_price=filled_price,
            )
        )

        if self.alerts:
            from src.models import OrderResponse, OrderStatus

            await self.alerts.on_order_filled(
                tenant_id=tenant_id,
                session_id=session_id,
                order=OrderResponse(
                    id=order_id,
                    symbol=order.symbol,
                    side=order.side,
                    qty=order.qty,
                    order_type=order.order_type,
                    status=OrderStatus.FILLED,
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
        alpaca_order: AlpacaOrderResponse,
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
                side=order.side.value,
                qty=Decimal(str(order.qty)),
                order_type=cast(
                    Literal["market", "limit", "stop", "stop_limit"], order.order_type.value
                ),
                time_in_force=order.time_in_force.value,
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
                broker_order_id=alpaca_order.get("id", ""),
            )
        )

        # Emit fill if applicable
        status = alpaca_order.get("status", "").lower()
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
                    filled_qty=Decimal(alpaca_order.get("filled_qty", "0")),
                )
            )

    def _side_to_signal_type(self, side: OrderSide) -> Literal["buy", "sell", "short", "cover"]:
        """Convert order side to signal type."""
        if side == OrderSide.BUY:
            return "buy"
        else:
            return "sell"
