"""Market data service: Timescale store first, Redis cache + Alpaca fallback."""

import logging
from datetime import UTC, datetime, timedelta

from llamatrade_alpaca import MarketDataClient, get_market_data_client_async

from src.cache import (
    TTL_LATEST_BAR,
    TTL_LATEST_QUOTE,
    TTL_SNAPSHOT,
    MarketDataCache,
    get_cache,
)
from src.models import Bar, Quote, Snapshot, Timeframe
from src.store.intervals import subtract
from src.store.models import (
    AGGREGATE_RELATION_BY_TIMEFRAME,
    BASE_TABLE_BY_TIMEFRAME,
    BarRow,
    bar_row_from_alpaca,
)
from src.store.repository import BarStore, get_bar_store

logger = logging.getLogger(__name__)

# Timeframes the store can answer: base tables (writable) + continuous aggregates.
_STORE_BASE_TIMEFRAMES = frozenset(BASE_TABLE_BY_TIMEFRAME)
_STORE_READABLE_TIMEFRAMES = _STORE_BASE_TIMEFRAMES | frozenset(AGGREGATE_RELATION_BY_TIMEFRAME)

# Approximate bar duration per timeframe — used only to keep the currently
# *forming* bar out of the durable store (we persist closed bars only).
_TF_DURATION = {
    "1Min": timedelta(minutes=1),
    "5Min": timedelta(minutes=5),
    "15Min": timedelta(minutes=15),
    "30Min": timedelta(minutes=30),
    "1Hour": timedelta(hours=1),
    "4Hour": timedelta(hours=4),
    "1Day": timedelta(days=1),
    "1Week": timedelta(weeks=1),
    "1Month": timedelta(days=31),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _bar_row_to_bar(row: BarRow) -> Bar:
    """Convert a stored row back to the Alpaca-shaped domain ``Bar``."""
    return Bar(
        timestamp=row.time,
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=row.volume,
        vwap=float(row.vwap) if row.vwap is not None else None,
        trade_count=row.trade_count,
    )


def _dedupe_sorted_by_time(bars: list[Bar]) -> list[Bar]:
    """Sort by timestamp and drop duplicate timestamps (store vs fetched overlap)."""
    bars.sort(key=lambda b: b.timestamp)
    out: list[Bar] = []
    seen: set[datetime] = set()
    for bar in bars:
        if bar.timestamp not in seen:
            seen.add(bar.timestamp)
            out.append(bar)
    return out


class MarketDataService:
    """Service layer: read-through over the Timescale store, Alpaca as fallback."""

    def __init__(
        self,
        alpaca: MarketDataClient,
        cache: MarketDataCache | None,
        store: BarStore | None = None,
    ):
        self._alpaca = alpaca
        self._cache = cache
        self._store = store

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
        """Historical bars: served from the Timescale store, gap-filled from Alpaca."""
        symbol = symbol.upper()
        tf = timeframe.value

        if self._store is not None and not refresh and tf in _STORE_READABLE_TIMEFRAMES:
            try:
                return await self._get_bars_via_store(symbol, timeframe, tf, start, end, limit)
            except Exception:
                logger.warning(
                    "Store read failed for %s %s; falling back to Alpaca", symbol, tf, exc_info=True
                )

        return await self._get_bars_via_cache(symbol, timeframe, start, end, limit, refresh)

    async def _get_bars_via_store(
        self,
        symbol: str,
        timeframe: Timeframe,
        tf: str,
        start: datetime,
        end: datetime | None,
        limit: int,
    ) -> list[Bar]:
        """Store-first read: select stored bars, fetch only the gaps from Alpaca.

        Closed bars from the gaps are written back (base timeframes only); the
        currently-forming bar is fetched for the response but never persisted.
        """
        assert self._store is not None
        step = _TF_DURATION.get(tf, timedelta(0))
        end_eff = end or _utcnow()
        closed_boundary = _utcnow() - step

        stored = await self._store.select_bars(symbol, tf, start, end_eff)
        # The last stored bar covers [max, max+step); fold that in so a complete
        # range isn't reported as having a spurious trailing gap of one bar.
        covered = await self._store.covered_interval(symbol, tf, start, end_eff)
        covered_intervals = [(covered[0], covered[1] + step)] if covered else []
        gaps = subtract((start, end_eff), covered_intervals)

        fetched: list[Bar] = []
        for gap_start, gap_end in gaps:
            bars = await self._alpaca.get_bars(
                symbol=symbol, timeframe=timeframe, start=gap_start, end=gap_end, limit=limit
            )
            if not bars:
                continue
            fetched.extend(bars)
            if tf in _STORE_BASE_TIMEFRAMES:
                closed = [b for b in bars if b.timestamp < closed_boundary]
                if closed:
                    await self._store.upsert_bars(
                        [bar_row_from_alpaca(symbol, b) for b in closed], tf
                    )

        merged = _dedupe_sorted_by_time([_bar_row_to_bar(r) for r in stored] + fetched)
        return merged[:limit] if limit else merged

    async def _get_bars_via_cache(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None,
        limit: int,
        refresh: bool,
    ) -> list[Bar]:
        """Legacy/fallback path: Redis cache then Alpaca (used when store is off)."""
        if self._cache and not refresh:
            cache_key = MarketDataCache.bars_key(symbol, timeframe, start, end, limit)
            cached = await self._cache.get(cache_key)
            if cached:
                return MarketDataCache.deserialize_model_list(cached, Bar)

        bars = await self._alpaca.get_bars(
            symbol=symbol, timeframe=timeframe, start=start, end=end, limit=limit
        )

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

        # Store-first: per-symbol read-through (cheap local selects + targeted
        # Alpaca gap fills). Keeps the same gap-fill/write-back semantics as the
        # single-symbol path.
        tf = timeframe.value
        if self._store is not None and not refresh and tf in _STORE_READABLE_TIMEFRAMES:
            store_result: dict[str, list[Bar]] = {}
            for symbol in symbols:
                store_result[symbol] = await self.get_bars(
                    symbol, timeframe, start, end, limit, refresh
                )
            return store_result

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
    store = get_bar_store()  # None when MARKET_DATA_DB_URL is unset (legacy mode)
    return MarketDataService(alpaca=alpaca, cache=cache, store=store)
