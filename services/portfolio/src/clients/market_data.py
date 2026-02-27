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
        self.base_url = base_url or os.getenv("MARKET_DATA_URL", "http://localhost:8840")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_latest_price(self, symbol: str) -> float:
        """Get the latest price for a single symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Latest price as float
        """
        client = await self._get_client()
        response = await client.get(f"/quotes/{symbol}/latest")
        response.raise_for_status()
        data = response.json()
        # Use midpoint of bid/ask or last trade price
        return float(data.get("price", data.get("last", 0.0)))

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
            try:
                prices[symbol] = await self.get_latest_price(symbol)
            except Exception:
                # If we can't get a price, use 0.0 as fallback
                prices[symbol] = 0.0
        return prices


# Singleton instance
_market_data_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Get or create the market data client singleton."""
    global _market_data_client
    if _market_data_client is None:
        _market_data_client = MarketDataClient()
    return _market_data_client
