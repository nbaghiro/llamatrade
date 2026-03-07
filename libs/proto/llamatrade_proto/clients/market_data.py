"""Market Data gRPC client."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from llamatrade_proto.clients.base import BaseGRPCClient

if TYPE_CHECKING:
    from llamatrade_proto.generated import (
        market_data_pb2,
        market_data_pb2_grpc,
    )

logger = logging.getLogger(__name__)


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


class MarketDataClient(BaseGRPCClient):
    """Client for the Market Data gRPC service.

    This client provides methods for fetching historical market data
    and streaming real-time updates.

    Example:
        async with MarketDataClient("market-data:8840") as client:
            # Fetch historical bars
            bars = await client.get_historical_bars(
                symbol="AAPL",
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 31),
                timeframe="1D"
            )

            # Stream real-time bars
            async for bar in client.stream_bars(["AAPL", "GOOGL"]):
                print(f"{bar.symbol}: {bar.close}")
    """

    def __init__(
        self,
        target: str = "market-data:8840",
        *,
        secure: bool = False,
        credentials: object | None = None,
        interceptors: list[object] | None = None,
        options: list[tuple[str, str | int | bool]] | None = None,
    ) -> None:
        """Initialize the Market Data client.

        Args:
            target: The gRPC server address
            secure: Whether to use TLS
            credentials: Optional channel credentials
            interceptors: Optional client interceptors
            options: Optional channel options
        """
        super().__init__(
            target,
            secure=secure,
            credentials=credentials,  # type: ignore[arg-type]
            interceptors=interceptors,  # type: ignore[arg-type]
            options=options,
        )
        self._stub: market_data_pb2_grpc.MarketDataServiceStub | None = None

    @property
    def stub(self) -> market_data_pb2_grpc.MarketDataServiceStub:
        """Get the gRPC stub (lazy initialization)."""
        if self._stub is None:
            # Import generated code (will be available after buf generate)
            try:
                from llamatrade_proto.generated import (
                    market_data_pb2_grpc,
                )

                self._stub = market_data_pb2_grpc.MarketDataServiceStub(self.channel)
            except ImportError:
                raise RuntimeError(
                    "Generated gRPC code not found. Run 'make generate' in libs/proto"
                )
        return self._stub

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
        """Fetch historical bar data.

        Args:
            symbol: The ticker symbol
            start: Start datetime
            end: End datetime
            timeframe: Bar timeframe (1MIN, 5MIN, 15MIN, 1HOUR, 1DAY, etc.)
            adjust_for_splits: Whether to adjust prices for splits
            page_size: Number of bars per page

        Returns:
            List of Bar objects
        """
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Map timeframe string to enum
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

        request = market_data_pb2.GetHistoricalBarsRequest(
            symbol=symbol,
            start=common_pb2.Timestamp(seconds=int(start.timestamp())),
            end=common_pb2.Timestamp(seconds=int(end.timestamp())),
            timeframe=timeframe_map.get(timeframe.upper(), market_data_pb2.TIMEFRAME_1DAY),
            adjust_for_splits=adjust_for_splits,
            pagination=common_pb2.PaginationRequest(page=1, page_size=page_size),
        )

        response = await self.stub.GetHistoricalBars(request)

        return [self._proto_to_bar(bar) for bar in response.bars]

    async def stream_bars(
        self,
        symbols: list[str],
        timeframe: str = "1MIN",
    ) -> AsyncIterator[Bar]:
        """Stream real-time bar updates.

        Args:
            symbols: List of ticker symbols
            timeframe: Bar timeframe

        Yields:
            Bar objects as they arrive
        """
        from llamatrade_proto.generated import market_data_pb2

        timeframe_map = {
            "1MIN": market_data_pb2.TIMEFRAME_1MIN,
            "5MIN": market_data_pb2.TIMEFRAME_5MIN,
        }

        request = market_data_pb2.StreamBarsRequest(
            symbols=symbols,
            timeframe=timeframe_map.get(timeframe.upper(), market_data_pb2.TIMEFRAME_1MIN),
        )

        async for bar in self.stub.StreamBars(request):
            yield self._proto_to_bar(bar)

    async def stream_quotes(self, symbols: list[str]) -> AsyncIterator[Quote]:
        """Stream real-time quote updates.

        Args:
            symbols: List of ticker symbols

        Yields:
            Quote objects as they arrive
        """
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.StreamQuotesRequest(symbols=symbols)

        async for quote in self.stub.StreamQuotes(request):
            yield self._proto_to_quote(quote)

    async def stream_trades(self, symbols: list[str]) -> AsyncIterator[Trade]:
        """Stream real-time trade ticks.

        Args:
            symbols: List of ticker symbols

        Yields:
            Trade objects as they arrive
        """
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.StreamTradesRequest(symbols=symbols)

        async for trade in self.stub.StreamTrades(request):
            yield self._proto_to_trade(trade)

    async def get_snapshot(self, symbol: str) -> Snapshot:
        """Get current market snapshot for a symbol.

        Args:
            symbol: The ticker symbol

        Returns:
            Snapshot with latest price, bid/ask, and daily change
        """
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.GetSnapshotRequest(symbol=symbol)
        response = await self.stub.GetSnapshot(request)
        return self._proto_to_snapshot(response)

    async def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Get current market snapshots for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbol to Snapshot
        """
        from llamatrade_proto.generated import market_data_pb2

        request = market_data_pb2.GetSnapshotsRequest(symbols=symbols)
        response = await self.stub.GetSnapshots(request)
        return {
            symbol: self._proto_to_snapshot(snapshot)
            for symbol, snapshot in response.snapshots.items()
        }

    async def get_latest_price(self, symbol: str) -> Decimal:
        """Get the latest price for a symbol.

        Convenience method that extracts price from snapshot.

        Args:
            symbol: The ticker symbol

        Returns:
            Latest price as Decimal
        """
        snapshot = await self.get_snapshot(symbol)
        return snapshot.latest_price

    async def get_latest_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        """Get latest prices for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbol to latest price
        """
        snapshots = await self.get_snapshots(symbols)
        return {symbol: snapshot.latest_price for symbol, snapshot in snapshots.items()}

    def _proto_to_snapshot(self, proto_snapshot: market_data_pb2.Snapshot) -> Snapshot:
        """Convert protobuf Snapshot to dataclass."""
        # Determine latest price: prefer trade price, then quote midpoint, then bar close
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
            # If no trade price, use quote midpoint
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
