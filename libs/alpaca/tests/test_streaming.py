"""Tests for the shared Alpaca WebSocket streaming clients."""

import json
from collections import deque
from decimal import Decimal

import pytest

from llamatrade_alpaca import (
    AlpacaCredentials,
    BarStreamClient,
    MarketDataStreamClient,
    MockBarStream,
    MockTradeStream,
    StreamBar,
    TradeEventType,
    TradingStreamClient,
)
from llamatrade_alpaca.config import AlpacaUrls
from llamatrade_alpaca.streaming.base import AlpacaWebSocketBase
from llamatrade_alpaca.streaming.market_data_stream import MessageType


class FakeWebSocket:
    """Minimal stand-in for a ``websockets`` ClientConnection."""

    def __init__(self, incoming: list[object] | None = None) -> None:
        from websockets.protocol import State

        self.state = State.OPEN
        self.sent: list[dict[str, object]] = []
        self._incoming: deque[object] = deque(incoming or [])

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        if not self._incoming:
            raise AssertionError("recv called with no queued messages")
        return json.dumps(self._incoming.popleft())

    async def close(self) -> None:
        from websockets.protocol import State

        self.state = State.CLOSED

    def queue(self, message: object) -> None:
        self._incoming.append(message)


def attach_ws(client: AlpacaWebSocketBase, ws: FakeWebSocket) -> FakeWebSocket:
    """Install a FakeWebSocket on a stream client's private ``_ws`` slot.

    One typed seam (via cast) instead of per-line suppressions: the fake
    mirrors the ClientConnection surface the clients use (send/recv/close/state).
    Returns the fake so tests can assert on ``ws.sent``.
    """
    from typing import cast

    from websockets.asyncio.client import ClientConnection

    client._ws = cast(ClientConnection, ws)
    return ws


@pytest.fixture
def creds() -> AlpacaCredentials:
    return AlpacaCredentials(api_key="k", api_secret="s")


# =============================================================================
# Config
# =============================================================================


def test_stream_urls_distinguish_data_and_trade_streams() -> None:
    assert AlpacaUrls.stream_url(paper=True).startswith("wss://stream.data")
    assert AlpacaUrls.stream_url(paper=False).startswith("wss://stream.data")
    assert AlpacaUrls.trade_stream_url(paper=True) == "wss://paper-api.alpaca.markets/stream"
    assert AlpacaUrls.trade_stream_url(paper=False) == "wss://api.alpaca.markets/stream"


# =============================================================================
# Market data stream
# =============================================================================


def test_market_data_url_selected_by_paper_flag(creds: AlpacaCredentials) -> None:
    paper = MarketDataStreamClient(credentials=creds, paper=True)
    live = MarketDataStreamClient(credentials=creds, paper=False)
    assert paper.url == AlpacaUrls.STREAM_PAPER
    assert live.url == AlpacaUrls.STREAM_LIVE


def test_market_data_accepts_api_key_secret() -> None:
    client = MarketDataStreamClient(api_key="abc", api_secret="def")
    assert client.credentials.api_key == "abc"
    assert client.credentials.api_secret == "def"


def test_parse_trade_quote_bar(creds: AlpacaCredentials) -> None:
    c = MarketDataStreamClient(credentials=creds)
    trade = c._parse_trade({"p": 10.5, "s": 100, "x": "V", "t": "2024-01-01T00:00:00Z"})
    assert trade == {
        "price": 10.5,
        "size": 100,
        "exchange": "V",
        "timestamp": "2024-01-01T00:00:00Z",
    }

    quote = c._parse_quote({"bp": 1.0, "bs": 2, "ap": 3.0, "as": 4, "t": "ts"})
    assert quote == {
        "bid_price": 1.0,
        "bid_size": 2,
        "ask_price": 3.0,
        "ask_size": 4,
        "timestamp": "ts",
    }

    bar = c._parse_bar({"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 1000, "t": "ts"})
    assert bar == {
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 1000,
        "timestamp": "ts",
    }


async def test_authenticate_success_then_failure(creds: AlpacaCredentials) -> None:
    c = MarketDataStreamClient(credentials=creds)
    ws = attach_ws(
        c,
        FakeWebSocket(
            [[{"T": MessageType.SUCCESS, "msg": "connected"}], [{"T": MessageType.SUCCESS}]]
        ),
    )
    assert await c._authenticate() is True
    assert ws.sent[0] == {"action": "auth", "key": "k", "secret": "s"}

    c2 = MarketDataStreamClient(credentials=creds)
    attach_ws(
        c2, FakeWebSocket([[{"T": MessageType.SUCCESS}], [{"T": MessageType.ERROR, "msg": "bad"}]])
    )
    assert await c2._authenticate() is False


async def test_subscribe_tracks_symbols(creds: AlpacaCredentials) -> None:
    c = MarketDataStreamClient(credentials=creds)
    ws = attach_ws(c, FakeWebSocket([[{"T": MessageType.SUBSCRIPTION, "bars": ["AAPL"]}]]))
    c._authenticated = True
    ok = await c.subscribe(bars=["aapl"])
    assert ok is True
    assert "AAPL" in c.subscribed_symbols["bars"]
    assert ws.sent[0] == {"action": "subscribe", "bars": ["AAPL"]}


async def test_dispatch_invokes_callbacks(creds: AlpacaCredentials) -> None:
    c = MarketDataStreamClient(credentials=creds)
    received: list[tuple[str, dict[str, object]]] = []

    async def on_bar(symbol: str, data: dict[str, object]) -> None:
        received.append((symbol, data))

    c.set_callbacks(on_bar=on_bar)
    await c._dispatch_message(
        {"T": MessageType.BAR, "S": "AAPL", "o": 1, "h": 2, "l": 1, "c": 2, "v": 5, "t": "ts"}
    )
    assert received[0][0] == "AAPL"
    assert received[0][1]["close"] == 2.0


# =============================================================================
# Trading (account) stream
# =============================================================================


def test_trading_stream_url(creds: AlpacaCredentials) -> None:
    assert TradingStreamClient(credentials=creds, paper=True).url.endswith(
        "paper-api.alpaca.markets/stream"
    )


async def test_trading_authenticate(creds: AlpacaCredentials) -> None:
    c = TradingStreamClient(credentials=creds)
    attach_ws(c, FakeWebSocket([{"stream": "authorization", "data": {"status": "authorized"}}]))
    assert await c._authenticate() is True

    c2 = TradingStreamClient(credentials=creds)
    attach_ws(c2, FakeWebSocket([{"stream": "authorization", "data": {"status": "unauthorized"}}]))
    assert await c2._authenticate() is False


async def test_trading_subscribe(creds: AlpacaCredentials) -> None:
    c = TradingStreamClient(credentials=creds)
    ws = attach_ws(
        c, FakeWebSocket([{"stream": "listening", "data": {"streams": ["trade_updates"]}}])
    )
    c._authenticated = True
    assert await c.subscribe() is True
    assert c.subscribed is True
    assert ws.sent[0] == {
        "action": "listen",
        "data": {"streams": ["trade_updates"]},
    }


def test_parse_fill_event(creds: AlpacaCredentials) -> None:
    c = TradingStreamClient(credentials=creds)
    event = c._parse_trade_event(
        {
            "event": "fill",
            "timestamp": "2024-01-01T00:00:00Z",
            "qty": "10",
            "price": "100.5",
            "order": {
                "id": "o1",
                "client_order_id": "c1",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "qty": "10",
                "filled_qty": "10",
                "filled_avg_price": "100.5",
            },
        }
    )
    assert event is not None
    assert event.event_type == TradeEventType.FILL
    assert event.fill is not None
    assert event.fill.fill_qty == Decimal("10")
    assert event.fill.fill_price == Decimal("100.5")
    assert event.fill.remaining_qty == Decimal("0")


def test_parse_unknown_event_returns_none(creds: AlpacaCredentials) -> None:
    c = TradingStreamClient(credentials=creds)
    assert c._parse_trade_event({"event": "not_a_real_event", "order": {}}) is None


# =============================================================================
# MockTradeStream
# =============================================================================


async def test_mock_trade_stream_emits_fills() -> None:
    mock = MockTradeStream()
    assert await mock.connect() is True
    assert await mock.subscribe() is True
    mock.add_fill("o1", "AAPL", "buy", Decimal("5"), Decimal("10"))

    events = []
    async for event in mock.stream():
        events.append(event)
        await mock.disconnect()  # stop after first
        break
    assert events[0].event_type == TradeEventType.FILL
    assert events[0].symbol == "AAPL"


# =============================================================================
# Bar stream (generator-based market-data bars)
# =============================================================================


def test_bar_stream_uses_data_stream_url(creds: AlpacaCredentials) -> None:
    assert BarStreamClient(credentials=creds, paper=True).url == AlpacaUrls.STREAM_PAPER
    assert BarStreamClient(credentials=creds, paper=False).url == AlpacaUrls.STREAM_LIVE


def test_bar_stream_accepts_api_key_secret() -> None:
    c = BarStreamClient(api_key="abc", api_secret="def")
    assert c.credentials.api_key == "abc"
    assert c.credentials.api_secret == "def"


def test_parse_bar_to_streambar(creds: AlpacaCredentials) -> None:
    c = BarStreamClient(credentials=creds)
    bar = c._parse_bar(
        {
            "S": "AAPL",
            "t": "2024-01-01T00:00:00Z",
            "o": 1,
            "h": 2,
            "l": 0.5,
            "c": 1.5,
            "v": 1000,
            "vw": 1.25,
            "n": 42,
        }
    )
    assert isinstance(bar, StreamBar)
    assert bar.symbol == "AAPL"
    assert bar.close == 1.5
    assert bar.vwap == 1.25
    assert bar.trade_count == 42
    assert bar.timestamp.year == 2024


async def test_bar_stream_authenticate_and_subscribe(creds: AlpacaCredentials) -> None:
    c = BarStreamClient(credentials=creds)
    attach_ws(
        c,
        FakeWebSocket(
            [[{"T": MessageType.SUCCESS, "msg": "connected"}], [{"T": MessageType.SUCCESS}]]
        ),
    )
    assert await c._authenticate() is True

    ws = attach_ws(c, FakeWebSocket([[{"T": MessageType.SUBSCRIPTION, "bars": ["AAPL"]}]]))
    c._authenticated = True
    assert await c.subscribe(["aapl"]) is True
    assert "AAPL" in c.subscribed_symbols
    assert ws.sent[0] == {"action": "subscribe", "bars": ["AAPL"]}


async def test_mock_bar_stream_emits_bars() -> None:
    from datetime import UTC, datetime

    bar = StreamBar(
        symbol="AAPL",
        timestamp=datetime.now(UTC),
        open=1,
        high=2,
        low=0.5,
        close=1.5,
        volume=100,
    )
    mock = MockBarStream(bars={"AAPL": [bar]})
    assert await mock.connect() is True
    assert await mock.subscribe(["AAPL"]) is True

    out = []
    async for b in mock.stream():
        out.append(b)
        await mock.disconnect()
        break
    assert out[0].symbol == "AAPL"
