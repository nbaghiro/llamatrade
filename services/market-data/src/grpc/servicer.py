# mypy: ignore-errors
"""Market Data gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import grpc.aio

from src.alpaca.client import get_alpaca_client
from src.models import Timeframe
from src.streaming.manager import get_stream_manager

logger = logging.getLogger(__name__)


class MarketDataServicer:
    """gRPC servicer for the Market Data service.

    Implements the MarketDataService defined in market_data.proto.
    """

    # Map proto timeframe enum to internal Timeframe
    _TIMEFRAME_MAP: dict[int, Timeframe] = {}

    @classmethod
    def _init_timeframe_map(cls) -> None:
        """Initialize the timeframe mapping."""
        if cls._TIMEFRAME_MAP:
            return

        try:
            from llamatrade.v1 import market_data_pb2

            cls._TIMEFRAME_MAP = {
                market_data_pb2.TIMEFRAME_1MIN: Timeframe.MINUTE_1,
                market_data_pb2.TIMEFRAME_5MIN: Timeframe.MINUTE_5,
                market_data_pb2.TIMEFRAME_15MIN: Timeframe.MINUTE_15,
                market_data_pb2.TIMEFRAME_30MIN: Timeframe.MINUTE_30,
                market_data_pb2.TIMEFRAME_1HOUR: Timeframe.HOUR_1,
                market_data_pb2.TIMEFRAME_4HOUR: Timeframe.HOUR_4,
                market_data_pb2.TIMEFRAME_1DAY: Timeframe.DAY_1,
                market_data_pb2.TIMEFRAME_1WEEK: Timeframe.WEEK_1,
            }
        except ImportError:
            logger.warning("gRPC generated code not available - using fallback")

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._init_timeframe_map()

    async def GetHistoricalBars(
        self,
        request: "market_data_pb2.GetHistoricalBarsRequest",
        context: grpc.aio.ServicerContext,
    ) -> "market_data_pb2.GetHistoricalBarsResponse":
        """Get historical OHLCV bars for a symbol."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        try:
            client = await get_alpaca_client()

            # Parse request parameters
            symbol = request.symbol
            start = datetime.fromtimestamp(request.start.seconds, tz=timezone.utc)
            end = datetime.fromtimestamp(request.end.seconds, tz=timezone.utc) if request.HasField("end") else None
            timeframe = self._TIMEFRAME_MAP.get(request.timeframe, Timeframe.DAY_1)

            # Get limit from pagination if provided
            limit = 1000
            if request.HasField("pagination"):
                limit = min(request.pagination.page_size, 10000)

            # Fetch bars from Alpaca
            bars = await client.get_bars(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )

            # Convert to proto response
            proto_bars = []
            for bar in bars:
                proto_bar = market_data_pb2.Bar(
                    symbol=symbol,
                    timestamp=common_pb2.Timestamp(
                        seconds=int(bar.timestamp.timestamp()),
                        nanos=bar.timestamp.microsecond * 1000,
                    ),
                    open=common_pb2.Decimal(value=str(bar.open)),
                    high=common_pb2.Decimal(value=str(bar.high)),
                    low=common_pb2.Decimal(value=str(bar.low)),
                    close=common_pb2.Decimal(value=str(bar.close)),
                    volume=bar.volume,
                )
                if bar.trade_count is not None:
                    proto_bar.trade_count = bar.trade_count
                if bar.vwap is not None:
                    proto_bar.vwap.CopyFrom(common_pb2.Decimal(value=str(bar.vwap)))
                proto_bars.append(proto_bar)

            return market_data_pb2.GetHistoricalBarsResponse(
                bars=proto_bars,
                pagination=common_pb2.PaginationResponse(
                    total_items=len(proto_bars),
                    total_pages=1,
                    current_page=1,
                    page_size=len(proto_bars),
                    has_next=False,
                    has_previous=False,
                ),
            )

        except Exception as e:
            logger.error("GetHistoricalBars error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to fetch historical bars: {e}",
            )

    async def GetMultiBars(
        self,
        request: "market_data_pb2.GetMultiBarsRequest",
        context: grpc.aio.ServicerContext,
    ) -> "market_data_pb2.GetMultiBarsResponse":
        """Get historical bars for multiple symbols."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        try:
            client = await get_alpaca_client()

            symbols = list(request.symbols)
            start = datetime.fromtimestamp(request.start.seconds, tz=timezone.utc)
            end = datetime.fromtimestamp(request.end.seconds, tz=timezone.utc) if request.HasField("end") else None
            timeframe = self._TIMEFRAME_MAP.get(request.timeframe, Timeframe.DAY_1)
            limit = request.limit if request.limit > 0 else 1000

            # Fetch bars from Alpaca
            multi_bars = await client.get_multi_bars(
                symbols=symbols,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )

            # Convert to proto response
            bars_map = {}
            for symbol, bars in multi_bars.items():
                proto_bars = []
                for bar in bars:
                    proto_bar = market_data_pb2.Bar(
                        symbol=symbol,
                        timestamp=common_pb2.Timestamp(
                            seconds=int(bar.timestamp.timestamp()),
                            nanos=bar.timestamp.microsecond * 1000,
                        ),
                        open=common_pb2.Decimal(value=str(bar.open)),
                        high=common_pb2.Decimal(value=str(bar.high)),
                        low=common_pb2.Decimal(value=str(bar.low)),
                        close=common_pb2.Decimal(value=str(bar.close)),
                        volume=bar.volume,
                    )
                    if bar.trade_count is not None:
                        proto_bar.trade_count = bar.trade_count
                    if bar.vwap is not None:
                        proto_bar.vwap.CopyFrom(common_pb2.Decimal(value=str(bar.vwap)))
                    proto_bars.append(proto_bar)
                bars_map[symbol] = market_data_pb2.BarList(bars=proto_bars)

            return market_data_pb2.GetMultiBarsResponse(bars=bars_map)

        except Exception as e:
            logger.error("GetMultiBars error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to fetch multi bars: {e}",
            )

    async def GetSnapshot(
        self,
        request: "market_data_pb2.GetSnapshotRequest",
        context: grpc.aio.ServicerContext,
    ) -> "market_data_pb2.Snapshot":
        """Get current market snapshot for a symbol."""

        try:
            client = await get_alpaca_client()
            snapshot = await client.get_snapshot(request.symbol)

            if snapshot is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Snapshot not found for symbol: {request.symbol}",
                )

            return self._to_proto_snapshot(request.symbol, snapshot)

        except Exception as e:
            logger.error("GetSnapshot error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to fetch snapshot: {e}",
            )

    async def GetSnapshots(
        self,
        request: "market_data_pb2.GetSnapshotsRequest",
        context: grpc.aio.ServicerContext,
    ) -> "market_data_pb2.GetSnapshotsResponse":
        """Get snapshots for multiple symbols."""
        from llamatrade.v1 import market_data_pb2

        try:
            client = await get_alpaca_client()
            snapshots = await client.get_multi_snapshots(list(request.symbols))

            proto_snapshots = {}
            for symbol, snapshot in snapshots.items():
                proto_snapshots[symbol] = self._to_proto_snapshot(symbol, snapshot)

            return market_data_pb2.GetSnapshotsResponse(snapshots=proto_snapshots)

        except Exception as e:
            logger.error("GetSnapshots error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to fetch snapshots: {e}",
            )

    async def GetMarketStatus(
        self,
        request: "market_data_pb2.GetMarketStatusRequest",
        context: grpc.aio.ServicerContext,
    ) -> "market_data_pb2.GetMarketStatusResponse":
        """Get current market status."""
        from llamatrade.v1 import market_data_pb2

        # Simplified implementation - would need market calendar integration
        # For now, return a basic status based on time
        from datetime import datetime, time

        now = datetime.now(timezone.utc)
        market_open = time(14, 30)  # 9:30 AM ET in UTC
        market_close = time(21, 0)  # 4:00 PM ET in UTC

        current_time = now.time()
        weekday = now.weekday()

        if weekday >= 5:  # Weekend
            status = market_data_pb2.MARKET_STATUS_CLOSED
        elif market_open <= current_time <= market_close:
            status = market_data_pb2.MARKET_STATUS_OPEN
        elif current_time < market_open:
            status = market_data_pb2.MARKET_STATUS_PRE_MARKET
        else:
            status = market_data_pb2.MARKET_STATUS_AFTER_HOURS

        return market_data_pb2.GetMarketStatusResponse(status=status)

    async def StreamBars(
        self,
        request: "market_data_pb2.StreamBarsRequest",
        context: grpc.aio.ServicerContext,
    ):
        """Stream real-time bar updates."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        from src.streaming.manager import StreamType

        symbols = [s.upper() for s in request.symbols]
        logger.info("Starting bar stream for symbols: %s", symbols)

        stream_manager = get_stream_manager()
        stream_id = id(context)

        try:
            # Connect and get our queue
            queue = await stream_manager.connect(stream_id)

            # Subscribe to bar updates for requested symbols
            await stream_manager.subscribe(
                client_id=stream_id,
                trades=[],
                quotes=[],
                bars=symbols,
            )

            while not context.cancelled():
                try:
                    # Wait for data with timeout for keepalive
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Only yield bar messages
                    if message.stream_type == StreamType.BAR:
                        data = message.data
                        yield market_data_pb2.Bar(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=int(data["timestamp"].timestamp())
                                if hasattr(data["timestamp"], "timestamp")
                                else int(datetime.fromisoformat(str(data["timestamp"])).timestamp())
                            ),
                            open=common_pb2.Decimal(value=str(data["open"])),
                            high=common_pb2.Decimal(value=str(data["high"])),
                            low=common_pb2.Decimal(value=str(data["low"])),
                            close=common_pb2.Decimal(value=str(data["close"])),
                            volume=data["volume"],
                        )
                except asyncio.TimeoutError:
                    # Continue waiting - client is still connected
                    continue

        except asyncio.CancelledError:
            logger.info("Bar stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed bar stream for symbols: %s", symbols)

    async def StreamQuotes(
        self,
        request: "market_data_pb2.StreamQuotesRequest",
        context: grpc.aio.ServicerContext,
    ):
        """Stream real-time quote updates."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        from src.streaming.manager import StreamType

        symbols = [s.upper() for s in request.symbols]
        logger.info("Starting quote stream for symbols: %s", symbols)

        stream_manager = get_stream_manager()
        stream_id = id(context)

        try:
            # Connect and get our queue
            queue = await stream_manager.connect(stream_id)

            # Subscribe to quote updates for requested symbols
            await stream_manager.subscribe(
                client_id=stream_id,
                trades=[],
                quotes=symbols,
                bars=[],
            )

            while not context.cancelled():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    if message.stream_type == StreamType.QUOTE:
                        data = message.data
                        yield market_data_pb2.Quote(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=int(data["timestamp"].timestamp())
                                if hasattr(data["timestamp"], "timestamp")
                                else int(datetime.fromisoformat(str(data["timestamp"])).timestamp())
                            ),
                            bid_price=common_pb2.Decimal(value=str(data["bid_price"])),
                            bid_size=data["bid_size"],
                            ask_price=common_pb2.Decimal(value=str(data["ask_price"])),
                            ask_size=data["ask_size"],
                        )
                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.info("Quote stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed quote stream for symbols: %s", symbols)

    async def StreamTrades(
        self,
        request: "market_data_pb2.StreamTradesRequest",
        context: grpc.aio.ServicerContext,
    ):
        """Stream real-time trade updates."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        from src.streaming.manager import StreamType

        symbols = [s.upper() for s in request.symbols]
        logger.info("Starting trade stream for symbols: %s", symbols)

        stream_manager = get_stream_manager()
        stream_id = id(context)

        try:
            # Connect and get our queue
            queue = await stream_manager.connect(stream_id)

            # Subscribe to trade updates for requested symbols
            await stream_manager.subscribe(
                client_id=stream_id,
                trades=symbols,
                quotes=[],
                bars=[],
            )

            while not context.cancelled():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    if message.stream_type == StreamType.TRADE:
                        data = message.data
                        yield market_data_pb2.Trade(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=int(data["timestamp"].timestamp())
                                if hasattr(data["timestamp"], "timestamp")
                                else int(datetime.fromisoformat(str(data["timestamp"])).timestamp())
                            ),
                            price=common_pb2.Decimal(value=str(data["price"])),
                            size=data["size"],
                            exchange=data.get("exchange", ""),
                        )
                except asyncio.TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.info("Trade stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed trade stream for symbols: %s", symbols)

    def _to_proto_snapshot(
        self,
        symbol: str,
        snapshot: "Snapshot",
    ) -> "market_data_pb2.Snapshot":
        """Convert internal Snapshot to proto Snapshot."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        proto_snapshot = market_data_pb2.Snapshot(symbol=symbol)

        if snapshot.daily_bar:
            proto_snapshot.daily_bar.CopyFrom(
                self._bar_to_proto(symbol, snapshot.daily_bar)
            )
        if snapshot.prev_daily_bar:
            proto_snapshot.previous_daily_bar.CopyFrom(
                self._bar_to_proto(symbol, snapshot.prev_daily_bar)
            )
        if snapshot.latest_quote:
            proto_snapshot.latest_quote.CopyFrom(
                market_data_pb2.Quote(
                    symbol=symbol,
                    timestamp=common_pb2.Timestamp(
                        seconds=int(snapshot.latest_quote.timestamp.timestamp())
                    ),
                    bid_price=common_pb2.Decimal(value=str(snapshot.latest_quote.bid_price)),
                    bid_size=snapshot.latest_quote.bid_size,
                    ask_price=common_pb2.Decimal(value=str(snapshot.latest_quote.ask_price)),
                    ask_size=snapshot.latest_quote.ask_size,
                )
            )
        if snapshot.latest_trade:
            proto_snapshot.latest_trade.CopyFrom(
                market_data_pb2.Trade(
                    symbol=symbol,
                    timestamp=common_pb2.Timestamp(
                        seconds=int(snapshot.latest_trade.timestamp.timestamp())
                    ),
                    price=common_pb2.Decimal(value=str(snapshot.latest_trade.price)),
                    size=snapshot.latest_trade.size,
                    exchange=snapshot.latest_trade.exchange or "",
                )
            )

        # Calculate change if we have both daily bars
        if snapshot.daily_bar and snapshot.prev_daily_bar:
            change = snapshot.daily_bar.close - snapshot.prev_daily_bar.close
            if snapshot.prev_daily_bar.close > 0:
                change_percent = (change / snapshot.prev_daily_bar.close) * 100
            else:
                change_percent = 0.0
            proto_snapshot.change.CopyFrom(common_pb2.Decimal(value=str(change)))
            proto_snapshot.change_percent.CopyFrom(common_pb2.Decimal(value=f"{change_percent:.2f}"))

        return proto_snapshot

    def _bar_to_proto(self, symbol: str, bar: "Bar") -> "market_data_pb2.Bar":
        """Convert internal Bar to proto Bar."""
        from llamatrade.v1 import common_pb2, market_data_pb2

        proto_bar = market_data_pb2.Bar(
            symbol=symbol,
            timestamp=common_pb2.Timestamp(
                seconds=int(bar.timestamp.timestamp()),
                nanos=bar.timestamp.microsecond * 1000,
            ),
            open=common_pb2.Decimal(value=str(bar.open)),
            high=common_pb2.Decimal(value=str(bar.high)),
            low=common_pb2.Decimal(value=str(bar.low)),
            close=common_pb2.Decimal(value=str(bar.close)),
            volume=bar.volume,
        )
        if bar.trade_count is not None:
            proto_bar.trade_count = bar.trade_count
        if bar.vwap is not None:
            proto_bar.vwap.CopyFrom(common_pb2.Decimal(value=str(bar.vwap)))
        return proto_bar
