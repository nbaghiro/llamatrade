"""Tests for event sourcing infrastructure."""

from decimal import Decimal
from uuid import uuid4

import pytest
from src.events.aggregates import (
    OrderState,
    PositionAggregate,
    PositionState,
    SessionState,
)
from src.events.base import deserialize_event
from src.events.trading_events import (
    CircuitBreakerReset,
    CircuitBreakerTriggered,
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    PositionClosed,
    PositionIncreased,
    PositionOpened,
    PositionReduced,
    SessionStarted,
    SignalGenerated,
    SignalRejected,
)


class TestTradingEvents:
    """Tests for event creation and serialization."""

    def test_signal_generated_creation(self):
        """Test creating a SignalGenerated event."""
        event = SignalGenerated(
            tenant_id=uuid4(),
            session_id=uuid4(),
            symbol="AAPL",
            signal_type="buy",
            price=Decimal("150.00"),
            qty=Decimal("100"),
            confidence=0.85,
            indicators={"rsi": 35.5, "macd": 0.5},
        )

        assert event.event_type == "signal.generated"
        assert event.symbol == "AAPL"
        assert event.signal_type == "buy"
        assert event.confidence == 0.85

    def test_order_submitted_creation(self):
        """Test creating an OrderSubmitted event."""
        order_id = uuid4()
        event = OrderSubmitted(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order_id=order_id,
            client_order_id=f"lt-{order_id}",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            stop_loss_price=Decimal("145.00"),
            take_profit_price=Decimal("160.00"),
        )

        assert event.event_type == "order.submitted"
        assert event.order_id == order_id
        assert event.stop_loss_price == Decimal("145.00")

    def test_position_opened_creation(self):
        """Test creating a PositionOpened event."""
        event = PositionOpened(
            tenant_id=uuid4(),
            session_id=uuid4(),
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            entry_price=Decimal("150.00"),
            order_id=uuid4(),
        )

        assert event.event_type == "position.opened"
        assert event.side == "long"

    def test_event_serialization(self):
        """Test event to_dict and deserialization."""
        tenant_id = uuid4()
        session_id = uuid4()
        order_id = uuid4()

        original = OrderSubmitted(
            tenant_id=tenant_id,
            session_id=session_id,
            order_id=order_id,
            client_order_id=f"lt-{order_id}",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="limit",
            limit_price=Decimal("149.50"),
        )

        # Serialize
        data = original.to_dict()
        assert data["event_type"] == "order.submitted"
        assert data["symbol"] == "AAPL"

        # Deserialize
        restored = deserialize_event(data)
        assert isinstance(restored, OrderSubmitted)
        assert restored.order_id == order_id
        assert restored.symbol == "AAPL"
        assert restored.side == "buy"


class TestSessionAggregate:
    """Tests for SessionState aggregate."""

    @pytest.fixture
    def session_ids(self):
        """Create session and tenant IDs."""
        return {
            "tenant_id": uuid4(),
            "session_id": uuid4(),
            "strategy_id": uuid4(),
        }

    def test_initial_state(self, session_ids):
        """Test initial session state."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )

        assert state.status == "unknown"
        assert len(state.positions) == 0
        assert len(state.orders) == 0
        assert state.realized_pnl == Decimal("0")

    def test_session_started(self, session_ids):
        """Test applying SessionStarted event."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )

        event = SessionStarted(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            strategy_id=session_ids["strategy_id"],
            strategy_name="Test Strategy",
            mode="paper",
            symbols=["AAPL", "GOOGL"],
            starting_equity=Decimal("100000"),
        )
        event.sequence = 1

        state.apply(event)

        assert state.status == "active"
        assert state.strategy_name == "Test Strategy"
        assert state.mode == "paper"
        assert "AAPL" in state.symbols
        assert state.starting_equity == Decimal("100000")

    def test_order_lifecycle(self, session_ids):
        """Test full order lifecycle through events."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )

        order_id = uuid4()

        # Submit order
        submit_event = OrderSubmitted(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            order_id=order_id,
            client_order_id=f"lt-{order_id}",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
        )
        submit_event.sequence = 1
        state.apply(submit_event)

        assert order_id in state.orders
        assert state.orders[order_id].status == "submitted"
        assert state.orders_submitted == 1

        # Accept order
        accept_event = OrderAccepted(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            order_id=order_id,
            broker_order_id="alpaca-123",
        )
        accept_event.sequence = 2
        state.apply(accept_event)

        assert state.orders[order_id].status == "accepted"
        assert state.orders[order_id].broker_order_id == "alpaca-123"

        # Fill order
        fill_event = OrderFilled(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            order_id=order_id,
            symbol="AAPL",
            side="buy",
            filled_qty=Decimal("100"),
            filled_avg_price=Decimal("150.50"),
        )
        fill_event.sequence = 3
        state.apply(fill_event)

        assert state.orders[order_id].status == "filled"
        assert state.orders[order_id].filled_qty == Decimal("100")
        assert state.orders_filled == 1

    def test_position_lifecycle(self, session_ids):
        """Test full position lifecycle through events."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )

        order_id = uuid4()

        # Open position
        open_event = PositionOpened(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            entry_price=Decimal("150.00"),
            order_id=order_id,
        )
        open_event.sequence = 1
        state.apply(open_event)

        assert "AAPL" in state.positions
        assert state.positions["AAPL"].qty == Decimal("100")
        assert state.positions["AAPL"].avg_cost == Decimal("150.00")

        # Increase position
        increase_event = PositionIncreased(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            symbol="AAPL",
            qty_added=Decimal("50"),
            price=Decimal("152.00"),
            new_total_qty=Decimal("150"),
            new_avg_cost=Decimal("150.67"),
            order_id=uuid4(),
        )
        increase_event.sequence = 2
        state.apply(increase_event)

        assert state.positions["AAPL"].qty == Decimal("150")
        assert state.positions["AAPL"].avg_cost == Decimal("150.67")

        # Reduce position
        reduce_event = PositionReduced(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            symbol="AAPL",
            qty_removed=Decimal("50"),
            exit_price=Decimal("155.00"),
            remaining_qty=Decimal("100"),
            realized_pnl=Decimal("216.50"),  # (155 - 150.67) * 50
            order_id=uuid4(),
        )
        reduce_event.sequence = 3
        state.apply(reduce_event)

        assert state.positions["AAPL"].qty == Decimal("100")
        assert state.realized_pnl == Decimal("216.50")

        # Close position
        close_event = PositionClosed(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            symbol="AAPL",
            exit_price=Decimal("160.00"),
            realized_pnl=Decimal("933.00"),  # (160 - 150.67) * 100
            order_id=uuid4(),
        )
        close_event.sequence = 4
        state.apply(close_event)

        assert "AAPL" not in state.positions
        assert state.realized_pnl == Decimal("1149.50")  # 216.50 + 933.00

    def test_circuit_breaker_events(self, session_ids):
        """Test circuit breaker state changes."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )
        state.status = "active"

        # Trigger circuit breaker
        trigger_event = CircuitBreakerTriggered(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            reason="consecutive_losses",
            details={"count": 5},
        )
        trigger_event.sequence = 1
        state.apply(trigger_event)

        assert state.circuit_breaker_triggered is True
        assert state.circuit_breaker_reason == "consecutive_losses"
        assert state.status == "paused"

        # Reset circuit breaker
        reset_event = CircuitBreakerReset(
            tenant_id=session_ids["tenant_id"],
            session_id=session_ids["session_id"],
            was_forced=True,
        )
        reset_event.sequence = 2
        state.apply(reset_event)

        assert state.circuit_breaker_triggered is False
        assert state.circuit_breaker_reason is None
        assert state.status == "active"

    def test_get_open_orders(self, session_ids):
        """Test filtering for open orders."""
        state = SessionState(
            session_id=session_ids["session_id"],
            tenant_id=session_ids["tenant_id"],
        )

        # Add various orders
        for i, status in enumerate(["submitted", "filled", "cancelled", "accepted"]):
            order_id = uuid4()
            state.orders[order_id] = OrderState(
                order_id=order_id,
                client_order_id=f"lt-{order_id}",
                symbol="AAPL",
                side="buy",
                qty=Decimal("100"),
                order_type="market",
                time_in_force="day",
                status=status,
            )

        open_orders = state.get_open_orders()

        # Should only include submitted and accepted
        assert len(open_orders) == 2
        assert all(o.status in {"submitted", "accepted"} for o in open_orders)


class TestPositionAggregate:
    """Tests for PositionAggregate."""

    def test_position_lifecycle(self):
        """Test position aggregate through events."""
        position = PositionAggregate(symbol="AAPL")
        tenant_id = uuid4()
        session_id = uuid4()

        # Open
        open_event = PositionOpened(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            entry_price=Decimal("150.00"),
            order_id=uuid4(),
        )
        open_event.sequence = 1
        position.apply(open_event)

        assert position.qty == Decimal("100")
        assert position.side == "long"
        assert position.avg_cost == Decimal("150.00")

        # Close
        close_event = PositionClosed(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            exit_price=Decimal("160.00"),
            realized_pnl=Decimal("1000.00"),
            order_id=uuid4(),
        )
        close_event.sequence = 2
        position.apply(close_event)

        assert position.qty == Decimal("0")
        assert position.side is None
        assert position.realized_pnl == Decimal("1000.00")

    def test_ignores_other_symbols(self):
        """Test that position ignores events for other symbols."""
        position = PositionAggregate(symbol="AAPL")
        tenant_id = uuid4()
        session_id = uuid4()

        # Event for different symbol
        event = PositionOpened(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="GOOGL",
            side="long",
            qty=Decimal("50"),
            entry_price=Decimal("2800.00"),
            order_id=uuid4(),
        )
        position.apply(event)

        # Should not affect AAPL position
        assert position.qty == Decimal("0")
        assert position.side is None


class TestPositionState:
    """Tests for PositionState calculations."""

    def test_market_value(self):
        """Test market value calculation."""
        position = PositionState(
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            avg_cost=Decimal("150.00"),
        )

        assert position.market_value == Decimal("15000.00")

    def test_unrealized_pnl_long(self):
        """Test unrealized P&L for long position."""
        position = PositionState(
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            avg_cost=Decimal("150.00"),
        )

        # Price up
        assert position.unrealized_pnl(Decimal("160.00")) == Decimal("1000.00")
        # Price down
        assert position.unrealized_pnl(Decimal("140.00")) == Decimal("-1000.00")

    def test_unrealized_pnl_short(self):
        """Test unrealized P&L for short position."""
        position = PositionState(
            symbol="AAPL",
            side="short",
            qty=Decimal("100"),
            avg_cost=Decimal("150.00"),
        )

        # Price down (good for short)
        assert position.unrealized_pnl(Decimal("140.00")) == Decimal("1000.00")
        # Price up (bad for short)
        assert position.unrealized_pnl(Decimal("160.00")) == Decimal("-1000.00")


class TestSignalEvents:
    """Tests for signal events."""

    def test_signal_generated_with_indicators(self):
        """Test signal with indicator data."""
        event = SignalGenerated(
            tenant_id=uuid4(),
            session_id=uuid4(),
            symbol="AAPL",
            signal_type="buy",
            price=Decimal("150.00"),
            qty=Decimal("100"),
            confidence=0.9,
            indicators={
                "rsi": 28.5,
                "macd": 0.75,
                "bb_lower": 148.50,
            },
        )

        assert event.indicators["rsi"] == 28.5
        assert event.indicators["macd"] == 0.75

    def test_signal_rejected(self):
        """Test signal rejection event."""
        event = SignalRejected(
            tenant_id=uuid4(),
            session_id=uuid4(),
            symbol="AAPL",
            signal_type="buy",
            reason="risk_check_failed",
            details={
                "violations": ["max_position_size", "daily_loss_limit"],
            },
        )

        assert event.reason == "risk_check_failed"
        assert "max_position_size" in event.details["violations"]


class TestOrderEvents:
    """Tests for order events."""

    def test_order_cancelled_with_partial_fill(self):
        """Test cancelled order that had partial fill."""
        event = OrderCancelled(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order_id=uuid4(),
            reason="user_requested",
            filled_qty=Decimal("50"),  # Partial fill before cancel
        )

        assert event.reason == "user_requested"
        assert event.filled_qty == Decimal("50")

    def test_order_rejected(self):
        """Test order rejection event."""
        event = OrderRejected(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order_id=uuid4(),
            reason="insufficient_buying_power",
            broker_message="Account has insufficient buying power",
        )

        assert event.reason == "insufficient_buying_power"
        assert "insufficient" in event.broker_message.lower()
