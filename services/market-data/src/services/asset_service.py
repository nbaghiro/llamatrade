"""Asset reference data (Alpaca /v2/assets) with Redis caching.

Kept separate from MarketDataService: assets come from the Trading API, are
near-static, and are consumed as generic reference data (name, venue,
tradability) rather than time-series market data.
"""

import asyncio
import logging

from llamatrade_alpaca import Asset, TradingClient, get_trading_client_async

from src.cache import TTL_ASSET, MarketDataCache, get_cache

logger = logging.getLogger(__name__)


class AssetService:
    """Fetch asset metadata by symbol, cached per symbol."""

    def __init__(self, alpaca: TradingClient, cache: MarketDataCache | None):
        self._alpaca = alpaca
        self._cache = cache

    async def get_assets(self, symbols: list[str], refresh: bool = False) -> dict[str, Asset]:
        """Asset metadata keyed by symbol. Unknown symbols are omitted."""
        wanted = list(dict.fromkeys(s.upper() for s in symbols))
        if not wanted:
            return {}

        found: dict[str, Asset] = {}

        if self._cache and not refresh:
            key_to_symbol = {MarketDataCache.asset_key(s): s for s in wanted}
            cached = await self._cache.mget(list(key_to_symbol))
            for key, raw in cached.items():
                if raw:
                    found[key_to_symbol[key]] = MarketDataCache.deserialize_model(raw, Asset)

        misses = [s for s in wanted if s not in found]
        if not misses:
            return found

        fetched = await asyncio.gather(
            *(self._alpaca.get_asset(symbol) for symbol in misses),
            return_exceptions=True,
        )

        for symbol, result in zip(misses, fetched, strict=True):
            if isinstance(result, BaseException):
                logger.warning("get_asset failed for %s: %s", symbol, result)
                continue
            if result is None:
                continue
            found[symbol] = result
            if self._cache:
                await self._cache.set(
                    MarketDataCache.asset_key(symbol),
                    MarketDataCache.serialize_model(result),
                    TTL_ASSET,
                )

        return found


async def get_asset_service() -> AssetService:
    """FastAPI dependency to get the asset service."""
    alpaca = await get_trading_client_async()
    return AssetService(alpaca=alpaca, cache=get_cache())
