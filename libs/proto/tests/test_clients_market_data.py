"""Tests for llamatrade_proto.clients.market_data module."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.market_data import (
    Bar,
    MarketDataClient,
    Quote,
    Trade,
)


class TestBar:
    """Tests for Bar dataclass."""

    def test_create_bar_minimal(self) -> None:
        """Test creating Bar with required fields."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            open=Decimal("150.00"),
            high=Decimal("152.50"),
            low=Decimal("149.50"),
            close=Decimal("151.00"),
            volume=1000000,
        )

        assert bar.symbol == "AAPL"
        assert bar.timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert bar.open == Decimal("150.00")
        assert bar.high == Decimal("152.50")
        assert bar.low == Decimal("149.50")
        assert bar.close == Decimal("151.00")
        assert bar.volume == 1000000
        assert bar.trade_count is None
        assert bar.vwap is None

    def test_create_bar_with_optional_fields(self) -> None:
        """Test creating Bar with all fields."""
        bar = Bar(
            symbol="GOOGL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            open=Decimal("140.00"),
            high=Decimal("142.00"),
            low=Decimal("139.00"),
            close=Decimal("141.50"),
            volume=500000,
            trade_count=5000,
            vwap=Decimal("140.75"),
        )

        assert bar.trade_count == 5000
        assert bar.vwap == Decimal("140.75")

    def test_bar_zero_volume(self) -> None:
        """Test creating Bar with zero volume."""
        bar = Bar(
            symbol="LOW_VOLUME",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            open=Decimal("10.00"),
            high=Decimal("10.00"),
            low=Decimal("10.00"),
            close=Decimal("10.00"),
            volume=0,
        )

        assert bar.volume == 0


class TestQuote:
    """Tests for Quote dataclass."""

    def test_create_quote(self) -> None:
        """Test creating Quote."""
        quote = Quote(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            bid_price=Decimal("150.00"),
            bid_size=100,
            ask_price=Decimal("150.05"),
            ask_size=200,
        )

        assert quote.symbol == "AAPL"
        assert quote.timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert quote.bid_price == Decimal("150.00")
        assert quote.bid_size == 100
        assert quote.ask_price == Decimal("150.05")
        assert quote.ask_size == 200

    def test_quote_spread(self) -> None:
        """Test calculating spread from Quote."""
        quote = Quote(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            bid_price=Decimal("150.00"),
            bid_size=100,
            ask_price=Decimal("150.10"),
            ask_size=200,
        )

        spread = quote.ask_price - quote.bid_price
        assert spread == Decimal("0.10")


class TestTrade:
    """Tests for Trade dataclass."""

    def test_create_trade_minimal(self) -> None:
        """Test creating Trade with required fields."""
        trade = Trade(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            price=Decimal("150.50"),
            size=100,
        )

        assert trade.symbol == "AAPL"
        assert trade.timestamp == datetime(2024, 1, 15, 10, 0, 0)
        assert trade.price == Decimal("150.50")
        assert trade.size == 100
        assert trade.exchange is None

    def test_create_trade_with_exchange(self) -> None:
        """Test creating Trade with exchange."""
        trade = Trade(
            symbol="GOOGL",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            price=Decimal("140.25"),
            size=50,
            exchange="NASDAQ",
        )

        assert trade.exchange == "NASDAQ"

    def test_trade_small_size(self) -> None:
        """Test creating Trade with small size."""
        trade = Trade(
            symbol="BRK.A",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            price=Decimal("500000.00"),
            size=1,
        )

        assert trade.size == 1


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test MarketDataClient initialization with defaults."""
        client = MarketDataClient()

        assert client._target == "market-data:8840"
        assert client._secure is False
        assert client._stub is None

    def test_init_with_custom_target(self) -> None:
        """Test MarketDataClient initialization with custom target."""
        client = MarketDataClient("localhost:9000")

        assert client._target == "localhost:9000"

    def test_init_with_secure(self) -> None:
        """Test MarketDataClient initialization with secure=True."""
        client = MarketDataClient(secure=True)

        assert client._secure is True

    def test_init_with_interceptors(self) -> None:
        """Test MarketDataClient initialization with interceptors."""
        interceptor = object()
        client = MarketDataClient(interceptors=[interceptor])

        assert client._interceptors == [interceptor]

    def test_init_with_custom_options(self) -> None:
        """Test MarketDataClient initialization with custom options."""
        options = [("grpc.max_send_message_length", 100)]
        client = MarketDataClient(options=options)

        assert client._options == options


class TestMarketDataClientStub:
    """Tests for MarketDataClient stub property."""

    def test_stub_raises_on_missing_generated_code(self) -> None:
        """Test stub raises RuntimeError when generated code is missing."""
        client = MarketDataClient()

        with patch("grpc.aio.insecure_channel"):
            with patch.dict("sys.modules", {"llamatrade_proto.generated": None}):
                with pytest.raises((RuntimeError, ImportError)):
                    _ = client.stub


class TestMarketDataClientGetHistoricalBars:
    """Tests for MarketDataClient.get_historical_bars method."""

    @pytest.mark.asyncio
    async def test_get_historical_bars_success(self) -> None:
        """Test get_historical_bars returns list of bars."""
        client = MarketDataClient()

        # Create mock proto bar
        mock_timestamp = MagicMock()
        mock_timestamp.seconds = 1705320000

        mock_open = MagicMock()
        mock_open.value = "150.00"

        mock_high = MagicMock()
        mock_high.value = "152.00"

        mock_low = MagicMock()
        mock_low.value = "149.00"

        mock_close = MagicMock()
        mock_close.value = "151.00"

        mock_bar = MagicMock()
        mock_bar.symbol = "AAPL"
        mock_bar.timestamp = mock_timestamp
        mock_bar.open = mock_open
        mock_bar.high = mock_high
        mock_bar.low = mock_low
        mock_bar.close = mock_close
        mock_bar.volume = 1000000
        mock_bar.trade_count = 5000
        mock_bar.HasField = lambda field: field in ["open", "high", "low", "close"]
        mock_bar.vwap = None

        mock_response = MagicMock()
        mock_response.bars = [mock_bar]

        mock_stub = MagicMock()
        mock_stub.GetHistoricalBars = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        # Mock the market_data_pb2 module
        mock_market_data_pb2 = MagicMock()
        mock_market_data_pb2.TIMEFRAME_1MIN = 1
        mock_market_data_pb2.TIMEFRAME_5MIN = 2
        mock_market_data_pb2.TIMEFRAME_15MIN = 3
        mock_market_data_pb2.TIMEFRAME_30MIN = 4
        mock_market_data_pb2.TIMEFRAME_1HOUR = 5
        mock_market_data_pb2.TIMEFRAME_4HOUR = 6
        mock_market_data_pb2.TIMEFRAME_1DAY = 7
        mock_market_data_pb2.TIMEFRAME_1WEEK = 8
        mock_market_data_pb2.TIMEFRAME_1MONTH = 9

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.market_data_pb2": mock_market_data_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.get_historical_bars(
                symbol="AAPL",
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                timeframe="1D",
            )

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].open == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_get_historical_bars_empty(self) -> None:
        """Test get_historical_bars returns empty list."""
        client = MarketDataClient()

        mock_response = MagicMock()
        mock_response.bars = []

        mock_stub = MagicMock()
        mock_stub.GetHistoricalBars = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_market_data_pb2 = MagicMock()
        mock_market_data_pb2.TIMEFRAME_1DAY = 7

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.market_data_pb2": mock_market_data_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.get_historical_bars(
                symbol="AAPL",
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
            )

        assert result == []


class TestMarketDataClientProtoConversion:
    """Tests for MarketDataClient proto conversion methods."""

    def test_proto_to_bar_with_vwap(self) -> None:
        """Test _proto_to_bar with vwap."""
        client = MarketDataClient()

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = 1705320000

        mock_open = MagicMock()
        mock_open.value = "150.00"

        mock_high = MagicMock()
        mock_high.value = "152.00"

        mock_low = MagicMock()
        mock_low.value = "149.00"

        mock_close = MagicMock()
        mock_close.value = "151.00"

        mock_vwap = MagicMock()
        mock_vwap.value = "150.50"

        mock_bar = MagicMock()
        mock_bar.symbol = "AAPL"
        mock_bar.timestamp = mock_timestamp
        mock_bar.open = mock_open
        mock_bar.high = mock_high
        mock_bar.low = mock_low
        mock_bar.close = mock_close
        mock_bar.volume = 1000000
        mock_bar.trade_count = 5000
        mock_bar.vwap = mock_vwap
        mock_bar.HasField = lambda field: True

        result = client._proto_to_bar(mock_bar)

        assert result.symbol == "AAPL"
        assert result.vwap == Decimal("150.50")
        assert result.trade_count == 5000

    def test_proto_to_quote(self) -> None:
        """Test _proto_to_quote conversion."""
        client = MarketDataClient()

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = 1705320000

        mock_bid = MagicMock()
        mock_bid.value = "150.00"

        mock_ask = MagicMock()
        mock_ask.value = "150.05"

        mock_quote = MagicMock()
        mock_quote.symbol = "AAPL"
        mock_quote.timestamp = mock_timestamp
        mock_quote.bid_price = mock_bid
        mock_quote.bid_size = 100
        mock_quote.ask_price = mock_ask
        mock_quote.ask_size = 200

        result = client._proto_to_quote(mock_quote)

        assert result.symbol == "AAPL"
        assert result.bid_price == Decimal("150.00")
        assert result.ask_price == Decimal("150.05")
        assert result.bid_size == 100
        assert result.ask_size == 200

    def test_proto_to_trade_with_exchange(self) -> None:
        """Test _proto_to_trade with exchange."""
        client = MarketDataClient()

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = 1705320000

        mock_price = MagicMock()
        mock_price.value = "150.50"

        mock_trade = MagicMock()
        mock_trade.symbol = "AAPL"
        mock_trade.timestamp = mock_timestamp
        mock_trade.price = mock_price
        mock_trade.size = 100
        mock_trade.exchange = "NASDAQ"

        result = client._proto_to_trade(mock_trade)

        assert result.symbol == "AAPL"
        assert result.price == Decimal("150.50")
        assert result.size == 100
        assert result.exchange == "NASDAQ"

    def test_proto_to_trade_without_exchange(self) -> None:
        """Test _proto_to_trade without exchange."""
        client = MarketDataClient()

        mock_timestamp = MagicMock()
        mock_timestamp.seconds = 1705320000

        mock_price = MagicMock()
        mock_price.value = "150.50"

        mock_trade = MagicMock()
        mock_trade.symbol = "AAPL"
        mock_trade.timestamp = mock_timestamp
        mock_trade.price = mock_price
        mock_trade.size = 100
        mock_trade.exchange = ""

        result = client._proto_to_trade(mock_trade)

        assert result.exchange is None
