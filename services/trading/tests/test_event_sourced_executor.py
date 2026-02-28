"""Tests for event-sourced order executor."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
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
from src.models import OrderCreate, OrderSide, OrderType, TimeInForce


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
            return_value={
                "id": "alpaca-123",
                "status": "accepted",
                "client_order_id": "lt-abc123",
            }
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
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
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
        assert "Insufficient buying power" in rejected_event.broker_message

    async def test_submit_order_idempotent_on_existing(
        self, executor, mock_alpaca, mock_event_store, sample_order
    ):
        """Test that existing order in Alpaca is detected (crash recovery)."""
        # Simulate an existing order found in Alpaca
        mock_alpaca.get_order_by_client_id.return_value = {
            "id": "alpaca-existing",
            "status": "filled",
            "filled_qty": "100",
            "filled_avg_price": "150.50",
        }

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
        mock_alpaca.submit_order.return_value = {
            "id": "alpaca-123",
            "status": "filled",
            "filled_qty": "100",
            "filled_avg_price": "150.50",
        }

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
