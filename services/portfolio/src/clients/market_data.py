"""Market data client for fetching current prices from market-data service via gRPC."""

import logging
import os
from decimal import Decimal

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

    async def get_latest_price(self, symbol: str) -> Decimal:
        """Get the latest price for a single symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Latest price as Decimal

        Raises:
            Exception: If price cannot be fetched
        """
        symbol = symbol.upper()
        client = self._get_client()
        return await client.get_latest_price(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        """Get latest prices for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to latest price (as Decimal)
        """
        if not symbols:
            return {}

        symbols = [s.upper() for s in symbols]
        try:
            client = self._get_client()
            return await client.get_latest_prices(symbols)
        except Exception as e:
            logger.warning("Failed to get prices for %s: %s", symbols, e)
            # Return zeros for failed lookups
            return {symbol: Decimal(0) for symbol in symbols}

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

    async def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Get market snapshots for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary mapping symbol to Snapshot
        """
        if not symbols:
            return {}

        symbols = [s.upper() for s in symbols]
        try:
            client = self._get_client()
            return await client.get_snapshots(symbols)
        except Exception as e:
            logger.warning("Failed to get snapshots for %s: %s", symbols, e)
            return {}


# Singleton instance
_market_data_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Get or create the market data client singleton."""
    global _market_data_client
    if _market_data_client is None:
        _market_data_client = MarketDataClient()
    return _market_data_client
