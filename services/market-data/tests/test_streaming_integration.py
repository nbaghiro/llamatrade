"""End-to-end integration tests for streaming infrastructure.

These tests verify that data flows correctly through the entire streaming pipeline:
Alpaca WebSocket -> AlpacaStreamClient -> StreamBridge -> StreamManager -> Client Queue
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import BarData
from src.streaming.bridge import (
    BroadcastCircuitBreaker,
    StreamBridge,
    init_stream_bridge,
)
from src.streaming.manager import (
    QUEUE_MAX_SIZE,
    StreamManager,
    StreamMessage,
    StreamType,
    reset_stream_manager,
)


@pytest.fixture
def mock_alpaca_stream():
    """Create a mock Alpaca stream client for testing."""
    stream = MagicMock()
    stream.connected = True
    stream.authenticated = True
    stream.subscribe = AsyncMock(return_value=True)
    stream.unsubscribe = AsyncMock(return_value=True)
    stream.run = AsyncMock()
    stream.set_callbacks = MagicMock()
    return stream


@pytest.fixture
def stream_manager():
    """Create a fresh StreamManager for each test."""
    reset_stream_manager()
    return StreamManager()


@pytest.fixture
async def bridge_with_manager(mock_alpaca_stream, stream_manager):
    """Create a StreamBridge wired to a real StreamManager."""
    bridge = await init_stream_bridge(mock_alpaca_stream, stream_manager)
    yield bridge, stream_manager
    # Cleanup
    from src.streaming.bridge import close_stream_bridge

    await close_stream_bridge()


class TestStreamingEndToEnd:
    """End-to-end tests for the streaming pipeline."""

    async def test_data_flows_from_alpaca_to_client_queue(self, mock_alpaca_stream, stream_manager):
        """Verify data flows through the entire pipeline.

        This is the critical integration test that catches the callback wiring bug.
        """
        # Create bridge and wire callbacks
        bridge = StreamBridge(mock_alpaca_stream, stream_manager)

        # Wire up callbacks (this is what init_stream_bridge does)
        stream_manager.set_subscription_callbacks(
            on_subscribe=bridge.add_subscriptions,
            on_unsubscribe=bridge.remove_subscriptions,
        )

        # Simulate a client connecting and subscribing
        client_id = 1
        queue = await stream_manager.connect(client_id)
        await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])

        # Verify bridge received the subscription callback
        # (This would fail if callbacks weren't awaited properly)
        mock_alpaca_stream.subscribe.assert_called_once_with(trades=[], quotes=[], bars=["AAPL"])

        # Simulate Alpaca sending a bar
        bar_data: BarData = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Call the bridge's bar handler (simulating Alpaca callback)
        await bridge._broadcast_bar("AAPL", bar_data)

        # Verify data arrived in client queue
        assert not queue.empty()
        message: StreamMessage = queue.get_nowait()
        assert message.stream_type == StreamType.BAR
        assert message.symbol == "AAPL"
        assert message.data["close"] == 151.5

    async def test_subscription_callback_is_awaited(self, mock_alpaca_stream, stream_manager):
        """Verify that subscription callbacks are properly awaited.

        This catches the bug where callbacks were called but not awaited,
        creating coroutine objects that were never executed.
        """
        # Track whether add_subscriptions was actually called
        call_tracker = {"called": False}

        async def tracking_add_subscriptions(trades, quotes, bars):
            call_tracker["called"] = True
            # Verify we're actually running (not just a coroutine object)
            await asyncio.sleep(0)

        stream_manager.set_subscription_callbacks(
            on_subscribe=tracking_add_subscriptions,
            on_unsubscribe=None,
        )

        # Subscribe should trigger the callback
        client_id = 1
        await stream_manager.connect(client_id)
        await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])

        # If callbacks weren't awaited, this would be False
        assert call_tracker["called"], "Subscription callback was not awaited!"

    async def test_unsubscription_callback_is_awaited(self, mock_alpaca_stream, stream_manager):
        """Verify that unsubscription callbacks are properly awaited."""
        call_tracker = {"called": False}

        async def tracking_remove_subscriptions(trades, quotes, bars):
            call_tracker["called"] = True
            await asyncio.sleep(0)

        stream_manager.set_subscription_callbacks(
            on_subscribe=None,
            on_unsubscribe=tracking_remove_subscriptions,
        )

        client_id = 1
        await stream_manager.connect(client_id)
        await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])
        await stream_manager.disconnect(client_id)

        assert call_tracker["called"], "Unsubscription callback was not awaited!"


class TestQueueMaxSize:
    """Tests for queue size limits and backpressure."""

    async def test_queue_has_max_size(self, stream_manager):
        """Verify queues are created with maxsize to prevent memory exhaustion."""
        client_id = 1
        queue = await stream_manager.connect(client_id)

        # Queue should have maxsize set
        assert queue.maxsize == QUEUE_MAX_SIZE

    async def test_full_queue_drops_messages(self, stream_manager):
        """Verify messages are dropped when queue is full."""
        client_id = 1
        queue = await stream_manager.connect(client_id)
        await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])

        bar_data: BarData = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Fill the queue
        for _ in range(QUEUE_MAX_SIZE):
            await stream_manager.broadcast_bar("AAPL", bar_data)

        assert queue.full()

        # Next message should be dropped (not raise exception)
        await stream_manager.broadcast_bar("AAPL", bar_data)

        # Queue should still be at max size
        assert queue.qsize() == QUEUE_MAX_SIZE


class TestCircuitBreaker:
    """Tests for the broadcast circuit breaker."""

    def test_circuit_breaker_opens_after_threshold(self):
        """Verify circuit breaker opens after consecutive failures."""
        cb = BroadcastCircuitBreaker()

        # Record failures up to threshold
        for i in range(9):
            opened = cb.record_failure()
            assert not opened, f"Circuit opened early at failure {i + 1}"
            assert not cb.is_open

        # 10th failure should open the circuit
        opened = cb.record_failure()
        assert opened
        assert cb.is_open
        assert cb.consecutive_failures == 10

    def test_circuit_breaker_resets_on_success(self):
        """Verify circuit breaker resets after successful operation."""
        cb = BroadcastCircuitBreaker()

        # Get close to threshold
        for _ in range(8):
            cb.record_failure()

        # Success should reset
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert not cb.is_open

    def test_circuit_breaker_blocks_attempts_when_open(self):
        """Verify circuit breaker prevents attempts when open."""
        cb = BroadcastCircuitBreaker()

        # Open the circuit
        for _ in range(10):
            cb.record_failure()

        assert cb.is_open
        assert not cb.should_attempt()

    async def test_bridge_uses_circuit_breaker(self, mock_alpaca_stream, stream_manager):
        """Verify bridge respects circuit breaker state."""
        bridge = StreamBridge(mock_alpaca_stream, stream_manager)

        # Wire up manager
        stream_manager.set_subscription_callbacks(
            on_subscribe=bridge.add_subscriptions,
            on_unsubscribe=bridge.remove_subscriptions,
        )

        # Connect client
        client_id = 1
        await stream_manager.connect(client_id)
        await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])

        # Initially circuit is closed
        assert not bridge._circuit_breaker.is_open

        bar_data: BarData = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Broadcast should succeed and record success
        await bridge._broadcast_bar("AAPL", bar_data)
        assert bridge._circuit_breaker.total_successes == 1


class TestMultipleClients:
    """Tests for multiple concurrent client handling."""

    async def test_multiple_clients_receive_data(self, stream_manager):
        """Verify multiple clients each receive broadcast data."""
        # Connect multiple clients
        client_ids = [1, 2, 3]
        queues = {}

        for client_id in client_ids:
            queues[client_id] = await stream_manager.connect(client_id)
            await stream_manager.subscribe(client_id, trades=[], quotes=[], bars=["AAPL"])

        bar_data: BarData = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Broadcast once
        await stream_manager.broadcast_bar("AAPL", bar_data)

        # All clients should receive the message
        for client_id, queue in queues.items():
            assert not queue.empty(), f"Client {client_id} didn't receive message"
            message = queue.get_nowait()
            assert message.symbol == "AAPL"

    async def test_client_only_receives_subscribed_symbols(self, stream_manager):
        """Verify clients only receive data for symbols they subscribed to."""
        # Client 1 subscribes to AAPL
        queue1 = await stream_manager.connect(1)
        await stream_manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

        # Client 2 subscribes to TSLA
        queue2 = await stream_manager.connect(2)
        await stream_manager.subscribe(2, trades=[], quotes=[], bars=["TSLA"])

        bar_data: BarData = {
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.5,
            "volume": 1000000,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Broadcast AAPL
        await stream_manager.broadcast_bar("AAPL", bar_data)

        # Only client 1 should receive it
        assert not queue1.empty()
        assert queue2.empty()

        # Broadcast TSLA
        await stream_manager.broadcast_bar("TSLA", bar_data)

        # Only client 2 should receive it (queue1 already drained above check)
        assert not queue2.empty()


class TestReferenceCountingIntegration:
    """Tests for bridge reference counting integration."""

    async def test_alpaca_subscription_on_first_client(self, mock_alpaca_stream, stream_manager):
        """Verify Alpaca is subscribed when first client subscribes."""
        bridge = StreamBridge(mock_alpaca_stream, stream_manager)
        stream_manager.set_subscription_callbacks(
            on_subscribe=bridge.add_subscriptions,
            on_unsubscribe=bridge.remove_subscriptions,
        )

        # First client subscribes
        await stream_manager.connect(1)
        await stream_manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

        # Alpaca should be subscribed
        mock_alpaca_stream.subscribe.assert_called_once()

    async def test_alpaca_not_resubscribed_on_second_client(
        self, mock_alpaca_stream, stream_manager
    ):
        """Verify Alpaca is NOT resubscribed when second client subscribes to same symbol."""
        bridge = StreamBridge(mock_alpaca_stream, stream_manager)
        stream_manager.set_subscription_callbacks(
            on_subscribe=bridge.add_subscriptions,
            on_unsubscribe=bridge.remove_subscriptions,
        )

        # First client subscribes
        await stream_manager.connect(1)
        await stream_manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

        # Second client subscribes to same symbol
        await stream_manager.connect(2)
        await stream_manager.subscribe(2, trades=[], quotes=[], bars=["AAPL"])

        # Alpaca should only be subscribed once
        assert mock_alpaca_stream.subscribe.call_count == 1

    async def test_alpaca_unsubscribed_when_last_client_leaves(
        self, mock_alpaca_stream, stream_manager
    ):
        """Verify Alpaca is unsubscribed when last client unsubscribes."""
        bridge = StreamBridge(mock_alpaca_stream, stream_manager)
        stream_manager.set_subscription_callbacks(
            on_subscribe=bridge.add_subscriptions,
            on_unsubscribe=bridge.remove_subscriptions,
        )

        # Two clients subscribe
        await stream_manager.connect(1)
        await stream_manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])
        await stream_manager.connect(2)
        await stream_manager.subscribe(2, trades=[], quotes=[], bars=["AAPL"])

        # First client disconnects - Alpaca should NOT unsubscribe yet
        await stream_manager.disconnect(1)
        mock_alpaca_stream.unsubscribe.assert_not_called()

        # Second client disconnects - NOW Alpaca should unsubscribe
        await stream_manager.disconnect(2)
        mock_alpaca_stream.unsubscribe.assert_called_once()
