"""Alpaca API clients.

Ready-to-use clients for Alpaca Trading and Market Data APIs.
"""

import asyncio

from .market_data import MarketDataClient
from .trading import TradingClient

__all__ = [
    "MarketDataClient",
    "TradingClient",
    # Sync singleton helpers (for FastAPI Depends)
    "get_trading_client",
    "get_market_data_client",
    # Async singleton helpers (for gRPC/concurrent contexts)
    "get_trading_client_async",
    "get_market_data_client_async",
    # Close helpers
    "close_trading_client",
    "close_market_data_client",
    "close_all_clients",
]

# Singleton instances
_trading_client: TradingClient | None = None
_market_data_client: MarketDataClient | None = None
_client_lock: asyncio.Lock | None = None


def _get_client_lock() -> asyncio.Lock:
    """Get or create the client initialization lock."""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


# =============================================================================
# Sync singleton helpers (for FastAPI Depends)
# =============================================================================


def get_trading_client() -> TradingClient:
    """Get the singleton TradingClient instance (sync version).

    Creates a new client on first call, returns cached instance thereafter.
    Useful as a FastAPI dependency: `Depends(get_trading_client)`

    Note: For concurrent async contexts (e.g., gRPC), use get_trading_client_async().
    """
    global _trading_client
    if _trading_client is None:
        _trading_client = TradingClient()
    return _trading_client


def get_market_data_client() -> MarketDataClient:
    """Get the singleton MarketDataClient instance (sync version).

    Creates a new client on first call, returns cached instance thereafter.
    Useful as a FastAPI dependency: `Depends(get_market_data_client)`

    Note: For concurrent async contexts (e.g., gRPC), use get_market_data_client_async().
    """
    global _market_data_client
    if _market_data_client is None:
        _market_data_client = MarketDataClient()
    return _market_data_client


# =============================================================================
# Async singleton helpers (thread-safe for concurrent contexts)
# =============================================================================


async def get_trading_client_async() -> TradingClient:
    """Get the singleton TradingClient instance (async, thread-safe version).

    Uses asyncio.Lock to prevent race conditions during concurrent initialization.
    Recommended for gRPC servicers and other concurrent async contexts.
    """
    global _trading_client

    # Fast path: already initialized
    if _trading_client is not None:
        return _trading_client

    async with _get_client_lock():
        # Double-check after acquiring lock
        if _trading_client is None:
            _trading_client = TradingClient()
        return _trading_client


async def get_market_data_client_async() -> MarketDataClient:
    """Get the singleton MarketDataClient instance (async, thread-safe version).

    Uses asyncio.Lock to prevent race conditions during concurrent initialization.
    Recommended for gRPC servicers and other concurrent async contexts.
    """
    global _market_data_client

    # Fast path: already initialized
    if _market_data_client is not None:
        return _market_data_client

    async with _get_client_lock():
        # Double-check after acquiring lock
        if _market_data_client is None:
            _market_data_client = MarketDataClient()
        return _market_data_client


# =============================================================================
# Close helpers
# =============================================================================


async def close_trading_client() -> None:
    """Close the singleton TradingClient."""
    global _trading_client

    async with _get_client_lock():
        if _trading_client is not None:
            await _trading_client.close()
            _trading_client = None


async def close_market_data_client() -> None:
    """Close the singleton MarketDataClient."""
    global _market_data_client

    async with _get_client_lock():
        if _market_data_client is not None:
            await _market_data_client.close()
            _market_data_client = None


async def close_all_clients() -> None:
    """Close all singleton clients."""
    await close_trading_client()
    await close_market_data_client()
