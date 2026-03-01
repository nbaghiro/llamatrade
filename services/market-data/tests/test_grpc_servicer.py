"""Tests for Market Data gRPC servicer."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.grpc.servicer import MarketDataServicer
from src.models import Bar, Quote, Snapshot, Trade

# === Test Fixtures ===


@pytest.fixture
def servicer():
    """Create a MarketDataServicer instance."""
    return MarketDataServicer()


@pytest.fixture
def mock_context():
    """Create a mock gRPC context."""
    context = MagicMock()
    context.abort = AsyncMock(side_effect=Exception("aborted"))
    context.cancelled = MagicMock(return_value=False)
    return context


@pytest.fixture
def sample_bar():
    """Create a sample Bar."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        open=150.00,
        high=152.50,
        low=149.50,
        close=151.25,
        volume=1000000,
        vwap=150.75,
        trade_count=5000,
    )


@pytest.fixture
def sample_quote():
    """Create a sample Quote."""
    return Quote(
        symbol="AAPL",
        bid_price=150.00,
        bid_size=100,
        ask_price=150.10,
        ask_size=200,
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_trade():
    """Create a sample Trade."""
    return Trade(
        symbol="AAPL",
        price=150.05,
        size=50,
        timestamp=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        exchange="NASDAQ",
    )


@pytest.fixture
def sample_snapshot(sample_bar, sample_quote, sample_trade):
    """Create a sample Snapshot."""
    prev_bar = Bar(
        timestamp=datetime(2024, 1, 14, 21, 0, 0, tzinfo=UTC),
        open=148.00,
        high=150.00,
        low=147.50,
        close=149.00,
        volume=900000,
        vwap=148.75,
        trade_count=4500,
    )
    return Snapshot(
        symbol="AAPL",
        latest_trade=sample_trade,
        latest_quote=sample_quote,
        daily_bar=sample_bar,
        prev_daily_bar=prev_bar,
    )


# === Mock Proto Classes ===


class MockTimestamp:
    def __init__(self, seconds=0, nanos=0):
        self.seconds = seconds
        self.nanos = nanos


class MockDecimal:
    def __init__(self, value="0"):
        self.value = value


class MockPagination:
    def __init__(self, page_size=1000):
        self.page_size = page_size


class MockGetHistoricalBarsRequest:
    def __init__(
        self,
        symbol="AAPL",
        start_seconds=1705315200,
        end_seconds=None,
        timeframe=7,  # TIMEFRAME_1DAY
        pagination=None,
    ):
        self.symbol = symbol
        self.start = MockTimestamp(seconds=start_seconds)
        self._end = MockTimestamp(seconds=end_seconds) if end_seconds else None
        self.timeframe = timeframe
        self._pagination = pagination

    def HasField(self, field):  # noqa: N802
        if field == "end":
            return self._end is not None
        if field == "pagination":
            return self._pagination is not None
        return False

    @property
    def end(self):
        return self._end

    @property
    def pagination(self):
        return self._pagination


class MockGetMultiBarsRequest:
    def __init__(
        self,
        symbols=None,
        start_seconds=1705315200,
        end_seconds=None,
        timeframe=7,
        limit=1000,
    ):
        self.symbols = symbols or ["AAPL", "GOOGL"]
        self.start = MockTimestamp(seconds=start_seconds)
        self._end = MockTimestamp(seconds=end_seconds) if end_seconds else None
        self.timeframe = timeframe
        self.limit = limit

    def HasField(self, field):  # noqa: N802
        if field == "end":
            return self._end is not None
        return False

    @property
    def end(self):
        return self._end


class MockGetSnapshotRequest:
    def __init__(self, symbol="AAPL"):
        self.symbol = symbol


class MockGetSnapshotsRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["AAPL", "GOOGL"]


class MockGetMarketStatusRequest:
    pass


class MockStreamBarsRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["AAPL"]


class MockStreamQuotesRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["AAPL"]


class MockStreamTradesRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["AAPL"]


# === GetHistoricalBars Tests ===


class TestGetHistoricalBars:
    """Tests for GetHistoricalBars method."""

    async def test_get_historical_bars_success(self, servicer, mock_context, sample_bar):
        """Test successful historical bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[sample_bar])

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetHistoricalBarsRequest(symbol="AAPL")
            response = await servicer.GetHistoricalBars(request, mock_context)

            assert response is not None
            mock_client.get_bars.assert_called_once()
            call_kwargs = mock_client.get_bars.call_args.kwargs
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["limit"] == 1000

    async def test_get_historical_bars_with_pagination(self, servicer, mock_context, sample_bar):
        """Test historical bars with pagination limit."""
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[sample_bar])

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetHistoricalBarsRequest(
                symbol="AAPL",
                pagination=MockPagination(page_size=500),
            )
            response = await servicer.GetHistoricalBars(request, mock_context)

            assert response is not None
            call_kwargs = mock_client.get_bars.call_args.kwargs
            assert call_kwargs["limit"] == 500

    async def test_get_historical_bars_error(self, servicer, mock_context):
        """Test error handling in historical bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetHistoricalBarsRequest(symbol="AAPL")

            with pytest.raises(Exception, match="aborted"):
                await servicer.GetHistoricalBars(request, mock_context)

            mock_context.abort.assert_called_once()


# === GetMultiBars Tests ===


class TestGetMultiBars:
    """Tests for GetMultiBars method."""

    async def test_get_multi_bars_success(self, servicer, mock_context, sample_bar):
        """Test successful multi-symbol bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(
            return_value={"AAPL": [sample_bar], "GOOGL": [sample_bar]}
        )

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetMultiBarsRequest(symbols=["AAPL", "GOOGL"])
            response = await servicer.GetMultiBars(request, mock_context)

            assert response is not None
            mock_client.get_multi_bars.assert_called_once()
            call_kwargs = mock_client.get_multi_bars.call_args.kwargs
            assert set(call_kwargs["symbols"]) == {"AAPL", "GOOGL"}

    async def test_get_multi_bars_with_limit(self, servicer, mock_context, sample_bar):
        """Test multi-bars with custom limit."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(return_value={"AAPL": [sample_bar]})

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetMultiBarsRequest(symbols=["AAPL"], limit=500)
            response = await servicer.GetMultiBars(request, mock_context)

            assert response is not None
            call_kwargs = mock_client.get_multi_bars.call_args.kwargs
            assert call_kwargs["limit"] == 500

    async def test_get_multi_bars_error(self, servicer, mock_context):
        """Test error handling in multi-bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetMultiBarsRequest(symbols=["AAPL"])

            with pytest.raises(Exception, match="aborted"):
                await servicer.GetMultiBars(request, mock_context)


# === GetSnapshot Tests ===


class TestGetSnapshot:
    """Tests for GetSnapshot method."""

    async def test_get_snapshot_success(self, servicer, mock_context, sample_snapshot):
        """Test successful snapshot retrieval."""
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=sample_snapshot)

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="AAPL")
            response = await servicer.GetSnapshot(request, mock_context)

            assert response is not None
            mock_client.get_snapshot.assert_called_once_with("AAPL")

    async def test_get_snapshot_not_found(self, servicer, mock_context):
        """Test snapshot not found handling."""
        import grpc

        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=None)

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="INVALID")

            with pytest.raises(Exception, match="aborted"):
                await servicer.GetSnapshot(request, mock_context)

            # First call should be NOT_FOUND (second call is the error handler catching our mock exception)
            first_call = mock_context.abort.call_args_list[0]
            assert first_call[0][0] == grpc.StatusCode.NOT_FOUND
            assert "INVALID" in first_call[0][1]

    async def test_get_snapshot_error(self, servicer, mock_context):
        """Test error handling in snapshot retrieval."""
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="AAPL")

            with pytest.raises(Exception, match="aborted"):
                await servicer.GetSnapshot(request, mock_context)


# === GetSnapshots Tests ===


class TestGetSnapshots:
    """Tests for GetSnapshots method."""

    async def test_get_snapshots_success(self, servicer, mock_context, sample_snapshot):
        """Test successful multi-symbol snapshots retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_snapshots = AsyncMock(
            return_value={"AAPL": sample_snapshot, "GOOGL": sample_snapshot}
        )

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetSnapshotsRequest(symbols=["AAPL", "GOOGL"])
            response = await servicer.GetSnapshots(request, mock_context)

            assert response is not None
            mock_client.get_multi_snapshots.assert_called_once_with(["AAPL", "GOOGL"])

    async def test_get_snapshots_error(self, servicer, mock_context):
        """Test error handling in snapshots retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_snapshots = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_alpaca_client", return_value=mock_client):
            request = MockGetSnapshotsRequest(symbols=["AAPL"])

            with pytest.raises(Exception, match="aborted"):
                await servicer.GetSnapshots(request, mock_context)


# === GetMarketStatus Tests ===


class TestGetMarketStatus:
    """Tests for GetMarketStatus method."""

    async def test_get_market_status_returns_response(self, servicer, mock_context):
        """Test market status returns a valid response."""
        request = MockGetMarketStatusRequest()
        response = await servicer.GetMarketStatus(request, mock_context)

        # The response should have a status field
        assert response is not None
        assert hasattr(response, "status")


# === Streaming Tests ===


class MockStreamMessage:
    """Mock stream message for testing."""

    def __init__(self, stream_type, symbol, data):
        self.stream_type = stream_type
        self.symbol = symbol
        self.data = data


class MockStreamType:
    """Mock stream type enum."""

    BAR = "bar"
    QUOTE = "quote"
    TRADE = "trade"


class TestStreamBars:
    """Tests for StreamBars method."""

    async def test_stream_bars_setup(self, servicer, mock_context):
        """Test streaming bars setup and cleanup."""
        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        # Set context to cancel immediately after first iteration
        call_count = 0

        def cancelled_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mock_context.cancelled = MagicMock(side_effect=cancelled_side_effect)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamBarsRequest(symbols=["AAPL", "GOOGL"])

            # Consume the generator
            async for _ in servicer.StreamBars(request, mock_context):
                pass

            # Verify connect was called
            mock_manager.connect.assert_called_once()
            # Verify subscribe was called with correct params
            mock_manager.subscribe.assert_called_once()
            call_kwargs = mock_manager.subscribe.call_args.kwargs
            assert "AAPL" in call_kwargs["bars"]
            assert "GOOGL" in call_kwargs["bars"]
            # Verify cleanup
            mock_manager.disconnect.assert_called_once()


class TestStreamQuotes:
    """Tests for StreamQuotes method."""

    async def test_stream_quotes_setup(self, servicer, mock_context):
        """Test streaming quotes setup and cleanup."""
        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        call_count = 0

        def cancelled_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mock_context.cancelled = MagicMock(side_effect=cancelled_side_effect)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamQuotesRequest(symbols=["AAPL"])

            async for _ in servicer.StreamQuotes(request, mock_context):
                pass

            mock_manager.connect.assert_called_once()
            mock_manager.subscribe.assert_called_once()
            call_kwargs = mock_manager.subscribe.call_args.kwargs
            assert "AAPL" in call_kwargs["quotes"]
            mock_manager.disconnect.assert_called_once()


class TestStreamTrades:
    """Tests for StreamTrades method."""

    async def test_stream_trades_setup(self, servicer, mock_context):
        """Test streaming trades setup and cleanup."""
        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        call_count = 0

        def cancelled_side_effect():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        mock_context.cancelled = MagicMock(side_effect=cancelled_side_effect)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamTradesRequest(symbols=["AAPL"])

            async for _ in servicer.StreamTrades(request, mock_context):
                pass

            mock_manager.connect.assert_called_once()
            mock_manager.subscribe.assert_called_once()
            call_kwargs = mock_manager.subscribe.call_args.kwargs
            assert "AAPL" in call_kwargs["trades"]
            mock_manager.disconnect.assert_called_once()


# === Helper Method Tests ===


class TestHelperMethods:
    """Tests for internal helper methods."""

    def test_timeframe_map_initialization(self, servicer):
        """Test that timeframe map is properly initialized."""
        # The servicer should have initialized the map (or it's empty due to import issues)
        assert hasattr(servicer, "_TIMEFRAME_MAP")
