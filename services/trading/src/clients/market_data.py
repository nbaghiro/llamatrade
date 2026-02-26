"""HTTP client for market-data service."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class MarketDataClient:
    """Client for fetching prices from market-data service."""

    def __init__(self, base_url: str | None = None):
        default_url = os.getenv("MARKET_DATA_URL")
        self.base_url: str = base_url or default_url or "http://market-data:47804"
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

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

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Min",
        limit: int = 100,
    ) -> list[dict[str, float | int | str]]:
        """Get historical bars for a symbol.

        Args:
            symbol: The stock symbol
            timeframe: Bar timeframe (e.g., "1Min", "5Min", "1Hour")
            limit: Maximum number of bars to return

        Returns:
            List of bar dictionaries with OHLCV data
        """
        try:
            response = await self._client.get(
                f"/bars/{symbol.upper()}",
                params={"timeframe": timeframe, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()
            bars: list[dict[str, float | int | str]] = data.get("bars", [])
            return bars
        except Exception as e:
            logger.warning(f"Failed to get bars for {symbol}: {e}")
            return []


# Singleton client
_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Dependency to get market data client."""
    global _client
    if _client is None:
        _client = MarketDataClient()
    return _client
