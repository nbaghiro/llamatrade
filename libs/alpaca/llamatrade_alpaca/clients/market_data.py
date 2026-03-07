"""Alpaca Market Data API client.

Provides a ready-to-use client for market data including bars, quotes,
trades, and snapshots.

Example:
    from datetime import datetime, timedelta
    from llamatrade_alpaca import MarketDataClient, Timeframe

    client = MarketDataClient(paper=True)
    bars = await client.get_bars("AAPL", Timeframe.DAY_1, start=datetime.now() - timedelta(days=30))
    quote = await client.get_latest_quote("AAPL")
"""

import logging
from datetime import datetime

from ..client_base import AlpacaClientBase
from ..config import AlpacaCredentials, AlpacaUrls
from ..metrics import time_alpaca_call
from ..models import (
    Bar,
    Quote,
    Snapshot,
    Timeframe,
    parse_bar,
    parse_quote,
    parse_snapshot,
)
from ..resilience import RetryConfig, create_market_data_resilience, retry_with_backoff

logger = logging.getLogger(__name__)


class MarketDataClient(AlpacaClientBase):
    """Client for Alpaca Market Data API.

    Provides methods for:
    - Historical bars (OHLCV data)
    - Latest quotes and trades
    - Market snapshots

    All methods include metrics recording for observability.
    """

    BASE_URL_LIVE = AlpacaUrls.DATA_LIVE
    BASE_URL_PAPER = AlpacaUrls.DATA_PAPER

    def __init__(
        self,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        timeout: float = 30.0,
    ):
        """Initialize Alpaca Market Data Client.

        Args:
            credentials: Pre-configured credentials (takes precedence)
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            api_secret: Alpaca API secret (defaults to ALPACA_API_SECRET env var)
            paper: Use paper trading environment (default True)
            timeout: HTTP request timeout in seconds
        """
        rate_limiter, circuit_breaker = create_market_data_resilience()
        super().__init__(
            credentials=credentials,
            api_key=api_key,
            api_secret=api_secret,
            paper=paper,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            timeout=timeout,
        )

    # =========================================================================
    # Historical Bars
    # =========================================================================

    @retry_with_backoff(RetryConfig())
    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
        adjustment: str = "raw",
    ) -> list[Bar]:
        """Get historical bars for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            timeframe: Bar timeframe (e.g., Timeframe.DAY_1)
            start: Start datetime
            end: End datetime (optional, defaults to now)
            limit: Maximum bars to return (default 1000, max 10000)
            adjustment: Price adjustment ("raw", "split", "dividend", "all")

        Returns:
            List of Bar objects

        Raises:
            SymbolNotFoundError: If symbol is invalid
            AlpacaError: On API errors
        """
        params: dict[str, str | int] = {
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "limit": limit,
            "adjustment": adjustment,
        }
        if end:
            params["end"] = end.isoformat()

        async with time_alpaca_call("get_bars"):
            response = await self._get(f"/stocks/{symbol.upper()}/bars", params=params)
            data = response.json()
            return [parse_bar(bar) for bar in data.get("bars", [])]

    @retry_with_backoff(RetryConfig())
    async def get_multi_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
        adjustment: str = "raw",
    ) -> dict[str, list[Bar]]:
        """Get historical bars for multiple symbols.

        Args:
            symbols: List of stock symbols
            timeframe: Bar timeframe
            start: Start datetime
            end: End datetime (optional)
            limit: Maximum bars per symbol
            adjustment: Price adjustment

        Returns:
            Dict mapping symbol to list of Bars

        Raises:
            AlpacaError: On API errors
        """
        params: dict[str, str | int] = {
            "symbols": ",".join(s.upper() for s in symbols),
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "limit": limit,
            "adjustment": adjustment,
        }
        if end:
            params["end"] = end.isoformat()

        async with time_alpaca_call("get_multi_bars"):
            response = await self._get("/stocks/bars", params=params)
            data = response.json()

            result: dict[str, list[Bar]] = {}
            for symbol, bars in data.get("bars", {}).items():
                result[symbol] = [parse_bar(bar) for bar in bars]
            return result

    @retry_with_backoff(RetryConfig())
    async def get_latest_bar(self, symbol: str) -> Bar | None:
        """Get the latest bar for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Latest Bar or None if not available

        Raises:
            SymbolNotFoundError: If symbol is invalid
            AlpacaError: On API errors
        """
        async with time_alpaca_call("get_latest_bar"):
            response = await self._get(f"/stocks/{symbol.upper()}/bars/latest")
            data = response.json()

            bar = data.get("bar")
            if not bar:
                return None

            return parse_bar(bar)

    @retry_with_backoff(RetryConfig())
    async def get_latest_bars(self, symbols: list[str]) -> dict[str, Bar]:
        """Get the latest bar for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to latest Bar

        Raises:
            AlpacaError: On API errors
        """
        params = {"symbols": ",".join(s.upper() for s in symbols)}

        async with time_alpaca_call("get_latest_bars"):
            response = await self._get("/stocks/bars/latest", params=params)
            data = response.json()

            result: dict[str, Bar] = {}
            for symbol, bar_data in data.get("bars", {}).items():
                result[symbol] = parse_bar(bar_data)
            return result

    # =========================================================================
    # Quotes
    # =========================================================================

    @retry_with_backoff(RetryConfig())
    async def get_latest_quote(self, symbol: str) -> Quote | None:
        """Get the latest quote for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Latest Quote or None if not available

        Raises:
            SymbolNotFoundError: If symbol is invalid
            AlpacaError: On API errors
        """
        async with time_alpaca_call("get_latest_quote"):
            response = await self._get(f"/stocks/{symbol.upper()}/quotes/latest")
            data = response.json()

            quote = data.get("quote")
            if not quote:
                return None

            return parse_quote(quote, symbol.upper())

    @retry_with_backoff(RetryConfig())
    async def get_latest_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Get the latest quotes for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to latest Quote

        Raises:
            AlpacaError: On API errors
        """
        params = {"symbols": ",".join(s.upper() for s in symbols)}

        async with time_alpaca_call("get_latest_quotes"):
            response = await self._get("/stocks/quotes/latest", params=params)
            data = response.json()

            result: dict[str, Quote] = {}
            for symbol, quote_data in data.get("quotes", {}).items():
                result[symbol] = parse_quote(quote_data, symbol)
            return result

    # =========================================================================
    # Snapshots
    # =========================================================================

    @retry_with_backoff(RetryConfig())
    async def get_snapshot(self, symbol: str) -> Snapshot | None:
        """Get a complete market snapshot for a symbol.

        Includes latest trade, quote, and bars (minute, daily, previous daily).

        Args:
            symbol: Stock symbol

        Returns:
            Snapshot or None if not available

        Raises:
            SymbolNotFoundError: If symbol is invalid
            AlpacaError: On API errors
        """
        async with time_alpaca_call("get_snapshot"):
            response = await self._get(f"/stocks/{symbol.upper()}/snapshot")
            data = response.json()

            if not data:
                return None

            return parse_snapshot(data, symbol.upper())

    @retry_with_backoff(RetryConfig())
    async def get_multi_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Get market snapshots for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dict mapping symbol to Snapshot

        Raises:
            AlpacaError: On API errors
        """
        params = {"symbols": ",".join(s.upper() for s in symbols)}

        async with time_alpaca_call("get_multi_snapshots"):
            response = await self._get("/stocks/snapshots", params=params)
            data = response.json()

            result: dict[str, Snapshot] = {}
            for symbol, snapshot_data in data.items():
                result[symbol] = parse_snapshot(snapshot_data, symbol)
            return result
