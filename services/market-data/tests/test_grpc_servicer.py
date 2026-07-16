"""Tests for Market Data gRPC servicer."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from connectrpc.errors import ConnectError

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


def create_mock_historical_bars_request(
    symbol: str = "AAPL",
    start_seconds: int = 1705315200,
    end_seconds: int | None = None,
    timeframe: int = 7,  # TIMEFRAME_1DAY
    pagination: MockPagination | None = None,
) -> MagicMock:
    """Create a mock GetHistoricalBarsRequest."""
    mock = MagicMock()
    mock.symbol = symbol
    mock.start = MockTimestamp(seconds=start_seconds)
    mock.timeframe = timeframe

    # Configure end and pagination with proper HasField behavior
    end_value = MockTimestamp(seconds=end_seconds) if end_seconds else None
    mock.end = end_value
    mock.pagination = pagination
    mock.HasField = lambda field: {
        "end": end_value is not None,
        "pagination": pagination is not None,
    }.get(field, False)

    return mock


def create_mock_multi_bars_request(
    symbols: list[str] | None = None,
    start_seconds: int = 1705315200,
    end_seconds: int | None = None,
    timeframe: int = 7,
    limit: int = 1000,
) -> MagicMock:
    """Create a mock GetMultiBarsRequest."""
    mock = MagicMock()
    mock.symbols = symbols or ["AAPL", "GOOGL"]
    mock.start = MockTimestamp(seconds=start_seconds)
    mock.timeframe = timeframe
    mock.limit = limit

    # Configure end with proper HasField behavior
    end_value = MockTimestamp(seconds=end_seconds) if end_seconds else None
    mock.end = end_value
    mock.HasField = lambda field: {"end": end_value is not None}.get(field, False)

    return mock


class MockGetSnapshotRequest:
    def __init__(self, symbol="AAPL"):
        self.symbol = symbol


class MockGetSnapshotsRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["AAPL", "GOOGL"]


class MockGetMarketStatusRequest:
    pass


class MockGetAssetsRequest:
    def __init__(self, symbols=None):
        self.symbols = symbols or ["XLE"]


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

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_historical_bars_request(symbol="AAPL")
            response = await servicer.get_historical_bars(request, mock_context)

            assert response is not None
            mock_client.get_bars.assert_called_once()
            call_kwargs = mock_client.get_bars.call_args.kwargs
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["limit"] == 1000

    async def test_get_historical_bars_with_pagination(self, servicer, mock_context, sample_bar):
        """Test historical bars with pagination limit."""
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[sample_bar])

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_historical_bars_request(
                symbol="AAPL",
                pagination=MockPagination(page_size=500),
            )
            response = await servicer.get_historical_bars(request, mock_context)

            assert response is not None
            call_kwargs = mock_client.get_bars.call_args.kwargs
            assert call_kwargs["limit"] == 500

    async def test_get_historical_bars_error(self, servicer, mock_context):
        """Test error handling in historical bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_historical_bars_request(symbol="AAPL")

            with pytest.raises(ConnectError, match="Failed to fetch historical bars"):
                await servicer.get_historical_bars(request, mock_context)


# === GetMultiBars Tests ===


class TestGetMultiBars:
    """Tests for GetMultiBars method."""

    async def test_get_multi_bars_success(self, servicer, mock_context, sample_bar):
        """Test successful multi-symbol bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(
            return_value={"AAPL": [sample_bar], "GOOGL": [sample_bar]}
        )

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL", "GOOGL"])
            response = await servicer.get_multi_bars(request, mock_context)

            assert response is not None
            mock_client.get_multi_bars.assert_called_once()
            call_kwargs = mock_client.get_multi_bars.call_args.kwargs
            assert set(call_kwargs["symbols"]) == {"AAPL", "GOOGL"}

    async def test_get_multi_bars_with_limit(self, servicer, mock_context, sample_bar):
        """Test multi-bars with custom limit."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(return_value={"AAPL": [sample_bar]})

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL"], limit=500)
            response = await servicer.get_multi_bars(request, mock_context)

            assert response is not None
            call_kwargs = mock_client.get_multi_bars.call_args.kwargs
            assert call_kwargs["limit"] == 500

    async def test_get_multi_bars_error(self, servicer, mock_context):
        """Test error handling in multi-bars retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL"])

            with pytest.raises(ConnectError, match="Failed to fetch multi bars"):
                await servicer.get_multi_bars(request, mock_context)


# === StreamHistoricalBars Tests (13B) ===


class TestStreamHistoricalBars:
    """Tests for the StreamHistoricalBars server-streaming method."""

    async def test_stream_historical_bars_success(self, servicer, mock_context, sample_bar):
        """All symbols' bars are streamed (server-side fan-out via get_multi_bars)."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(
            return_value={"AAPL": [sample_bar], "GOOGL": [sample_bar]}
        )

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL", "GOOGL"])
            bars = [bar async for bar in servicer.stream_historical_bars(request, mock_context)]

            assert len(bars) == 2
            mock_client.get_multi_bars.assert_called_once()

    async def test_stream_historical_bars_error(self, servicer, mock_context):
        """A fetch failure surfaces as ConnectError before any bar is yielded."""
        mock_client = MagicMock()
        mock_client.get_multi_bars = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL"])

            with pytest.raises(ConnectError, match="Failed to fetch historical bars"):
                _ = [bar async for bar in servicer.stream_historical_bars(request, mock_context)]


# === GetSnapshot Tests ===


class TestGetSnapshot:
    """Tests for GetSnapshot method."""

    async def test_get_snapshot_success(self, servicer, mock_context, sample_snapshot):
        """Test successful snapshot retrieval."""
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=sample_snapshot)

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="AAPL")
            response = await servicer.get_snapshot(request, mock_context)

            assert response is not None
            mock_client.get_snapshot.assert_called_once_with("AAPL")

    async def test_get_snapshot_not_found(self, servicer, mock_context):
        """Test snapshot not found handling."""
        from connectrpc.code import Code

        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=None)

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            # Use a valid-format symbol that doesn't exist
            request = MockGetSnapshotRequest(symbol="ZZZZZ")

            with pytest.raises(ConnectError) as exc_info:
                await servicer.get_snapshot(request, mock_context)

            assert exc_info.value.code == Code.NOT_FOUND
            assert "ZZZZZ" in str(exc_info.value)

    async def test_get_snapshot_error(self, servicer, mock_context):
        """Test error handling in snapshot retrieval."""
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="AAPL")

            with pytest.raises(ConnectError, match="Failed to fetch snapshot"):
                await servicer.get_snapshot(request, mock_context)


# === GetSnapshots Tests ===


class TestGetSnapshots:
    """Tests for GetSnapshots method."""

    async def test_get_snapshots_success(self, servicer, mock_context, sample_snapshot):
        """Test successful multi-symbol snapshots retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_snapshots = AsyncMock(
            return_value={"AAPL": sample_snapshot, "GOOGL": sample_snapshot}
        )

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotsRequest(symbols=["AAPL", "GOOGL"])
            response = await servicer.get_snapshots(request, mock_context)

            assert response is not None
            mock_client.get_multi_snapshots.assert_called_once_with(["AAPL", "GOOGL"])

    async def test_get_snapshots_error(self, servicer, mock_context):
        """Test error handling in snapshots retrieval."""
        mock_client = MagicMock()
        mock_client.get_multi_snapshots = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotsRequest(symbols=["AAPL"])

            with pytest.raises(ConnectError, match="Failed to fetch snapshots"):
                await servicer.get_snapshots(request, mock_context)


# === GetAssets Tests ===


class TestGetAssets:
    """Tests for GetAssets method."""

    async def test_get_assets_success(self, servicer, mock_context):
        """Alpaca asset metadata is passed through to the proto, keyed by symbol."""
        from llamatrade_alpaca import Asset

        asset = Asset(
            id="b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
            symbol="XLE",
            name="Energy Select Sector SPDR Fund",
            asset_class="us_equity",
            exchange="ARCA",
            status="active",
            tradable=True,
            fractionable=True,
        )
        mock_service = MagicMock()
        mock_service.get_assets = AsyncMock(return_value={"XLE": asset})

        with patch("src.grpc.servicer.get_asset_service", return_value=mock_service):
            request = MockGetAssetsRequest(symbols=["XLE"])
            response = await servicer.get_assets(request, mock_context)

            proto = response.assets["XLE"]
            assert proto.name == "Energy Select Sector SPDR Fund"
            assert proto.symbol == "XLE"
            assert proto.exchange == "ARCA"
            assert proto.asset_class == "us_equity"
            assert proto.status == "active"
            assert proto.tradable is True
            assert proto.fractionable is True
            mock_service.get_assets.assert_called_once_with(["XLE"])

    async def test_get_assets_unknown_symbol_omitted(self, servicer, mock_context):
        """A symbol Alpaca doesn't know is simply absent from the map."""
        mock_service = MagicMock()
        mock_service.get_assets = AsyncMock(return_value={})

        with patch("src.grpc.servicer.get_asset_service", return_value=mock_service):
            request = MockGetAssetsRequest(symbols=["NOPE"])
            response = await servicer.get_assets(request, mock_context)

            assert "NOPE" not in response.assets

    async def test_get_assets_error(self, servicer, mock_context):
        """Errors surface as a Connect INTERNAL error."""
        mock_service = MagicMock()
        mock_service.get_assets = AsyncMock(side_effect=Exception("API error"))

        with patch("src.grpc.servicer.get_asset_service", return_value=mock_service):
            request = MockGetAssetsRequest(symbols=["XLE"])

            with pytest.raises(ConnectError, match="Failed to fetch assets"):
                await servicer.get_assets(request, mock_context)


# === GetMarketStatus Tests ===


class TestGetMarketStatus:
    """Tests for GetMarketStatus method."""

    @staticmethod
    def _valid_creds():
        """Patch AlpacaCredentials.from_env() to report present credentials."""
        creds = MagicMock()
        creds.is_valid.return_value = True
        return patch("src.grpc.servicer.AlpacaCredentials.from_env", return_value=creds)

    @staticmethod
    def _absent_creds():
        """Patch AlpacaCredentials.from_env() to report missing credentials."""
        creds = MagicMock()
        creds.is_valid.return_value = False
        return patch("src.grpc.servicer.AlpacaCredentials.from_env", return_value=creds)

    async def test_get_market_status_uses_alpaca_when_creds_present(self, servicer, mock_context):
        """With valid credentials the Alpaca clock is the source of truth."""
        from llamatrade_alpaca import MarketClock
        from llamatrade_proto.generated import market_data_pb2

        mock_clock = MarketClock(
            timestamp=datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
            is_open=True,
            next_open=datetime(2024, 1, 16, 14, 30, tzinfo=UTC),
            next_close=datetime(2024, 1, 15, 21, 0, tzinfo=UTC),
        )

        mock_trading_client = MagicMock()
        mock_trading_client.get_clock = AsyncMock(return_value=mock_clock)

        with (
            self._valid_creds(),
            patch(
                "src.grpc.servicer.get_trading_client_async",
                return_value=mock_trading_client,
            ),
        ):
            response = await servicer.get_market_status(MockGetMarketStatusRequest(), mock_context)

        assert response.status == market_data_pb2.MARKET_STATUS_OPEN
        assert response.next_open.seconds == int(mock_clock.next_open.timestamp())
        assert response.next_close.seconds == int(mock_clock.next_close.timestamp())
        mock_trading_client.get_clock.assert_called_once()

    async def test_get_market_status_calendar_when_creds_absent(self, servicer, mock_context):
        """Without credentials the calendar is used and Alpaca is never called."""
        from llamatrade_proto.generated import market_data_pb2

        mock_trading_client = MagicMock()
        mock_trading_client.get_clock = AsyncMock()

        with (
            self._absent_creds(),
            patch(
                "src.grpc.servicer.get_trading_client_async",
                return_value=mock_trading_client,
            ),
        ):
            response = await servicer.get_market_status(MockGetMarketStatusRequest(), mock_context)

        assert response.status in {
            market_data_pb2.MARKET_STATUS_OPEN,
            market_data_pb2.MARKET_STATUS_CLOSED,
            market_data_pb2.MARKET_STATUS_PRE_MARKET,
            market_data_pb2.MARKET_STATUS_AFTER_HOURS,
        }
        assert response.next_open.seconds > 0
        assert response.next_close.seconds > 0
        mock_trading_client.get_clock.assert_not_called()

    async def test_get_market_status_falls_back_to_calendar_on_alpaca_error(
        self, servicer, mock_context
    ):
        """A failing Alpaca clock degrades to the calendar instead of erroring."""
        from llamatrade_proto.generated import market_data_pb2

        mock_trading_client = MagicMock()
        mock_trading_client.get_clock = AsyncMock(
            side_effect=RuntimeError("Invalid API credentials")
        )

        with (
            self._valid_creds(),
            patch(
                "src.grpc.servicer.get_trading_client_async",
                return_value=mock_trading_client,
            ),
        ):
            response = await servicer.get_market_status(MockGetMarketStatusRequest(), mock_context)

        assert response.status in {
            market_data_pb2.MARKET_STATUS_OPEN,
            market_data_pb2.MARKET_STATUS_CLOSED,
            market_data_pb2.MARKET_STATUS_PRE_MARKET,
            market_data_pb2.MARKET_STATUS_AFTER_HOURS,
        }
        assert response.next_open.seconds > 0
        assert response.next_close.seconds > 0
        mock_trading_client.get_clock.assert_called_once()


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
        from src.streaming.manager import StreamType

        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        # Add a message to the queue so the test doesn't block
        bar_message = MagicMock()
        bar_message.stream_type = StreamType.BAR
        bar_message.symbol = "AAPL"
        bar_message.data = {
            "timestamp": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
            "open": 150.0,
            "high": 152.0,
            "low": 149.0,
            "close": 151.0,
            "volume": 1000000,
        }
        await mock_queue.put(bar_message)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamBarsRequest(symbols=["AAPL", "GOOGL"])

            # Consume one message then cancel the generator
            bars_received = []
            gen = servicer.stream_bars(request, mock_context)
            try:
                bar = await gen.__anext__()
                bars_received.append(bar)
            finally:
                # Properly close the generator to trigger cleanup
                await gen.aclose()

            assert len(bars_received) == 1
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
        from src.streaming.manager import StreamType

        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        # Add a quote message to the queue
        quote_message = MagicMock()
        quote_message.stream_type = StreamType.QUOTE
        quote_message.symbol = "AAPL"
        quote_message.data = {
            "timestamp": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
            "bid_price": 150.0,
            "bid_size": 100,
            "ask_price": 150.10,
            "ask_size": 200,
        }
        await mock_queue.put(quote_message)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamQuotesRequest(symbols=["AAPL"])

            quotes_received = []
            gen = servicer.stream_quotes(request, mock_context)
            try:
                quote = await gen.__anext__()
                quotes_received.append(quote)
            finally:
                await gen.aclose()

            assert len(quotes_received) == 1
            mock_manager.connect.assert_called_once()
            mock_manager.subscribe.assert_called_once()
            call_kwargs = mock_manager.subscribe.call_args.kwargs
            assert "AAPL" in call_kwargs["quotes"]
            mock_manager.disconnect.assert_called_once()


class TestStreamTrades:
    """Tests for StreamTrades method."""

    async def test_stream_trades_setup(self, servicer, mock_context):
        """Test streaming trades setup and cleanup."""
        from src.streaming.manager import StreamType

        mock_queue = asyncio.Queue()
        mock_manager = MagicMock()
        mock_manager.connect = AsyncMock(return_value=mock_queue)
        mock_manager.subscribe = AsyncMock()
        mock_manager.disconnect = AsyncMock()

        # Add a trade message to the queue
        trade_message = MagicMock()
        trade_message.stream_type = StreamType.TRADE
        trade_message.symbol = "AAPL"
        trade_message.data = {
            "timestamp": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
            "price": 150.05,
            "size": 100,
            "exchange": "NASDAQ",
            "conditions": [],
        }
        await mock_queue.put(trade_message)

        with patch("src.grpc.servicer.get_stream_manager", return_value=mock_manager):
            request = MockStreamTradesRequest(symbols=["AAPL"])

            trades_received = []
            gen = servicer.stream_trades(request, mock_context)
            try:
                trade = await gen.__anext__()
                trades_received.append(trade)
            finally:
                await gen.aclose()

            assert len(trades_received) == 1
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


class TestTimeframeMapping:
    """Tests for timeframe enum mapping."""

    async def test_get_historical_bars_monthly_timeframe(self, servicer, mock_context, sample_bar):
        """Test monthly timeframe mapping (TIMEFRAME_1MONTH)."""
        from src.models import Timeframe

        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[sample_bar])

        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            # 9 = TIMEFRAME_1MONTH in proto enum
            request = create_mock_historical_bars_request(symbol="AAPL", timeframe=9)
            response = await servicer.get_historical_bars(request, mock_context)

            assert response is not None
            mock_client.get_bars.assert_called_once()
            call_kwargs = mock_client.get_bars.call_args.kwargs
            # Verify the timeframe was mapped to MONTH_1
            assert call_kwargs["timeframe"] == Timeframe.MONTH_1

    def test_timeframe_map_contains_monthly(self, servicer):
        """Test that timeframe map includes TIMEFRAME_1MONTH."""
        from llamatrade_proto.generated import market_data_pb2

        from src.models import Timeframe

        # Ensure the map is initialized
        servicer._init_timeframe_map()

        # Check that MONTH_1 is mapped
        assert market_data_pb2.TIMEFRAME_1MONTH in servicer._TIMEFRAME_MAP
        assert servicer._TIMEFRAME_MAP[market_data_pb2.TIMEFRAME_1MONTH] == Timeframe.MONTH_1

    def test_all_timeframes_mapped(self, servicer):
        """Test that all proto timeframes have mappings."""
        from llamatrade_proto.generated import market_data_pb2

        from src.models import Timeframe

        servicer._init_timeframe_map()

        expected_mappings = {
            market_data_pb2.TIMEFRAME_1MIN: Timeframe.MINUTE_1,
            market_data_pb2.TIMEFRAME_5MIN: Timeframe.MINUTE_5,
            market_data_pb2.TIMEFRAME_15MIN: Timeframe.MINUTE_15,
            market_data_pb2.TIMEFRAME_30MIN: Timeframe.MINUTE_30,
            market_data_pb2.TIMEFRAME_1HOUR: Timeframe.HOUR_1,
            market_data_pb2.TIMEFRAME_4HOUR: Timeframe.HOUR_4,
            market_data_pb2.TIMEFRAME_1DAY: Timeframe.DAY_1,
            market_data_pb2.TIMEFRAME_1WEEK: Timeframe.WEEK_1,
            market_data_pb2.TIMEFRAME_1MONTH: Timeframe.MONTH_1,
        }

        for proto_tf, expected_internal in expected_mappings.items():
            assert servicer._TIMEFRAME_MAP.get(proto_tf) == expected_internal


# === Data-Quality Metric Wiring ===


def _md_exposition() -> str:
    from llamatrade_telemetry import get_metrics

    return get_metrics().decode()


def _md_sample(text: str, name: str, **labels: str) -> float | None:
    label_parts = {f'{k}="{v}"' for k, v in labels.items()}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if not head.startswith(name):
            continue
        if "{" in head:
            inner = head[head.index("{") + 1 : head.rindex("}")]
            line_labels = {part for part in inner.split(",") if part}
            if not label_parts.issubset(line_labels):
                continue
        elif label_parts:
            continue
        return float(value)
    return None


class TestServicerMetricsWiring:
    """Data-quality metrics fire at the real serve call sites."""

    async def test_historical_bars_records_staleness(self, servicer, mock_context, sample_bar):
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[sample_bar])
        before = _md_sample(
            _md_exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_historical_bars_request(symbol="AAPL")
            await servicer.get_historical_bars(request, mock_context)
        after = _md_sample(
            _md_exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        assert after == (before or 0.0) + 1.0

    async def test_historical_bars_empty_records_missing_symbol(self, servicer, mock_context):
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=[])
        before = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_historical_bars_request(symbol="AAPL")
            await servicer.get_historical_bars(request, mock_context)
        after = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        assert after == (before or 0.0) + 1.0

    async def test_intraday_bars_record_gap(self, servicer, mock_context):
        from datetime import timedelta

        now = datetime.now(UTC)
        gapped = [
            Bar(
                timestamp=now - timedelta(minutes=3),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1,
            ),
            Bar(
                timestamp=now - timedelta(minutes=1),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1,
            ),
        ]
        mock_client = MagicMock()
        mock_client.get_bars = AsyncMock(return_value=gapped)
        before = _md_sample(_md_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            # timeframe=1 -> TIMEFRAME_1MIN
            request = create_mock_historical_bars_request(symbol="AAPL", timeframe=1)
            await servicer.get_historical_bars(request, mock_context)
        after = _md_sample(_md_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        assert after == (before or 0.0) + 1.0

    async def test_multi_bars_missing_symbol_for_absent(self, servicer, mock_context, sample_bar):
        mock_client = MagicMock()
        # Only AAPL returns data; GOOGL is absent -> counts as missing.
        mock_client.get_multi_bars = AsyncMock(return_value={"AAPL": [sample_bar]})
        before = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = create_mock_multi_bars_request(symbols=["AAPL", "GOOGL"])
            await servicer.get_multi_bars(request, mock_context)
        after = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        assert after == (before or 0.0) + 1.0

    async def test_snapshot_records_quote_and_trade_staleness(
        self, servicer, mock_context, sample_snapshot
    ):
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=sample_snapshot)
        text_before = _md_exposition()
        q_before = _md_sample(
            text_before, "llamatrade_marketdata_data_staleness_seconds_count", data_type="quotes"
        )
        t_before = _md_sample(
            text_before, "llamatrade_marketdata_data_staleness_seconds_count", data_type="trades"
        )
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="AAPL")
            await servicer.get_snapshot(request, mock_context)
        text_after = _md_exposition()
        assert (
            _md_sample(
                text_after, "llamatrade_marketdata_data_staleness_seconds_count", data_type="quotes"
            )
            == (q_before or 0.0) + 1.0
        )
        assert (
            _md_sample(
                text_after, "llamatrade_marketdata_data_staleness_seconds_count", data_type="trades"
            )
            == (t_before or 0.0) + 1.0
        )

    async def test_snapshot_not_found_records_missing_symbol(self, servicer, mock_context):
        mock_client = MagicMock()
        mock_client.get_snapshot = AsyncMock(return_value=None)
        before = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        with patch("src.grpc.servicer.get_market_data_service", return_value=mock_client):
            request = MockGetSnapshotRequest(symbol="ZZZZZ")
            with pytest.raises(ConnectError):
                await servicer.get_snapshot(request, mock_context)
        after = _md_sample(_md_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        assert after == (before or 0.0) + 1.0
