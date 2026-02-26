"""Tests for StreamBridge class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models import BarData, QuoteData, TradeData
from src.streaming.alpaca_stream import AlpacaStreamClient
from src.streaming.bridge import (
    StreamBridge,
    close_stream_bridge,
    get_stream_bridge,
    init_stream_bridge,
)
from src.streaming.manager import StreamManager


@pytest.fixture
def mock_alpaca_stream():
    """Create a mock Alpaca stream client."""
    stream = MagicMock(spec=AlpacaStreamClient)
    stream.connected = True
    stream.authenticated = True
    stream.set_callbacks = MagicMock()
    stream.subscribe = AsyncMock(return_value=True)
    stream.unsubscribe = AsyncMock(return_value=True)
    stream.run = AsyncMock()
    return stream


@pytest.fixture
def mock_stream_manager():
    """Create a mock StreamManager."""
    manager = MagicMock(spec=StreamManager)
    manager.broadcast_trade = AsyncMock()
    manager.broadcast_quote = AsyncMock()
    manager.broadcast_bar = AsyncMock()
    return manager


@pytest.fixture
def bridge(mock_alpaca_stream, mock_stream_manager):
    """Create a test bridge."""
    return StreamBridge(mock_alpaca_stream, mock_stream_manager)


class TestStreamBridgeInit:
    """Tests for StreamBridge initialization."""

    def test_init_sets_callbacks(self, mock_alpaca_stream, mock_stream_manager):
        """Test that init sets up Alpaca callbacks."""
        StreamBridge(mock_alpaca_stream, mock_stream_manager)

        mock_alpaca_stream.set_callbacks.assert_called_once()
        kwargs = mock_alpaca_stream.set_callbacks.call_args[1]
        assert "on_trade" in kwargs
        assert "on_quote" in kwargs
        assert "on_bar" in kwargs

    def test_init_state(self, bridge):
        """Test initial bridge state."""
        assert bridge._running is False
        assert bridge._run_task is None
        assert len(bridge._trade_refs) == 0
        assert len(bridge._quote_refs) == 0
        assert len(bridge._bar_refs) == 0


class TestStreamBridgeStartStop:
    """Tests for start/stop methods."""

    async def test_start_creates_task(self, bridge, mock_alpaca_stream):
        """Test that start creates a run task."""
        await bridge.start()

        assert bridge._running is True
        assert bridge._run_task is not None

        await bridge.stop()

    async def test_start_idempotent(self, bridge):
        """Test that start is idempotent."""
        await bridge.start()
        task1 = bridge._run_task

        await bridge.start()
        task2 = bridge._run_task

        assert task1 is task2

        await bridge.stop()

    async def test_stop_cancels_task(self, bridge):
        """Test that stop cancels the run task."""
        await bridge.start()
        assert bridge._run_task is not None

        await bridge.stop()

        assert bridge._running is False
        assert bridge._run_task is None

    async def test_stop_handles_cancelled_error(self, bridge):
        """Test that stop handles CancelledError gracefully."""
        await bridge.start()
        await bridge.stop()

        # Should not raise
        assert bridge._run_task is None


class TestStreamBridgeAddSubscriptions:
    """Tests for add_subscriptions method."""

    async def test_add_subscriptions_increments_refs(self, bridge):
        """Test that add_subscriptions increments reference counts."""
        await bridge.add_subscriptions(trades=["AAPL"], quotes=["GOOGL"], bars=["SPY"])

        assert bridge._trade_refs["AAPL"] == 1
        assert bridge._quote_refs["GOOGL"] == 1
        assert bridge._bar_refs["SPY"] == 1

    async def test_add_subscriptions_normalizes_symbols(self, bridge):
        """Test that symbols are normalized to uppercase."""
        await bridge.add_subscriptions(trades=["aapl"])

        assert bridge._trade_refs["AAPL"] == 1

    async def test_add_subscriptions_multiple_clients(self, bridge):
        """Test adding subscriptions from multiple clients."""
        await bridge.add_subscriptions(trades=["AAPL"])
        await bridge.add_subscriptions(trades=["AAPL"])

        assert bridge._trade_refs["AAPL"] == 2

    async def test_add_subscriptions_subscribes_to_alpaca(self, bridge, mock_alpaca_stream):
        """Test that new subscriptions are forwarded to Alpaca."""
        await bridge.add_subscriptions(trades=["AAPL"])

        mock_alpaca_stream.subscribe.assert_called_once_with(
            trades=["AAPL"],
            quotes=[],
            bars=[],
        )

    async def test_add_subscriptions_no_duplicate_alpaca_sub(self, bridge, mock_alpaca_stream):
        """Test that existing subscriptions don't trigger Alpaca subscribe."""
        await bridge.add_subscriptions(trades=["AAPL"])
        mock_alpaca_stream.subscribe.reset_mock()

        await bridge.add_subscriptions(trades=["AAPL"])

        mock_alpaca_stream.subscribe.assert_not_called()

    async def test_add_subscriptions_when_disconnected(self, bridge, mock_alpaca_stream):
        """Test adding subscriptions when Alpaca is disconnected."""
        mock_alpaca_stream.connected = False

        await bridge.add_subscriptions(trades=["AAPL"])

        # Should still track refs but not call subscribe
        assert bridge._trade_refs["AAPL"] == 1
        mock_alpaca_stream.subscribe.assert_not_called()

    async def test_add_subscriptions_when_not_authenticated(self, bridge, mock_alpaca_stream):
        """Test adding subscriptions when not authenticated."""
        mock_alpaca_stream.authenticated = False

        await bridge.add_subscriptions(trades=["AAPL"])

        mock_alpaca_stream.subscribe.assert_not_called()


class TestStreamBridgeRemoveSubscriptions:
    """Tests for remove_subscriptions method."""

    async def test_remove_subscriptions_decrements_refs(self, bridge):
        """Test that remove_subscriptions decrements reference counts."""
        await bridge.add_subscriptions(trades=["AAPL"])
        await bridge.add_subscriptions(trades=["AAPL"])

        await bridge.remove_subscriptions(trades=["AAPL"])

        assert bridge._trade_refs["AAPL"] == 1

    async def test_remove_subscriptions_removes_when_zero(self, bridge):
        """Test that symbol is removed when ref count reaches zero."""
        await bridge.add_subscriptions(trades=["AAPL"])

        await bridge.remove_subscriptions(trades=["AAPL"])

        assert "AAPL" not in bridge._trade_refs

    async def test_remove_subscriptions_normalizes_symbols(self, bridge):
        """Test that symbols are normalized to uppercase."""
        await bridge.add_subscriptions(trades=["AAPL"])

        await bridge.remove_subscriptions(trades=["aapl"])

        assert "AAPL" not in bridge._trade_refs

    async def test_remove_subscriptions_unsubscribes_from_alpaca(self, bridge, mock_alpaca_stream):
        """Test that last unsubscription triggers Alpaca unsubscribe."""
        await bridge.add_subscriptions(trades=["AAPL"])
        mock_alpaca_stream.reset_mock()

        await bridge.remove_subscriptions(trades=["AAPL"])

        mock_alpaca_stream.unsubscribe.assert_called_once_with(
            trades=["AAPL"],
            quotes=[],
            bars=[],
        )

    async def test_remove_subscriptions_no_alpaca_unsub_if_others(self, bridge, mock_alpaca_stream):
        """Test that Alpaca unsubscribe is not called if others remain subscribed."""
        await bridge.add_subscriptions(trades=["AAPL"])
        await bridge.add_subscriptions(trades=["AAPL"])
        mock_alpaca_stream.reset_mock()

        await bridge.remove_subscriptions(trades=["AAPL"])

        mock_alpaca_stream.unsubscribe.assert_not_called()

    async def test_remove_subscriptions_when_disconnected(self, bridge, mock_alpaca_stream):
        """Test removing subscriptions when Alpaca is disconnected."""
        mock_alpaca_stream.connected = True
        await bridge.add_subscriptions(trades=["AAPL"])
        mock_alpaca_stream.connected = False

        await bridge.remove_subscriptions(trades=["AAPL"])

        # Should still remove refs but not call unsubscribe
        assert "AAPL" not in bridge._trade_refs
        mock_alpaca_stream.unsubscribe.assert_not_called()

    async def test_remove_subscriptions_nonexistent(self, bridge):
        """Test removing subscriptions that don't exist."""
        # Should not raise
        await bridge.remove_subscriptions(trades=["AAPL"])


class TestStreamBridgeHandlers:
    """Tests for data handlers."""

    def test_handle_trade_creates_task(self, bridge, mock_stream_manager):
        """Test that _handle_trade creates a broadcast task."""
        trade_data = TradeData(
            price=150.0,
            size=100,
            exchange="V",
            timestamp="2024-01-15T09:30:00Z",
        )

        with patch("asyncio.create_task") as mock_create_task:
            bridge._handle_trade("AAPL", trade_data)

        mock_create_task.assert_called_once()

    def test_handle_quote_creates_task(self, bridge, mock_stream_manager):
        """Test that _handle_quote creates a broadcast task."""
        quote_data = QuoteData(
            bid_price=150.0,
            bid_size=100,
            ask_price=150.1,
            ask_size=200,
            timestamp="2024-01-15T09:30:00Z",
        )

        with patch("asyncio.create_task") as mock_create_task:
            bridge._handle_quote("AAPL", quote_data)

        mock_create_task.assert_called_once()

    def test_handle_bar_creates_task(self, bridge, mock_stream_manager):
        """Test that _handle_bar creates a broadcast task."""
        bar_data = BarData(
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=10000,
            timestamp="2024-01-15T09:30:00Z",
        )

        with patch("asyncio.create_task") as mock_create_task:
            bridge._handle_bar("AAPL", bar_data)

        mock_create_task.assert_called_once()


class TestStreamBridgeBroadcast:
    """Tests for broadcast methods."""

    async def test_broadcast_trade_calls_manager(self, bridge, mock_stream_manager):
        """Test that _broadcast_trade calls StreamManager."""
        trade_data = TradeData(price=150.0, size=100, exchange="V", timestamp="")

        await bridge._broadcast_trade("AAPL", trade_data)

        mock_stream_manager.broadcast_trade.assert_called_once_with("AAPL", trade_data)

    async def test_broadcast_quote_calls_manager(self, bridge, mock_stream_manager):
        """Test that _broadcast_quote calls StreamManager."""
        quote_data = QuoteData(
            bid_price=150.0, bid_size=100, ask_price=150.1, ask_size=200, timestamp=""
        )

        await bridge._broadcast_quote("AAPL", quote_data)

        mock_stream_manager.broadcast_quote.assert_called_once_with("AAPL", quote_data)

    async def test_broadcast_bar_calls_manager(self, bridge, mock_stream_manager):
        """Test that _broadcast_bar calls StreamManager."""
        bar_data = BarData(
            open=150.0, high=151.0, low=149.0, close=150.5, volume=10000, timestamp=""
        )

        await bridge._broadcast_bar("AAPL", bar_data)

        mock_stream_manager.broadcast_bar.assert_called_once_with("AAPL", bar_data)

    async def test_broadcast_trade_handles_error(self, bridge, mock_stream_manager):
        """Test that broadcast handles errors gracefully."""
        mock_stream_manager.broadcast_trade = AsyncMock(side_effect=Exception("Broadcast failed"))
        trade_data = TradeData(price=150.0, size=100, exchange="V", timestamp="")

        # Should not raise
        await bridge._broadcast_trade("AAPL", trade_data)


class TestGlobalFunctions:
    """Tests for global singleton functions."""

    def test_get_stream_bridge_returns_none_initially(self):
        """Test that get_stream_bridge returns None when not initialized."""
        import src.streaming.bridge as module

        module._bridge = None

        result = get_stream_bridge()

        assert result is None

    async def test_init_stream_bridge(self, mock_alpaca_stream, mock_stream_manager):
        """Test initializing the stream bridge."""
        import src.streaming.bridge as module

        module._bridge = None

        result = await init_stream_bridge(mock_alpaca_stream, mock_stream_manager)

        assert result is not None
        assert isinstance(result, StreamBridge)

        await result.stop()
        module._bridge = None

    async def test_close_stream_bridge(self, mock_alpaca_stream, mock_stream_manager):
        """Test closing the stream bridge."""
        import src.streaming.bridge as module

        await init_stream_bridge(mock_alpaca_stream, mock_stream_manager)
        assert module._bridge is not None

        await close_stream_bridge()

        assert module._bridge is None

    async def test_close_stream_bridge_when_none(self):
        """Test closing when no bridge exists."""
        import src.streaming.bridge as module

        module._bridge = None

        # Should not raise
        await close_stream_bridge()
