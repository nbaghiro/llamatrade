"""Market data client for fetching current prices from market-data service via gRPC."""

import logging
import os
from typing import Any

from llamatrade_proto.clients.market_data import MarketDataClient as GRPCMarketDataClient
from llamatrade_proto.clients.market_data import Snapshot

logger = logging.getLogger(__name__)


class MarketDataClient:
    """gRPC client for fetching real-time market data from the market-data service."""

    def __init__(self, target: str | None = None):
        """Initialize the market data client.

        Args:
            target: gRPC target address for the market-data service
        """
        self.target = target or os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")
        self._client: GRPCMarketDataClient | None = None

    def _get_client(self) -> GRPCMarketDataClient:
        """Get or create the gRPC client."""
        if self._client is None:
            self._client = GRPCMarketDataClient(target=self.target)
        return self._client

    async def close(self) -> None:
        """Close the gRPC client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def get_latest_price(self, symbol: str) -> float | None:
        """Get the latest price for a single symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Latest price as float, or None if unavailable
        """
        symbol = symbol.upper()
        try:
            client = self._get_client()
            price = await client.get_latest_price(symbol)
            return float(price)
        except Exception as e:
            logger.warning("Failed to get price for %s: %s", symbol, e)
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

        symbols = [s.upper() for s in symbols]
        try:
            client = self._get_client()
            prices = await client.get_latest_prices(symbols)
            return {symbol: float(price) for symbol, price in prices.items()}
        except Exception as e:
            logger.warning("Failed to get prices for %s: %s", symbols, e)
            return {}

    async def get_snapshot(self, symbol: str) -> Snapshot | None:
        """Get full market snapshot for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Snapshot with latest price, bid/ask, and change info
        """
        symbol = symbol.upper()
        try:
            client = self._get_client()
            return await client.get_snapshot(symbol)
        except Exception as e:
            logger.warning("Failed to get snapshot for %s: %s", symbol, e)
            return None

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1D",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get historical bars for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            timeframe: Timeframe for bars (e.g., "1D", "1H", "1Min")
            limit: Maximum number of bars to return

        Returns:
            List of bar data dictionaries
        """
        from datetime import datetime, timedelta

        symbol = symbol.upper()
        try:
            client = self._get_client()
            # Calculate time range based on limit
            end = datetime.now()
            if timeframe in ("1D", "1DAY"):
                start = end - timedelta(days=limit or 100)
            elif timeframe in ("1H", "1HOUR"):
                start = end - timedelta(hours=limit or 100)
            else:
                start = end - timedelta(minutes=limit or 100)

            bars = await client.get_historical_bars(
                symbol=symbol,
                start=start,
                end=end,
                timeframe=timeframe,
            )
            return [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                }
                for bar in bars
            ]
        except Exception as e:
            logger.warning("Failed to get bars for %s: %s", symbol, e)
            return []


# Singleton instance
_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Get or create the market data client singleton."""
    global _client
    if _client is None:
        _client = MarketDataClient()
    return _client
