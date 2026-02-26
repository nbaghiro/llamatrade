"""Alpaca Market Data API client with resilience patterns."""

import logging
import os
from datetime import datetime

import httpx

from src.models import (
    Bar,
    Quote,
    Snapshot,
    Timeframe,
    Trade,
)
from src.resilience import (
    CircuitBreaker,
    RateLimiter,
    RetryConfig,
    get_circuit_breaker,
    get_rate_limiter,
    parse_alpaca_error,
    retry_with_backoff,
)

logger = logging.getLogger(__name__)


class AlpacaDataClient:
    """Client for Alpaca Market Data API with resilience patterns."""

    BASE_URL = "https://data.alpaca.markets/v2"
    PAPER_URL = "https://data.sandbox.alpaca.markets/v2"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET", "")
        self.paper = paper
        self.base_url = self.PAPER_URL if paper else self.BASE_URL

        # Resilience components
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._circuit_breaker = circuit_breaker or get_circuit_breaker()

        headers: dict[str, str] = {}
        if self.api_key:
            headers["APCA-API-KEY-ID"] = self.api_key
        if self.api_secret:
            headers["APCA-API-SECRET-KEY"] = self.api_secret

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
    ) -> httpx.Response:
        """Make a rate-limited request through circuit breaker.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters

        Returns:
            HTTP response

        Raises:
            AlpacaError: On API errors
            CircuitOpenError: If circuit breaker is open
        """
        # Acquire rate limit token
        await self._rate_limiter.acquire()

        # Execute through circuit breaker
        async def make_request() -> httpx.Response:
            response = await self._client.request(method, path, params=params)

            if response.status_code >= 400:
                raise parse_alpaca_error(response)

            return response

        return await self._circuit_breaker.call(make_request)

    @retry_with_backoff(RetryConfig())
    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Bar]:
        """Get historical bars for a symbol."""
        params: dict = {
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "limit": limit,
        }
        if end:
            params["end"] = end.isoformat()

        response = await self._request("GET", f"/stocks/{symbol}/bars", params=params)
        data = response.json()

        return [
            Bar(
                timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                open=bar["o"],
                high=bar["h"],
                low=bar["l"],
                close=bar["c"],
                volume=bar["v"],
                vwap=bar.get("vw"),
                trade_count=bar.get("n"),
            )
            for bar in data.get("bars", [])
        ]

    @retry_with_backoff(RetryConfig())
    async def get_multi_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Get historical bars for multiple symbols."""
        params: dict = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "limit": limit,
        }
        if end:
            params["end"] = end.isoformat()

        response = await self._request("GET", "/stocks/bars", params=params)
        data = response.json()

        result: dict[str, list[Bar]] = {}
        for symbol, bars in data.get("bars", {}).items():
            result[symbol] = [
                Bar(
                    timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                    open=bar["o"],
                    high=bar["h"],
                    low=bar["l"],
                    close=bar["c"],
                    volume=bar["v"],
                    vwap=bar.get("vw"),
                    trade_count=bar.get("n"),
                )
                for bar in bars
            ]
        return result

    @retry_with_backoff(RetryConfig())
    async def get_latest_bar(self, symbol: str) -> Bar | None:
        """Get the latest bar for a symbol."""
        response = await self._request("GET", f"/stocks/{symbol}/bars/latest")
        data = response.json()

        bar = data.get("bar")
        if not bar:
            return None

        return Bar(
            timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
            open=bar["o"],
            high=bar["h"],
            low=bar["l"],
            close=bar["c"],
            volume=bar["v"],
            vwap=bar.get("vw"),
            trade_count=bar.get("n"),
        )

    @retry_with_backoff(RetryConfig())
    async def get_latest_quote(self, symbol: str) -> Quote | None:
        """Get the latest quote for a symbol."""
        response = await self._request("GET", f"/stocks/{symbol}/quotes/latest")
        data = response.json()

        quote = data.get("quote")
        if not quote:
            return None

        return Quote(
            symbol=symbol,
            bid_price=quote["bp"],
            bid_size=quote["bs"],
            ask_price=quote["ap"],
            ask_size=quote["as"],
            timestamp=datetime.fromisoformat(quote["t"].replace("Z", "+00:00")),
        )

    @retry_with_backoff(RetryConfig())
    async def get_snapshot(self, symbol: str) -> Snapshot | None:
        """Get a complete market snapshot for a symbol."""
        response = await self._request("GET", f"/stocks/{symbol}/snapshot")
        data = response.json()

        if not data:
            return None

        return Snapshot(
            symbol=symbol,
            latest_trade=self._parse_trade(data.get("latestTrade"), symbol),
            latest_quote=self._parse_quote(data.get("latestQuote"), symbol),
            minute_bar=self._parse_bar(data.get("minuteBar")),
            daily_bar=self._parse_bar(data.get("dailyBar")),
            prev_daily_bar=self._parse_bar(data.get("prevDailyBar")),
        )

    @retry_with_backoff(RetryConfig())
    async def get_multi_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Get market snapshots for multiple symbols."""
        params = {"symbols": ",".join(symbols)}
        response = await self._request("GET", "/stocks/snapshots", params=params)
        data = response.json()

        result: dict[str, Snapshot] = {}
        for symbol, snapshot in data.items():
            result[symbol] = Snapshot(
                symbol=symbol,
                latest_trade=self._parse_trade(snapshot.get("latestTrade"), symbol),
                latest_quote=self._parse_quote(snapshot.get("latestQuote"), symbol),
                minute_bar=self._parse_bar(snapshot.get("minuteBar")),
                daily_bar=self._parse_bar(snapshot.get("dailyBar")),
                prev_daily_bar=self._parse_bar(snapshot.get("prevDailyBar")),
            )
        return result

    def _parse_bar(self, data: dict | None) -> Bar | None:
        if not data:
            return None
        return Bar(
            timestamp=datetime.fromisoformat(data["t"].replace("Z", "+00:00")),
            open=data["o"],
            high=data["h"],
            low=data["l"],
            close=data["c"],
            volume=data["v"],
            vwap=data.get("vw"),
            trade_count=data.get("n"),
        )

    def _parse_quote(self, data: dict | None, symbol: str) -> Quote | None:
        if not data:
            return None
        return Quote(
            symbol=symbol,
            bid_price=data["bp"],
            bid_size=data["bs"],
            ask_price=data["ap"],
            ask_size=data["as"],
            timestamp=datetime.fromisoformat(data["t"].replace("Z", "+00:00")),
        )

    def _parse_trade(self, data: dict | None, symbol: str) -> Trade | None:
        if not data:
            return None
        return Trade(
            symbol=symbol,
            price=data["p"],
            size=data["s"],
            timestamp=datetime.fromisoformat(data["t"].replace("Z", "+00:00")),
            exchange=data.get("x"),
        )


# Dependency
_client: AlpacaDataClient | None = None


async def get_alpaca_client() -> AlpacaDataClient:
    """Dependency to get Alpaca client."""
    global _client
    if _client is None:
        _client = AlpacaDataClient()
    return _client


async def close_alpaca_client() -> None:
    """Close the global Alpaca client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
