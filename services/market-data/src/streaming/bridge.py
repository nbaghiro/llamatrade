"""Bridge between Alpaca stream and StreamManager.

This module connects the Alpaca WebSocket client to the StreamManager,
routing incoming market data to subscribed clients.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from src.models import BarData, QuoteData, TradeData
from src.streaming.alpaca_stream import AlpacaStreamClient
from src.streaming.manager import StreamManager

logger = logging.getLogger(__name__)

# Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = 10  # Consecutive failures before opening circuit
CIRCUIT_BREAKER_RESET_TIMEOUT = 30.0  # Seconds before attempting reset


@dataclass
class BroadcastCircuitBreaker:
    """Circuit breaker for broadcast operations.

    Tracks consecutive failures and opens circuit to prevent
    continuous error logging when StreamManager is failing.
    """

    consecutive_failures: int = 0
    is_open: bool = False
    last_failure_time: float = 0.0
    total_failures: int = 0
    total_successes: int = 0

    def record_success(self) -> None:
        """Record a successful broadcast."""
        self.consecutive_failures = 0
        self.is_open = False
        self.total_successes += 1

    def record_failure(self) -> bool:
        """Record a failed broadcast.

        Returns:
            True if circuit just opened (threshold reached)
        """
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_failure_time = time.monotonic()

        if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD and not self.is_open:
            self.is_open = True
            return True
        return False

    def should_attempt(self) -> bool:
        """Check if broadcast should be attempted.

        Returns:
            True if circuit is closed or reset timeout has elapsed
        """
        if not self.is_open:
            return True

        # Check if reset timeout has elapsed
        elapsed = time.monotonic() - self.last_failure_time
        if elapsed >= CIRCUIT_BREAKER_RESET_TIMEOUT:
            logger.info("Circuit breaker reset timeout elapsed, attempting recovery")
            return True

        return False


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
        self._run_task: asyncio.Task[None] | None = None

        # Track symbol reference counts
        # symbol -> count of clients subscribed
        self._trade_refs: dict[str, int] = defaultdict(int)
        self._quote_refs: dict[str, int] = defaultdict(int)
        self._bar_refs: dict[str, int] = defaultdict(int)

        self._lock = asyncio.Lock()

        # Circuit breaker for broadcast failures
        self._circuit_breaker = BroadcastCircuitBreaker()

        # Set up Alpaca callbacks
        self._alpaca.set_callbacks(
            on_trade=self._handle_trade,
            on_quote=self._handle_quote,
            on_bar=self._handle_bar,
        )

    @property
    def circuit_breaker_status(self) -> dict[str, int | bool | float]:
        """Get circuit breaker status for monitoring."""
        return {
            "is_open": self._circuit_breaker.is_open,
            "consecutive_failures": self._circuit_breaker.consecutive_failures,
            "total_failures": self._circuit_breaker.total_failures,
            "total_successes": self._circuit_breaker.total_successes,
        }

    def clear_subscription_callbacks(self) -> None:
        """Clear subscription callbacks from the stream manager."""
        self._manager.set_subscription_callbacks(
            on_subscribe=None,
            on_unsubscribe=None,
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

    async def _handle_trade(self, symbol: str, data: TradeData) -> None:
        """Handle incoming trade data from Alpaca.

        Directly awaits the broadcast - no thread pool overhead.
        """
        await self._broadcast_trade(symbol, data)

    async def _handle_quote(self, symbol: str, data: QuoteData) -> None:
        """Handle incoming quote data from Alpaca."""
        await self._broadcast_quote(symbol, data)

    async def _handle_bar(self, symbol: str, data: BarData) -> None:
        """Handle incoming bar data from Alpaca."""
        await self._broadcast_bar(symbol, data)

    async def _broadcast_trade(self, symbol: str, data: TradeData) -> None:
        """Broadcast trade data to subscribed clients."""
        if not self._circuit_breaker.should_attempt():
            return

        try:
            await self._manager.broadcast_trade(symbol, data)
            self._circuit_breaker.record_success()
        except Exception as e:
            if self._circuit_breaker.record_failure():
                logger.error(
                    f"Circuit breaker OPEN: {self._circuit_breaker.consecutive_failures} "
                    f"consecutive broadcast failures. Last error: {e}"
                )
            else:
                logger.error(f"Error broadcasting trade for {symbol}: {e}")

    async def _broadcast_quote(self, symbol: str, data: QuoteData) -> None:
        """Broadcast quote data to subscribed clients."""
        if not self._circuit_breaker.should_attempt():
            return

        try:
            await self._manager.broadcast_quote(symbol, data)
            self._circuit_breaker.record_success()
        except Exception as e:
            if self._circuit_breaker.record_failure():
                logger.error(
                    f"Circuit breaker OPEN: {self._circuit_breaker.consecutive_failures} "
                    f"consecutive broadcast failures. Last error: {e}"
                )
            else:
                logger.error(f"Error broadcasting quote for {symbol}: {e}")

    async def _broadcast_bar(self, symbol: str, data: BarData) -> None:
        """Broadcast bar data to subscribed clients."""
        if not self._circuit_breaker.should_attempt():
            return

        try:
            await self._manager.broadcast_bar(symbol, data)
            self._circuit_breaker.record_success()
        except Exception as e:
            if self._circuit_breaker.record_failure():
                logger.error(
                    f"Circuit breaker OPEN: {self._circuit_breaker.consecutive_failures} "
                    f"consecutive broadcast failures. Last error: {e}"
                )
            else:
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

    # Wire up subscription callbacks so manager notifies bridge of changes
    stream_manager.set_subscription_callbacks(
        on_subscribe=_bridge.add_subscriptions,
        on_unsubscribe=_bridge.remove_subscriptions,
    )

    await _bridge.start()
    return _bridge


async def close_stream_bridge() -> None:
    """Stop and clean up the stream bridge."""
    global _bridge
    if _bridge:
        # Clear subscription callbacks before stopping
        _bridge.clear_subscription_callbacks()
        await _bridge.stop()
        _bridge = None
