"""Shared WebSocket fakes for the streaming test suites."""

import json
from collections import deque
from collections.abc import Callable, Coroutine
from typing import cast

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from llamatrade_alpaca.streaming.base import AlpacaWebSocketBase


class FakeWebSocket:
    """Minimal stand-in for a ``websockets`` ClientConnection.

    Queue an Exception instance to have ``recv`` raise it; a queued
    ``ConnectionClosed`` also flips the socket state to CLOSED, scripting a
    connection drop the way the real transport reports one.
    """

    def __init__(self, incoming: list[object] | None = None) -> None:
        self.state = State.OPEN
        self.sent: list[dict[str, object]] = []
        self._incoming: deque[object] = deque(incoming or [])

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        if not self._incoming:
            raise AssertionError("recv called with no queued messages")
        item = self._incoming.popleft()
        if isinstance(item, Exception):
            if isinstance(item, ConnectionClosed):
                self.state = State.CLOSED
            raise item
        return json.dumps(item)

    async def close(self) -> None:
        self.state = State.CLOSED

    def queue(self, message: object) -> None:
        self._incoming.append(message)


class StuckOpenWebSocket(FakeWebSocket):
    """``recv`` raises ConnectionClosed while the state flag stays OPEN.

    Pins that run-loop recovery is driven by the ConnectionClosed handler
    itself, not by the transport's state flag.
    """

    async def recv(self) -> str:
        raise ConnectionClosed(None, None)


def attach_ws(client: AlpacaWebSocketBase, ws: FakeWebSocket) -> FakeWebSocket:
    """Install a FakeWebSocket on a stream client's private ``_ws`` slot.

    One typed seam (via cast) instead of per-line suppressions: the fake
    mirrors the ClientConnection surface the clients use (send/recv/close/state).
    Returns the fake so tests can assert on ``ws.sent``.
    """
    client._ws = cast(ClientConnection, ws)
    return ws


class SleepRecorder:
    """Injectable ``_sleep`` that records delays instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_connect(ws: FakeWebSocket) -> Callable[[str], Coroutine[object, object, FakeWebSocket]]:
    """A ``websockets.connect`` stand-in handing out ``ws``."""

    async def _connect(url: str) -> FakeWebSocket:
        return ws

    return _connect


async def refuse_connect(url: str) -> FakeWebSocket:
    raise OSError("connection refused")
