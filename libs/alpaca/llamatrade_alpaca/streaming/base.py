"""Base WebSocket client for Alpaca streaming APIs.

Captures the parts shared by every Alpaca stream — transport, credential
handling, connect/disconnect, JSON send/receive, and reconnection with
exponential backoff + jitter — so concrete stream clients only implement the
protocol-specific bits (authentication handshake, subscription messages, and
message parsing).

Mirrors the REST ``AlpacaClientBase`` -> ``TradingClient`` / ``MarketDataClient``
pattern, but for the ``websockets`` transport.

Subclasses implement:
    - ``_authenticate()``  -> perform the auth handshake, return success
    - ``_resubscribe()``   -> re-establish subscriptions after a reconnect
"""

import abc
import asyncio
import json
import logging
import random
from collections.abc import Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.protocol import State

from ..config import AlpacaCredentials

logger = logging.getLogger(__name__)

# If a send takes longer than this, the connection is considered stalled.
WEBSOCKET_SEND_TIMEOUT = 10.0


class AlpacaWebSocketBase(abc.ABC):
    """Shared transport/auth/reconnect for Alpaca WebSocket streams.

    Args:
        url: Fully-resolved ``wss://`` endpoint for this stream.
        credentials: Alpaca credentials (defaults to ``ALPACA_API_KEY`` /
            ``ALPACA_API_SECRET`` env vars via ``AlpacaCredentials.from_env``).
        reconnect_delay: Base delay (seconds) for exponential backoff.
        max_reconnect_delay: Upper bound (seconds) on a single backoff delay.
        max_reconnect_attempts: Give up after this many consecutive attempts.
        jitter_factor: Fractional jitter added to each backoff delay.
        on_reconnect: Optional hook fired on each reconnect attempt (metrics).
        on_connection_change: Optional hook fired with the new connected state.
    """

    def __init__(
        self,
        url: str,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
        jitter_factor: float = 0.1,
        on_reconnect: Callable[[], None] | None = None,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.url = url
        self.credentials = credentials or AlpacaCredentials.from_env(api_key, api_secret)

        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.jitter_factor = jitter_factor

        self._on_reconnect = on_reconnect
        self._on_connection_change = on_connection_change

        self._ws: ClientConnection | None = None
        self._running = False
        self._authenticated = False
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------ state

    @property
    def connected(self) -> bool:
        """Whether the underlying WebSocket is open."""
        return self._ws is not None and self._ws.state == State.OPEN

    @property
    def authenticated(self) -> bool:
        """Whether the stream completed its auth handshake."""
        return self._authenticated

    def _set_connected(self, connected: bool) -> None:
        if self._on_connection_change is not None:
            self._on_connection_change(connected)

    # ------------------------------------------------------------- lifecycle

    async def connect(self) -> bool:
        """Open the WebSocket and run the subclass auth handshake.

        Returns:
            True if connected and authenticated.
        """
        try:
            self._ws = await websockets.connect(self.url)
            logger.info(f"Connected to Alpaca stream: {self.url}")

            if not await self._authenticate():
                self._authenticated = False
                return False

            self._authenticated = True
            self._reconnect_attempts = 0
            self._set_connected(True)
            logger.info(f"Authenticated with Alpaca stream: {self.url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca stream {self.url}: {e}")
            self._set_connected(False)
            return False

    async def disconnect(self) -> None:
        """Close the WebSocket and reset state."""
        self._running = False
        self._authenticated = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._on_disconnect()
        self._set_connected(False)
        logger.info(f"Disconnected from Alpaca stream: {self.url}")

    # --------------------------------------------------------------- transport

    async def _send(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload, guarded by a stall timeout."""
        if self._ws is None:
            raise RuntimeError("Cannot send: WebSocket is not connected")
        await asyncio.wait_for(
            self._ws.send(json.dumps(payload)),
            timeout=WEBSOCKET_SEND_TIMEOUT,
        )

    async def _recv(self, timeout: float = 10.0) -> Any | None:
        """Receive and JSON-decode one message.

        Returns the parsed JSON (a ``list`` for the data stream, a ``dict`` for
        the trading stream), or ``None`` on timeout / error.
        """
        if not self._ws:
            return None
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            return json.loads(raw)
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error receiving message from {self.url}: {e}")
            return None

    # -------------------------------------------------------------- reconnect

    async def _reconnect(self) -> bool:
        """Reconnect with exponential backoff + jitter, then resubscribe."""
        if self._reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {self.url}")
            self._running = False
            return False

        self._reconnect_attempts += 1
        if self._on_reconnect is not None:
            self._on_reconnect()

        base_delay = self.reconnect_delay * (2 ** (self._reconnect_attempts - 1))
        jitter = random.uniform(0, self.jitter_factor * base_delay)
        delay = min(base_delay + jitter, self.max_reconnect_delay)

        logger.info(
            f"Reconnecting to {self.url} in {delay:.2f}s "
            f"(attempt {self._reconnect_attempts}/{self.max_reconnect_attempts})"
        )
        await asyncio.sleep(delay)

        if await self.connect():
            await self._resubscribe()
            return True
        return False

    # ----------------------------------------------------------- subclass API

    @abc.abstractmethod
    async def _authenticate(self) -> bool:
        """Perform the stream-specific auth handshake. Return success."""
        raise NotImplementedError

    @abc.abstractmethod
    async def _resubscribe(self) -> None:
        """Re-establish subscriptions after a reconnect."""
        raise NotImplementedError

    def _on_disconnect(self) -> None:
        """Hook for subclasses to clear subscription state on disconnect."""
        return None

    def _auth_payload(self) -> dict[str, str]:
        """The common Alpaca auth message body."""
        return {
            "action": "auth",
            "key": self.credentials.api_key,
            "secret": self.credentials.api_secret,
        }
