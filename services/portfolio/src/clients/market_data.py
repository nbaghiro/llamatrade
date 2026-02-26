"""HTTP client for market-data service."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class MarketDataClient:
    """Client for fetching prices from market-data service."""

    def __init__(self, base_url: str | None = None):
        default_url = os.getenv("MARKET_DATA_URL") or "http://market-data:47804"
        resolved_url: str = base_url if base_url is not None else default_url
        self.base_url = resolved_url
        self._client = httpx.AsyncClient(base_url=resolved_url, timeout=10.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def get_latest_price(self, symbol: str) -> float | None:
        """Get latest price for a symbol.

        Args:
            symbol: The stock symbol (e.g., "AAPL")

        Returns:
            The latest close price, or None if unavailable
        """
        try:
            response = await self._client.get(f"/bars/{symbol.upper()}/latest")
            response.raise_for_status()
            data = response.json()
            return float(data.get("close", 0))
        except httpx.HTTPStatusError as e:
            logger.warning(f"Failed to get price for {symbol}: HTTP {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")
            return None

    async def get_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get latest prices for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest price (excludes failures)
        """
        result: dict[str, float] = {}
        for symbol in symbols:
            price = await self.get_latest_price(symbol)
            if price is not None:
                result[symbol.upper()] = price
        return result


# Singleton client
_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Dependency to get market data client."""
    global _client
    if _client is None:
        _client = MarketDataClient()
    return _client
