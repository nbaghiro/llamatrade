"""Tests for StreamManager class."""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.models import TradeData
from src.streaming.manager import (
    StreamManager,
    StreamMessage,
    StreamType,
    get_stream_manager,
    reset_stream_manager,
)


@pytest.fixture
def manager():
    """Create a fresh StreamManager for each test."""
    return StreamManager()


class TestStreamManagerProperties:
    """Tests for StreamManager properties."""

    def test_connection_count_initially_zero(self, manager):
        """Test that connection count starts at 0."""
        assert manager.connection_count == 0

    async def test_connection_count_increases(self, manager):
        """Test that connection count increases after connect."""
        await manager.connect(1)
        assert manager.connection_count == 1

    async def test_connection_count_multiple(self, manager):
        """Test multiple connections."""
        await manager.connect(1)
        await manager.connect(2)
        assert manager.connection_count == 2

    def test_subscription_count_initially_zero(self, manager):
        """Test that subscription counts start at 0."""
        counts = manager.subscription_count
        assert counts["trades"] == 0
        assert counts["quotes"] == 0
        assert counts["bars"] == 0

    async def test_subscription_count_after_subscribe(self, manager):
        """Test subscription counts after subscribing."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL", "TSLA"], quotes=["AAPL"], bars=[])

        counts = manager.subscription_count
        assert counts["trades"] == 2
        assert counts["quotes"] == 1
        assert counts["bars"] == 0

    def test_subscribed_symbols_initially_empty(self, manager):
        """Test that subscribed symbols starts empty."""
        symbols = manager.subscribed_symbols
        assert symbols["trades"] == set()
        assert symbols["quotes"] == set()
        assert symbols["bars"] == set()

    async def test_subscribed_symbols_after_subscribe(self, manager):
        """Test subscribed symbols after subscribing."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=["GOOGL"], bars=["SPY"])

        symbols = manager.subscribed_symbols
        assert "AAPL" in symbols["trades"]
        assert "GOOGL" in symbols["quotes"]
        assert "SPY" in symbols["bars"]


class TestStreamManagerConnect:
    """Tests for connect/disconnect methods."""

    async def test_connect_returns_queue(self, manager):
        """Test that connect returns an async queue."""
        queue = await manager.connect(1)
        assert isinstance(queue, asyncio.Queue)

    async def test_connect_adds_queue(self, manager):
        """Test that connect adds queue to connections."""
        await manager.connect(1)
        assert 1 in manager._queues
        assert isinstance(manager._queues[1], asyncio.Queue)

    async def test_disconnect_removes_queue(self, manager):
        """Test that disconnect removes queue."""
        await manager.connect(1)
        await manager.disconnect(1)
        assert 1 not in manager._queues

    async def test_disconnect_nonexistent_client(self, manager):
        """Test disconnecting a client that doesn't exist."""
        # Should not raise
        await manager.disconnect(999)
        assert manager.connection_count == 0

    async def test_disconnect_removes_subscriptions(self, manager):
        """Test that disconnect removes client's subscriptions."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=["AAPL"], bars=["AAPL"])

        await manager.disconnect(1)

        symbols = manager.subscribed_symbols
        assert "AAPL" not in symbols["trades"]
        assert "AAPL" not in symbols["quotes"]
        assert "AAPL" not in symbols["bars"]

    async def test_disconnect_calls_unsubscribe_callback(self, manager):
        """Test that disconnect calls unsubscribe callback when last client leaves."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.disconnect(1)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]  # trades

    async def test_disconnect_handles_callback_error(self, manager):
        """Test that disconnect handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Should not raise
        await manager.disconnect(1)
        assert manager.connection_count == 0


class TestStreamManagerSubscribe:
    """Tests for subscribe method."""

    async def test_subscribe_adds_to_subscription(self, manager):
        """Test that subscribe adds client to subscription list."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert 1 in manager._trade_subs["AAPL"]

    async def test_subscribe_normalizes_symbols(self, manager):
        """Test that subscribe normalizes symbols to uppercase."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["aapl"], quotes=["googl"], bars=["spy"])

        assert "AAPL" in manager.subscribed_symbols["trades"]
        assert "GOOGL" in manager.subscribed_symbols["quotes"]
        assert "SPY" in manager.subscribed_symbols["bars"]

    async def test_subscribe_calls_callback_for_new_symbol(self, manager):
        """Test that subscribe callback is called for new symbols."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_subscribe=callback)

        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]

    async def test_subscribe_no_callback_for_existing_symbol(self, manager):
        """Test that subscribe callback is not called if symbol already has subscribers."""
        callback = MagicMock()

        # First client subscribes
        await manager.connect(1)
        await manager.connect(2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Now set callback and subscribe second client
        manager.set_subscription_callbacks(on_subscribe=callback)
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        # Callback should not be called since AAPL already had a subscriber
        callback.assert_not_called()

    async def test_subscribe_handles_callback_error(self, manager):
        """Test that subscribe handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_subscribe=callback)

        await manager.connect(1)
        # Should not raise
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert "AAPL" in manager.subscribed_symbols["trades"]


class TestStreamManagerUnsubscribe:
    """Tests for unsubscribe method."""

    async def test_unsubscribe_removes_from_subscription(self, manager):
        """Test that unsubscribe removes client from subscription list."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert 1 not in manager._trade_subs["AAPL"]

    async def test_unsubscribe_normalizes_symbols(self, manager):
        """Test that unsubscribe normalizes symbols to uppercase."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["aapl"], quotes=[], bars=[])

        assert "AAPL" not in manager.subscribed_symbols["trades"]

    async def test_unsubscribe_calls_callback_when_last(self, manager):
        """Test that unsubscribe callback is called when last client leaves."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]

    async def test_unsubscribe_no_callback_if_others_remain(self, manager):
        """Test that unsubscribe callback is not called if other subscribers remain."""
        callback = MagicMock()

        # Two clients subscribe
        await manager.connect(1)
        await manager.connect(2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        manager.set_subscription_callbacks(on_unsubscribe=callback)
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Callback should not be called since client 2 is still subscribed
        callback.assert_not_called()

    async def test_unsubscribe_handles_callback_error(self, manager):
        """Test that unsubscribe handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        # Should not raise
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])


class TestStreamManagerBroadcast:
    """Tests for broadcast methods."""

    async def test_broadcast_trade_sends_to_queue(self, manager):
        """Test that broadcast_trade sends to subscribed client queues."""
        queue = await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        trade_data = {"price": 150.0, "size": 100}
        await manager.broadcast_trade("AAPL", trade_data)

        # Check the message in the queue
        message = queue.get_nowait()
        assert isinstance(message, StreamMessage)
        assert message.stream_type == StreamType.TRADE
        assert message.symbol == "AAPL"
        assert message.data == trade_data

    async def test_broadcast_quote_sends_to_queue(self, manager):
        """Test that broadcast_quote sends to subscribed client queues."""
        queue = await manager.connect(1)
        await manager.subscribe(1, trades=[], quotes=["AAPL"], bars=[])

        quote_data = {"bid_price": 150.0, "ask_price": 150.1}
        await manager.broadcast_quote("AAPL", quote_data)

        message = queue.get_nowait()
        assert message.stream_type == StreamType.QUOTE
        assert message.symbol == "AAPL"

    async def test_broadcast_bar_sends_to_queue(self, manager):
        """Test that broadcast_bar sends to subscribed client queues."""
        queue = await manager.connect(1)
        await manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

        bar_data = {"open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5}
        await manager.broadcast_bar("AAPL", bar_data)

        message = queue.get_nowait()
        assert message.stream_type == StreamType.BAR
        assert message.symbol == "AAPL"

    async def test_broadcast_normalizes_symbol(self, manager):
        """Test that broadcast normalizes symbol to uppercase."""
        queue = await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        await manager.broadcast_trade("aapl", {"price": 150.0})

        message = queue.get_nowait()
        assert message.symbol == "AAPL"

    async def test_broadcast_skips_unsubscribed_symbols(self, manager):
        """Test that broadcast doesn't send for unsubscribed symbols."""
        queue = await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Broadcast for a different symbol
        await manager.broadcast_trade("GOOGL", {"price": 140.0})

        assert queue.empty()

    async def test_broadcast_to_multiple_clients(self, manager):
        """Test that broadcast sends to all subscribed clients."""
        queue1 = await manager.connect(1)
        queue2 = await manager.connect(2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        await manager.broadcast_trade("AAPL", {"price": 150.0})

        # Both queues should have the message
        msg1 = queue1.get_nowait()
        msg2 = queue2.get_nowait()
        assert msg1.symbol == "AAPL"
        assert msg2.symbol == "AAPL"

    async def test_broadcast_disconnects_clients_without_queue(self, manager):
        """Test that broadcast disconnects clients whose queue is missing."""
        await manager.connect(1)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Manually remove the queue to simulate disconnection
        del manager._queues[1]

        await manager.broadcast_trade("AAPL", {"price": 150.0})

        # Client should be disconnected (subscriptions removed)
        assert "AAPL" not in manager.subscribed_symbols["trades"]

    async def test_broadcast_empty_subscriptions(self, manager):
        """Test that broadcast handles empty subscription list."""
        # Should not raise
        await manager.broadcast_trade("AAPL", {"price": 150.0})


class TestStreamMessageModel:
    """Tests for StreamMessage dataclass."""

    def test_stream_message_creation(self):
        """Test creating a StreamMessage."""
        data: TradeData = {
            "price": 150.0,
            "size": 100,
            "exchange": "NASDAQ",
            "timestamp": "2024-01-15T16:00:00Z",
        }
        msg = StreamMessage(
            stream_type=StreamType.TRADE,
            symbol="AAPL",
            data=data,
        )

        assert msg.stream_type == StreamType.TRADE
        assert msg.symbol == "AAPL"
        assert msg.data == data

    def test_stream_type_enum(self):
        """Test StreamType enum values."""
        assert StreamType.TRADE.value == "trade"
        assert StreamType.QUOTE.value == "quote"
        assert StreamType.BAR.value == "bar"


class TestStreamManagerCallbacks:
    """Tests for subscription callbacks."""

    def test_set_subscription_callbacks(self, manager):
        """Test setting subscription callbacks."""
        on_sub = MagicMock()
        on_unsub = MagicMock()

        manager.set_subscription_callbacks(on_subscribe=on_sub, on_unsubscribe=on_unsub)

        assert manager._on_subscribe is on_sub
        assert manager._on_unsubscribe is on_unsub

    def test_set_callbacks_with_none(self, manager):
        """Test setting callbacks to None."""
        manager.set_subscription_callbacks(on_subscribe=None, on_unsubscribe=None)

        assert manager._on_subscribe is None
        assert manager._on_unsubscribe is None


class TestSingletonFunctions:
    """Tests for singleton accessor functions."""

    def test_get_stream_manager_creates_singleton(self):
        """Test that get_stream_manager creates a singleton."""
        reset_stream_manager()

        manager1 = get_stream_manager()
        manager2 = get_stream_manager()

        assert manager1 is manager2

        reset_stream_manager()

    def test_reset_stream_manager_clears_singleton(self):
        """Test that reset_stream_manager clears the singleton."""
        manager1 = get_stream_manager()
        reset_stream_manager()
        manager2 = get_stream_manager()

        assert manager1 is not manager2

        reset_stream_manager()
