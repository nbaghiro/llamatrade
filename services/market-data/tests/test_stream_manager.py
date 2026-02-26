"""Tests for StreamManager class."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.streaming.manager import (
    StreamManager,
    get_stream_manager,
    reset_stream_manager,
)


@pytest.fixture
def manager():
    """Create a fresh StreamManager for each test."""
    return StreamManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestStreamManagerProperties:
    """Tests for StreamManager properties."""

    def test_connection_count_initially_zero(self, manager):
        """Test that connection count starts at 0."""
        assert manager.connection_count == 0

    async def test_connection_count_increases(self, manager, mock_websocket):
        """Test that connection count increases after connect."""
        await manager.connect(1, mock_websocket)
        assert manager.connection_count == 1

    async def test_connection_count_multiple(self, manager, mock_websocket):
        """Test multiple connections."""
        ws2 = AsyncMock()
        await manager.connect(1, mock_websocket)
        await manager.connect(2, ws2)
        assert manager.connection_count == 2

    def test_subscription_count_initially_zero(self, manager):
        """Test that subscription counts start at 0."""
        counts = manager.subscription_count
        assert counts["trades"] == 0
        assert counts["quotes"] == 0
        assert counts["bars"] == 0

    async def test_subscription_count_after_subscribe(self, manager, mock_websocket):
        """Test subscription counts after subscribing."""
        await manager.connect(1, mock_websocket)
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

    async def test_subscribed_symbols_after_subscribe(self, manager, mock_websocket):
        """Test subscribed symbols after subscribing."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=["GOOGL"], bars=["SPY"])

        symbols = manager.subscribed_symbols
        assert "AAPL" in symbols["trades"]
        assert "GOOGL" in symbols["quotes"]
        assert "SPY" in symbols["bars"]


class TestStreamManagerConnect:
    """Tests for connect/disconnect methods."""

    async def test_connect_adds_websocket(self, manager, mock_websocket):
        """Test that connect adds websocket to connections."""
        await manager.connect(1, mock_websocket)
        assert 1 in manager._connections
        assert manager._connections[1] is mock_websocket

    async def test_disconnect_removes_websocket(self, manager, mock_websocket):
        """Test that disconnect removes websocket."""
        await manager.connect(1, mock_websocket)
        await manager.disconnect(1)
        assert 1 not in manager._connections

    async def test_disconnect_nonexistent_client(self, manager):
        """Test disconnecting a client that doesn't exist."""
        # Should not raise
        await manager.disconnect(999)
        assert manager.connection_count == 0

    async def test_disconnect_removes_subscriptions(self, manager, mock_websocket):
        """Test that disconnect removes client's subscriptions."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=["AAPL"], bars=["AAPL"])

        await manager.disconnect(1)

        symbols = manager.subscribed_symbols
        assert "AAPL" not in symbols["trades"]
        assert "AAPL" not in symbols["quotes"]
        assert "AAPL" not in symbols["bars"]

    async def test_disconnect_calls_unsubscribe_callback(self, manager, mock_websocket):
        """Test that disconnect calls unsubscribe callback when last client leaves."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.disconnect(1)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]  # trades

    async def test_disconnect_handles_callback_error(self, manager, mock_websocket):
        """Test that disconnect handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Should not raise
        await manager.disconnect(1)
        assert manager.connection_count == 0


class TestStreamManagerSubscribe:
    """Tests for subscribe method."""

    async def test_subscribe_adds_to_subscription(self, manager, mock_websocket):
        """Test that subscribe adds client to subscription list."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert 1 in manager._trade_subs["AAPL"]

    async def test_subscribe_normalizes_symbols(self, manager, mock_websocket):
        """Test that subscribe normalizes symbols to uppercase."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["aapl"], quotes=["googl"], bars=["spy"])

        assert "AAPL" in manager.subscribed_symbols["trades"]
        assert "GOOGL" in manager.subscribed_symbols["quotes"]
        assert "SPY" in manager.subscribed_symbols["bars"]

    async def test_subscribe_calls_callback_for_new_symbol(self, manager, mock_websocket):
        """Test that subscribe callback is called for new symbols."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_subscribe=callback)

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]

    async def test_subscribe_no_callback_for_existing_symbol(self, manager, mock_websocket):
        """Test that subscribe callback is not called if symbol already has subscribers."""
        callback = MagicMock()

        # First client subscribes
        ws2 = AsyncMock()
        await manager.connect(1, mock_websocket)
        await manager.connect(2, ws2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Now set callback and subscribe second client
        manager.set_subscription_callbacks(on_subscribe=callback)
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        # Callback should not be called since AAPL already had a subscriber
        callback.assert_not_called()

    async def test_subscribe_handles_callback_error(self, manager, mock_websocket):
        """Test that subscribe handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_subscribe=callback)

        await manager.connect(1, mock_websocket)
        # Should not raise
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert "AAPL" in manager.subscribed_symbols["trades"]


class TestStreamManagerUnsubscribe:
    """Tests for unsubscribe method."""

    async def test_unsubscribe_removes_from_subscription(self, manager, mock_websocket):
        """Test that unsubscribe removes client from subscription list."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        assert 1 not in manager._trade_subs["AAPL"]

    async def test_unsubscribe_normalizes_symbols(self, manager, mock_websocket):
        """Test that unsubscribe normalizes symbols to uppercase."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["aapl"], quotes=[], bars=[])

        assert "AAPL" not in manager.subscribed_symbols["trades"]

    async def test_unsubscribe_calls_callback_when_last(self, manager, mock_websocket):
        """Test that unsubscribe callback is called when last client leaves."""
        callback = MagicMock()
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        callback.assert_called_once()
        args = callback.call_args[0]
        assert "AAPL" in args[0]

    async def test_unsubscribe_no_callback_if_others_remain(self, manager, mock_websocket):
        """Test that unsubscribe callback is not called if other subscribers remain."""
        callback = MagicMock()

        # Two clients subscribe
        ws2 = AsyncMock()
        await manager.connect(1, mock_websocket)
        await manager.connect(2, ws2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        manager.set_subscription_callbacks(on_unsubscribe=callback)
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Callback should not be called since client 2 is still subscribed
        callback.assert_not_called()

    async def test_unsubscribe_handles_callback_error(self, manager, mock_websocket):
        """Test that unsubscribe handles callback errors gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        manager.set_subscription_callbacks(on_unsubscribe=callback)

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        # Should not raise
        await manager.unsubscribe(1, trades=["AAPL"], quotes=[], bars=[])


class TestStreamManagerBroadcast:
    """Tests for broadcast methods."""

    async def test_broadcast_trade_sends_to_subscribers(self, manager, mock_websocket):
        """Test that broadcast_trade sends to subscribed clients."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        trade_data = {"price": 150.0, "size": 100}
        await manager.broadcast_trade("AAPL", trade_data)

        mock_websocket.send_json.assert_called_once()
        message = mock_websocket.send_json.call_args[0][0]
        assert message["type"] == "trade"
        assert message["symbol"] == "AAPL"

    async def test_broadcast_quote_sends_to_subscribers(self, manager, mock_websocket):
        """Test that broadcast_quote sends to subscribed clients."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=[], quotes=["AAPL"], bars=[])

        quote_data = {"bid_price": 150.0, "ask_price": 150.1}
        await manager.broadcast_quote("AAPL", quote_data)

        mock_websocket.send_json.assert_called_once()
        message = mock_websocket.send_json.call_args[0][0]
        assert message["type"] == "quote"
        assert message["symbol"] == "AAPL"

    async def test_broadcast_bar_sends_to_subscribers(self, manager, mock_websocket):
        """Test that broadcast_bar sends to subscribed clients."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

        bar_data = {"open": 150.0, "high": 151.0, "low": 149.0, "close": 150.5}
        await manager.broadcast_bar("AAPL", bar_data)

        mock_websocket.send_json.assert_called_once()
        message = mock_websocket.send_json.call_args[0][0]
        assert message["type"] == "bar"
        assert message["symbol"] == "AAPL"

    async def test_broadcast_normalizes_symbol(self, manager, mock_websocket):
        """Test that broadcast normalizes symbol to uppercase."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        await manager.broadcast_trade("aapl", {"price": 150.0})

        mock_websocket.send_json.assert_called_once()
        message = mock_websocket.send_json.call_args[0][0]
        assert message["symbol"] == "AAPL"

    async def test_broadcast_skips_unsubscribed_symbols(self, manager, mock_websocket):
        """Test that broadcast doesn't send for unsubscribed symbols."""
        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        # Broadcast for a different symbol
        await manager.broadcast_trade("GOOGL", {"price": 140.0})

        mock_websocket.send_json.assert_not_called()

    async def test_broadcast_to_multiple_clients(self, manager, mock_websocket):
        """Test that broadcast sends to all subscribed clients."""
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(1, mock_websocket)
        await manager.connect(2, ws2)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        await manager.subscribe(2, trades=["AAPL"], quotes=[], bars=[])

        await manager.broadcast_trade("AAPL", {"price": 150.0})

        mock_websocket.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    async def test_broadcast_disconnects_failed_clients(self, manager, mock_websocket):
        """Test that broadcast disconnects clients that fail to receive."""
        mock_websocket.send_json = AsyncMock(side_effect=Exception("Send failed"))

        await manager.connect(1, mock_websocket)
        await manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])

        await manager.broadcast_trade("AAPL", {"price": 150.0})

        # Client should be disconnected
        assert manager.connection_count == 0

    async def test_broadcast_empty_subscriptions(self, manager):
        """Test that broadcast handles empty subscription list."""
        # Should not raise
        await manager.broadcast_trade("AAPL", {"price": 150.0})


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
