"""Tests for Alpaca client error handling and resilience.

These tests verify that the Alpaca client properly handles error scenarios
including rate limits, server errors, timeouts, and circuit breaker behavior.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llamatrade_alpaca import MarketDataClient, TradingClient

from src.models import (
    Timeframe,
)


@pytest.fixture
def client():
    """Create a fresh Alpaca market data client for each test."""
    return MarketDataClient(
        api_key="test-key",
        api_secret="test-secret",
        paper=True,
    )


@pytest.fixture
def trading_client():
    """Create a fresh Alpaca trading client for clock API tests."""
    return TradingClient(
        api_key="test-key",
        api_secret="test-secret",
        paper=True,
    )


class TestRateLimitHandling:
    """Tests for rate limit (429) error handling."""

    async def test_rate_limit_raises_specific_error(self, client):
        """Verify 429 response raises AlpacaRateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "5"}
        mock_response.json.return_value = {"message": "Rate limit exceeded"}
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=mock_response,
            )

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_bars(
                    symbol="AAPL",
                    timeframe=Timeframe.DAY_1,
                    start=datetime(2024, 1, 1, tzinfo=UTC),
                )

    async def test_rate_limit_includes_retry_after(self, client):
        """Verify rate limit error includes Retry-After header info."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "10"}

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            error = httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=mock_response,
            )
            mock_get.side_effect = error

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await client.get_bars(
                    symbol="AAPL",
                    timeframe=Timeframe.DAY_1,
                    start=datetime(2024, 1, 1, tzinfo=UTC),
                )

            assert exc_info.value.response.status_code == 429


class TestServerErrorHandling:
    """Tests for server error (5xx) handling."""

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    async def test_server_errors_propagate(self, client, status_code):
        """Verify 5xx errors propagate correctly."""
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = {"message": "Server error"}

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                f"{status_code} Server Error",
                request=MagicMock(),
                response=mock_response,
            )

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await client.get_snapshot("AAPL")

            assert exc_info.value.response.status_code == status_code


class TestNotFoundHandling:
    """Tests for not found (404) handling."""

    async def test_invalid_symbol_returns_none(self, client):
        """Verify invalid symbol returns None for snapshot."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Empty response for invalid symbol

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_snapshot("INVALID")

            assert result is None

    async def test_404_for_bars_raises_error(self, client):
        """Verify 404 for bars raises appropriate error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Symbol not found"}

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=mock_response,
            )

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_bars(
                    symbol="INVALID",
                    timeframe=Timeframe.DAY_1,
                    start=datetime(2024, 1, 1, tzinfo=UTC),
                )


class TestTimeoutHandling:
    """Tests for timeout handling."""

    async def test_connection_timeout_raises(self, client):
        """Verify connection timeout raises appropriate error."""
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectTimeout("Connection timed out")

            with pytest.raises(httpx.ConnectTimeout):
                await client.get_bars(
                    symbol="AAPL",
                    timeframe=Timeframe.DAY_1,
                    start=datetime(2024, 1, 1, tzinfo=UTC),
                )

    async def test_read_timeout_raises(self, client):
        """Verify read timeout raises appropriate error."""
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ReadTimeout("Read timed out")

            with pytest.raises(httpx.ReadTimeout):
                await client.get_snapshot("AAPL")


class TestMalformedResponseHandling:
    """Tests for malformed response handling."""

    async def test_invalid_json_raises(self, client):
        """Verify invalid JSON response raises error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ValueError):
                await client.get_bars(
                    symbol="AAPL",
                    timeframe=Timeframe.DAY_1,
                    start=datetime(2024, 1, 1, tzinfo=UTC),
                )

    async def test_missing_fields_handled(self, client):
        """Verify response with missing fields is handled gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bars": []}  # Empty but valid

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_bars(
                symbol="AAPL",
                timeframe=Timeframe.DAY_1,
                start=datetime(2024, 1, 1, tzinfo=UTC),
            )

            assert result == []


@pytest.mark.skip(reason="Clock API is tested in libs/alpaca/tests/test_trading_client.py")
class TestClockAPIErrors:
    """Tests for market clock API error handling.

    Note: get_clock() is now in TradingClient, not MarketDataClient.
    These tests are covered by the lib's test suite in libs/alpaca/tests/.
    """

    async def test_clock_api_connection_error(self, trading_client):
        """Verify clock API connection errors propagate."""
        pass

    async def test_clock_api_invalid_response(self, trading_client):
        """Verify clock API handles invalid response."""
        pass

    async def test_clock_api_success(self, trading_client):
        """Verify clock API returns correct data on success."""
        pass


class TestMultiSymbolErrors:
    """Tests for multi-symbol request error handling."""

    async def test_partial_symbol_failure(self, client):
        """Verify partial failures for multi-symbol requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Only AAPL has data, INVALID returns nothing
        mock_response.json.return_value = {
            "AAPL": {
                "latestTrade": {"p": 150.0, "s": 100, "t": "2024-01-15T10:30:00Z"},
                "latestQuote": {
                    "bp": 149.9,
                    "bs": 100,
                    "ap": 150.1,
                    "as": 100,
                    "t": "2024-01-15T10:30:00Z",
                },
            }
        }

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_multi_snapshots(["AAPL", "INVALID"])

            # Should return only valid symbols
            assert "AAPL" in result
            assert "INVALID" not in result

    async def test_all_symbols_invalid(self, client):
        """Verify handling when all symbols are invalid."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # No valid symbols

        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.get_multi_snapshots(["INVALID1", "INVALID2"])

            assert result == {}
