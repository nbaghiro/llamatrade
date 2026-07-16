"""Market Data client (MarketDataService, hosted by the market-data service).

The market-data service serves MarketDataService as a Connect ASGI app
(HTTP/1.1), so callers use the generated Connect client — not a native-gRPC
channel. Inter-service calls carry a minted service token so they clear the
service's fail-closed auth.

Consumed by the trading service (risk / position pricing) and the backtest
engine (historical-bar streaming). The portfolio service has its own equivalent
Connect client.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from llamatrade_common.auth import mint_service_token
from llamatrade_proto.generated.market_data_connect import MarketDataServiceClient

if TYPE_CHECKING:
    from llamatrade_proto.generated import market_data_pb2

logger = logging.getLogger(__name__)


def _normalize_target(target: str) -> str:
    """Connect needs an absolute URL; accept bare ``host:port`` too."""
    if target.startswith(("http://", "https://")):
        return target
    return f"http://{target}"


def _timeframe_to_proto(timeframe: str) -> market_data_pb2.Timeframe.ValueType:
    """Map a timeframe string (e.g. "1D", "1MIN") to the proto Timeframe enum.

    Unknown values fall back to daily. Shared by the historical-bar RPCs.
    """
    from llamatrade_proto.generated import market_data_pb2

    timeframe_map = {
        "1MIN": market_data_pb2.TIMEFRAME_1MIN,
        "5MIN": market_data_pb2.TIMEFRAME_5MIN,
        "15MIN": market_data_pb2.TIMEFRAME_15MIN,
        "30MIN": market_data_pb2.TIMEFRAME_30MIN,
        "1HOUR": market_data_pb2.TIMEFRAME_1HOUR,
        "4HOUR": market_data_pb2.TIMEFRAME_4HOUR,
        "1DAY": market_data_pb2.TIMEFRAME_1DAY,
        "1D": market_data_pb2.TIMEFRAME_1DAY,
        "1WEEK": market_data_pb2.TIMEFRAME_1WEEK,
        "1MONTH": market_data_pb2.TIMEFRAME_1MONTH,
    }
    return timeframe_map.get(timeframe.upper(), market_data_pb2.TIMEFRAME_1DAY)


@dataclass
class Bar:
    """OHLCV bar data."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    trade_count: int | None = None
    vwap: Decimal | None = None


@dataclass
class Quote:
    """Bid/ask quote data."""

    symbol: str
    timestamp: datetime
    bid_price: Decimal
    bid_size: int
    ask_price: Decimal
    ask_size: int


@dataclass
class Trade:
    """Trade tick data."""

    symbol: str
    timestamp: datetime
    price: Decimal
    size: int
    exchange: str | None = None


@dataclass
class Snapshot:
    """Market data snapshot for a symbol."""

    symbol: str
    latest_price: Decimal
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    latest_bar: Bar | None = None
    change: Decimal | None = None
    change_percent: Decimal | None = None


class MarketDataClient:
    """Connect client for the MarketDataService API (market-data service, :8840).

    Example:
        async with MarketDataClient("market-data:8840") as client:
            bars = await client.get_historical_bars(
                symbol="AAPL", start=..., end=..., timeframe="1D"
            )
            async for bar in client.stream_bars(["AAPL", "GOOGL"]):
                print(f"{bar.symbol}: {bar.close}")
    """

    def __init__(self, target: str = "market-data:8840", *, service_name: str = "internal") -> None:
        self.target = _normalize_target(target)
        self._service_name = service_name
        self._client: MarketDataServiceClient | None = None

    def _get_client(self) -> MarketDataServiceClient:
        if self._client is None:
            self._client = MarketDataServiceClient(self.target)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Internal service token so the call clears market-data's fail-closed auth."""
        return {"Authorization": f"Bearer {mint_service_token(service_name=self._service_name)}"}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> MarketDataClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def get_historical_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1D",
        *,
        adjust_for_splits: bool = True,
        page_size: int = 1000,
    ) -> list[Bar]:
        """Fetch historical bar data for a single symbol."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        request = market_data_pb2.GetHistoricalBarsRequest(
            symbol=symbol,
            start=common_pb2.Timestamp(seconds=int(start.timestamp())),
            end=common_pb2.Timestamp(seconds=int(end.timestamp())),
            timeframe=_timeframe_to_proto(timeframe),
            adjust_for_splits=adjust_for_splits,
            pagination=common_pb2.PaginationRequest(page=1, page_size=page_size),
        )
        response = await self._get_client().get_historical_bars(request, headers=self._headers())
        return [self._proto_to_bar(bar) for bar in response.bars]

    async def get_multi_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "1D",
        *,
        limit: int = 0,
    ) -> dict[str, list[Bar]]:
        """Fetch historical bars for many symbols in a single batch RPC.

        The server fans out across symbols; a symbol with no data maps to an
        empty list (or is omitted from the map).
        """
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        request = market_data_pb2.GetMultiBarsRequest(
            symbols=symbols,
            start=common_pb2.Timestamp(seconds=int(start.timestamp())),
            end=common_pb2.Timestamp(seconds=int(end.timestamp())),
            timeframe=_timeframe_to_proto(timeframe),
            limit=limit,
        )
        response = await self._get_client().get_multi_bars(request, headers=self._headers())
        return {
            symbol: [self._proto_to_bar(bar) for bar in bar_list.bars]
            for symbol, bar_list in response.bars.items()
        }

    async def stream_historical_bars(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
        timeframe: str = "1D",
        *,
        limit: int = 0,
    ) -> AsyncIterator[Bar]:
        """Stream historical bars for many symbols in timestamp order (one call).

        Yields bars incrementally so the consumer never buffers the whole dataset
        as a single response.
        """
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        request = market_data_pb2.StreamHistoricalBarsRequest(
            symbols=symbols,
            start=common_pb2.Timestamp(seconds=int(start.timestamp())),
            end=common_pb2.Timestamp(seconds=int(end.timestamp())),
            timeframe=_timeframe_to_proto(timeframe),
            limit=limit,
        )
        async for bar in self._get_client().stream_historical_bars(request, headers=self._headers()):
            yield self._proto_to_bar(bar)

    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str = "1MIN",
    ) -> AsyncIterator[Bar]:
        """Stream real-time bar updates."""
        from llamatrade_proto.generated import market_data_pb2

        timeframe_map = {
            "1MIN": market_data_pb2.TIMEFRAME_1MIN,
            "5MIN": market_data_pb2.TIMEFRAME_5MIN,
        }
        request = market_data_pb2.StreamBarsRequest(
            symbols=symbols,
            timeframe=timeframe_map.get(timeframe.upper(), market_data_pb2.TIMEFRAME_1MIN),
        )
        async for bar in self._get_client().stream_bars(request, headers=self._headers()):
            yield self._proto_to_bar(bar)

    async def stream_quotes(self, symbols: list[str]) -> AsyncIterator[Quote]:
        """Stream real-time quote updates."""
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.StreamQuotesRequest(symbols=symbols)
        async for quote in self._get_client().stream_quotes(request, headers=self._headers()):
            yield self._proto_to_quote(quote)

    async def stream_trades(self, symbols: list[str]) -> AsyncIterator[Trade]:
        """Stream real-time trade ticks."""
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.StreamTradesRequest(symbols=symbols)
        async for trade in self._get_client().stream_trades(request, headers=self._headers()):
            yield self._proto_to_trade(trade)

    async def get_snapshot(self, symbol: str) -> Snapshot:
        """Get current market snapshot for a symbol."""
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.GetSnapshotRequest(symbol=symbol)
        response = await self._get_client().get_snapshot(request, headers=self._headers())
        return self._proto_to_snapshot(response)

    async def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Get current market snapshots for multiple symbols."""
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.GetSnapshotsRequest(symbols=symbols)
        response = await self._get_client().get_snapshots(request, headers=self._headers())
        return {
            symbol: self._proto_to_snapshot(snapshot)
            for symbol, snapshot in response.snapshots.items()
        }

    async def get_latest_price(self, symbol: str) -> Decimal:
        """Get the latest price for a symbol (extracted from its snapshot)."""
        snapshot = await self.get_snapshot(symbol)
        return snapshot.latest_price

    async def get_latest_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        """Get latest prices for multiple symbols."""
        snapshots = await self.get_snapshots(symbols)
        return {symbol: snapshot.latest_price for symbol, snapshot in snapshots.items()}

    def _proto_to_snapshot(self, proto_snapshot: market_data_pb2.Snapshot) -> Snapshot:
        """Convert protobuf Snapshot to dataclass."""
        # Latest price: prefer trade price, then quote midpoint, then bar close.
        latest_price = Decimal(0)
        bid_price = None
        ask_price = None

        if proto_snapshot.HasField("latest_trade") and proto_snapshot.latest_trade.HasField(
            "price"
        ):
            latest_price = Decimal(proto_snapshot.latest_trade.price.value)

        if proto_snapshot.HasField("latest_quote"):
            quote = proto_snapshot.latest_quote
            if quote.HasField("bid_price"):
                bid_price = Decimal(quote.bid_price.value)
            if quote.HasField("ask_price"):
                ask_price = Decimal(quote.ask_price.value)
            if latest_price == 0 and bid_price and ask_price:
                latest_price = (bid_price + ask_price) / 2

        if latest_price == 0 and proto_snapshot.HasField("latest_bar"):
            if proto_snapshot.latest_bar.HasField("close"):
                latest_price = Decimal(proto_snapshot.latest_bar.close.value)

        return Snapshot(
            symbol=proto_snapshot.symbol,
            latest_price=latest_price,
            bid_price=bid_price,
            ask_price=ask_price,
            latest_bar=self._proto_to_bar(proto_snapshot.latest_bar)
            if proto_snapshot.HasField("latest_bar")
            else None,
            change=Decimal(proto_snapshot.change.value)
            if proto_snapshot.HasField("change")
            else None,
            change_percent=Decimal(proto_snapshot.change_percent.value)
            if proto_snapshot.HasField("change_percent")
            else None,
        )

    def _proto_to_bar(self, proto_bar: market_data_pb2.Bar) -> Bar:
        """Convert protobuf Bar to dataclass."""
        return Bar(
            symbol=proto_bar.symbol,
            timestamp=datetime.fromtimestamp(proto_bar.timestamp.seconds),
            open=Decimal(proto_bar.open.value) if proto_bar.HasField("open") else Decimal(0),
            high=Decimal(proto_bar.high.value) if proto_bar.HasField("high") else Decimal(0),
            low=Decimal(proto_bar.low.value) if proto_bar.HasField("low") else Decimal(0),
            close=Decimal(proto_bar.close.value) if proto_bar.HasField("close") else Decimal(0),
            volume=proto_bar.volume,
            trade_count=proto_bar.trade_count if proto_bar.trade_count else None,
            vwap=Decimal(proto_bar.vwap.value) if proto_bar.HasField("vwap") else None,
        )

    def _proto_to_quote(self, proto_quote: market_data_pb2.Quote) -> Quote:
        """Convert protobuf Quote to dataclass."""
        return Quote(
            symbol=proto_quote.symbol,
            timestamp=datetime.fromtimestamp(proto_quote.timestamp.seconds),
            bid_price=Decimal(proto_quote.bid_price.value),
            bid_size=proto_quote.bid_size,
            ask_price=Decimal(proto_quote.ask_price.value),
            ask_size=proto_quote.ask_size,
        )

    def _proto_to_trade(self, proto_trade: market_data_pb2.Trade) -> Trade:
        """Convert protobuf Trade to dataclass."""
        return Trade(
            symbol=proto_trade.symbol,
            timestamp=datetime.fromtimestamp(proto_trade.timestamp.seconds),
            price=Decimal(proto_trade.price.value),
            size=proto_trade.size,
            exchange=proto_trade.exchange if proto_trade.exchange else None,
        )
