"""Aggregates that derive state from events.

Aggregates are the "current state" view built by replaying events.
They provide the read model for queries while events remain the
source of truth.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID

from src.events.base import TradingEvent
from src.events.store import EventStore
from src.events.trading_events import (
    CircuitBreakerReset,
    CircuitBreakerTriggered,
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderPartiallyFilled,
    OrderRejected,
    OrderSubmitted,
    PositionClosed,
    PositionIncreased,
    PositionOpened,
    PositionReduced,
    SessionPaused,
    SessionResumed,
    SessionStarted,
    SessionStopped,
    SignalGenerated,
    SignalRejected,
)


@dataclass
class OrderState:
    """Current state of an order derived from events."""

    order_id: UUID
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: str = "pending"  # pending, submitted, accepted, filled, partial, cancelled, rejected
    broker_order_id: str | None = None
    filled_qty: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    # Bracket info
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    parent_order_id: UUID | None = None
    # Timestamps
    submitted_at: int | None = None  # Event sequence
    filled_at: int | None = None


@dataclass
class PositionState:
    """Current state of a position derived from events."""

    symbol: str
    side: Literal["long", "short"]
    qty: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal = Decimal("0")
    opened_at: int | None = None  # Event sequence when opened
    last_updated_at: int | None = None

    @property
    def market_value(self) -> Decimal:
        """Calculate market value at avg cost."""
        return self.qty * self.avg_cost

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L at a given price."""
        if self.side == "long":
            return (current_price - self.avg_cost) * self.qty
        else:  # short
            return (self.avg_cost - current_price) * self.qty


@dataclass
class SessionState:
    """Current state of a trading session derived from events.

    This is the main aggregate that holds all session state including
    positions, orders, and metrics.
    """

    session_id: UUID
    tenant_id: UUID

    # Session info
    strategy_id: UUID | None = None
    strategy_name: str | None = None
    mode: Literal["live", "paper"] | None = None
    symbols: list[str] = field(default_factory=list)

    # Status
    status: str = "unknown"  # starting, active, paused, stopped, error
    circuit_breaker_triggered: bool = False
    circuit_breaker_reason: str | None = None

    # Positions and orders
    positions: dict[str, PositionState] = field(default_factory=dict)
    orders: dict[UUID, OrderState] = field(default_factory=dict)

    # Metrics
    starting_equity: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    signals_generated: int = 0
    signals_rejected: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0
    orders_rejected: int = 0

    # Event tracking
    version: int = 0  # Last event sequence applied
    events_applied: int = 0

    def apply(self, event: TradingEvent) -> None:
        """Apply an event to update state.

        This method dispatches to specific handlers based on event type.
        """
        # Session events
        if isinstance(event, SessionStarted):
            self._apply_session_started(event)
        elif isinstance(event, SessionStopped):
            self._apply_session_stopped(event)
        elif isinstance(event, SessionPaused):
            self._apply_session_paused(event)
        elif isinstance(event, SessionResumed):
            self._apply_session_resumed(event)

        # Signal events
        elif isinstance(event, SignalGenerated):
            self.signals_generated += 1
        elif isinstance(event, SignalRejected):
            self.signals_rejected += 1

        # Order events
        elif isinstance(event, OrderSubmitted):
            self._apply_order_submitted(event)
        elif isinstance(event, OrderAccepted):
            self._apply_order_accepted(event)
        elif isinstance(event, OrderFilled):
            self._apply_order_filled(event)
        elif isinstance(event, OrderPartiallyFilled):
            self._apply_order_partial(event)
        elif isinstance(event, OrderCancelled):
            self._apply_order_cancelled(event)
        elif isinstance(event, OrderRejected):
            self._apply_order_rejected(event)

        # Position events
        elif isinstance(event, PositionOpened):
            self._apply_position_opened(event)
        elif isinstance(event, PositionIncreased):
            self._apply_position_increased(event)
        elif isinstance(event, PositionReduced):
            self._apply_position_reduced(event)
        elif isinstance(event, PositionClosed):
            self._apply_position_closed(event)

        # Circuit breaker events
        elif isinstance(event, CircuitBreakerTriggered):
            self.circuit_breaker_triggered = True
            self.circuit_breaker_reason = event.reason
            self.status = "paused"
        elif isinstance(event, CircuitBreakerReset):
            self.circuit_breaker_triggered = False
            self.circuit_breaker_reason = None
            if self.status == "paused":
                self.status = "active"

        # Update version
        if event.sequence is not None:
            self.version = event.sequence
        self.events_applied += 1

    def _apply_session_started(self, event: SessionStarted) -> None:
        self.strategy_id = event.strategy_id
        self.strategy_name = event.strategy_name
        self.mode = event.mode
        self.symbols = event.symbols.copy()
        self.starting_equity = event.starting_equity
        self.status = "active"

    def _apply_session_stopped(self, event: SessionStopped) -> None:
        self.status = "stopped"

    def _apply_session_paused(self, event: SessionPaused) -> None:
        self.status = "paused"

    def _apply_session_resumed(self, event: SessionResumed) -> None:
        self.status = "active"

    def _apply_order_submitted(self, event: OrderSubmitted) -> None:
        self.orders[event.order_id] = OrderState(
            order_id=event.order_id,
            client_order_id=event.client_order_id,
            symbol=event.symbol,
            side=event.side,
            qty=event.qty,
            order_type=event.order_type,
            time_in_force=event.time_in_force,
            limit_price=event.limit_price,
            stop_price=event.stop_price,
            stop_loss_price=event.stop_loss_price,
            take_profit_price=event.take_profit_price,
            parent_order_id=event.parent_order_id,
            status="submitted",
            submitted_at=event.sequence,
        )
        self.orders_submitted += 1

    def _apply_order_accepted(self, event: OrderAccepted) -> None:
        if event.order_id in self.orders:
            order = self.orders[event.order_id]
            order.status = "accepted"
            order.broker_order_id = event.broker_order_id

    def _apply_order_filled(self, event: OrderFilled) -> None:
        if event.order_id in self.orders:
            order = self.orders[event.order_id]
            order.status = "filled"
            order.filled_qty = event.filled_qty
            order.filled_avg_price = event.filled_avg_price
            order.filled_at = event.sequence
        self.orders_filled += 1

    def _apply_order_partial(self, event: OrderPartiallyFilled) -> None:
        if event.order_id in self.orders:
            order = self.orders[event.order_id]
            order.status = "partial"
            order.filled_qty = event.filled_qty
            order.filled_avg_price = event.filled_avg_price

    def _apply_order_cancelled(self, event: OrderCancelled) -> None:
        if event.order_id in self.orders:
            order = self.orders[event.order_id]
            order.status = "cancelled"
            order.filled_qty = event.filled_qty
        self.orders_cancelled += 1

    def _apply_order_rejected(self, event: OrderRejected) -> None:
        if event.order_id in self.orders:
            order = self.orders[event.order_id]
            order.status = "rejected"
        self.orders_rejected += 1

    def _apply_position_opened(self, event: PositionOpened) -> None:
        self.positions[event.symbol] = PositionState(
            symbol=event.symbol,
            side=event.side,
            qty=event.qty,
            avg_cost=event.entry_price,
            opened_at=event.sequence,
            last_updated_at=event.sequence,
        )

    def _apply_position_increased(self, event: PositionIncreased) -> None:
        if event.symbol in self.positions:
            pos = self.positions[event.symbol]
            pos.qty = event.new_total_qty
            pos.avg_cost = event.new_avg_cost
            pos.last_updated_at = event.sequence

    def _apply_position_reduced(self, event: PositionReduced) -> None:
        if event.symbol in self.positions:
            pos = self.positions[event.symbol]
            pos.qty = event.remaining_qty
            pos.realized_pnl += event.realized_pnl
            pos.last_updated_at = event.sequence
            self.realized_pnl += event.realized_pnl

    def _apply_position_closed(self, event: PositionClosed) -> None:
        if event.symbol in self.positions:
            pos = self.positions[event.symbol]
            pos.realized_pnl += event.realized_pnl
            self.realized_pnl += event.realized_pnl
            del self.positions[event.symbol]

    @classmethod
    async def load(
        cls,
        session_id: UUID,
        tenant_id: UUID,
        event_store: EventStore,
        from_sequence: int = 0,
    ) -> "SessionState":
        """Load session state by replaying events.

        Args:
            session_id: The session to load.
            tenant_id: The tenant ID.
            event_store: Event store to read from.
            from_sequence: Start from this sequence (for incremental loads).

        Returns:
            SessionState with all events applied.
        """
        state = cls(session_id=session_id, tenant_id=tenant_id)

        async for event in event_store.read_stream(
            session_id=session_id,
            from_sequence=from_sequence,
        ):
            state.apply(event)

        return state

    def get_open_orders(self) -> list[OrderState]:
        """Get all orders that are still open."""
        open_statuses = {"pending", "submitted", "accepted", "partial"}
        return [o for o in self.orders.values() if o.status in open_statuses]

    def get_position(self, symbol: str) -> PositionState | None:
        """Get position for a symbol, or None if no position."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if we have a position in a symbol."""
        return symbol in self.positions


@dataclass
class PositionAggregate:
    """Lightweight aggregate for just position state.

    Use this when you only need position info without full session state.
    """

    symbol: str
    side: Literal["long", "short"] | None = None
    qty: Decimal = Decimal("0")
    avg_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    version: int = 0

    def apply(self, event: TradingEvent) -> None:
        """Apply event if it affects this position."""
        if isinstance(event, PositionOpened) and event.symbol == self.symbol:
            self.side = event.side
            self.qty = event.qty
            self.avg_cost = event.entry_price

        elif isinstance(event, PositionIncreased) and event.symbol == self.symbol:
            self.qty = event.new_total_qty
            self.avg_cost = event.new_avg_cost

        elif isinstance(event, PositionReduced) and event.symbol == self.symbol:
            self.qty = event.remaining_qty
            self.realized_pnl += event.realized_pnl

        elif isinstance(event, PositionClosed) and event.symbol == self.symbol:
            self.qty = Decimal("0")
            self.side = None
            self.realized_pnl += event.realized_pnl

        if event.sequence is not None:
            self.version = event.sequence

    @classmethod
    async def load(
        cls,
        symbol: str,
        session_id: UUID,
        event_store: EventStore,
    ) -> "PositionAggregate":
        """Load position state by replaying position events."""
        position = cls(symbol=symbol)

        # Only read position-related events for efficiency
        position_event_types = [
            "position.opened",
            "position.increased",
            "position.reduced",
            "position.closed",
        ]

        async for event in event_store.read_stream(
            session_id=session_id,
            event_types=position_event_types,
        ):
            if hasattr(event, "symbol") and event.symbol == symbol:
                position.apply(event)

        return position
