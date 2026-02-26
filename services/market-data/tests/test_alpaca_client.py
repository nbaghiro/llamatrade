"""Tests for Alpaca Market Data API client."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.alpaca.client import (
    AlpacaDataClient,
    close_alpaca_client,
    get_alpaca_client,
)
from src.models import Timeframe


def create_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx Response."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    return mock_response


@pytest.fixture
def mock_httpx_client():
    """Mock httpx async client."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def mock_rate_limiter():
    """Mock rate limiter."""
    limiter = AsyncMock()
    limiter.acquire = AsyncMock()
    return limiter


@pytest.fixture
def mock_circuit_breaker():
    """Mock circuit breaker."""
    breaker = AsyncMock()

    # Circuit breaker calls the function passed to it
    async def call_through(func):
        return await func()

    breaker.call = call_through
    return breaker


class TestAlpacaDataClientInit:
    """Tests for AlpacaDataClient initialization."""

    def test_init_paper_mode(self):
        """Test initialization in paper mode."""
        with patch("httpx.AsyncClient") as mock_client:
            with patch("src.alpaca.client.get_rate_limiter") as mock_rl:
                with patch("src.alpaca.client.get_circuit_breaker") as mock_cb:
                    mock_rl.return_value = MagicMock()
                    mock_cb.return_value = MagicMock()

                    client = AlpacaDataClient(
                        api_key="test-key",
                        api_secret="test-secret",
                        paper=True,
                    )

                    assert client.base_url == AlpacaDataClient.PAPER_URL
                    call_kwargs = mock_client.call_args[1]
                    assert call_kwargs["base_url"] == AlpacaDataClient.PAPER_URL

    def test_init_live_mode(self):
        """Test initialization in live mode."""
        with patch("httpx.AsyncClient"):
            with patch("src.alpaca.client.get_rate_limiter") as mock_rl:
                with patch("src.alpaca.client.get_circuit_breaker") as mock_cb:
                    mock_rl.return_value = MagicMock()
                    mock_cb.return_value = MagicMock()

                    client = AlpacaDataClient(
                        api_key="test-key",
                        api_secret="test-secret",
                        paper=False,
                    )

                    assert client.base_url == AlpacaDataClient.BASE_URL

    def test_init_from_env(self):
        """Test initialization from environment variables."""
        with patch.dict(
            "os.environ",
            {"ALPACA_API_KEY": "env-key", "ALPACA_API_SECRET": "env-secret"},
        ):
            with patch("httpx.AsyncClient") as mock_client:
                with patch("src.alpaca.client.get_rate_limiter") as mock_rl:
                    with patch("src.alpaca.client.get_circuit_breaker") as mock_cb:
                        mock_rl.return_value = MagicMock()
                        mock_cb.return_value = MagicMock()

                        AlpacaDataClient()

                        call_kwargs = mock_client.call_args[1]
                        assert call_kwargs["headers"]["APCA-API-KEY-ID"] == "env-key"

    def test_init_with_custom_resilience(self):
        """Test initialization with custom resilience components."""
        custom_limiter = MagicMock()
        custom_breaker = MagicMock()

        with patch("httpx.AsyncClient"):
            client = AlpacaDataClient(
                api_key="key",
                api_secret="secret",
                rate_limiter=custom_limiter,
                circuit_breaker=custom_breaker,
            )

            assert client._rate_limiter is custom_limiter
            assert client._circuit_breaker is custom_breaker


class TestAlpacaDataClientMethods:
    """Tests for AlpacaDataClient API methods."""

    async def test_close(self, mock_httpx_client):
        """Test closing the client."""
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client

            await client.close()

        mock_httpx_client.aclose.assert_called_once()

    async def test_get_bars_success(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting historical bars."""
        bar_data = {
            "bars": [
                {
                    "t": "2024-01-15T16:00:00Z",
                    "o": 150.0,
                    "h": 152.5,
                    "l": 149.0,
                    "c": 151.75,
                    "v": 1000000,
                    "vw": 150.5,
                    "n": 5000,
                },
                {
                    "t": "2024-01-16T16:00:00Z",
                    "o": 151.75,
                    "h": 153.0,
                    "l": 150.5,
                    "c": 152.25,
                    "v": 1100000,
                },
            ]
        }
        mock_response = create_mock_response(bar_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            start = datetime(2024, 1, 15, tzinfo=UTC)
            bars = await client.get_bars("AAPL", Timeframe.DAY_1, start)

        assert len(bars) == 2
        assert bars[0].open == 150.0
        assert bars[0].close == 151.75
        assert bars[0].vwap == 150.5
        assert bars[1].vwap is None  # Missing in response

    async def test_get_bars_with_end_date(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting bars with end date."""
        mock_response = create_mock_response({"bars": []})
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            start = datetime(2024, 1, 15, tzinfo=UTC)
            end = datetime(2024, 1, 20, tzinfo=UTC)
            await client.get_bars("AAPL", Timeframe.DAY_1, start, end=end)

        call_kwargs = mock_httpx_client.request.call_args[1]
        assert "end" in call_kwargs["params"]

    async def test_get_multi_bars(self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker):
        """Test getting bars for multiple symbols."""
        bar_data = {
            "bars": {
                "AAPL": [
                    {
                        "t": "2024-01-15T16:00:00Z",
                        "o": 150.0,
                        "h": 152.5,
                        "l": 149.0,
                        "c": 151.75,
                        "v": 1000000,
                    }
                ],
                "GOOGL": [
                    {
                        "t": "2024-01-15T16:00:00Z",
                        "o": 140.0,
                        "h": 142.0,
                        "l": 139.0,
                        "c": 141.5,
                        "v": 500000,
                    }
                ],
            }
        }
        mock_response = create_mock_response(bar_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            start = datetime(2024, 1, 15, tzinfo=UTC)
            result = await client.get_multi_bars(["AAPL", "GOOGL"], Timeframe.DAY_1, start)

        assert "AAPL" in result
        assert "GOOGL" in result
        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].close == 151.75

    async def test_get_latest_bar_success(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting latest bar."""
        bar_data = {
            "bar": {
                "t": "2024-01-15T16:00:00Z",
                "o": 150.0,
                "h": 152.5,
                "l": 149.0,
                "c": 151.75,
                "v": 1000000,
            }
        }
        mock_response = create_mock_response(bar_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            bar = await client.get_latest_bar("AAPL")

        assert bar is not None
        assert bar.close == 151.75

    async def test_get_latest_bar_none(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting latest bar when none exists."""
        mock_response = create_mock_response({"bar": None})
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            bar = await client.get_latest_bar("AAPL")

        assert bar is None

    async def test_get_latest_quote_success(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting latest quote."""
        quote_data = {
            "quote": {
                "t": "2024-01-15T16:00:00Z",
                "bp": 151.50,
                "bs": 100,
                "ap": 151.55,
                "as": 200,
            }
        }
        mock_response = create_mock_response(quote_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            quote = await client.get_latest_quote("AAPL")

        assert quote is not None
        assert quote.bid_price == 151.50
        assert quote.ask_price == 151.55
        assert quote.symbol == "AAPL"

    async def test_get_latest_quote_none(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting latest quote when none exists."""
        mock_response = create_mock_response({"quote": None})
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            quote = await client.get_latest_quote("AAPL")

        assert quote is None

    async def test_get_snapshot_success(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting a market snapshot."""
        snapshot_data = {
            "latestTrade": {
                "t": "2024-01-15T16:00:00Z",
                "p": 151.52,
                "s": 50,
                "x": "NASDAQ",
            },
            "latestQuote": {
                "t": "2024-01-15T16:00:00Z",
                "bp": 151.50,
                "bs": 100,
                "ap": 151.55,
                "as": 200,
            },
            "minuteBar": {
                "t": "2024-01-15T16:00:00Z",
                "o": 151.0,
                "h": 152.0,
                "l": 150.5,
                "c": 151.5,
                "v": 50000,
            },
            "dailyBar": {
                "t": "2024-01-15T16:00:00Z",
                "o": 150.0,
                "h": 153.0,
                "l": 149.0,
                "c": 152.0,
                "v": 5000000,
            },
            "prevDailyBar": None,
        }
        mock_response = create_mock_response(snapshot_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            snapshot = await client.get_snapshot("AAPL")

        assert snapshot is not None
        assert snapshot.symbol == "AAPL"
        assert snapshot.latest_trade is not None
        assert snapshot.latest_trade.price == 151.52
        assert snapshot.latest_quote is not None
        assert snapshot.minute_bar is not None
        assert snapshot.daily_bar is not None
        assert snapshot.prev_daily_bar is None

    async def test_get_snapshot_empty(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting snapshot when symbol has no data."""
        mock_response = create_mock_response({})
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            snapshot = await client.get_snapshot("INVALID")

        assert snapshot is None

    async def test_get_multi_snapshots(
        self, mock_httpx_client, mock_rate_limiter, mock_circuit_breaker
    ):
        """Test getting snapshots for multiple symbols."""
        snapshots_data = {
            "AAPL": {
                "latestTrade": {
                    "t": "2024-01-15T16:00:00Z",
                    "p": 151.52,
                    "s": 50,
                },
                "latestQuote": {
                    "t": "2024-01-15T16:00:00Z",
                    "bp": 151.50,
                    "bs": 100,
                    "ap": 151.55,
                    "as": 200,
                },
            },
            "GOOGL": {
                "latestTrade": {
                    "t": "2024-01-15T16:00:00Z",
                    "p": 141.25,
                    "s": 30,
                },
                "latestQuote": {
                    "t": "2024-01-15T16:00:00Z",
                    "bp": 141.20,
                    "bs": 150,
                    "ap": 141.30,
                    "as": 100,
                },
            },
        }
        mock_response = create_mock_response(snapshots_data)
        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            client._client = mock_httpx_client
            client._rate_limiter = mock_rate_limiter
            client._circuit_breaker = mock_circuit_breaker

            result = await client.get_multi_snapshots(["AAPL", "GOOGL"])

        assert "AAPL" in result
        assert "GOOGL" in result
        assert result["AAPL"].latest_trade.price == 151.52
        assert result["GOOGL"].latest_trade.price == 141.25


class TestParsingMethods:
    """Tests for parsing helper methods."""

    def test_parse_bar_none(self):
        """Test parsing None bar data."""
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_bar(None)
        assert result is None

    def test_parse_bar_valid(self):
        """Test parsing valid bar data."""
        bar_data = {
            "t": "2024-01-15T16:00:00Z",
            "o": 150.0,
            "h": 152.5,
            "l": 149.0,
            "c": 151.75,
            "v": 1000000,
            "vw": 150.5,
            "n": 5000,
        }
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_bar(bar_data)

        assert result is not None
        assert result.open == 150.0
        assert result.close == 151.75
        assert result.vwap == 150.5

    def test_parse_quote_none(self):
        """Test parsing None quote data."""
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_quote(None, "AAPL")
        assert result is None

    def test_parse_quote_valid(self):
        """Test parsing valid quote data."""
        quote_data = {
            "t": "2024-01-15T16:00:00Z",
            "bp": 151.50,
            "bs": 100,
            "ap": 151.55,
            "as": 200,
        }
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_quote(quote_data, "AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.bid_price == 151.50

    def test_parse_trade_none(self):
        """Test parsing None trade data."""
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_trade(None, "AAPL")
        assert result is None

    def test_parse_trade_valid(self):
        """Test parsing valid trade data."""
        trade_data = {
            "t": "2024-01-15T16:00:00Z",
            "p": 151.52,
            "s": 50,
            "x": "NASDAQ",
        }
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_trade(trade_data, "AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.price == 151.52
        assert result.exchange == "NASDAQ"

    def test_parse_trade_no_exchange(self):
        """Test parsing trade without exchange."""
        trade_data = {
            "t": "2024-01-15T16:00:00Z",
            "p": 151.52,
            "s": 50,
        }
        with patch.object(AlpacaDataClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaDataClient()
            result = client._parse_trade(trade_data, "AAPL")

        assert result is not None
        assert result.exchange is None


class TestGlobalClientManagement:
    """Tests for global client accessor functions."""

    async def test_get_alpaca_client_creates_singleton(self):
        """Test that get_alpaca_client creates a singleton."""
        import src.alpaca.client as module

        module._client = None

        with patch("httpx.AsyncClient"):
            with patch("src.alpaca.client.get_rate_limiter") as mock_rl:
                with patch("src.alpaca.client.get_circuit_breaker") as mock_cb:
                    mock_rl.return_value = MagicMock()
                    mock_cb.return_value = MagicMock()

                    client1 = await get_alpaca_client()
                    client2 = await get_alpaca_client()

        assert client1 is client2
        module._client = None

    async def test_close_alpaca_client(self):
        """Test closing the global client."""
        import src.alpaca.client as module

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        module._client = mock_client

        await close_alpaca_client()

        mock_client.close.assert_called_once()
        assert module._client is None

    async def test_close_alpaca_client_when_none(self):
        """Test closing when no client exists."""
        import src.alpaca.client as module

        module._client = None

        # Should not raise
        await close_alpaca_client()

        assert module._client is None
