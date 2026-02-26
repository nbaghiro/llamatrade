"""Tests for market data client."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.clients.market_data import MarketDataClient, MarketDataError


class TestMarketDataClient:
    """Tests for MarketDataClient."""

    def test_init_default_url(self):
        """Test client initializes with default URL."""
        client = MarketDataClient()
        assert client.base_url == "http://localhost:47400"
        assert client.timeout == 30.0

    def test_init_custom_url(self):
        """Test client initializes with custom URL."""
        client = MarketDataClient(base_url="http://custom:8000", timeout=60.0)
        assert client.base_url == "http://custom:8000"
        assert client.timeout == 60.0

    @pytest.mark.asyncio
    async def test_fetch_bars_success(self):
        """Test successful bar fetching."""
        mock_response_data = {
            "bars": [
                {
                    "timestamp": "2024-01-02T09:30:00Z",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "volume": 10000,
                },
                {
                    "timestamp": "2024-01-03T09:30:00Z",
                    "open": 104.0,
                    "high": 108.0,
                    "low": 103.0,
                    "close": 107.0,
                    "volume": 12000,
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            bars = await client.fetch_bars(
                symbols=["AAPL"],
                timeframe="1D",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

            assert "AAPL" in bars
            assert len(bars["AAPL"]) == 2
            assert bars["AAPL"][0]["close"] == 104.0
            assert bars["AAPL"][0]["volume"] == 10000

    @pytest.mark.asyncio
    async def test_fetch_bars_multiple_symbols(self):
        """Test fetching bars for multiple symbols."""
        mock_response_data = {
            "bars": [
                {
                    "t": "2024-01-02T09:30:00Z",
                    "o": 100.0,
                    "h": 105.0,
                    "l": 99.0,
                    "c": 104.0,
                    "v": 10000,
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            bars = await client.fetch_bars(
                symbols=["AAPL", "MSFT", "GOOG"],
                timeframe="1D",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

            assert len(bars) == 3
            assert "AAPL" in bars
            assert "MSFT" in bars
            assert "GOOG" in bars

    @pytest.mark.asyncio
    async def test_fetch_bars_short_field_names(self):
        """Test parsing bars with short field names (t, o, h, l, c, v)."""
        mock_response_data = {
            "bars": [
                {
                    "t": "2024-01-02T09:30:00Z",
                    "o": 100.0,
                    "h": 105.0,
                    "l": 99.0,
                    "c": 104.0,
                    "v": 10000,
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            bars = await client.fetch_bars(
                symbols=["AAPL"],
                timeframe="1D",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

            bar = bars["AAPL"][0]
            assert bar["open"] == 100.0
            assert bar["high"] == 105.0
            assert bar["low"] == 99.0
            assert bar["close"] == 104.0
            assert bar["volume"] == 10000

    @pytest.mark.asyncio
    async def test_fetch_bars_http_error(self):
        """Test that HTTP errors raise MarketDataError."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client.get.side_effect = httpx.HTTPError("Connection failed")

            client = MarketDataClient()

            with pytest.raises(MarketDataError) as exc_info:
                await client.fetch_bars(
                    symbols=["AAPL"],
                    timeframe="1D",
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 1, 31),
                )

            assert "Failed to fetch bars for AAPL" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_bars_empty_response(self):
        """Test handling empty bars response."""
        mock_response_data = {"bars": []}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            bars = await client.fetch_bars(
                symbols=["AAPL"],
                timeframe="1D",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

            assert "AAPL" in bars
            assert len(bars["AAPL"]) == 0

    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """Test health check returns True when service is healthy."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            result = await client.check_health()

            assert result is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self):
        """Test health check returns False when service is unhealthy."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = AsyncMock()
            mock_response.status_code = 503
            mock_client.get.return_value = mock_response

            client = MarketDataClient()
            result = await client.check_health()

            assert result is False

    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """Test health check returns False on connection error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_client.get.side_effect = httpx.HTTPError("Connection refused")

            client = MarketDataClient()
            result = await client.check_health()

            assert result is False
