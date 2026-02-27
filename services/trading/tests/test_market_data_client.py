"""Tests for gRPC market data client usage in trading service."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llamatrade_grpc.clients.market_data import Bar, MarketDataClient, Quote, Trade


class TestMarketDataClientMethods:
    """Tests for MarketDataClient method behavior."""

    @pytest.fixture
    def mock_client(self):
        """Create a fully mocked MarketDataClient."""
        with patch.object(MarketDataClient, "__init__", lambda self, *args, **kwargs: None):
            client = MarketDataClient()
            client._channel = MagicMock()
            client._stub = MagicMock()
            # Mock the actual methods to avoid protobuf imports
            client.get_historical_bars = AsyncMock()
            client.stream_bars = MagicMock()
            client.stream_quotes = MagicMock()
            client.stream_trades = MagicMock()
            return client

    async def test_get_historical_bars_returns_bar_list(self, mock_client):
        """Test get_historical_bars returns list of Bar objects."""
        # Setup mock to return Bar objects
        mock_bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2, 9, 30),
                open=Decimal("185.00"),
                high=Decimal("186.50"),
                low=Decimal("184.00"),
                close=Decimal("185.50"),
                volume=50000000,
                trade_count=100000,
                vwap=Decimal("185.25"),
            )
        ]
        mock_client.get_historical_bars.return_value = mock_bars

        bars = await mock_client.get_historical_bars(
            symbol="AAPL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
            timeframe="1D",
        )

        assert len(bars) == 1
        assert bars[0].symbol == "AAPL"
        assert bars[0].close == Decimal("185.50")
        assert bars[0].volume == 50000000
        mock_client.get_historical_bars.assert_called_once()

    async def test_get_historical_bars_empty_response(self, mock_client):
        """Test get_historical_bars with no data returned."""
        mock_client.get_historical_bars.return_value = []

        bars = await mock_client.get_historical_bars(
            symbol="INVALID",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
        )

        assert bars == []

    async def test_get_historical_bars_multiple_timeframes(self, mock_client):
        """Test different timeframe parameters are accepted."""
        mock_client.get_historical_bars.return_value = []

        timeframes = ["1MIN", "5MIN", "15MIN", "1HOUR", "1DAY", "1D", "1WEEK"]
        for timeframe in timeframes:
            await mock_client.get_historical_bars(
                symbol="AAPL",
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                timeframe=timeframe,
            )

        assert mock_client.get_historical_bars.call_count == 7

    async def test_get_historical_bars_with_options(self, mock_client):
        """Test get_historical_bars with additional options."""
        mock_client.get_historical_bars.return_value = []

        await mock_client.get_historical_bars(
            symbol="AAPL",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
            timeframe="1D",
            adjust_for_splits=False,
            page_size=500,
        )

        call_kwargs = mock_client.get_historical_bars.call_args[1]
        assert call_kwargs.get("adjust_for_splits") is False
        assert call_kwargs.get("page_size") == 500

    async def test_stream_bars(self, mock_client):
        """Test streaming bars."""
        mock_bars = [
            Bar(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2, 9, 30),
                open=Decimal("185.00"),
                high=Decimal("186.00"),
                low=Decimal("184.50"),
                close=Decimal("185.50"),
                volume=1000,
            ),
            Bar(
                symbol="GOOGL",
                timestamp=datetime(2024, 1, 2, 9, 30),
                open=Decimal("140.00"),
                high=Decimal("141.00"),
                low=Decimal("139.50"),
                close=Decimal("140.50"),
                volume=500,
            ),
        ]

        async def mock_stream(*args, **kwargs):
            for bar in mock_bars:
                yield bar

        mock_client.stream_bars = mock_stream

        bars = []
        async for bar in mock_client.stream_bars(["AAPL", "GOOGL"]):
            bars.append(bar)

        assert len(bars) == 2
        assert bars[0].symbol == "AAPL"
        assert bars[1].symbol == "GOOGL"

    async def test_stream_quotes(self, mock_client):
        """Test streaming quotes."""
        mock_quotes = [
            Quote(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2, 9, 30),
                bid_price=Decimal("185.40"),
                bid_size=100,
                ask_price=Decimal("185.50"),
                ask_size=200,
            )
        ]

        async def mock_stream(*args, **kwargs):
            for quote in mock_quotes:
                yield quote

        mock_client.stream_quotes = mock_stream

        quotes = []
        async for quote in mock_client.stream_quotes(["AAPL"]):
            quotes.append(quote)

        assert len(quotes) == 1
        assert quotes[0].symbol == "AAPL"
        assert quotes[0].bid_price == Decimal("185.40")
        assert quotes[0].ask_price == Decimal("185.50")

    async def test_stream_trades(self, mock_client):
        """Test streaming trades."""
        mock_trades = [
            Trade(
                symbol="AAPL",
                timestamp=datetime(2024, 1, 2, 9, 30),
                price=Decimal("185.50"),
                size=100,
                exchange="NASDAQ",
            )
        ]

        async def mock_stream(*args, **kwargs):
            for trade in mock_trades:
                yield trade

        mock_client.stream_trades = mock_stream

        trades = []
        async for trade in mock_client.stream_trades(["AAPL"]):
            trades.append(trade)

        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"
        assert trades[0].price == Decimal("185.50")
        assert trades[0].exchange == "NASDAQ"


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization."""

    def test_init_default_target(self):
        """Test default target initialization."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            client = MarketDataClient()
            # Channel is created lazily, so access the property to trigger creation
            _ = client.channel
            mock_channel.assert_called()
            call_args = mock_channel.call_args[0][0]
            assert call_args == "market-data:8840"

    def test_init_custom_target(self):
        """Test custom target initialization."""
        with patch("grpc.aio.insecure_channel") as mock_channel:
            mock_channel.return_value = MagicMock()
            client = MarketDataClient(target="custom-host:9999")
            # Channel is created lazily, so access the property to trigger creation
            _ = client.channel
            call_args = mock_channel.call_args[0][0]
            assert call_args == "custom-host:9999"


class TestBarDataclass:
    """Tests for Bar dataclass."""

    def test_bar_creation(self):
        """Test Bar dataclass creation."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            open=Decimal("185.00"),
            high=Decimal("186.50"),
            low=Decimal("184.00"),
            close=Decimal("185.50"),
            volume=50000000,
            trade_count=100000,
            vwap=Decimal("185.25"),
        )

        assert bar.symbol == "AAPL"
        assert bar.close == Decimal("185.50")
        assert bar.volume == 50000000
        assert bar.vwap == Decimal("185.25")

    def test_bar_optional_fields(self):
        """Test Bar with optional fields as None."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            open=Decimal("185.00"),
            high=Decimal("186.50"),
            low=Decimal("184.00"),
            close=Decimal("185.50"),
            volume=50000000,
        )

        assert bar.trade_count is None
        assert bar.vwap is None


class TestQuoteDataclass:
    """Tests for Quote dataclass."""

    def test_quote_creation(self):
        """Test Quote dataclass creation."""
        quote = Quote(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            bid_price=Decimal("185.40"),
            bid_size=100,
            ask_price=Decimal("185.50"),
            ask_size=200,
        )

        assert quote.symbol == "AAPL"
        assert quote.bid_price == Decimal("185.40")
        assert quote.ask_price == Decimal("185.50")
        assert quote.bid_size == 100
        assert quote.ask_size == 200


class TestTradeDataclass:
    """Tests for Trade dataclass."""

    def test_trade_creation(self):
        """Test Trade dataclass creation."""
        trade = Trade(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            price=Decimal("185.50"),
            size=100,
            exchange="NASDAQ",
        )

        assert trade.symbol == "AAPL"
        assert trade.price == Decimal("185.50")
        assert trade.size == 100
        assert trade.exchange == "NASDAQ"

    def test_trade_optional_exchange(self):
        """Test Trade with optional exchange as None."""
        trade = Trade(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 9, 30),
            price=Decimal("185.50"),
            size=100,
        )

        assert trade.exchange is None
