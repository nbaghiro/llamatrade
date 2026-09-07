"""Error handling and resilience for MarketDataClient at the HTTP seam.

Every test drives the real client through respx so the typed AlpacaError
mapping, retry/backoff, and circuit breaker are exercised end to end;
asyncio.sleep is patched so backoff costs no wall-clock time.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import Response

from llamatrade_alpaca import (
    AlpacaRateLimitError,
    AlpacaServerError,
    Bar,
    CircuitOpenError,
    MarketDataClient,
    SymbolNotFoundError,
    Timeframe,
)

BASE_URL = "https://data.alpaca.markets/v2"
_BARS_URL = f"{BASE_URL}/stocks/AAPL/bars"
_START = datetime(2024, 1, 1, tzinfo=UTC)

_EMPTY_PAGE = {"bars": [], "next_page_token": None}
_ONE_BAR_PAGE = {
    "bars": [{"t": "2024-01-02T00:00:00Z", "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10}],
    "next_page_token": None,
}


@pytest.fixture
async def client() -> AsyncIterator[MarketDataClient]:
    c = MarketDataClient(api_key="test-key", api_secret="test-secret", paper=True)
    yield c
    await c.close()


async def _get_bars(client: MarketDataClient, symbol: str = "AAPL") -> list[Bar]:
    return await client.get_bars(symbol=symbol, timeframe=Timeframe.DAY_1, start=_START)


class TestRateLimitHandling:
    """429 responses map to AlpacaRateLimitError and are retried."""

    @respx.mock
    async def test_429_maps_to_rate_limit_error_with_retry_after(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(_BARS_URL).mock(
            return_value=Response(
                429, json={"message": "rate limited"}, headers={"Retry-After": "7"}
            )
        )

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(AlpacaRateLimitError) as exc_info:
                await _get_bars(client)

        assert exc_info.value.retry_after == 7
        assert exc_info.value.status_code == 429
        # Rate limits are retryable: initial call + 3 retries.
        assert route.call_count == 4

    @respx.mock
    async def test_429_retried_then_recovers(self, client: MarketDataClient) -> None:
        route = respx.get(_BARS_URL)
        route.side_effect = [
            Response(429, json={"message": "rate limited"}),
            Response(200, json=_EMPTY_PAGE),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            assert await _get_bars(client) == []

        assert route.call_count == 2


class TestServerErrorsAndCircuit:
    """5xx responses map to AlpacaServerError; persistence opens the breaker."""

    @respx.mock
    async def test_5xx_maps_to_server_error_after_retries(self, client: MarketDataClient) -> None:
        route = respx.get(_BARS_URL).mock(return_value=Response(503, json={"message": "down"}))

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(AlpacaServerError) as exc_info:
                await _get_bars(client)

        assert exc_info.value.status_code == 503
        # Initial call + 3 retries; the market-data breaker (threshold 5) stays closed.
        assert route.call_count == 4

    @respx.mock
    async def test_persistent_5xx_opens_circuit_on_next_call(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(_BARS_URL).mock(return_value=Response(500, json={"message": "down"}))

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(AlpacaServerError):
                await _get_bars(client)  # four failures recorded
            with pytest.raises(CircuitOpenError):
                await _get_bars(client)  # fifth opens the breaker; retry surfaces CircuitOpenError

        assert route.call_count == 5

    @respx.mock
    async def test_server_error_retried_then_recovers(self, client: MarketDataClient) -> None:
        route = respx.get(_BARS_URL)
        route.side_effect = [
            Response(500, json={"message": "boom"}),
            Response(502, json={"message": "boom"}),
            Response(200, json=_ONE_BAR_PAGE),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            bars = await _get_bars(client)

        assert [b.close for b in bars] == [1.5]
        assert route.call_count == 3


class TestNotFoundHandling:
    """404/422 map to SymbolNotFoundError and are never retried."""

    @respx.mock
    async def test_404_maps_to_symbol_not_found_without_retry(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(f"{BASE_URL}/stocks/INVALID/bars").mock(
            return_value=Response(404, json={"message": "symbol not found"})
        )

        with pytest.raises(SymbolNotFoundError) as exc_info:
            await _get_bars(client, symbol="INVALID")

        assert exc_info.value.symbol == "INVALID"
        assert route.call_count == 1

    @respx.mock
    async def test_422_maps_to_symbol_not_found_without_retry(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(f"{BASE_URL}/stocks/BAD/bars").mock(
            return_value=Response(422, json={"message": "invalid symbol"})
        )

        with pytest.raises(SymbolNotFoundError):
            await _get_bars(client, symbol="BAD")

        assert route.call_count == 1

    @respx.mock
    async def test_empty_snapshot_returns_none(self, client: MarketDataClient) -> None:
        respx.get(f"{BASE_URL}/stocks/INVALID/snapshot").mock(return_value=Response(200, json={}))

        assert await client.get_snapshot("INVALID") is None


class TestTimeoutHandling:
    """Transport timeouts are retried through the backoff loop."""

    @respx.mock
    async def test_connect_timeout_retried_then_raises(self, client: MarketDataClient) -> None:
        route = respx.get(_BARS_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(httpx.ConnectTimeout):
                await _get_bars(client)

        assert route.call_count == 4

    @respx.mock
    async def test_read_timeout_retried_then_recovers(self, client: MarketDataClient) -> None:
        route = respx.get(_BARS_URL)
        route.side_effect = [
            httpx.ReadTimeout("slow"),
            Response(200, json=_EMPTY_PAGE),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            assert await _get_bars(client) == []

        assert route.call_count == 2


class TestMalformedResponseHandling:
    """Bodies that are not the JSON we expect."""

    @respx.mock
    async def test_invalid_json_success_body_raises_without_retry(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(_BARS_URL).mock(return_value=Response(200, text="<html>gateway</html>"))

        with pytest.raises(ValueError):
            await _get_bars(client)

        assert route.call_count == 1

    @respx.mock
    async def test_non_json_error_body_still_maps_to_typed_error(
        self, client: MarketDataClient
    ) -> None:
        route = respx.get(_BARS_URL).mock(return_value=Response(503, text="Service Unavailable"))

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(AlpacaServerError) as exc_info:
                await _get_bars(client)

        assert exc_info.value.message == "Service Unavailable"
        assert route.call_count == 4


class TestMultiSymbolResults:
    """Multi-symbol endpoints return only the symbols Alpaca resolved."""

    @respx.mock
    async def test_partial_symbol_results_returned_as_is(self, client: MarketDataClient) -> None:
        respx.get(f"{BASE_URL}/stocks/snapshots").mock(
            return_value=Response(
                200,
                json={
                    "AAPL": {
                        "latestQuote": {
                            "t": "2024-01-15T14:30:00Z",
                            "bp": 150.0,
                            "bs": 100,
                            "ap": 150.1,
                            "as": 200,
                        }
                    }
                },
            )
        )

        result = await client.get_multi_snapshots(["AAPL", "INVALID"])

        assert set(result) == {"AAPL"}

    @respx.mock
    async def test_no_valid_symbols_returns_empty(self, client: MarketDataClient) -> None:
        respx.get(f"{BASE_URL}/stocks/snapshots").mock(return_value=Response(200, json={}))

        assert await client.get_multi_snapshots(["INVALID1", "INVALID2"]) == {}
