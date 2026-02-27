"""Market data client for fetching current prices from market-data service."""

import os

import httpx


class MarketDataClient:
    """HTTP client for fetching real-time market data from the market-data service."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        """Initialize the market data client.

        Args:
            base_url: Base URL for the market-data service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv("MARKET_DATA_URL", "http://market-data:8840")
        self.timeout = timeout
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()

    async def get_latest_price(self, symbol: str) -> float | None:
        """Get the latest price for a single symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Latest close price as float, or None if unavailable
        """
        symbol = symbol.upper()
        try:
            response = await self._client.get(f"/bars/{symbol}/latest")
            response.raise_for_status()
            data = response.json()
            return float(data.get("close", 0.0))
        except Exception:
            return None

    async def get_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get latest prices for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest price
        """
        if not symbols:
            return {}

        prices = {}
        for symbol in symbols:
            symbol = symbol.upper()
            price = await self.get_latest_price(symbol)
            if price is not None:
                prices[symbol] = price
        return prices

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int | None = None,
    ) -> list[dict]:
        """Get historical bars for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            timeframe: Timeframe for bars (e.g., "1D", "1H", "1Min")
            limit: Maximum number of bars to return

        Returns:
            List of bar data dictionaries
        """
        symbol = symbol.upper()
        try:
            params: dict[str, str | int] = {"timeframe": timeframe}
            if limit is not None:
                params["limit"] = limit

            response = await self._client.get(f"/bars/{symbol}", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("bars", [])
        except Exception:
            return []


# Singleton instance
_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Get or create the market data client singleton."""
    global _client
    if _client is None:
        _client = MarketDataClient()
    return _client
