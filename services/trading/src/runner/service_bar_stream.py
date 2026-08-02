"""Live bar stream backed by the market-data service's shared fan-out.

Drop-in for ``llamatrade_alpaca.BarStreamClient`` behind the runner's ``bar_stream``
seam. Instead of each live session opening its own per-tenant Alpaca market-data
WebSocket (Alpaca allows one stream per key, so a tenant can't run two live strategies
at once, and N sessions = N connections), this consumes the market-data service's
``StreamBars`` RPC — one shared platform ingest connection fanned out to all sessions.
Per-tenant credentials stay reserved for order execution / trade-updates.

Opt-in via ``TRADING_BARS_FROM_SERVICE`` (see ``providers.build_bar_stream``); the
per-tenant Alpaca stream remains the default until paper-QA validates the swap.

Note: the service fans out 1-minute bars; the runner folds them into the strategy's
period grid (``FormingBarAggregator``), so the source resolution is not what the
strategy sees.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable

from llamatrade_alpaca import StreamBar
from llamatrade_proto.clients.market_data import MarketDataClient

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY_S = 1.0
_RECONNECT_MAX_DELAY_S = 60.0


class ServiceBarStream:
    """A ``bar_stream``-compatible adapter over the market-data ``StreamBars`` fan-out."""

    def __init__(
        self,
        target: str,
        *,
        on_reconnect: Callable[[], None] | None = None,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        self._target = target
        self._on_reconnect = on_reconnect
        self._on_connection_change = on_connection_change
        self._client: MarketDataClient | None = None
        self._symbols: list[str] = []
        self._connected = False
        self._running = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Open the client. The service RPC is per-call, so this just readies it."""
        self._client = MarketDataClient(self._target)
        self._connected = True
        if self._on_connection_change is not None:
            self._on_connection_change(True)
        return True

    async def subscribe(self, symbols: list[str]) -> bool:
        self._symbols = [s.upper() for s in symbols]
        return True

    async def disconnect(self) -> None:
        self._running = False
        self._connected = False
        if self._on_connection_change is not None:
            self._on_connection_change(False)

    async def stream(self) -> AsyncGenerator[StreamBar]:
        """Yield live bars from the service, reconnecting the RPC on drops.

        Reconnection is internal (mirroring ``BarStreamClient.stream``) so the runner's
        ``async for bar in bar_stream.stream()`` loop is unaffected by transient drops.
        """
        if self._client is None:
            await self.connect()
        assert self._client is not None
        self._running = True
        attempt = 0
        while self._running:
            try:
                async for bar in self._client.stream_bars(self._symbols, timeframe="1MIN"):
                    attempt = 0  # a delivered bar means the stream is healthy
                    yield StreamBar(
                        symbol=bar.symbol,
                        timestamp=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=int(bar.volume),
                        vwap=float(bar.vwap) if bar.vwap is not None else None,
                        trade_count=(int(bar.trade_count) if bar.trade_count is not None else None),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("service bar stream dropped; reconnecting", exc_info=True)
            if not self._running:
                break
            attempt += 1
            if self._on_reconnect is not None:
                self._on_reconnect()
            delay = min(_RECONNECT_BASE_DELAY_S * (2 ** (attempt - 1)), _RECONNECT_MAX_DELAY_S)
            await asyncio.sleep(delay)
