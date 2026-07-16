"""Tests for llamatrade_proto.clients.market_data module (Connect client)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
        assert quote.bid_price == Decimal("150.00")
        assert quote.ask_price == Decimal("150.05")

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

        assert quote.ask_price - quote.bid_price == Decimal("0.10")


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
        assert trade.price == Decimal("150.50")
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


def _mock_proto_bar(symbol: str, close: str) -> MagicMock:
    """A MagicMock shaped like a proto Bar (fields carry a ``.value`` string)."""
    bar = MagicMock()
    bar.symbol = symbol
    bar.timestamp = MagicMock(seconds=1705320000)
    for field in ("open", "high", "low", "close"):
        setattr(bar, field, MagicMock(value=close))
    bar.volume = 1000
    bar.trade_count = 0
    bar.HasField = lambda f: f in ("open", "high", "low", "close")
    bar.vwap = None
    return bar


def _connect_client(client: MarketDataClient) -> MagicMock:
    """Attach a mock Connect client + no-op auth headers; return the mock."""
    conn = MagicMock()
    client._client = conn
    client._headers = lambda: {}  # type: ignore[method-assign]
    return conn


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization (Connect client)."""

    def test_init_with_defaults(self) -> None:
        """Bare host:port is normalized to an absolute URL; lazy client."""
        client = MarketDataClient()
        assert client.target == "http://market-data:8840"
        assert client._service_name == "internal"
        assert client._client is None

    def test_init_with_custom_target(self) -> None:
        client = MarketDataClient("localhost:9000")
        assert client.target == "http://localhost:9000"

    def test_init_preserves_absolute_url(self) -> None:
        client = MarketDataClient("https://market-data.internal")
        assert client.target == "https://market-data.internal"

    def test_init_with_service_name(self) -> None:
        client = MarketDataClient(service_name="backtest")
        assert client._service_name == "backtest"


class TestMarketDataClientGetHistoricalBars:
    """Tests for MarketDataClient.get_historical_bars (Connect)."""

    @pytest.mark.asyncio
    async def test_get_historical_bars_success(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_historical_bars = AsyncMock(
            return_value=MagicMock(bars=[_mock_proto_bar("AAPL", "151.00")])
        )

        result = await client.get_historical_bars(
            symbol="AAPL", start=datetime(2024, 1, 1), end=datetime(2024, 1, 31), timeframe="1D"
        )

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].close == Decimal("151.00")
        conn.get_historical_bars.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_historical_bars_empty(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_historical_bars = AsyncMock(return_value=MagicMock(bars=[]))

        result = await client.get_historical_bars(
            symbol="AAPL", start=datetime(2024, 1, 1), end=datetime(2024, 1, 31)
        )

        assert result == []


class TestMarketDataClientGetMultiBars:
    """Tests for MarketDataClient.get_multi_bars (batched fetch, 16B)."""

    @pytest.mark.asyncio
    async def test_get_multi_bars_success(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_multi_bars = AsyncMock(
            return_value=MagicMock(
                bars={
                    "AAPL": MagicMock(bars=[_mock_proto_bar("AAPL", "150.00")]),
                    "SPY": MagicMock(bars=[_mock_proto_bar("SPY", "400.00")]),
                }
            )
        )

        result = await client.get_multi_bars(
            symbols=["AAPL", "SPY"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 31),
            timeframe="1D",
            limit=5000,
        )

        assert set(result) == {"AAPL", "SPY"}
        assert result["AAPL"][0].close == Decimal("150.00")
        assert result["SPY"][0].close == Decimal("400.00")
        conn.get_multi_bars.assert_awaited_once()


class TestMarketDataClientStreamHistoricalBars:
    """Tests for MarketDataClient.stream_historical_bars (streamed batch, 13B)."""

    @pytest.mark.asyncio
    async def test_stream_historical_bars_yields_bars(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)

        async def fake_stream(_request, headers=None):
            yield _mock_proto_bar("AAPL", "150.00")
            yield _mock_proto_bar("SPY", "400.00")

        conn.stream_historical_bars = fake_stream

        out = [
            bar
            async for bar in client.stream_historical_bars(
                symbols=["AAPL", "SPY"],
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                timeframe="1D",
            )
        ]

        assert [bar.symbol for bar in out] == ["AAPL", "SPY"]
        assert out[0].close == Decimal("150.00")


class TestMarketDataClientProtoConversion:
    """Tests for MarketDataClient proto conversion methods."""

    def test_proto_to_bar_with_vwap(self) -> None:
        """Test _proto_to_bar with vwap."""
        client = MarketDataClient()

        mock_vwap = MagicMock()
        mock_vwap.value = "150.50"

        mock_bar = _mock_proto_bar("AAPL", "151.00")
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

        mock_quote = MagicMock()
        mock_quote.symbol = "AAPL"
        mock_quote.timestamp = MagicMock(seconds=1705320000)
        mock_quote.bid_price = MagicMock(value="150.00")
        mock_quote.bid_size = 100
        mock_quote.ask_price = MagicMock(value="150.05")
        mock_quote.ask_size = 200

        result = client._proto_to_quote(mock_quote)

        assert result.symbol == "AAPL"
        assert result.bid_price == Decimal("150.00")
        assert result.ask_price == Decimal("150.05")

    def test_proto_to_trade_with_exchange(self) -> None:
        """Test _proto_to_trade with exchange."""
        client = MarketDataClient()

        mock_trade = MagicMock()
        mock_trade.symbol = "AAPL"
        mock_trade.timestamp = MagicMock(seconds=1705320000)
        mock_trade.price = MagicMock(value="150.50")
        mock_trade.size = 100
        mock_trade.exchange = "NASDAQ"

        result = client._proto_to_trade(mock_trade)

        assert result.price == Decimal("150.50")
        assert result.exchange == "NASDAQ"

    def test_proto_to_trade_without_exchange(self) -> None:
        """Test _proto_to_trade without exchange."""
        client = MarketDataClient()

        mock_trade = MagicMock()
        mock_trade.symbol = "AAPL"
        mock_trade.timestamp = MagicMock(seconds=1705320000)
        mock_trade.price = MagicMock(value="150.50")
        mock_trade.size = 100
        mock_trade.exchange = ""

        result = client._proto_to_trade(mock_trade)

        assert result.exchange is None
