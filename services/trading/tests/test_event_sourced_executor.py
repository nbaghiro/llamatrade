"""Tests for event-sourced order executor."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.events.aggregates import SessionState
from src.events.trading_events import (
    OrderAccepted,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    SignalRejected,
)
from src.executor.event_sourced_executor import (
    EventSourcedOrderExecutor,
    generate_deterministic_order_id,
)
from src.models import BracketType, OrderCreate


class TestDeterministicOrderId:
    """Tests for deterministic order ID generation."""

    def test_same_inputs_produce_same_id(self):
        """Test that identical inputs produce identical order IDs."""
        session_id = uuid4()
        symbol = "AAPL"
        side = "buy"
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        id1 = generate_deterministic_order_id(session_id, symbol, side, timestamp)
        id2 = generate_deterministic_order_id(session_id, symbol, side, timestamp)

        assert id1 == id2
        assert id1.startswith("lt-")

    def test_different_sessions_produce_different_ids(self):
        """Test that different sessions produce different order IDs."""
        symbol = "AAPL"
        side = "buy"
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        id1 = generate_deterministic_order_id(uuid4(), symbol, side, timestamp)
        id2 = generate_deterministic_order_id(uuid4(), symbol, side, timestamp)

        assert id1 != id2

    def test_different_symbols_produce_different_ids(self):
        """Test that different symbols produce different order IDs."""
        session_id = uuid4()
        side = "buy"
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        id1 = generate_deterministic_order_id(session_id, "AAPL", side, timestamp)
        id2 = generate_deterministic_order_id(session_id, "GOOGL", side, timestamp)

        assert id1 != id2

    def test_different_timestamps_produce_different_ids(self):
        """Test that different timestamps produce different order IDs."""
        session_id = uuid4()
        symbol = "AAPL"
        side = "buy"

        id1 = generate_deterministic_order_id(
            session_id, symbol, side, datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        )
        id2 = generate_deterministic_order_id(
            session_id, symbol, side, datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC)
        )

        assert id1 != id2


class TestEventSourcedOrderExecutor:
    """Tests for EventSourcedOrderExecutor."""

    @pytest.fixture
    def mock_event_store(self):
        """Create mock event store."""
        store = AsyncMock()
        store.append = AsyncMock(return_value=1)
        return store

    @pytest.fixture
    def mock_alpaca(self):
        """Create mock Alpaca client."""
        client = AsyncMock()
        client.get_order_by_client_id = AsyncMock(return_value=None)
        client.submit_order = AsyncMock(
            return_value=AlpacaOrder(
                id="alpaca-123",
                symbol="AAPL",
                qty=100.0,
                side=AlpacaOrderSide.BUY,
                order_type=AlpacaOrderType.MARKET,
                status=AlpacaOrderStatus.ACCEPTED,
                time_in_force=AlpacaTimeInForce.DAY,
                client_order_id="lt-abc123",
                created_at=datetime.now(UTC),
            )
        )
        return client

    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager."""
        risk = AsyncMock()
        risk.check_order = AsyncMock(return_value=MagicMock(passed=True, violations=[]))
        return risk

    @pytest.fixture
    def executor(self, mock_event_store, mock_alpaca, mock_risk_manager):
        """Create executor with mocks."""
        return EventSourcedOrderExecutor(
            event_store=mock_event_store,
            alpaca_client=mock_alpaca,
            risk_manager=mock_risk_manager,
        )

    @pytest.fixture
    def sample_order(self):
        """Create sample order."""
        return OrderCreate(
            symbol="AAPL",
            qty=100,
            side=ORDER_SIDE_BUY,
            order_type=ORDER_TYPE_MARKET,
            time_in_force=TIME_IN_FORCE_DAY,
        )

    async def test_submit_order_emits_events(self, executor, mock_event_store, sample_order):
        """Test that submitting an order emits OrderSubmitted and OrderAccepted."""
        tenant_id = uuid4()
        session_id = uuid4()

        order_id = await executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order,
        )

        assert order_id is not None

        # Verify events were appended
        assert mock_event_store.append.call_count == 2

        # First call should be OrderSubmitted
        first_event = mock_event_store.append.call_args_list[0][0][0]
        assert isinstance(first_event, OrderSubmitted)
        assert first_event.symbol == "AAPL"
        assert first_event.side == "buy"
        assert first_event.qty == Decimal("100")

        # Second call should be OrderAccepted
        second_event = mock_event_store.append.call_args_list[1][0][0]
        assert isinstance(second_event, OrderAccepted)
        assert second_event.broker_order_id == "alpaca-123"

    async def test_submit_order_uses_deterministic_client_id(
        self, executor, mock_alpaca, sample_order
    ):
        """Test that order uses deterministic client_order_id."""
        tenant_id = uuid4()
        session_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        await executor.submit_order(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order,
            signal_timestamp=timestamp,
        )

        # Verify client_order_id was passed to Alpaca
        call_kwargs = mock_alpaca.submit_order.call_args[1]
        assert "client_order_id" in call_kwargs
        assert call_kwargs["client_order_id"].startswith("lt-")

    async def test_submit_order_risk_rejection(
        self, executor, mock_risk_manager, mock_event_store, sample_order
    ):
        """Test that risk rejection emits SignalRejected event."""
        mock_risk_manager.check_order.return_value = MagicMock(
            passed=False,
            violations=["max_position_size_exceeded"],
        )

        with pytest.raises(ValueError, match="Risk check failed"):
            await executor.submit_order(
                tenant_id=uuid4(),
                session_id=uuid4(),
                order=sample_order,
            )

        # Verify SignalRejected event was emitted
        event = mock_event_store.append.call_args[0][0]
        assert isinstance(event, SignalRejected)
        assert event.reason == "risk_check_failed"
        assert "max_position_size_exceeded" in event.details["violations"]

    async def test_submit_order_broker_rejection(
        self, executor, mock_alpaca, mock_event_store, sample_order
    ):
        """Test that broker rejection emits OrderRejected event."""
        mock_alpaca.submit_order.side_effect = Exception("Insufficient buying power")

        with pytest.raises(ValueError, match="Failed to submit order"):
            await executor.submit_order(
                tenant_id=uuid4(),
                session_id=uuid4(),
                order=sample_order,
            )

        # Verify OrderSubmitted then OrderRejected events
        assert mock_event_store.append.call_count == 2
        submitted_event = mock_event_store.append.call_args_list[0][0][0]
        rejected_event = mock_event_store.append.call_args_list[1][0][0]

        assert isinstance(submitted_event, OrderSubmitted)
        assert isinstance(rejected_event, OrderRejected)
        assert rejected_event.broker_message is not None
        assert "Insufficient buying power" in rejected_event.broker_message

    async def test_submit_order_idempotent_on_existing(
        self, executor, mock_alpaca, mock_event_store, sample_order
    ):
        """Test that existing order in Alpaca is detected (crash recovery)."""
        # Simulate an existing order found in Alpaca
        mock_alpaca.get_order_by_client_id.return_value = AlpacaOrder(
            id="alpaca-existing",
            symbol="AAPL",
            qty=100.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.DAY,
            filled_qty=100.0,
            filled_avg_price=150.50,
            created_at=datetime.now(UTC),
        )

        order_id = await executor.submit_order(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order=sample_order,
        )

        assert order_id is not None

        # Should NOT call submit_order since order already exists
        mock_alpaca.submit_order.assert_not_called()

        # Should emit events based on existing order state
        assert mock_event_store.append.call_count >= 2

    async def test_submit_order_immediate_fill(
        self, executor, mock_alpaca, mock_event_store, sample_order
    ):
        """Test handling of immediately filled market orders."""
        mock_alpaca.submit_order.return_value = AlpacaOrder(
            id="alpaca-123",
            symbol="AAPL",
            qty=100.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.DAY,
            filled_qty=100.0,
            filled_avg_price=150.50,
            created_at=datetime.now(UTC),
        )

        await executor.submit_order(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order=sample_order,
        )

        # Should emit OrderSubmitted, OrderAccepted, and OrderFilled
        assert mock_event_store.append.call_count == 3

        events = [call[0][0] for call in mock_event_store.append.call_args_list]
        assert isinstance(events[0], OrderSubmitted)
        assert isinstance(events[1], OrderAccepted)
        assert isinstance(events[2], OrderFilled)

        fill_event = events[2]
        assert fill_event.filled_qty == Decimal("100")
        assert fill_event.filled_avg_price == Decimal("150.50")


class TestEventSourcedExecutorRecovery:
    """Tests for crash recovery functionality."""

    @pytest.fixture
    def mock_event_store(self):
        """Create mock event store with read capability."""
        store = AsyncMock()
        store.append = AsyncMock(return_value=1)

        async def read_stream(*args, **kwargs):
            # Return empty stream by default
            return
            yield  # Makes this a generator

        store.read_stream = read_stream
        return store

    @pytest.fixture
    def mock_alpaca(self):
        """Create mock Alpaca client."""
        client = AsyncMock()
        client.get_order_by_client_id = AsyncMock(return_value=None)
        client.get_order = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def executor(self, mock_event_store, mock_alpaca):
        """Create executor with mocks."""
        return EventSourcedOrderExecutor(
            event_store=mock_event_store,
            alpaca_client=mock_alpaca,
            risk_manager=AsyncMock(),
        )

    async def test_get_session_state_loads_from_events(self, executor):
        """Test that session state is loaded from events."""
        tenant_id = uuid4()
        session_id = uuid4()

        state = await executor.get_session_state(session_id, tenant_id)

        assert isinstance(state, SessionState)
        assert state.session_id == session_id
        assert state.tenant_id == tenant_id

    async def test_recover_from_crash(self, executor, mock_alpaca, mock_event_store):
        """Test crash recovery checks Alpaca for unconfirmed orders."""
        tenant_id = uuid4()
        session_id = uuid4()

        # Simulate recovery
        state = await executor.recover_from_crash(session_id, tenant_id)

        assert isinstance(state, SessionState)


class TestSignalRecording:
    """Tests for signal recording."""

    @pytest.fixture
    def mock_event_store(self):
        """Create mock event store."""
        store = AsyncMock()
        store.append = AsyncMock(return_value=1)
        return store

    @pytest.fixture
    def executor(self, mock_event_store):
        """Create executor with mocks."""
        return EventSourcedOrderExecutor(
            event_store=mock_event_store,
            alpaca_client=AsyncMock(),
            risk_manager=AsyncMock(),
        )

    async def test_record_signal(self, executor, mock_event_store):
        """Test recording a signal event."""
        from src.events.trading_events import SignalGenerated

        tenant_id = uuid4()
        session_id = uuid4()

        await executor.record_signal(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            signal_type="buy",
            price=Decimal("150.00"),
            qty=Decimal("100"),
            confidence=0.85,
            indicators={"rsi": 35.5},
        )

        mock_event_store.append.assert_called_once()
        event = mock_event_store.append.call_args[0][0]

        assert isinstance(event, SignalGenerated)
        assert event.symbol == "AAPL"
        assert event.signal_type == "buy"
        assert event.confidence == 0.85
        assert event.indicators["rsi"] == 35.5


class TestPositionRecording:
    """Tests for position event recording."""

    @pytest.fixture
    def mock_event_store(self):
        """Create mock event store."""
        store = AsyncMock()
        store.append = AsyncMock(return_value=1)
        return store

    @pytest.fixture
    def executor(self, mock_event_store):
        """Create executor with mocks."""
        return EventSourcedOrderExecutor(
            event_store=mock_event_store,
            alpaca_client=AsyncMock(),
            risk_manager=AsyncMock(),
        )

    async def test_record_position_opened(self, executor, mock_event_store):
        """Test recording position opened event."""
        from src.events.trading_events import PositionOpened

        tenant_id = uuid4()
        session_id = uuid4()
        order_id = uuid4()

        await executor.record_position_opened(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            side="long",
            qty=Decimal("100"),
            entry_price=Decimal("150.00"),
            order_id=order_id,
        )

        event = mock_event_store.append.call_args[0][0]
        assert isinstance(event, PositionOpened)
        assert event.symbol == "AAPL"
        assert event.side == "long"

    async def test_record_position_closed(self, executor, mock_event_store):
        """Test recording position closed event."""
        from src.events.trading_events import PositionClosed

        tenant_id = uuid4()
        session_id = uuid4()
        order_id = uuid4()

        await executor.record_position_closed(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            exit_price=Decimal("160.00"),
            realized_pnl=Decimal("1000.00"),
            order_id=order_id,
        )

        event = mock_event_store.append.call_args[0][0]
        assert isinstance(event, PositionClosed)
        assert event.symbol == "AAPL"
        assert event.realized_pnl == Decimal("1000.00")


class TestBracketOrders:
    """Tests for bracket order functionality."""

    @pytest.fixture
    def mock_event_store(self):
        """Create mock event store."""
        store = AsyncMock()
        store.append = AsyncMock(return_value=1)
        return store

    @pytest.fixture
    def mock_alpaca(self):
        """Create mock Alpaca client."""
        client = AsyncMock()
        client.submit_order = AsyncMock(
            return_value=AlpacaOrder(
                id="alpaca-bracket-123",
                symbol="AAPL",
                qty=100.0,
                side=AlpacaOrderSide.SELL,
                order_type=AlpacaOrderType.STOP_LIMIT,
                status=AlpacaOrderStatus.ACCEPTED,
                time_in_force=AlpacaTimeInForce.GTC,
                client_order_id="lt-abc123-stop_loss",
                created_at=datetime.now(UTC),
            )
        )
        # cancel_order now returns None on success (raises on failure)
        client.cancel_order = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def mock_alerts(self):
        """Create mock alert service."""
        service = AsyncMock()
        service.on_stop_loss_hit = AsyncMock()
        service.on_take_profit_hit = AsyncMock()
        return service

    @pytest.fixture
    def executor(self, mock_event_store, mock_alpaca, mock_alerts):
        """Create executor with mocks."""
        return EventSourcedOrderExecutor(
            event_store=mock_event_store,
            alpaca_client=mock_alpaca,
            risk_manager=AsyncMock(),
            alert_service=mock_alerts,
        )

    async def test_submit_bracket_orders_both(self, executor, mock_event_store, mock_alpaca):
        """Test submitting both stop-loss and take-profit orders."""
        from src.events.trading_events import BracketOrderAccepted, BracketOrderCreated

        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()

        sl_id, tp_id = await executor.submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order_id=parent_order_id,
            parent_client_order_id="lt-abc123",
            symbol="AAPL",
            entry_side=ORDER_SIDE_BUY,
            qty=Decimal("100"),
            filled_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),
            take_profit_price=Decimal("160.00"),
        )

        # Should have submitted both orders
        assert sl_id is not None
        assert tp_id is not None
        assert mock_alpaca.submit_order.call_count == 2

        # Should have emitted 4 events (2x BracketOrderCreated + 2x BracketOrderAccepted)
        assert mock_event_store.append.call_count == 4

        # Check event types
        events = [call[0][0] for call in mock_event_store.append.call_args_list]
        created_events = [e for e in events if isinstance(e, BracketOrderCreated)]
        accepted_events = [e for e in events if isinstance(e, BracketOrderAccepted)]

        assert len(created_events) == 2
        assert len(accepted_events) == 2

        # Check bracket types
        bracket_types = {e.bracket_type for e in created_events}
        assert bracket_types == {"stop_loss", "take_profit"}

    async def test_submit_bracket_orders_stop_loss_only(
        self, executor, mock_event_store, mock_alpaca
    ):
        """Test submitting only stop-loss order."""
        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()

        sl_id, tp_id = await executor.submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order_id=parent_order_id,
            parent_client_order_id="lt-abc123",
            symbol="AAPL",
            entry_side=ORDER_SIDE_BUY,
            qty=Decimal("100"),
            filled_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),
            take_profit_price=None,
        )

        assert sl_id is not None
        assert tp_id is None
        assert mock_alpaca.submit_order.call_count == 1

        # Check the submitted order uses stop-limit for SL
        call_args = mock_alpaca.submit_order.call_args
        assert call_args.kwargs["order_type"] == "stop_limit"
        assert call_args.kwargs["stop_price"] == 145.0
        assert call_args.kwargs["side"] == "sell"  # Exit side opposite of entry

    async def test_submit_bracket_orders_take_profit_only(
        self, executor, mock_event_store, mock_alpaca
    ):
        """Test submitting only take-profit order."""
        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()

        sl_id, tp_id = await executor.submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order_id=parent_order_id,
            parent_client_order_id="lt-abc123",
            symbol="AAPL",
            entry_side=ORDER_SIDE_BUY,
            qty=Decimal("100"),
            filled_price=Decimal("150.00"),
            stop_loss_price=None,
            take_profit_price=Decimal("160.00"),
        )

        assert sl_id is None
        assert tp_id is not None
        assert mock_alpaca.submit_order.call_count == 1

        # Check the submitted order uses limit for TP
        call_args = mock_alpaca.submit_order.call_args
        assert call_args.kwargs["order_type"] == "limit"
        assert call_args.kwargs["limit_price"] == 160.0
        assert call_args.kwargs["side"] == "sell"

    async def test_submit_bracket_orders_short_position(
        self, executor, mock_event_store, mock_alpaca
    ):
        """Test bracket orders for short position have correct exit side."""
        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()

        sl_id, tp_id = await executor.submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order_id=parent_order_id,
            parent_client_order_id="lt-abc123",
            symbol="AAPL",
            entry_side=ORDER_SIDE_SELL,  # Short entry
            qty=Decimal("100"),
            filled_price=Decimal("150.00"),
            stop_loss_price=Decimal("155.00"),  # SL above entry for shorts
            take_profit_price=Decimal("140.00"),  # TP below entry for shorts
        )

        assert sl_id is not None
        assert tp_id is not None

        # Exit side should be BUY for shorts
        for call in mock_alpaca.submit_order.call_args_list:
            assert call.kwargs["side"] == "buy"

    async def test_submit_bracket_order_failure_continues(
        self, executor, mock_event_store, mock_alpaca
    ):
        """Test that bracket order failure doesn't raise - returns None."""
        mock_alpaca.submit_order = AsyncMock(side_effect=Exception("API error"))

        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()

        # Should not raise, but return None for both
        sl_id, tp_id = await executor.submit_bracket_orders(
            tenant_id=tenant_id,
            session_id=session_id,
            parent_order_id=parent_order_id,
            parent_client_order_id="lt-abc123",
            symbol="AAPL",
            entry_side=ORDER_SIDE_BUY,
            qty=Decimal("100"),
            filled_price=Decimal("150.00"),
            stop_loss_price=Decimal("145.00"),
            take_profit_price=Decimal("160.00"),
        )

        # Both should be None due to failure
        assert sl_id is None
        assert tp_id is None

    async def test_handle_bracket_fill_stop_loss(
        self, executor, mock_event_store, mock_alpaca, mock_alerts
    ):
        """Test handling stop-loss fill with OCO cancellation."""
        from src.events.trading_events import BracketOrderCancelled, BracketOrderTriggered

        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()
        sl_order_id = uuid4()
        tp_order_id = uuid4()

        await executor.handle_bracket_fill(
            tenant_id=tenant_id,
            session_id=session_id,
            filled_order_id=sl_order_id,
            parent_order_id=parent_order_id,
            bracket_type=BracketType.STOP_LOSS,
            symbol="AAPL",
            filled_qty=Decimal("100"),
            filled_price=Decimal("145.00"),
            sibling_order_ids=[tp_order_id],
            sibling_broker_order_ids=["alpaca-tp-123"],
        )

        # Should emit BracketOrderTriggered
        events = [call[0][0] for call in mock_event_store.append.call_args_list]
        triggered = [e for e in events if isinstance(e, BracketOrderTriggered)]
        assert len(triggered) == 1
        assert triggered[0].bracket_type == "stop_loss"

        # Should emit BracketOrderCancelled for sibling
        cancelled = [e for e in events if isinstance(e, BracketOrderCancelled)]
        assert len(cancelled) == 1
        assert cancelled[0].bracket_type == "take_profit"
        assert cancelled[0].reason == "oco_triggered"

        # Should cancel sibling via Alpaca
        mock_alpaca.cancel_order.assert_called_once_with("alpaca-tp-123")

        # Should send stop-loss alert
        mock_alerts.on_stop_loss_hit.assert_called_once()

    async def test_handle_bracket_fill_take_profit(
        self, executor, mock_event_store, mock_alpaca, mock_alerts
    ):
        """Test handling take-profit fill with OCO cancellation."""
        from src.events.trading_events import BracketOrderCancelled, BracketOrderTriggered

        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()
        sl_order_id = uuid4()
        tp_order_id = uuid4()

        await executor.handle_bracket_fill(
            tenant_id=tenant_id,
            session_id=session_id,
            filled_order_id=tp_order_id,
            parent_order_id=parent_order_id,
            bracket_type=BracketType.TAKE_PROFIT,
            symbol="AAPL",
            filled_qty=Decimal("100"),
            filled_price=Decimal("160.00"),
            sibling_order_ids=[sl_order_id],
            sibling_broker_order_ids=["alpaca-sl-123"],
        )

        # Should emit BracketOrderTriggered
        events = [call[0][0] for call in mock_event_store.append.call_args_list]
        triggered = [e for e in events if isinstance(e, BracketOrderTriggered)]
        assert len(triggered) == 1
        assert triggered[0].bracket_type == "take_profit"

        # Should emit BracketOrderCancelled for sibling
        cancelled = [e for e in events if isinstance(e, BracketOrderCancelled)]
        assert len(cancelled) == 1
        assert cancelled[0].bracket_type == "stop_loss"

        # Should send take-profit alert
        mock_alerts.on_take_profit_hit.assert_called_once()

    async def test_handle_bracket_fill_no_siblings(self, executor, mock_event_store, mock_alpaca):
        """Test handling bracket fill when no siblings to cancel."""

        tenant_id = uuid4()
        session_id = uuid4()
        parent_order_id = uuid4()
        sl_order_id = uuid4()

        await executor.handle_bracket_fill(
            tenant_id=tenant_id,
            session_id=session_id,
            filled_order_id=sl_order_id,
            parent_order_id=parent_order_id,
            bracket_type=BracketType.STOP_LOSS,
            symbol="AAPL",
            filled_qty=Decimal("100"),
            filled_price=Decimal("145.00"),
            sibling_order_ids=None,
            sibling_broker_order_ids=None,
        )

        # Should not try to cancel anything
        mock_alpaca.cancel_order.assert_not_called()

        # Should still emit triggered event
        assert mock_event_store.append.call_count == 1
