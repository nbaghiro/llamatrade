"""Market-data adapter: current prices + daily closes over the Connect protocol.

The market-data service is served as a Connect ASGI app (HTTP/1.1), so callers
use the generated Connect client — not a native-gRPC channel. Inter-service calls
carry a minted service token so they pass market-data's fail-closed auth.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal

from llamatrade_common.auth import mint_service_token
from llamatrade_proto.generated import common_pb2, market_data_pb2
from llamatrade_proto.generated.market_data_connect import MarketDataServiceClient

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


class MarketDataClient:
    """Connect client for fetching market data from the market-data service."""

    def __init__(self, target: str | None = None):
        raw = target or os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")
        self.target = _normalize_target(raw)
        self._client: MarketDataServiceClient | None = None

    def _get_client(self) -> MarketDataServiceClient:
        if self._client is None:
            self._client = MarketDataServiceClient(self.target)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Internal service token so the call clears market-data's fail-closed auth."""
        return {"Authorization": f"Bearer {mint_service_token(service_name='portfolio')}"}

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
            client = self._get_client()
            response = await client.get_snapshots(
                market_data_pb2.GetSnapshotsRequest(symbols=upper),
                headers=self._headers(),
            )
        except Exception as e:
            logger.warning("Failed to get prices for %s: %s", upper, e)
            return {}
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
        try:
            client = self._get_client()
            response = await client.get_historical_bars(
                market_data_pb2.GetHistoricalBarsRequest(
                    symbol=symbol.upper(),
                    start=common_pb2.Timestamp(seconds=int(start.timestamp())),
                    end=common_pb2.Timestamp(seconds=int(end.timestamp())),
                    timeframe=market_data_pb2.TIMEFRAME_1DAY,
                    adjust_for_splits=True,
                    pagination=common_pb2.PaginationRequest(page=1, page_size=1000),
                ),
                headers=self._headers(),
            )
        except Exception as e:
            logger.warning("Failed to get daily closes for %s: %s", symbol, e)
            return {}
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
