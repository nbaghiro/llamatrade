"""Tests for MarketDataClient."""

import pytest
import respx
from httpx import Response

from llamatrade_alpaca import (
    Bar,
    MarketDataClient,
    Quote,
    Snapshot,
    Timeframe,
)

# Paper mode uses sandbox URL
BASE_URL = "https://data.sandbox.alpaca.markets/v2"


@pytest.fixture
def market_client() -> MarketDataClient:
    """Create a MarketDataClient for testing."""
    return MarketDataClient(
        api_key="test_key",
        api_secret="test_secret",
        paper=True,
    )


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization."""

    def test_init_with_credentials(self) -> None:
        """Test client initialization with explicit credentials."""
        client = MarketDataClient(
            api_key="my_key",
            api_secret="my_secret",
            paper=True,
        )
        assert client.paper is True


class TestGetBars:
    """Tests for get_bars method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_bars_success(self, market_client: MarketDataClient) -> None:
        """Test successful bars retrieval."""
        from datetime import datetime

        respx.get(f"{BASE_URL}/stocks/AAPL/bars").mock(
            return_value=Response(
                200,
                json={
                    "bars": [
                        {
                            "t": "2024-01-15T09:30:00Z",
                            "o": 150.00,
                            "h": 151.50,
                            "l": 149.50,
                            "c": 151.00,
                            "v": 1000000,
                            "vw": 150.50,
                            "n": 5000,
                        },
                        {
                            "t": "2024-01-15T09:31:00Z",
                            "o": 151.00,
                            "h": 152.00,
                            "l": 150.50,
                            "c": 151.75,
                            "v": 800000,
                        },
                    ]
                },
            )
        )

        bars = await market_client.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.MINUTE_1,
            start=datetime(2024, 1, 15),
        )

        assert len(bars) == 2
        assert isinstance(bars[0], Bar)
        assert bars[0].open == 150.00
        assert bars[0].close == 151.00

        await market_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_bars_empty(self, market_client: MarketDataClient) -> None:
        """Test getting bars for a period with no data."""
        from datetime import datetime

        respx.get(f"{BASE_URL}/stocks/AAPL/bars").mock(
            return_value=Response(200, json={"bars": []})
        )

        bars = await market_client.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 15),
        )

        assert bars == []

        await market_client.close()


class TestGetMultiBars:
    """Tests for get_multi_bars method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_multi_bars(self, market_client: MarketDataClient) -> None:
        """Test getting bars for multiple symbols."""
        from datetime import datetime

        respx.get(f"{BASE_URL}/stocks/bars").mock(
            return_value=Response(
                200,
                json={
                    "bars": {
                        "AAPL": [
                            {
                                "t": "2024-01-15T00:00:00Z",
                                "o": 150.00,
                                "h": 152.00,
                                "l": 149.00,
                                "c": 151.00,
                                "v": 10000000,
                            }
                        ],
                        "MSFT": [
                            {
                                "t": "2024-01-15T00:00:00Z",
                                "o": 350.00,
                                "h": 355.00,
                                "l": 348.00,
                                "c": 352.00,
                                "v": 8000000,
                            }
                        ],
                    }
                },
            )
        )

        bars = await market_client.get_multi_bars(
            symbols=["AAPL", "MSFT"],
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 15),
        )

        assert "AAPL" in bars
        assert "MSFT" in bars
        assert len(bars["AAPL"]) == 1
        assert bars["AAPL"][0].close == 151.00

        await market_client.close()


class TestGetLatestBar:
    """Tests for get_latest_bar method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_latest_bar(self, market_client: MarketDataClient) -> None:
        """Test getting the latest bar."""
        respx.get(f"{BASE_URL}/stocks/AAPL/bars/latest").mock(
            return_value=Response(
                200,
                json={
                    "bar": {
                        "t": "2024-01-15T14:30:00Z",
                        "o": 150.00,
                        "h": 151.00,
                        "l": 149.50,
                        "c": 150.75,
                        "v": 500000,
                    }
                },
            )
        )

        bar = await market_client.get_latest_bar("AAPL")

        assert bar is not None
        assert isinstance(bar, Bar)
        assert bar.close == 150.75

        await market_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_latest_bar_not_available(self, market_client: MarketDataClient) -> None:
        """Test getting latest bar when not available."""
        respx.get(f"{BASE_URL}/stocks/AAPL/bars/latest").mock(return_value=Response(200, json={}))

        bar = await market_client.get_latest_bar("AAPL")

        assert bar is None

        await market_client.close()


class TestGetLatestQuote:
    """Tests for get_latest_quote method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_latest_quote(self, market_client: MarketDataClient) -> None:
        """Test getting the latest quote."""
        respx.get(f"{BASE_URL}/stocks/AAPL/quotes/latest").mock(
            return_value=Response(
                200,
                json={
                    "quote": {
                        "t": "2024-01-15T14:30:00Z",
                        "bp": 150.00,
                        "bs": 100,
                        "ap": 150.10,
                        "as": 200,
                    }
                },
            )
        )

        quote = await market_client.get_latest_quote("AAPL")

        assert quote is not None
        assert isinstance(quote, Quote)
        assert quote.bid_price == 150.00
        assert quote.ask_price == 150.10

        await market_client.close()


class TestGetSnapshot:
    """Tests for get_snapshot method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot(self, market_client: MarketDataClient) -> None:
        """Test getting a market snapshot."""
        respx.get(f"{BASE_URL}/stocks/AAPL/snapshot").mock(
            return_value=Response(
                200,
                json={
                    "latestTrade": {
                        "t": "2024-01-15T14:30:00Z",
                        "p": 150.50,
                        "s": 100,
                        "x": "NYSE",
                    },
                    "latestQuote": {
                        "t": "2024-01-15T14:30:00Z",
                        "bp": 150.00,
                        "bs": 100,
                        "ap": 150.10,
                        "as": 200,
                    },
                    "minuteBar": {
                        "t": "2024-01-15T14:30:00Z",
                        "o": 150.00,
                        "h": 151.00,
                        "l": 149.50,
                        "c": 150.75,
                        "v": 500000,
                    },
                    "dailyBar": {
                        "t": "2024-01-15T00:00:00Z",
                        "o": 149.00,
                        "h": 152.00,
                        "l": 148.50,
                        "c": 150.75,
                        "v": 10000000,
                    },
                },
            )
        )

        snapshot = await market_client.get_snapshot("AAPL")

        assert snapshot is not None
        assert isinstance(snapshot, Snapshot)
        assert snapshot.symbol == "AAPL"
        assert snapshot.latest_trade is not None
        assert snapshot.latest_quote is not None
        assert snapshot.minute_bar is not None
        assert snapshot.daily_bar is not None

        await market_client.close()


class TestGetMultiSnapshots:
    """Tests for get_multi_snapshots method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_multi_snapshots(self, market_client: MarketDataClient) -> None:
        """Test getting snapshots for multiple symbols."""
        respx.get(f"{BASE_URL}/stocks/snapshots").mock(
            return_value=Response(
                200,
                json={
                    "AAPL": {
                        "latestQuote": {
                            "t": "2024-01-15T14:30:00Z",
                            "bp": 150.00,
                            "bs": 100,
                            "ap": 150.10,
                            "as": 200,
                        },
                    },
                    "MSFT": {
                        "latestQuote": {
                            "t": "2024-01-15T14:30:00Z",
                            "bp": 350.00,
                            "bs": 50,
                            "ap": 350.25,
                            "as": 75,
                        },
                    },
                },
            )
        )

        snapshots = await market_client.get_multi_snapshots(["AAPL", "MSFT"])

        assert "AAPL" in snapshots
        assert "MSFT" in snapshots
        assert isinstance(snapshots["AAPL"], Snapshot)

        await market_client.close()
