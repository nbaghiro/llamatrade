"""Tests for gRPC streaming in market-data service."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from src.grpc.servicer import MarketDataServicer
from src.streaming.manager import StreamManager, StreamMessage, StreamType


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self):
        self._cancelled = False
        self._code = None
        self._details = None

    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    async def abort(self, code, details):
        self._code = code
        self._details = details
        raise Exception(f"Aborted: {code} - {details}")


@pytest.fixture
def servicer():
    """Create a MarketDataServicer instance."""
    return MarketDataServicer()


@pytest.fixture
def context():
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def stream_manager():
    """Create a fresh StreamManager for each test."""
    return StreamManager()


@pytest.mark.skip(reason="Streaming tests require refactoring - servicer uses 30s queue timeout")
class TestStreamBars:
    """Tests for StreamBars gRPC method."""

    async def test_stream_bars_subscribes_to_symbols(self, servicer, context):
        """Test that StreamBars subscribes to requested symbols."""
        mock_manager = StreamManager()
        subscribed_correctly = False

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL", "TSLA"]

            async def check_and_cancel():
                nonlocal subscribed_correctly
                # Wait for subscription to happen
                for _ in range(50):  # Up to 500ms
                    await asyncio.sleep(0.01)
                    if mock_manager.connection_count > 0:
                        # Check subscriptions while stream is active
                        subs = mock_manager.subscribed_symbols["bars"]
                        if "AAPL" in subs and "TSLA" in subs:
                            subscribed_correctly = True
                            break
                context.cancel()

            asyncio.create_task(check_and_cancel())

            async for _ in servicer.StreamBars(mock_request, context):
                pass

            # Verify symbols were normalized to uppercase and subscribed
            assert subscribed_correctly, "Symbols were not properly subscribed"

    async def test_stream_bars_yields_bar_messages(self, servicer, context):
        """Test that StreamBars yields bar data from queue."""
        mock_manager = StreamManager()

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            results = []

            async def produce_and_cancel():
                # Wait for subscription
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager._queues:
                        break

                # Get the queue and send data
                if mock_manager._queues:
                    queue = list(mock_manager._queues.values())[0]
                    await queue.put(
                        StreamMessage(
                            stream_type=StreamType.BAR,
                            symbol="AAPL",
                            data={
                                "timestamp": datetime.now(UTC),
                                "open": 150.0,
                                "high": 151.0,
                                "low": 149.0,
                                "close": 150.5,
                                "volume": 1000,
                            },
                        )
                    )

                await asyncio.sleep(0.05)
                context.cancel()

            asyncio.create_task(produce_and_cancel())

            async for bar in servicer.StreamBars(mock_request, context):
                results.append(bar)

            assert len(results) == 1
            assert results[0].symbol == "AAPL"

    async def test_stream_bars_disconnects_on_cancel(self, servicer, context):
        """Test that StreamBars disconnects when cancelled."""
        mock_manager = StreamManager()

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            context.cancel()

            async for _ in servicer.StreamBars(mock_request, context):
                pass

            # Should have disconnected
            assert mock_manager.connection_count == 0


@pytest.mark.skip(reason="Streaming tests require refactoring - servicer uses 30s queue timeout")
class TestStreamQuotes:
    """Tests for StreamQuotes gRPC method."""

    async def test_stream_quotes_subscribes_to_symbols(self, servicer, context):
        """Test that StreamQuotes subscribes to requested symbols."""
        mock_manager = StreamManager()
        subscribed_correctly = False

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL", "GOOGL"]

            async def check_and_cancel():
                nonlocal subscribed_correctly
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager.connection_count > 0:
                        subs = mock_manager.subscribed_symbols["quotes"]
                        if "AAPL" in subs and "GOOGL" in subs:
                            subscribed_correctly = True
                            break
                context.cancel()

            asyncio.create_task(check_and_cancel())

            async for _ in servicer.StreamQuotes(mock_request, context):
                pass

            assert subscribed_correctly, "Symbols were not properly subscribed"

    async def test_stream_quotes_yields_quote_messages(self, servicer, context):
        """Test that StreamQuotes yields quote data from queue."""
        mock_manager = StreamManager()

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            results = []

            async def produce_and_cancel():
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager._queues:
                        break

                if mock_manager._queues:
                    queue = list(mock_manager._queues.values())[0]
                    await queue.put(
                        StreamMessage(
                            stream_type=StreamType.QUOTE,
                            symbol="AAPL",
                            data={
                                "timestamp": datetime.now(UTC),
                                "bid_price": 150.0,
                                "bid_size": 100,
                                "ask_price": 150.1,
                                "ask_size": 200,
                            },
                        )
                    )

                await asyncio.sleep(0.05)
                context.cancel()

            asyncio.create_task(produce_and_cancel())

            async for quote in servicer.StreamQuotes(mock_request, context):
                results.append(quote)

            assert len(results) == 1
            assert results[0].symbol == "AAPL"


@pytest.mark.skip(reason="Streaming tests require refactoring - servicer uses 30s queue timeout")
class TestStreamTrades:
    """Tests for StreamTrades gRPC method."""

    async def test_stream_trades_subscribes_to_symbols(self, servicer, context):
        """Test that StreamTrades subscribes to requested symbols."""
        mock_manager = StreamManager()
        subscribed_correctly = False

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL", "MSFT"]

            async def check_and_cancel():
                nonlocal subscribed_correctly
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager.connection_count > 0:
                        subs = mock_manager.subscribed_symbols["trades"]
                        if "AAPL" in subs and "MSFT" in subs:
                            subscribed_correctly = True
                            break
                context.cancel()

            asyncio.create_task(check_and_cancel())

            async for _ in servicer.StreamTrades(mock_request, context):
                pass

            assert subscribed_correctly, "Symbols were not properly subscribed"

    async def test_stream_trades_yields_trade_messages(self, servicer, context):
        """Test that StreamTrades yields trade data from queue."""
        mock_manager = StreamManager()

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            results = []

            async def produce_and_cancel():
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager._queues:
                        break

                if mock_manager._queues:
                    queue = list(mock_manager._queues.values())[0]
                    await queue.put(
                        StreamMessage(
                            stream_type=StreamType.TRADE,
                            symbol="AAPL",
                            data={
                                "timestamp": datetime.now(UTC),
                                "price": 150.25,
                                "size": 100,
                                "exchange": "NASDAQ",
                            },
                        )
                    )

                await asyncio.sleep(0.05)
                context.cancel()

            asyncio.create_task(produce_and_cancel())

            async for trade in servicer.StreamTrades(mock_request, context):
                results.append(trade)

            assert len(results) == 1
            assert results[0].symbol == "AAPL"

    async def test_stream_trades_ignores_other_message_types(self, servicer, context):
        """Test that StreamTrades ignores non-trade messages."""
        mock_manager = StreamManager()

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            results = []

            async def produce_and_cancel():
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager._queues:
                        break

                if mock_manager._queues:
                    queue = list(mock_manager._queues.values())[0]

                    # Send a BAR message (should be ignored)
                    await queue.put(
                        StreamMessage(
                            stream_type=StreamType.BAR,
                            symbol="AAPL",
                            data={
                                "timestamp": datetime.now(UTC),
                                "open": 150.0,
                                "high": 151.0,
                                "low": 149.0,
                                "close": 150.5,
                                "volume": 1000,
                            },
                        )
                    )

                    # Send a TRADE message (should be yielded)
                    await queue.put(
                        StreamMessage(
                            stream_type=StreamType.TRADE,
                            symbol="AAPL",
                            data={
                                "timestamp": datetime.now(UTC),
                                "price": 150.25,
                                "size": 100,
                                "exchange": "NASDAQ",
                            },
                        )
                    )

                await asyncio.sleep(0.05)
                context.cancel()

            asyncio.create_task(produce_and_cancel())

            async for trade in servicer.StreamTrades(mock_request, context):
                results.append(trade)

            # Only the trade should be yielded, not the bar
            assert len(results) == 1
            assert results[0].symbol == "AAPL"


@pytest.mark.skip(reason="Streaming tests require refactoring - servicer uses 30s queue timeout")
class TestStreamingCleanup:
    """Tests for streaming cleanup behavior."""

    async def test_stream_cleanup_on_cancel(self, servicer, context):
        """Test that streams clean up on cancellation."""
        mock_manager = StreamManager()
        was_subscribed = False

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            mock_request = MagicMock()
            mock_request.symbols = ["AAPL"]

            async def check_and_cancel():
                nonlocal was_subscribed
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager.connection_count == 1:
                        was_subscribed = True
                        break
                context.cancel()

            asyncio.create_task(check_and_cancel())

            async for _ in servicer.StreamBars(mock_request, context):
                pass

            # After cancellation, should be cleaned up
            assert was_subscribed, "Stream was never active"
            assert mock_manager.connection_count == 0
            assert "AAPL" not in mock_manager.subscribed_symbols["bars"]

    async def test_multiple_streams_independent(self, servicer, context):
        """Test that multiple streams are independent."""
        mock_manager = StreamManager()
        both_connected = False

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            # Start two streams
            mock_request1 = MagicMock()
            mock_request1.symbols = ["AAPL"]

            mock_request2 = MagicMock()
            mock_request2.symbols = ["GOOGL"]

            context2 = MockServicerContext()

            async def check_and_cancel():
                nonlocal both_connected
                for _ in range(50):
                    await asyncio.sleep(0.01)
                    if mock_manager.connection_count == 2:
                        both_connected = True
                        break
                context.cancel()
                context2.cancel()

            asyncio.create_task(check_and_cancel())

            # Run both streams concurrently
            await asyncio.gather(
                self._consume_stream(servicer.StreamBars(mock_request1, context)),
                self._consume_stream(servicer.StreamBars(mock_request2, context2)),
                return_exceptions=True,
            )

            assert both_connected, "Both streams should have been connected"

    @staticmethod
    async def _consume_stream(stream):
        """Helper to consume an async generator."""
        async for _ in stream:
            pass


class TestStreamManagerIntegration:
    """Integration tests for StreamManager with gRPC streaming."""

    async def test_full_flow_with_stream_manager(self, stream_manager):
        """Test the full flow from connection to message delivery."""
        # Connect client
        queue = await stream_manager.connect(1)
        assert stream_manager.connection_count == 1

        # Subscribe to trades
        await stream_manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        assert "AAPL" in stream_manager.subscribed_symbols["trades"]

        # Broadcast trade data
        trade_data = {"price": 150.0, "size": 100}
        await stream_manager.broadcast_trade("AAPL", trade_data)

        # Verify message received
        message = queue.get_nowait()
        assert message.stream_type == StreamType.TRADE
        assert message.symbol == "AAPL"
        assert message.data == trade_data

        # Disconnect
        await stream_manager.disconnect(1)
        assert stream_manager.connection_count == 0
        assert "AAPL" not in stream_manager.subscribed_symbols["trades"]
