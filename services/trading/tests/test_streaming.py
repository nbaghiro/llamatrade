"""Tests for trading event streaming infrastructure (Redis Streams transport)."""

from typing import cast
from uuid import uuid4

import pytest

from llamatrade_common.events import Event, EventBus, EventType

from src.streaming.publisher import (
    OrderUpdate,
    PositionUpdate,
    TradingEventPublisher,
)
from src.streaming.subscriber import TradingEventSubscriber


class _StubBus:
    """EventBus stand-in: records publishes; tail yields canned entries."""

    def __init__(self, entries: list[tuple[str, dict[str, str]]] | None = None) -> None:
        self.published: list[tuple[str, dict[str, str], int | None]] = []
        self._entries = entries or []
        self.tail_calls: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, stream, fields, *, maxlen=None, approximate=True):
        self.published.append((stream, fields, maxlen))
        return "1-0"

    async def tail(self, stream, *, last_id="$", block_ms=5000, count=100):
        self.tail_calls.append((stream, last_id))
        for entry in self._entries:
            yield entry

    async def close(self):
        self.closed = True


def _publisher() -> tuple[TradingEventPublisher, _StubBus]:
    bus = _StubBus()
    return TradingEventPublisher(event_bus=cast("EventBus", bus)), bus


class TestOrderUpdate:
    """Tests for OrderUpdate dataclass."""

    def test_to_dict(self) -> None:
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id="alpaca-789",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
            filled_qty=10.0,
            filled_avg_price=150.50,
            update_type="filled",
        )
        result = update.to_dict()
        assert result["session_id"] == "session-123"
        assert result["order_id"] == "order-456"
        assert result["alpaca_order_id"] == "alpaca-789"
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"
        assert result["qty"] == 10.0
        assert result["status"] == "filled"
        assert result["filled_avg_price"] == 150.50
        assert "timestamp" in result

    def test_defaults(self) -> None:
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id=None,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="submitted",
        )
        assert update.filled_qty == 0.0
        assert update.filled_avg_price is None
        assert update.update_type == "status_change"


class TestPositionUpdate:
    """Tests for PositionUpdate dataclass."""

    def test_to_dict(self) -> None:
        update = PositionUpdate(
            session_id="session-123",
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
        )
        result = update.to_dict()
        assert result["session_id"] == "session-123"
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 100.0
        assert result["side"] == "long"
        assert result["market_value"] == 15500.0
        assert result["update_type"] == "opened"


class TestTradingEventPublisher:
    """Tests for TradingEventPublisher (streams transport)."""

    async def test_publish_order_update(self) -> None:
        publisher, bus = _publisher()
        session_id = uuid4()
        update = OrderUpdate(
            session_id=str(session_id),
            order_id="order-123",
            alpaca_order_id="alpaca-456",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
            update_type="filled",
        )

        entry_id = await publisher.publish_order_update(session_id, update)

        assert entry_id == "1-0"
        assert len(bus.published) == 1
        stream, fields, _maxlen = bus.published[0]
        assert stream == f"trading:orders:{session_id}"
        event = Event.from_redis_stream(fields)
        assert event.type == EventType.ORDER_FILLED
        assert event.data["order_id"] == "order-123"

    async def test_publish_position_update(self) -> None:
        publisher, bus = _publisher()
        session_id = uuid4()
        update = PositionUpdate(
            session_id=str(session_id),
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
        )

        await publisher.publish_position_update(session_id, update)

        assert len(bus.published) == 1
        stream, fields, _ = bus.published[0]
        assert stream == f"trading:positions:{session_id}"
        assert Event.from_redis_stream(fields).type == EventType.POSITION_OPENED

    async def test_publish_order_submitted(self) -> None:
        publisher, bus = _publisher()
        await publisher.publish_order_submitted(
            session_id=uuid4(),
            order_id=uuid4(),
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
        )
        assert len(bus.published) == 1
        assert Event.from_redis_stream(bus.published[0][1]).type == EventType.ORDER_SUBMITTED

    async def test_publish_order_filled(self) -> None:
        publisher, bus = _publisher()
        await publisher.publish_order_filled(
            session_id=uuid4(),
            order_id=uuid4(),
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            filled_qty=10.0,
            filled_avg_price=150.50,
        )
        assert Event.from_redis_stream(bus.published[0][1]).type == EventType.ORDER_FILLED

    async def test_publish_position_opened(self) -> None:
        publisher, bus = _publisher()
        await publisher.publish_position_opened(
            session_id=uuid4(),
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
        )
        assert Event.from_redis_stream(bus.published[0][1]).type == EventType.POSITION_OPENED

    async def test_publish_uses_ui_maxlen(self) -> None:
        from src.streaming.publisher import TRADING_UI_MAXLEN

        publisher, bus = _publisher()
        update = OrderUpdate(
            session_id="s1",
            order_id="o1",
            alpaca_order_id=None,
            symbol="SPY",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
        )
        await publisher.publish_order_update("s1", update)
        assert bus.published[0][2] == TRADING_UI_MAXLEN

    async def test_close_closes_bus(self) -> None:
        publisher, bus = _publisher()
        await publisher.close()
        assert bus.closed is True

    async def test_close_without_connection(self) -> None:
        await TradingEventPublisher().close()  # Should not raise


class TestTradingEventSubscriber:
    """Tests for TradingEventSubscriber."""

    async def test_parse_order_update(self) -> None:
        subscriber = TradingEventSubscriber()
        data = {
            "session_id": "session-123",
            "order_id": "order-456",
            "alpaca_order_id": "alpaca-789",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10.0,
            "order_type": "market",
            "status": "filled",
            "filled_qty": 10.0,
            "filled_avg_price": 150.50,
            "update_type": "filled",
            "timestamp": "2025-01-06T12:00:00Z",
        }
        result = subscriber._parse_order_update(data)
        assert result.session_id == "session-123"
        assert result.order_id == "order-456"
        assert result.status == "filled"
        assert result.filled_avg_price == 150.50

    async def test_parse_position_update(self) -> None:
        subscriber = TradingEventSubscriber()
        data = {
            "session_id": "session-123",
            "symbol": "AAPL",
            "qty": 100.0,
            "side": "long",
            "cost_basis": 15000.0,
            "market_value": 15500.0,
            "unrealized_pnl": 500.0,
            "unrealized_pnl_percent": 3.33,
            "current_price": 155.0,
            "update_type": "opened",
            "timestamp": "2025-01-06T12:00:00Z",
        }
        result = subscriber._parse_position_update(data)
        assert result.session_id == "session-123"
        assert result.symbol == "AAPL"
        assert result.qty == 100.0
        assert result.unrealized_pnl == 500.0

    async def test_close_without_connection(self) -> None:
        await TradingEventSubscriber().close()  # Should not raise


class TestUiStreamTail:
    """Tail-read consumption with reconnect cursors."""

    @pytest.mark.asyncio
    async def test_tail_orders_yields_cursor_and_update(self) -> None:
        update = OrderUpdate(
            session_id="s1",
            order_id="o1",
            alpaca_order_id="a1",
            symbol="SPY",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
        )
        entry = Event(type=EventType.ORDER_FILLED, data=update.to_dict()).to_redis_stream()
        bus = _StubBus(entries=[("7-0", entry)])
        subscriber = TradingEventSubscriber(event_bus=cast("EventBus", bus))

        results = [(cid, upd) async for cid, upd in subscriber.tail_orders("s1")]

        assert results[0][0] == "7-0"
        assert results[0][1].order_id == "o1"
        assert results[0][1].status == "filled"
        assert bus.tail_calls == [("trading:orders:s1", "$")]

    @pytest.mark.asyncio
    async def test_tail_passes_reconnect_cursor(self) -> None:
        bus = _StubBus()
        subscriber = TradingEventSubscriber(event_bus=cast("EventBus", bus))

        async for _ in subscriber.tail_positions("s1", last_seen_id="42-0"):
            pass

        assert bus.tail_calls == [("trading:positions:s1", "42-0")]

    @pytest.mark.asyncio
    async def test_close_closes_bus(self) -> None:
        bus = _StubBus()
        subscriber = TradingEventSubscriber(event_bus=cast("EventBus", bus))
        await subscriber.close()
        assert bus.closed is True
