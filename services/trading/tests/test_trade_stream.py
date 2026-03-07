"""Tests for the Alpaca trade stream (order/fill updates)."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from src.runner.trade_stream import (
    AlpacaTradeStream,
    FillData,
    MockTradeStream,
    TradeEvent,
    TradeEventType,
    TradeStreamConfig,
)


class TestTradeStreamConfig:
    """Tests for TradeStreamConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TradeStreamConfig()
        assert config.paper is True
        assert config.reconnect_delay == 1.0
        assert config.max_reconnect_delay == 60.0
        assert config.max_reconnect_attempts == 10
        assert config.jitter_factor == 0.1

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TradeStreamConfig(
            api_key="test-key",
            api_secret="test-secret",
            paper=False,
            reconnect_delay=2.0,
        )
        assert config.api_key == "test-key"
        assert config.api_secret == "test-secret"
        assert config.paper is False
        assert config.reconnect_delay == 2.0


class TestTradeEventType:
    """Tests for TradeEventType enum."""

    def test_fill_event(self):
        """Test fill event type."""
        assert TradeEventType.FILL.value == "fill"

    def test_partial_fill_event(self):
        """Test partial fill event type."""
        assert TradeEventType.PARTIAL_FILL.value == "partial_fill"

    def test_canceled_event(self):
        """Test canceled event type."""
        assert TradeEventType.CANCELED.value == "canceled"

    def test_rejected_event(self):
        """Test rejected event type."""
        assert TradeEventType.REJECTED.value == "rejected"


class TestFillData:
    """Tests for FillData dataclass."""

    def test_fill_data_creation(self):
        """Test creating fill data."""
        now = datetime.now(UTC)
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.25"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        assert fill.order_id == "order-123"
        assert fill.client_order_id == "client-456"
        assert fill.symbol == "AAPL"
        assert fill.side == "buy"
        assert fill.fill_qty == Decimal("10")
        assert fill.fill_price == Decimal("150.25")
        assert fill.remaining_qty == Decimal("0")

    def test_fill_data_with_position_qty(self):
        """Test fill data with position quantity."""
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.25"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=datetime.now(UTC),
            position_qty=Decimal("50"),
        )
        assert fill.position_qty == Decimal("50")


class TestTradeEvent:
    """Tests for TradeEvent dataclass."""

    def test_trade_event_creation(self):
        """Test creating trade event."""
        now = datetime.now(UTC)
        event = TradeEvent(
            event_type=TradeEventType.NEW,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=now,
        )
        assert event.event_type == TradeEventType.NEW
        assert event.order_id == "order-123"
        assert event.symbol == "AAPL"
        assert event.fill is None

    def test_trade_event_with_fill(self):
        """Test trade event with fill data."""
        now = datetime.now(UTC)
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.25"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.25"),
            timestamp=now,
            fill=fill,
        )
        assert event.event_type == TradeEventType.FILL
        assert event.fill is not None
        assert event.fill.fill_qty == Decimal("10")


class TestMockTradeStream:
    """Tests for MockTradeStream."""

    async def test_mock_stream_connect(self):
        """Test mock stream connection."""
        stream = MockTradeStream()
        assert not stream.connected

        result = await stream.connect()
        assert result is True
        assert stream.connected

    async def test_mock_stream_disconnect(self):
        """Test mock stream disconnection."""
        stream = MockTradeStream()
        await stream.connect()
        await stream.subscribe()

        await stream.disconnect()
        assert not stream.connected
        assert not stream.subscribed

    async def test_mock_stream_subscribe(self):
        """Test mock stream subscription."""
        stream = MockTradeStream()
        await stream.connect()

        result = await stream.subscribe()
        assert result is True
        assert stream.subscribed

    async def test_mock_stream_subscribe_not_connected(self):
        """Test subscription fails when not connected."""
        stream = MockTradeStream()
        result = await stream.subscribe()
        assert result is False

    async def test_mock_stream_add_fill(self):
        """Test adding a fill event."""
        stream = MockTradeStream()
        stream.add_fill(
            order_id="order-123",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.25"),
            client_order_id="client-456",
        )

        # Event should be in queue
        event = stream._event_queue.get_nowait()
        assert event.event_type == TradeEventType.FILL
        assert event.symbol == "AAPL"
        assert event.fill is not None
        assert event.fill.fill_qty == Decimal("10")

    async def test_mock_stream_add_event(self):
        """Test adding a custom event."""
        stream = MockTradeStream()
        event = TradeEvent(
            event_type=TradeEventType.CANCELED,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=datetime.now(UTC),
        )
        stream.add_event(event)

        queued_event = stream._event_queue.get_nowait()
        assert queued_event.event_type == TradeEventType.CANCELED

    async def test_mock_stream_stream_pre_configured_events(self):
        """Test streaming pre-configured events."""
        events = [
            TradeEvent(
                event_type=TradeEventType.NEW,
                order_id=f"order-{i}",
                client_order_id=f"client-{i}",
                symbol="AAPL",
                side="buy",
                order_type="market",
                qty=Decimal("10"),
                filled_qty=Decimal("0"),
                filled_avg_price=None,
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]

        stream = MockTradeStream(events=events)
        received = []

        async def collect_events():
            async for event in stream.stream():
                received.append(event)
                if len(received) >= 3:
                    await stream.disconnect()

        await asyncio.wait_for(collect_events(), timeout=1.0)

        assert len(received) == 3
        assert all(e.event_type == TradeEventType.NEW for e in received)


class TestAlpacaTradeStream:
    """Tests for AlpacaTradeStream."""

    def test_stream_urls(self):
        """Test paper vs live URLs."""
        paper_stream = AlpacaTradeStream(TradeStreamConfig(paper=True))
        assert paper_stream.url == AlpacaTradeStream.PAPER_URL

        live_stream = AlpacaTradeStream(TradeStreamConfig(paper=False))
        assert live_stream.url == AlpacaTradeStream.LIVE_URL

    def test_initial_state(self):
        """Test initial stream state."""
        stream = AlpacaTradeStream()
        assert not stream.connected
        assert not stream.authenticated
        assert not stream.subscribed

    def test_parse_trade_event_fill(self):
        """Test parsing a fill event."""
        stream = AlpacaTradeStream()

        data = {
            "event": "fill",
            "order": {
                "id": "order-123",
                "client_order_id": "client-456",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "qty": "10",
                "filled_qty": "10",
                "filled_avg_price": "150.25",
                "updated_at": "2025-01-15T10:30:00Z",
            },
            "qty": "10",
            "price": "150.25",
            "timestamp": "2025-01-15T10:30:00Z",
        }

        event = stream._parse_trade_event(data)
        assert event is not None
        assert event.event_type == TradeEventType.FILL
        assert event.symbol == "AAPL"
        assert event.fill is not None
        assert event.fill.fill_qty == Decimal("10")
        assert event.fill.fill_price == Decimal("150.25")

    def test_parse_trade_event_canceled(self):
        """Test parsing a canceled event."""
        stream = AlpacaTradeStream()

        data = {
            "event": "canceled",
            "order": {
                "id": "order-123",
                "client_order_id": "client-456",
                "symbol": "AAPL",
                "side": "buy",
                "type": "limit",
                "qty": "10",
                "filled_qty": "0",
                "updated_at": "2025-01-15T10:30:00Z",
            },
        }

        event = stream._parse_trade_event(data)
        assert event is not None
        assert event.event_type == TradeEventType.CANCELED
        assert event.fill is None

    def test_parse_trade_event_unknown_type(self):
        """Test parsing an unknown event type returns None."""
        stream = AlpacaTradeStream()

        data = {
            "event": "unknown_event_type",
            "order": {
                "id": "order-123",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "qty": "10",
            },
        }

        event = stream._parse_trade_event(data)
        assert event is None

    def test_parse_trade_event_partial_fill(self):
        """Test parsing a partial fill event."""
        stream = AlpacaTradeStream()

        data = {
            "event": "partial_fill",
            "order": {
                "id": "order-123",
                "client_order_id": "client-456",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "qty": "100",
                "filled_qty": "50",
                "filled_avg_price": "150.25",
                "updated_at": "2025-01-15T10:30:00Z",
            },
            "qty": "50",
            "price": "150.25",
        }

        event = stream._parse_trade_event(data)
        assert event is not None
        assert event.event_type == TradeEventType.PARTIAL_FILL
        assert event.fill is not None
        assert event.fill.fill_qty == Decimal("50")
        assert event.fill.remaining_qty == Decimal("50")
