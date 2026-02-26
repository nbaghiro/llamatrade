"""Tests for market data client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.clients.market_data import MarketDataClient, get_market_data_client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx async client."""
    return AsyncMock(spec=httpx.AsyncClient)


def create_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx Response with synchronous methods."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    return mock_response


class TestMarketDataClient:
    """Test suite for MarketDataClient."""

    async def test_get_latest_price_success(self, mock_httpx_client):
        """Test successful price fetch."""
        mock_response = create_mock_response(
            {
                "symbol": "AAPL",
                "close": 185.50,
                "open": 184.00,
                "high": 186.00,
                "low": 183.50,
                "volume": 50000000,
            }
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            price = await client.get_latest_price("AAPL")

        assert price == 185.50
        mock_httpx_client.get.assert_called_once_with("/bars/AAPL/latest")

    async def test_get_latest_price_http_error(self, mock_httpx_client):
        """Test price fetch with HTTP error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            price = await client.get_latest_price("INVALID")

        assert price is None

    async def test_get_latest_price_network_error(self, mock_httpx_client):
        """Test price fetch with network error."""
        mock_httpx_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            price = await client.get_latest_price("AAPL")

        assert price is None

    async def test_get_prices_multiple_symbols(self, mock_httpx_client):
        """Test fetching prices for multiple symbols."""
        responses = {
            "AAPL": create_mock_response({"close": 185.50}),
            "GOOGL": create_mock_response({"close": 140.25}),
            "MSFT": create_mock_response({"close": 380.00}),
        }

        async def mock_get(url: str):
            for symbol, response in responses.items():
                if symbol in url:
                    return response
            raise httpx.HTTPStatusError("Not Found", request=MagicMock(), response=MagicMock())

        mock_httpx_client.get = mock_get

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            prices = await client.get_prices(["AAPL", "GOOGL", "MSFT"])

        assert prices == {
            "AAPL": 185.50,
            "GOOGL": 140.25,
            "MSFT": 380.00,
        }

    async def test_get_prices_handles_failures(self, mock_httpx_client):
        """Test that get_prices skips failed symbols."""
        success_response = create_mock_response({"close": 185.50})
        fail_response = MagicMock(spec=httpx.Response)
        fail_response.status_code = 404
        fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=fail_response
        )

        async def mock_get(url: str):
            if "AAPL" in url:
                return success_response
            return fail_response

        mock_httpx_client.get = mock_get

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            prices = await client.get_prices(["AAPL", "INVALID"])

        assert prices == {"AAPL": 185.50}

    async def test_symbol_case_normalization(self, mock_httpx_client):
        """Test that symbols are normalized to uppercase."""
        mock_response = create_mock_response({"close": 185.50})
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            await client.get_latest_price("aapl")

        mock_httpx_client.get.assert_called_once_with("/bars/AAPL/latest")

    async def test_get_bars_success(self, mock_httpx_client):
        """Test fetching historical bars."""
        mock_response = create_mock_response(
            {
                "bars": [
                    {"timestamp": "2024-01-15T09:30:00Z", "close": 185.0},
                    {"timestamp": "2024-01-15T09:31:00Z", "close": 185.5},
                ]
            }
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            bars = await client.get_bars("AAPL", timeframe="1Min", limit=100)

        assert len(bars) == 2
        mock_httpx_client.get.assert_called_once_with(
            "/bars/AAPL",
            params={"timeframe": "1Min", "limit": 100},
        )

    async def test_get_bars_error_returns_empty(self, mock_httpx_client):
        """Test that get_bars returns empty list on error."""
        mock_httpx_client.get = AsyncMock(side_effect=Exception("Error"))

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            bars = await client.get_bars("AAPL")

        assert bars == []

    async def test_get_bars_empty_response(self, mock_httpx_client):
        """Test get_bars with no bars in response."""
        mock_response = create_mock_response({"bars": []})
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            bars = await client.get_bars("AAPL")

        assert bars == []

    async def test_get_bars_missing_bars_key(self, mock_httpx_client):
        """Test get_bars when response lacks 'bars' key."""
        mock_response = create_mock_response({"data": []})
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            bars = await client.get_bars("AAPL")

        assert bars == []

    async def test_get_latest_price_missing_close(self, mock_httpx_client):
        """Test price fetch when response lacks 'close' field."""
        mock_response = create_mock_response({"symbol": "AAPL", "open": 185.0})
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            price = await client.get_latest_price("AAPL")

        assert price == 0.0

    async def test_close_client(self, mock_httpx_client):
        """Test closing the HTTP client."""
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client._client = mock_httpx_client

            await client.close()

        mock_httpx_client.aclose.assert_called_once()

    async def test_get_prices_empty_list(self, mock_httpx_client):
        """Test get_prices with empty symbol list."""
        with patch.object(MarketDataClient, "__init__", lambda self, base_url=None: None):
            client = MarketDataClient()
            client.base_url = "http://test"
            client._client = mock_httpx_client

            prices = await client.get_prices([])

        assert prices == {}


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization."""

    def test_init_default_url(self):
        """Test default URL initialization."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("httpx.AsyncClient") as mock_client:
                MarketDataClient()
                mock_client.assert_called_once_with(
                    base_url="http://market-data:47804", timeout=10.0
                )

    def test_init_custom_url(self):
        """Test custom URL initialization."""
        with patch("httpx.AsyncClient") as mock_client:
            MarketDataClient(base_url="http://custom:8080")
            mock_client.assert_called_once_with(base_url="http://custom:8080", timeout=10.0)

    def test_init_url_from_env(self):
        """Test URL from environment variable."""
        with patch.dict("os.environ", {"MARKET_DATA_URL": "http://env-url:9000"}):
            with patch("httpx.AsyncClient") as mock_client:
                MarketDataClient()
                mock_client.assert_called_once_with(base_url="http://env-url:9000", timeout=10.0)


class TestGetMarketDataClient:
    """Tests for singleton client accessor."""

    def test_get_client_creates_singleton(self):
        """Test that get_market_data_client creates a singleton."""
        import src.clients.market_data as module

        # Reset singleton
        module._client = None

        with patch("httpx.AsyncClient"):
            client1 = get_market_data_client()
            client2 = get_market_data_client()

        assert client1 is client2

        # Clean up
        module._client = None

    def test_get_client_returns_existing(self):
        """Test that existing client is returned."""
        import src.clients.market_data as module

        mock_client = MagicMock()
        module._client = mock_client

        result = get_market_data_client()

        assert result is mock_client

        # Clean up
        module._client = None
