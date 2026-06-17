"""Tests for trading event streaming infrastructure (Redis Streams transport).

Order/position UI events carry the proto ``trading_pb2.OrderUpdate`` /
``trading_pb2.PositionUpdate`` directly on the bus (via ``OrderEvents`` /
``PositionEvents``), so the publisher builds protos and the subscriber yields
them unchanged.
"""

from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import pytest

from llamatrade_events import OrderEvents, PositionEvents
from llamatrade_proto.generated import trading_pb2

from src.streaming.publisher import TradingEventPublisher
from src.streaming.subscriber import TradingEventSubscriber


class _StubOrderEvents:
    """OrderEvents stand-in: records publishes; tail yields canned entries."""

    def __init__(self, entries: list[tuple[str, trading_pb2.OrderUpdate]] | None = None) -> None:
        self.published: list[tuple[str, trading_pb2.OrderUpdate]] = []
        self._entries = entries or []
        self.tail_calls: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, session_id, update, *, tenant_id="", user_id="", event_id=None):
        self.published.append((str(session_id), update))
        return "1-0"

    async def tail(self, session_id, *, from_cursor="$"):
        self.tail_calls.append((str(session_id), from_cursor))
        for entry in self._entries:
            yield entry

    async def close(self):
        self.closed = True


class _StubPositionEvents:
    """PositionEvents stand-in: records publishes; tail yields canned entries."""

    def __init__(self, entries: list[tuple[str, trading_pb2.PositionUpdate]] | None = None) -> None:
        self.published: list[tuple[str, trading_pb2.PositionUpdate]] = []
        self._entries = entries or []
        self.tail_calls: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, session_id, update, *, tenant_id="", user_id="", event_id=None):
        self.published.append((str(session_id), update))
        return "1-0"

    async def tail(self, session_id, *, from_cursor="$"):
        self.tail_calls.append((str(session_id), from_cursor))
        for entry in self._entries:
            yield entry

    async def close(self):
        self.closed = True


def _publisher() -> tuple[TradingEventPublisher, _StubOrderEvents, _StubPositionEvents]:
    orders = _StubOrderEvents()
    positions = _StubPositionEvents()
    publisher = TradingEventPublisher(
        orders_events=cast("OrderEvents", orders),
        positions_events=cast("PositionEvents", positions),
    )
    return publisher, orders, positions


class TestTradingEventPublisher:
    """Tests for TradingEventPublisher (streams transport, proto payloads)."""

    async def test_publish_order_update(self) -> None:
        publisher, orders, _ = _publisher()
        session_id = uuid4()
        update = trading_pb2.OrderUpdate(
            order=trading_pb2.Order(id="order-123", symbol="AAPL"),
            event_type="filled",
        )

        cursor = await publisher.publish_order_update(session_id, update)

        assert cursor == "1-0"
        assert len(orders.published) == 1
        published_session, published_update = orders.published[0]
        assert published_session == str(session_id)
        assert published_update.order.id == "order-123"
        assert published_update.event_type == "filled"

    async def test_publish_position_update(self) -> None:
        publisher, _, positions = _publisher()
        session_id = uuid4()
        update = trading_pb2.PositionUpdate(
            position=trading_pb2.Position(symbol="AAPL"),
            event_type="opened",
        )

        await publisher.publish_position_update(session_id, update)

        assert len(positions.published) == 1
        published_session, published_update = positions.published[0]
        assert published_session == str(session_id)
        assert published_update.position.symbol == "AAPL"
        assert published_update.event_type == "opened"

    async def test_publish_order_submitted(self) -> None:
        publisher, orders, _ = _publisher()
        session_id = uuid4()
        order_id = uuid4()
        await publisher.publish_order_submitted(
            session_id=session_id,
            order_id=order_id,
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
        )
        assert len(orders.published) == 1
        _, update = orders.published[0]
        assert update.event_type == "submitted"
        assert update.order.id == str(order_id)
        assert update.order.client_order_id == "alpaca-123"
        assert update.order.symbol == "AAPL"
        assert update.order.side == trading_pb2.ORDER_SIDE_BUY
        assert update.order.type == trading_pb2.ORDER_TYPE_MARKET
        assert update.order.status == trading_pb2.ORDER_STATUS_SUBMITTED
        assert update.order.quantity.value == "10.0"
        assert update.timestamp.seconds > 0

    async def test_publish_order_filled(self) -> None:
        publisher, orders, _ = _publisher()
        await publisher.publish_order_filled(
            session_id=uuid4(),
            order_id=uuid4(),
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side="sell",
            qty=10.0,
            order_type="limit",
            filled_qty=10.0,
            filled_avg_price=150.50,
        )
        _, update = orders.published[0]
        assert update.event_type == "filled"
        assert update.order.side == trading_pb2.ORDER_SIDE_SELL
        assert update.order.type == trading_pb2.ORDER_TYPE_LIMIT
        assert update.order.status == trading_pb2.ORDER_STATUS_FILLED
        assert update.order.filled_quantity.value == "10.0"
        assert update.order.average_fill_price.value == "150.5"

    async def test_publish_order_cancelled(self) -> None:
        publisher, orders, _ = _publisher()
        await publisher.publish_order_cancelled(
            session_id=uuid4(),
            order_id=uuid4(),
            alpaca_order_id=None,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            filled_qty=3.0,
        )
        _, update = orders.published[0]
        assert update.event_type == "cancelled"
        assert update.order.client_order_id == ""
        assert update.order.status == trading_pb2.ORDER_STATUS_CANCELLED
        assert update.order.filled_quantity.value == "3.0"

    async def test_publish_position_opened(self) -> None:
        publisher, _, positions = _publisher()
        await publisher.publish_position_opened(
            session_id=uuid4(),
            symbol="AAPL",
            qty=100.0,
            side="long",
            entry_price=150.0,
        )
        _, update = positions.published[0]
        assert update.event_type == "opened"
        assert update.position.symbol == "AAPL"
        assert update.position.side == trading_pb2.POSITION_SIDE_LONG
        assert update.position.quantity.value == "100.0"
        # cost_basis = qty * entry_price; average_entry_price = cost_basis / qty
        assert update.position.cost_basis.value == "15000.0"
        assert update.position.average_entry_price.value == "150.0"
        assert update.position.current_price.value == "150.0"
        assert update.timestamp.seconds > 0

    async def test_publish_position_closed(self) -> None:
        publisher, _, positions = _publisher()
        await publisher.publish_position_closed(
            session_id=uuid4(),
            symbol="AAPL",
            side="short",
            exit_price=144.0,
            realized_pnl=300.0,
        )
        _, update = positions.published[0]
        assert update.event_type == "closed"
        assert update.position.side == trading_pb2.POSITION_SIDE_SHORT
        assert update.position.quantity.value == "0.0"
        assert update.position.current_price.value == "144.0"

    async def test_close_closes_channels(self) -> None:
        publisher, orders, positions = _publisher()
        await publisher.close()
        assert orders.closed is True
        assert positions.closed is True

    async def test_close_without_connection(self) -> None:
        await TradingEventPublisher().close()  # Should not raise


class TestTradingEventSubscriber:
    """Tests for TradingEventSubscriber."""

    async def test_close_without_connection(self) -> None:
        await TradingEventSubscriber().close()  # Should not raise


class TestUiStreamTail:
    """Tail-read consumption with reconnect cursors."""

    @pytest.mark.asyncio
    async def test_tail_orders_yields_cursor_and_update(self) -> None:
        update = trading_pb2.OrderUpdate(
            order=trading_pb2.Order(id="o1", symbol="SPY", status=trading_pb2.ORDER_STATUS_FILLED),
            event_type="filled",
        )
        orders = _StubOrderEvents(entries=[("7-0", update)])
        subscriber = TradingEventSubscriber(orders_events=cast("OrderEvents", orders))

        results = [(cur, upd) async for cur, upd in subscriber.tail_orders("s1")]

        assert results[0][0] == "7-0"
        assert results[0][1].order.id == "o1"
        assert results[0][1].order.status == trading_pb2.ORDER_STATUS_FILLED
        assert orders.tail_calls == [("s1", "$")]

    @pytest.mark.asyncio
    async def test_tail_passes_reconnect_cursor(self) -> None:
        positions = _StubPositionEvents()
        subscriber = TradingEventSubscriber(positions_events=cast("PositionEvents", positions))

        async def _consume() -> AsyncIterator[None]:
            async for _ in subscriber.tail_positions("s1", last_seen_id="42-0"):
                yield None

        async for _ in _consume():
            pass

        assert positions.tail_calls == [("s1", "42-0")]

    @pytest.mark.asyncio
    async def test_close_closes_channels(self) -> None:
        orders = _StubOrderEvents()
        positions = _StubPositionEvents()
        subscriber = TradingEventSubscriber(
            orders_events=cast("OrderEvents", orders),
            positions_events=cast("PositionEvents", positions),
        )
        await subscriber.close()
        assert orders.closed is True
        assert positions.closed is True
