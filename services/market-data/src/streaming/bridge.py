"""Bridge between Alpaca stream and StreamManager.

This module connects the Alpaca WebSocket client to the StreamManager,
routing incoming market data to subscribed clients.
"""

import asyncio
import logging
from collections import defaultdict

from src.models import BarData, QuoteData, TradeData
from src.streaming.alpaca_stream import AlpacaStreamClient
from src.streaming.manager import StreamManager

logger = logging.getLogger(__name__)


class StreamBridge:
    """Bridges Alpaca stream data to client subscriptions.

    This class:
    - Tracks aggregated subscriptions across all connected clients
    - Subscribes/unsubscribes to Alpaca based on client demand
    - Routes incoming data from Alpaca to subscribed clients
    """

    def __init__(
        self,
        alpaca_stream: AlpacaStreamClient,
        stream_manager: StreamManager,
    ):
        self._alpaca = alpaca_stream
        self._manager = stream_manager
        self._running = False
        self._run_task: asyncio.Task | None = None

        # Track symbol reference counts
        # symbol -> count of clients subscribed
        self._trade_refs: dict[str, int] = defaultdict(int)
        self._quote_refs: dict[str, int] = defaultdict(int)
        self._bar_refs: dict[str, int] = defaultdict(int)

        self._lock = asyncio.Lock()

        # Set up Alpaca callbacks
        self._alpaca.set_callbacks(
            on_trade=self._handle_trade,
            on_quote=self._handle_quote,
            on_bar=self._handle_bar,
        )

    async def start(self) -> None:
        """Start the bridge and Alpaca stream processing."""
        if self._running:
            return

        self._running = True
        self._run_task = asyncio.create_task(self._run())
        logger.info("Stream bridge started")

    async def stop(self) -> None:
        """Stop the bridge and Alpaca stream processing."""
        self._running = False

        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
            self._run_task = None

        logger.info("Stream bridge stopped")

    async def _run(self) -> None:
        """Run the Alpaca stream processing loop."""
        try:
            await self._alpaca.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Stream bridge error: {e}")

    async def add_subscriptions(
        self,
        trades: list[str] | None = None,
        quotes: list[str] | None = None,
        bars: list[str] | None = None,
    ) -> None:
        """Add subscriptions for a client.

        This is called when a client subscribes to new symbols.
        If this is the first subscription for a symbol, we subscribe to Alpaca.

        Args:
            trades: Trade symbols to add
            quotes: Quote symbols to add
            bars: Bar symbols to add
        """
        new_trades: list[str] = []
        new_quotes: list[str] = []
        new_bars: list[str] = []

        async with self._lock:
            for symbol in trades or []:
                symbol = symbol.upper()
                self._trade_refs[symbol] += 1
                if self._trade_refs[symbol] == 1:
                    new_trades.append(symbol)

            for symbol in quotes or []:
                symbol = symbol.upper()
                self._quote_refs[symbol] += 1
                if self._quote_refs[symbol] == 1:
                    new_quotes.append(symbol)

            for symbol in bars or []:
                symbol = symbol.upper()
                self._bar_refs[symbol] += 1
                if self._bar_refs[symbol] == 1:
                    new_bars.append(symbol)

        # Subscribe to Alpaca for new symbols
        if new_trades or new_quotes or new_bars:
            if self._alpaca.connected and self._alpaca.authenticated:
                await self._alpaca.subscribe(
                    trades=new_trades,
                    quotes=new_quotes,
                    bars=new_bars,
                )
                logger.debug(
                    f"Added Alpaca subscriptions: trades={new_trades}, "
                    f"quotes={new_quotes}, bars={new_bars}"
                )

    async def remove_subscriptions(
        self,
        trades: list[str] | None = None,
        quotes: list[str] | None = None,
        bars: list[str] | None = None,
    ) -> None:
        """Remove subscriptions for a client.

        This is called when a client unsubscribes from symbols.
        If this was the last subscription for a symbol, we unsubscribe from Alpaca.

        Args:
            trades: Trade symbols to remove
            quotes: Quote symbols to remove
            bars: Bar symbols to remove
        """
        remove_trades: list[str] = []
        remove_quotes: list[str] = []
        remove_bars: list[str] = []

        async with self._lock:
            for symbol in trades or []:
                symbol = symbol.upper()
                if self._trade_refs[symbol] > 0:
                    self._trade_refs[symbol] -= 1
                    if self._trade_refs[symbol] == 0:
                        remove_trades.append(symbol)
                        del self._trade_refs[symbol]

            for symbol in quotes or []:
                symbol = symbol.upper()
                if self._quote_refs[symbol] > 0:
                    self._quote_refs[symbol] -= 1
                    if self._quote_refs[symbol] == 0:
                        remove_quotes.append(symbol)
                        del self._quote_refs[symbol]

            for symbol in bars or []:
                symbol = symbol.upper()
                if self._bar_refs[symbol] > 0:
                    self._bar_refs[symbol] -= 1
                    if self._bar_refs[symbol] == 0:
                        remove_bars.append(symbol)
                        del self._bar_refs[symbol]

        # Unsubscribe from Alpaca for symbols with no clients
        if remove_trades or remove_quotes or remove_bars:
            if self._alpaca.connected:
                await self._alpaca.unsubscribe(
                    trades=remove_trades,
                    quotes=remove_quotes,
                    bars=remove_bars,
                )
                logger.debug(
                    f"Removed Alpaca subscriptions: trades={remove_trades}, "
                    f"quotes={remove_quotes}, bars={remove_bars}"
                )

    def _handle_trade(self, symbol: str, data: TradeData) -> None:
        """Handle incoming trade data from Alpaca.

        Note: This is called from asyncio.to_thread, so we need to
        schedule the async broadcast on the event loop.
        """
        asyncio.create_task(self._broadcast_trade(symbol, data))

    def _handle_quote(self, symbol: str, data: QuoteData) -> None:
        """Handle incoming quote data from Alpaca."""
        asyncio.create_task(self._broadcast_quote(symbol, data))

    def _handle_bar(self, symbol: str, data: BarData) -> None:
        """Handle incoming bar data from Alpaca."""
        asyncio.create_task(self._broadcast_bar(symbol, data))

    async def _broadcast_trade(self, symbol: str, data: TradeData) -> None:
        """Broadcast trade data to subscribed clients."""
        try:
            await self._manager.broadcast_trade(symbol, data)
        except Exception as e:
            logger.error(f"Error broadcasting trade for {symbol}: {e}")

    async def _broadcast_quote(self, symbol: str, data: QuoteData) -> None:
        """Broadcast quote data to subscribed clients."""
        try:
            await self._manager.broadcast_quote(symbol, data)
        except Exception as e:
            logger.error(f"Error broadcasting quote for {symbol}: {e}")

    async def _broadcast_bar(self, symbol: str, data: BarData) -> None:
        """Broadcast bar data to subscribed clients."""
        try:
            await self._manager.broadcast_bar(symbol, data)
        except Exception as e:
            logger.error(f"Error broadcasting bar for {symbol}: {e}")


# Global instance
_bridge: StreamBridge | None = None


def get_stream_bridge() -> StreamBridge | None:
    """Get the global stream bridge instance."""
    return _bridge


async def init_stream_bridge(
    alpaca_stream: AlpacaStreamClient,
    stream_manager: StreamManager,
) -> StreamBridge:
    """Initialize and start the stream bridge.

    Args:
        alpaca_stream: Connected Alpaca stream client
        stream_manager: StreamManager for client connections

    Returns:
        Initialized and started StreamBridge
    """
    global _bridge
    _bridge = StreamBridge(alpaca_stream, stream_manager)
    await _bridge.start()
    return _bridge


async def close_stream_bridge() -> None:
    """Stop and clean up the stream bridge."""
    global _bridge
    if _bridge:
        await _bridge.stop()
        _bridge = None
