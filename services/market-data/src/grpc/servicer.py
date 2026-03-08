"""Market Data Connect servicer implementation."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_alpaca import get_market_data_client_async, get_trading_client_async

from src.models import BarData, QuoteData, Timeframe, TradeData
from src.streaming.manager import StreamType, get_stream_manager

if TYPE_CHECKING:
    from llamatrade_proto.generated import market_data_pb2

    from src.models import Bar, Snapshot

logger = logging.getLogger(__name__)

# Symbol validation pattern: 1-5 uppercase letters (standard US stocks)
# Also allows crypto pairs like BTC/USD
SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}(/[A-Z]{3,4})?$")

# Nil UUID for detecting missing context
_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass
class RequestTenantContext:
    """Tenant context extracted from request headers."""

    tenant_id: UUID | None
    user_id: UUID | None
    is_authenticated: bool

    def log_context(self) -> dict[str, str]:
        """Return context dict for structured logging."""
        return {
            "tenant_id": str(self.tenant_id) if self.tenant_id else "anonymous",
            "user_id": str(self.user_id) if self.user_id else "anonymous",
            "authenticated": str(self.is_authenticated),
        }


def _extract_tenant_context(ctx: AnyContext) -> RequestTenantContext:
    """Extract tenant context from request headers.

    For market data (public data), authentication is optional but
    we extract context for logging and rate limiting purposes.

    Headers checked:
    - X-Tenant-ID: Tenant identifier
    - X-User-ID: User identifier
    - Authorization: Bearer token (for future JWT extraction)
    """
    tenant_id: UUID | None = None
    user_id: UUID | None = None

    # Try to extract from headers via request_headers() method
    headers = ctx.request_headers()

    # Extract tenant ID
    tenant_id_str = headers.get("x-tenant-id") or headers.get("X-Tenant-ID")
    if tenant_id_str:
        try:
            tenant_id = UUID(tenant_id_str)
            if tenant_id == _NIL_UUID:
                tenant_id = None
        except ValueError:
            pass

    # Extract user ID
    user_id_str = headers.get("x-user-id") or headers.get("X-User-ID")
    if user_id_str:
        try:
            user_id = UUID(user_id_str)
            if user_id == _NIL_UUID:
                user_id = None
        except ValueError:
            pass

    return RequestTenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        is_authenticated=tenant_id is not None,
    )


def _validate_symbol(symbol: str) -> str:
    """Validate and normalize a stock symbol.

    Args:
        symbol: The symbol to validate

    Returns:
        Normalized (uppercase) symbol

    Raises:
        ConnectError: If symbol is invalid
    """
    if not symbol:
        raise ConnectError(Code.INVALID_ARGUMENT, "Symbol is required")

    symbol = symbol.upper().strip()

    if not SYMBOL_PATTERN.match(symbol):
        raise ConnectError(
            Code.INVALID_ARGUMENT,
            f"Invalid symbol format: '{symbol}'. Expected 1-5 uppercase letters "
            "(e.g., 'AAPL', 'TSLA') or crypto pair (e.g., 'BTC/USD')",
        )

    return symbol


def _validate_symbols(symbols: list[str]) -> list[str]:
    """Validate and normalize a list of symbols.

    Args:
        symbols: List of symbols to validate

    Returns:
        List of normalized symbols

    Raises:
        ConnectError: If any symbol is invalid or list is empty
    """
    if not symbols:
        raise ConnectError(Code.INVALID_ARGUMENT, "At least one symbol is required")

    return [_validate_symbol(s) for s in symbols]


def _to_timestamp_seconds(ts: str | datetime) -> int:
    """Convert a timestamp (string or datetime) to Unix seconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp())
    return int(datetime.fromisoformat(ts).timestamp())


class MarketDataServicer:
    """Connect servicer for the Market Data service.

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
            from llamatrade_proto.generated import market_data_pb2

            cls._TIMEFRAME_MAP = {
                market_data_pb2.TIMEFRAME_1MIN: Timeframe.MINUTE_1,
                market_data_pb2.TIMEFRAME_5MIN: Timeframe.MINUTE_5,
                market_data_pb2.TIMEFRAME_15MIN: Timeframe.MINUTE_15,
                market_data_pb2.TIMEFRAME_30MIN: Timeframe.MINUTE_30,
                market_data_pb2.TIMEFRAME_1HOUR: Timeframe.HOUR_1,
                market_data_pb2.TIMEFRAME_4HOUR: Timeframe.HOUR_4,
                market_data_pb2.TIMEFRAME_1DAY: Timeframe.DAY_1,
                market_data_pb2.TIMEFRAME_1WEEK: Timeframe.WEEK_1,
                market_data_pb2.TIMEFRAME_1MONTH: Timeframe.MONTH_1,
            }
        except ImportError:
            logger.warning("gRPC generated code not available - using fallback")

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._init_timeframe_map()

    async def get_historical_bars(
        self,
        request: market_data_pb2.GetHistoricalBarsRequest,
        ctx: AnyContext,
    ) -> market_data_pb2.GetHistoricalBarsResponse:
        """Get historical OHLCV bars for a symbol."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbol
        symbol = _validate_symbol(request.symbol)

        logger.info(
            "get_historical_bars request",
            extra={"symbol": symbol, **tenant_ctx.log_context()},
        )

        try:
            client = await get_market_data_client_async()

            # Parse request parameters
            start = datetime.fromtimestamp(request.start.seconds, tz=UTC)
            end = (
                datetime.fromtimestamp(request.end.seconds, tz=UTC)
                if request.HasField("end")
                else None
            )
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

            # Convert to proto response using helper
            proto_bars = [self._bar_to_proto(symbol, bar) for bar in bars]

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
            logger.error("get_historical_bars error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"Failed to fetch historical bars: {e}") from e

    async def get_multi_bars(
        self,
        request: market_data_pb2.GetMultiBarsRequest,
        ctx: AnyContext,
    ) -> market_data_pb2.GetMultiBarsResponse:
        """Get historical bars for multiple symbols."""
        from llamatrade_proto.generated import market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbols
        symbols = _validate_symbols(list(request.symbols))

        logger.info(
            "get_multi_bars request",
            extra={"symbols": symbols, "count": len(symbols), **tenant_ctx.log_context()},
        )

        try:
            client = await get_market_data_client_async()

            start = datetime.fromtimestamp(request.start.seconds, tz=UTC)
            end = (
                datetime.fromtimestamp(request.end.seconds, tz=UTC)
                if request.HasField("end")
                else None
            )
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

            # Convert to proto response using helper
            bars_map = {
                symbol: market_data_pb2.BarList(
                    bars=[self._bar_to_proto(symbol, bar) for bar in bars]
                )
                for symbol, bars in multi_bars.items()
            }

            return market_data_pb2.GetMultiBarsResponse(bars=bars_map)

        except Exception as e:
            logger.error("get_multi_bars error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"Failed to fetch multi bars: {e}") from e

    async def get_snapshot(
        self,
        request: market_data_pb2.GetSnapshotRequest,
        ctx: AnyContext,
    ) -> market_data_pb2.Snapshot:
        """Get current market snapshot for a symbol."""
        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbol
        symbol = _validate_symbol(request.symbol)

        logger.info(
            "get_snapshot request",
            extra={"symbol": symbol, **tenant_ctx.log_context()},
        )

        try:
            client = await get_market_data_client_async()
            snapshot = await client.get_snapshot(symbol)

            if snapshot is None:
                raise ConnectError(Code.NOT_FOUND, f"Snapshot not found for symbol: {symbol}")

            return self._to_proto_snapshot(symbol, snapshot)

        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_snapshot error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"Failed to fetch snapshot: {e}") from e

    async def get_snapshots(
        self,
        request: market_data_pb2.GetSnapshotsRequest,
        ctx: AnyContext,
    ) -> market_data_pb2.GetSnapshotsResponse:
        """Get snapshots for multiple symbols."""
        from llamatrade_proto.generated import market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbols
        symbols = _validate_symbols(list(request.symbols))

        logger.info(
            "get_snapshots request",
            extra={"symbols": symbols, "count": len(symbols), **tenant_ctx.log_context()},
        )

        try:
            client = await get_market_data_client_async()
            snapshots_data = await client.get_multi_snapshots(symbols)

            proto_snapshots: dict[str, market_data_pb2.Snapshot] = {}
            for symbol, snapshot in snapshots_data.items():
                proto_snapshots[symbol] = self._to_proto_snapshot(symbol, snapshot)

            return market_data_pb2.GetSnapshotsResponse(snapshots=proto_snapshots)

        except Exception as e:
            logger.error("get_snapshots error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"Failed to fetch snapshots: {e}") from e

    async def get_market_status(
        self,
        request: market_data_pb2.GetMarketStatusRequest,
        ctx: AnyContext,
    ) -> market_data_pb2.GetMarketStatusResponse:
        """Get current market status from Alpaca clock API.

        Uses the Alpaca Trading API's /v2/clock endpoint for accurate
        market status that accounts for DST, holidays, and early closes.
        """
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Extract tenant context for logging (market status is public)
        tenant_ctx = _extract_tenant_context(ctx)
        logger.debug("get_market_status request", extra=tenant_ctx.log_context())

        try:
            # Clock endpoint is on trading API, not market data API
            trading_client = await get_trading_client_async()
            clock = await trading_client.get_clock()

            # Determine status from clock
            if clock.is_open:
                status = market_data_pb2.MARKET_STATUS_OPEN
            else:
                # Check if we're in pre-market or after-hours
                now = clock.timestamp
                if now < clock.next_open:
                    # Before next open - could be pre-market or closed
                    # Pre-market is typically 4:00 AM - 9:30 AM ET
                    hours_until_open = (clock.next_open - now).total_seconds() / 3600
                    if hours_until_open <= 5.5:  # Within pre-market window
                        status = market_data_pb2.MARKET_STATUS_PRE_MARKET
                    else:
                        status = market_data_pb2.MARKET_STATUS_CLOSED
                else:
                    # After close - after-hours until 8:00 PM ET typically
                    hours_since_close = (now - clock.next_close).total_seconds() / 3600
                    if hours_since_close <= 4:  # Within after-hours window
                        status = market_data_pb2.MARKET_STATUS_AFTER_HOURS
                    else:
                        status = market_data_pb2.MARKET_STATUS_CLOSED

            return market_data_pb2.GetMarketStatusResponse(
                status=status,
                next_open=common_pb2.Timestamp(
                    seconds=int(clock.next_open.timestamp()),
                    nanos=clock.next_open.microsecond * 1000,
                ),
                next_close=common_pb2.Timestamp(
                    seconds=int(clock.next_close.timestamp()),
                    nanos=clock.next_close.microsecond * 1000,
                ),
            )

        except Exception as e:
            logger.error("get_market_status error: %s", e, exc_info=True)
            raise ConnectError(Code.INTERNAL, f"Failed to fetch market status: {e}") from e

    async def stream_bars(
        self,
        request: market_data_pb2.StreamBarsRequest,
        ctx: AnyContext,
    ) -> AsyncIterator[market_data_pb2.Bar]:
        """Stream real-time bar updates."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbols
        symbols = _validate_symbols(list(request.symbols))

        logger.info(
            "Starting bar stream",
            extra={"symbols": symbols, **tenant_ctx.log_context()},
        )

        stream_manager = get_stream_manager()
        stream_id = id(ctx)

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

            while True:
                try:
                    # Wait for data with timeout for keepalive
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Only yield bar messages
                    if message.stream_type == StreamType.BAR:
                        data = cast(BarData, message.data)
                        yield market_data_pb2.Bar(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=_to_timestamp_seconds(data["timestamp"])
                            ),
                            open=common_pb2.Decimal(value=str(data["open"])),
                            high=common_pb2.Decimal(value=str(data["high"])),
                            low=common_pb2.Decimal(value=str(data["low"])),
                            close=common_pb2.Decimal(value=str(data["close"])),
                            volume=data["volume"],
                        )
                except TimeoutError:
                    # Continue waiting - client is still connected
                    continue

        except asyncio.CancelledError:
            logger.info("Bar stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed bar stream for symbols: %s", symbols)

    async def stream_quotes(
        self,
        request: market_data_pb2.StreamQuotesRequest,
        ctx: AnyContext,
    ) -> AsyncIterator[market_data_pb2.Quote]:
        """Stream real-time quote updates."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbols
        symbols = _validate_symbols(list(request.symbols))

        logger.info(
            "Starting quote stream",
            extra={"symbols": symbols, **tenant_ctx.log_context()},
        )

        stream_manager = get_stream_manager()
        stream_id = id(ctx)

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

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    if message.stream_type == StreamType.QUOTE:
                        data = cast(QuoteData, message.data)
                        yield market_data_pb2.Quote(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=_to_timestamp_seconds(data["timestamp"])
                            ),
                            bid_price=common_pb2.Decimal(value=str(data["bid_price"])),
                            bid_size=data["bid_size"],
                            ask_price=common_pb2.Decimal(value=str(data["ask_price"])),
                            ask_size=data["ask_size"],
                        )
                except TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.info("Quote stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed quote stream for symbols: %s", symbols)

    async def stream_trades(
        self,
        request: market_data_pb2.StreamTradesRequest,
        ctx: AnyContext,
    ) -> AsyncIterator[market_data_pb2.Trade]:
        """Stream real-time trade updates."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        # Extract tenant context for logging
        tenant_ctx = _extract_tenant_context(ctx)

        # Validate symbols
        symbols = _validate_symbols(list(request.symbols))

        logger.info(
            "Starting trade stream",
            extra={"symbols": symbols, **tenant_ctx.log_context()},
        )

        stream_manager = get_stream_manager()
        stream_id = id(ctx)

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

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)

                    if message.stream_type == StreamType.TRADE:
                        data = cast(TradeData, message.data)
                        yield market_data_pb2.Trade(
                            symbol=message.symbol,
                            timestamp=common_pb2.Timestamp(
                                seconds=_to_timestamp_seconds(data["timestamp"])
                            ),
                            price=common_pb2.Decimal(value=str(data["price"])),
                            size=data["size"],
                            exchange=data["exchange"],
                        )
                except TimeoutError:
                    continue

        except asyncio.CancelledError:
            logger.info("Trade stream cancelled for symbols: %s", symbols)
        finally:
            await stream_manager.disconnect(stream_id)
            logger.info("Closed trade stream for symbols: %s", symbols)

    def _to_proto_snapshot(
        self,
        symbol: str,
        snapshot: Snapshot,
    ) -> market_data_pb2.Snapshot:
        """Convert internal Snapshot to proto Snapshot."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        proto_snapshot = market_data_pb2.Snapshot(symbol=symbol)

        if snapshot.daily_bar:
            proto_snapshot.daily_bar.CopyFrom(self._bar_to_proto(symbol, snapshot.daily_bar))
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
            proto_snapshot.change_percent.CopyFrom(
                common_pb2.Decimal(value=f"{change_percent:.2f}")
            )

        return proto_snapshot

    def _bar_to_proto(self, symbol: str, bar: Bar) -> market_data_pb2.Bar:
        """Convert internal Bar to proto Bar."""
        from llamatrade_proto.generated import common_pb2, market_data_pb2

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
