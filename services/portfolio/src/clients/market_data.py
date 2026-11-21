"""Market-data adapter: current prices + daily closes over the Connect protocol.

The market-data service is served as a Connect ASGI app (HTTP/1.1), so callers
use the generated Connect client — not a native-gRPC channel. Inter-service calls
carry a minted service token so they pass market-data's fail-closed auth.

Reads run inside a pooled DB transaction, and the dashboard fans out one request
per strategy, so results are shared across requests for a short TTL, concurrent
identical fetches are coalesced, and every call is bounded by a timeout: a slow
upstream degrades to cost-basis marks instead of pinning DB connections.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Hashable, Sequence
from datetime import date, datetime
from decimal import Decimal

from llamatrade_common.auth import mint_service_token
from llamatrade_proto.generated import common_pb2, market_data_pb2
from llamatrade_proto.generated.market_data_connect import MarketDataServiceClient
from llamatrade_proto.timestamps import to_proto_timestamp
from llamatrade_telemetry import inject_headers

logger = logging.getLogger(__name__)


def _normalize_target(target: str) -> str:
    """Connect needs an absolute URL; accept bare ``host:port`` too."""
    if target.startswith(("http://", "https://")):
        return target
    return f"http://{target}"


def _bar_close(bar: market_data_pb2.Bar) -> Decimal:
    """Non-zero close price of a bar, or 0 when absent/zero."""
    if bar.HasField("close"):
        close = Decimal(bar.close.value)
        if close:
            return close
    return Decimal(0)


def _snapshot_price(snapshot: market_data_pb2.Snapshot) -> Decimal:
    """Latest price from a snapshot: trade → quote midpoint → daily/latest close.

    Returns 0 when the snapshot carries no usable price, letting callers treat it
    as a miss (fall back to cost basis) rather than marking a position to zero.
    """
    if snapshot.HasField("latest_trade") and snapshot.latest_trade.HasField("price"):
        price = Decimal(snapshot.latest_trade.price.value)
        if price:
            return price
    if snapshot.HasField("latest_quote"):
        quote = snapshot.latest_quote
        if quote.HasField("bid_price") and quote.HasField("ask_price"):
            bid = Decimal(quote.bid_price.value)
            ask = Decimal(quote.ask_price.value)
            if bid and ask:
                return (bid + ask) / 2
    if snapshot.HasField("daily_bar") and (close := _bar_close(snapshot.daily_bar)):
        return close
    if snapshot.HasField("latest_bar") and (close := _bar_close(snapshot.latest_bar)):
        return close
    return Decimal(0)


class _Absent:
    """Marks a key the loader answered without a value (cached like a value)."""


_ABSENT = _Absent()


class _SharedTtlLoader[K: Hashable, V]:
    """TTL cache with single-flight loading, shared across concurrent requests.

    A key's value (or its absence) is reused for ``ttl`` seconds; keys already
    being loaded are awaited rather than fetched again. A failed load is not
    cached, so the next caller retries, and its error reaches every waiter.
    """

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._values: dict[K, tuple[float, V | _Absent]] = {}
        self._inflight: dict[K, asyncio.Future[V | _Absent]] = {}

    async def get_many(
        self, keys: Sequence[K], load: Callable[[list[K]], Awaitable[dict[K, V]]]
    ) -> dict[K, V]:
        now = self._clock()
        found: dict[K, V] = {}
        waiting: dict[K, asyncio.Future[V | _Absent]] = {}
        to_load: list[K] = []
        for key in dict.fromkeys(keys):
            cached = self._values.get(key)
            if cached is not None and now - cached[0] < self._ttl:
                if not isinstance(cached[1], _Absent):
                    found[key] = cached[1]
            elif key in self._inflight:
                waiting[key] = self._inflight[key]
            else:
                to_load.append(key)

        if to_load:
            loop = asyncio.get_running_loop()
            futures = {key: loop.create_future() for key in to_load}
            self._inflight.update(futures)
            try:
                loaded = await load(to_load)
            except BaseException as exc:
                error = exc if isinstance(exc, Exception) else RuntimeError("load cancelled")
                for future in futures.values():
                    future.set_exception(error)
                    future.exception()  # mark retrieved when nobody else is waiting
                raise
            else:
                stamp = self._clock()
                for key, future in futures.items():
                    value: V | _Absent = loaded[key] if key in loaded else _ABSENT
                    self._values[key] = (stamp, value)
                    future.set_result(value)
                    if not isinstance(value, _Absent):
                        found[key] = value
            finally:
                for key in to_load:
                    self._inflight.pop(key, None)

        for key, future in waiting.items():
            value = await asyncio.shield(future)
            if not isinstance(value, _Absent):
                found[key] = value
        return found


def _env_seconds(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


class MarketDataClient:
    """Connect client for fetching market data from the market-data service."""

    def __init__(
        self,
        target: str | None = None,
        *,
        price_ttl: float | None = None,
        closes_ttl: float | None = None,
        call_timeout: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        raw = target or os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")
        self.target = _normalize_target(raw)
        self._client: MarketDataServiceClient | None = None
        self._call_timeout = (
            call_timeout
            if call_timeout is not None
            else _env_seconds("MARKET_DATA_CALL_TIMEOUT_SECONDS", 5.0)
        )
        self._prices = _SharedTtlLoader[str, Decimal](
            price_ttl
            if price_ttl is not None
            else _env_seconds("MARKET_DATA_PRICE_TTL_SECONDS", 15.0),
            clock,
        )
        self._closes = _SharedTtlLoader[tuple[str, date, date], dict[date, float]](
            closes_ttl
            if closes_ttl is not None
            else _env_seconds("MARKET_DATA_CLOSES_TTL_SECONDS", 300.0),
            clock,
        )

    def _get_client(self) -> MarketDataServiceClient:
        if self._client is None:
            self._client = MarketDataServiceClient(self.target)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Internal service token so the call clears market-data's fail-closed auth."""
        return inject_headers(
            {"Authorization": f"Bearer {mint_service_token(service_name='portfolio')}"}
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def get_latest_price(self, symbol: str) -> Decimal:
        """Latest price for a single symbol (0 if unavailable)."""
        prices = await self.get_prices([symbol])
        return prices.get(symbol.upper(), Decimal(0))

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        """Latest price per symbol; symbols without a usable price are omitted.

        Omitting (rather than returning 0) lets the read model fall back to cost
        basis, so a transient market-data outage never marks positions to zero.
        """
        if not symbols:
            return {}
        upper = [s.upper() for s in symbols]
        try:
            return await self._prices.get_many(upper, self._fetch_prices)
        except Exception as e:
            logger.warning("Failed to get prices for %s: %s", upper, e)
            return {}

    async def _fetch_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        async with asyncio.timeout(self._call_timeout):
            response = await self._get_client().get_snapshots(
                market_data_pb2.GetSnapshotsRequest(symbols=symbols),
                headers=self._headers(),
            )
        prices: dict[str, Decimal] = {}
        for symbol, snapshot in response.snapshots.items():
            price = _snapshot_price(snapshot)
            if price:
                prices[symbol.upper()] = price
        return prices

    async def get_daily_closes(
        self, symbol: str, start: datetime, end: datetime
    ) -> dict[date, float]:
        """Daily close prices keyed by date over a window (empty on failure).

        Used for benchmark comparison (e.g. SPY) in performance analytics.
        """
        key = (symbol.upper(), start.date(), end.date())

        async def load(
            keys: list[tuple[str, date, date]],
        ) -> dict[tuple[str, date, date], dict[date, float]]:
            return {key: await self._fetch_daily_closes(key[0], start, end)}

        try:
            closes = await self._closes.get_many([key], load)
        except Exception as e:
            logger.warning("Failed to get daily closes for %s: %s", symbol, e)
            return {}
        return dict(closes.get(key, {}))

    async def _fetch_daily_closes(
        self, symbol: str, start: datetime, end: datetime
    ) -> dict[date, float]:
        async with asyncio.timeout(self._call_timeout):
            response = await self._get_client().get_historical_bars(
                market_data_pb2.GetHistoricalBarsRequest(
                    symbol=symbol,
                    start=to_proto_timestamp(start),
                    end=to_proto_timestamp(end),
                    timeframe=market_data_pb2.TIMEFRAME_1DAY,
                    adjust_for_splits=True,
                    pagination=common_pb2.PaginationRequest(page=1, page_size=1000),
                ),
                headers=self._headers(),
            )
        closes: dict[date, float] = {}
        for bar in response.bars:
            if bar.HasField("close"):
                closes[datetime.fromtimestamp(bar.timestamp.seconds).date()] = float(
                    Decimal(bar.close.value)
                )
        return closes


_market_data_client: MarketDataClient | None = None


def get_market_data_client() -> MarketDataClient:
    """Get or create the market data client singleton."""
    global _market_data_client
    if _market_data_client is None:
        _market_data_client = MarketDataClient()
    return _market_data_client
