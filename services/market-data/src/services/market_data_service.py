"""Market data service with Redis caching layer."""

import logging
from datetime import datetime

from llamatrade_alpaca import MarketDataClient, get_market_data_client_async

from src.cache import (
    TTL_LATEST_BAR,
    TTL_LATEST_QUOTE,
    TTL_SNAPSHOT,
    MarketDataCache,
    get_cache,
)
from src.models import Bar, Quote, Snapshot, Timeframe

logger = logging.getLogger(__name__)


class MarketDataService:
    """Service layer for market data with caching."""

    def __init__(self, alpaca: MarketDataClient, cache: MarketDataCache | None):
        self._alpaca = alpaca
        self._cache = cache

    # === Historical Bars ===

    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
        refresh: bool = False,
    ) -> list[Bar]:
        """Get historical bars for a symbol with caching."""
        symbol = symbol.upper()

        # Try cache first (unless refresh requested)
        if self._cache and not refresh:
            cache_key = MarketDataCache.bars_key(symbol, timeframe, start, end, limit)
            cached = await self._cache.get(cache_key)
            if cached:
                return MarketDataCache.deserialize_model_list(cached, Bar)

        # Fetch from Alpaca
        bars = await self._alpaca.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )

        # Cache the result
        if self._cache and bars:
            cache_key = MarketDataCache.bars_key(symbol, timeframe, start, end, limit)
            ttl = MarketDataCache.calculate_bars_ttl(start, end)
            serialized = MarketDataCache.serialize_model_list(bars)
            await self._cache.set(cache_key, serialized, ttl)

        return bars

    async def get_multi_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
        refresh: bool = False,
    ) -> dict[str, list[Bar]]:
        """Get historical bars for multiple symbols with caching.

        Note: Multi-symbol requests are cached per-symbol for flexibility.
        Uses batch mget to avoid N+1 Redis lookups.
        """
        symbols = [s.upper() for s in symbols]
        result: dict[str, list[Bar]] = {}
        symbols_to_fetch: list[str] = []

        # Check cache for all symbols in one round-trip (unless refresh requested)
        if self._cache and not refresh:
            # Build key -> symbol mapping
            key_to_symbol = {
                MarketDataCache.bars_key(symbol, timeframe, start, end, limit): symbol
                for symbol in symbols
            }
            # Batch fetch from cache
            cached_values = await self._cache.mget(list(key_to_symbol.keys()))
            for key, value in cached_values.items():
                symbol = key_to_symbol[key]
                if value is not None:
                    result[symbol] = MarketDataCache.deserialize_model_list(value, Bar)
                else:
                    symbols_to_fetch.append(symbol)
        else:
            symbols_to_fetch = symbols

        # Fetch remaining from Alpaca
        if symbols_to_fetch:
            fetched = await self._alpaca.get_multi_bars(
                symbols=symbols_to_fetch,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )

            # Cache and merge results
            for symbol, bars in fetched.items():
                result[symbol] = bars
                if self._cache and bars:
                    cache_key = MarketDataCache.bars_key(symbol, timeframe, start, end, limit)
                    ttl = MarketDataCache.calculate_bars_ttl(start, end)
                    serialized = MarketDataCache.serialize_model_list(bars)
                    await self._cache.set(cache_key, serialized, ttl)

        return result

    # === Latest Bar ===

    async def get_latest_bar(
        self,
        symbol: str,
        refresh: bool = False,
    ) -> Bar | None:
        """Get the latest bar for a symbol with caching."""
        symbol = symbol.upper()

        # Try cache first (unless refresh requested)
        if self._cache and not refresh:
            cache_key = MarketDataCache.latest_bar_key(symbol)
            cached = await self._cache.get(cache_key)
            if cached:
                return MarketDataCache.deserialize_model(cached, Bar)

        # Fetch from Alpaca
        bar = await self._alpaca.get_latest_bar(symbol=symbol)

        # Cache the result
        if self._cache and bar:
            cache_key = MarketDataCache.latest_bar_key(symbol)
            serialized = MarketDataCache.serialize_model(bar)
            await self._cache.set(cache_key, serialized, TTL_LATEST_BAR)

        return bar

    # === Latest Quote ===

    async def get_latest_quote(
        self,
        symbol: str,
        refresh: bool = False,
    ) -> Quote | None:
        """Get the latest quote for a symbol with caching."""
        symbol = symbol.upper()

        # Try cache first (unless refresh requested)
        if self._cache and not refresh:
            cache_key = MarketDataCache.latest_quote_key(symbol)
            cached = await self._cache.get(cache_key)
            if cached:
                return MarketDataCache.deserialize_model(cached, Quote)

        # Fetch from Alpaca
        quote = await self._alpaca.get_latest_quote(symbol=symbol)

        # Cache the result
        if self._cache and quote:
            cache_key = MarketDataCache.latest_quote_key(symbol)
            serialized = MarketDataCache.serialize_model(quote)
            await self._cache.set(cache_key, serialized, TTL_LATEST_QUOTE)

        return quote

    # === Snapshot ===

    async def get_snapshot(
        self,
        symbol: str,
        refresh: bool = False,
    ) -> Snapshot | None:
        """Get a market snapshot for a symbol with caching."""
        symbol = symbol.upper()

        # Try cache first (unless refresh requested)
        if self._cache and not refresh:
            cache_key = MarketDataCache.snapshot_key(symbol)
            cached = await self._cache.get(cache_key)
            if cached:
                return MarketDataCache.deserialize_model(cached, Snapshot)

        # Fetch from Alpaca
        snapshot = await self._alpaca.get_snapshot(symbol=symbol)

        # Cache the result
        if self._cache and snapshot:
            cache_key = MarketDataCache.snapshot_key(symbol)
            serialized = MarketDataCache.serialize_model(snapshot)
            await self._cache.set(cache_key, serialized, TTL_SNAPSHOT)

        return snapshot

    async def get_multi_snapshots(
        self,
        symbols: list[str],
        refresh: bool = False,
    ) -> dict[str, Snapshot]:
        """Get market snapshots for multiple symbols with caching.

        Uses batch mget to avoid N+1 Redis lookups.
        """
        symbols = [s.upper() for s in symbols]
        result: dict[str, Snapshot] = {}
        symbols_to_fetch: list[str] = []

        # Check cache for all symbols in one round-trip (unless refresh requested)
        if self._cache and not refresh:
            # Build key -> symbol mapping
            key_to_symbol = {MarketDataCache.snapshot_key(symbol): symbol for symbol in symbols}
            # Batch fetch from cache
            cached_values = await self._cache.mget(list(key_to_symbol.keys()))
            for key, value in cached_values.items():
                symbol = key_to_symbol[key]
                if value is not None:
                    result[symbol] = MarketDataCache.deserialize_model(value, Snapshot)
                else:
                    symbols_to_fetch.append(symbol)
        else:
            symbols_to_fetch = symbols

        # Fetch remaining from Alpaca
        if symbols_to_fetch:
            fetched = await self._alpaca.get_multi_snapshots(symbols=symbols_to_fetch)

            # Cache and merge results
            for symbol, snapshot in fetched.items():
                result[symbol] = snapshot
                if self._cache:
                    cache_key = MarketDataCache.snapshot_key(symbol)
                    serialized = MarketDataCache.serialize_model(snapshot)
                    await self._cache.set(cache_key, serialized, TTL_SNAPSHOT)

        return result


# === FastAPI Dependency ===


async def get_market_data_service() -> MarketDataService:
    """FastAPI dependency to get the market data service."""
    alpaca = await get_market_data_client_async()
    cache = get_cache()
    return MarketDataService(alpaca=alpaca, cache=cache)
