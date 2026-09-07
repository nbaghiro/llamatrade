"""Tests for the shared Alpaca WebSocket streaming clients."""

import asyncio
import inspect
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from llamatrade_alpaca import (
    AlpacaCredentials,
    BarData,
    BarStreamClient,
    MarketDataStreamClient,
    MockBarStream,
    MockTradeStream,
    QuoteData,
    StreamBar,
    TradeData,
    TradeEvent,
    TradeEventType,
    TradingStreamClient,
)
from llamatrade_alpaca.config import AlpacaUrls
from llamatrade_alpaca.streaming import base as streaming_base
from llamatrade_alpaca.streaming import market_data_stream as mds_module
from llamatrade_alpaca.streaming.market_data_stream import (
    MessageType,
    close_market_data_stream,
    get_market_data_stream,
    init_market_data_stream,
)
from tests.streaming_fakes import (
    FakeWebSocket,
    SleepRecorder,
    StuckOpenWebSocket,
    attach_ws,
    make_connect,
    refuse_connect,
)


def _fill_msg(order_id: str) -> dict[str, object]:
    return {
        "stream": "trade_updates",
        "data": {
            "event": "fill",
            "timestamp": "2024-01-01T00:00:00Z",
            "qty": "10",
            "price": "100.5",
            "order": {
                "id": order_id,
                "client_order_id": f"c-{order_id}",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "qty": "10",
                "filled_qty": "10",
                "filled_avg_price": "100.5",
            },
        },
    }


def _bar_item(symbol: str, close: float) -> dict[str, object]:
    return {
        "T": "b",
        "S": symbol,
        "t": "2024-01-01T00:00:00Z",
        "o": 1,
        "h": 2,
        "l": 0.5,
        "c": close,
        "v": 100,
    }


def _stream_bar(symbol: str, close: float) -> StreamBar:
    return StreamBar(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def _trade_event(order_id: str) -> TradeEvent:
    return TradeEvent(
        event_type=TradeEventType.FILL,
        order_id=order_id,
        client_order_id="",
        symbol="AAPL",
        side="buy",
        order_type="market",
        qty=Decimal("1"),
        filled_qty=Decimal("1"),
        filled_avg_price=Decimal("10"),
        timestamp=datetime.now(UTC),
    )


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

    c.set_callbacks(on_bar=cast(Any, on_bar))
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


# =============================================================================
# TradingStreamClient.stream() — the real run loop over FakeWebSocket
# =============================================================================


class TestTradingStreamLoop:
    async def test_yields_events_and_skips_non_trade_messages(
        self, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(credentials=creds)
        attach_ws(
            client,
            FakeWebSocket(
                [
                    {"stream": "listening", "data": {"streams": ["trade_updates"]}},
                    _fill_msg("o1"),
                    {"stream": "trade_updates", "data": {"event": "not_a_real_event"}},
                    _fill_msg("o2"),
                ]
            ),
        )
        client._authenticated = True

        gen = client.stream()
        first = await anext(gen)
        second = await anext(gen)
        await gen.aclose()

        assert [first.order_id, second.order_id] == ["o1", "o2"]
        assert first.event_type == TradeEventType.FILL

    async def test_connects_from_cold_start(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(credentials=creds, reconnect_delay=0.0, jitter_factor=0.0)
        client._sleep = SleepRecorder()
        ws = FakeWebSocket(
            [
                {"stream": "authorization", "data": {"status": "authorized"}},
                {"stream": "listening", "data": {"streams": ["trade_updates"]}},
                _fill_msg("o-cold"),
            ]
        )
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(ws))

        gen = client.stream()
        event = await anext(gen)
        await gen.aclose()

        assert event.order_id == "o-cold"
        assert client.authenticated is True
        assert client.subscribed is True
        assert ws.sent[0]["action"] == "auth"
        assert ws.sent[1] == {"action": "listen", "data": {"streams": ["trade_updates"]}}

    async def test_reconnects_and_resubscribes_after_drop(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(credentials=creds, reconnect_delay=0.0, jitter_factor=0.0)
        sleeper = SleepRecorder()
        client._sleep = sleeper
        attach_ws(client, FakeWebSocket([ConnectionClosed(None, None)]))
        client._authenticated = True

        fresh = FakeWebSocket(
            [
                {"stream": "authorization", "data": {"status": "authorized"}},
                {"stream": "listening", "data": {"streams": ["trade_updates"]}},
                _fill_msg("o-after-reconnect"),
            ]
        )
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(fresh))

        gen = client.stream()
        event = await anext(gen)
        await gen.aclose()

        assert event.order_id == "o-after-reconnect"
        assert client.subscribed is True
        assert fresh.sent[1] == {"action": "listen", "data": {"streams": ["trade_updates"]}}
        assert len(sleeper.delays) == 1  # one backoff sleep for the one reconnect
        assert client._reconnect_attempts == 0  # reset by the successful reconnect

    async def test_gives_up_and_exhausts_when_reconnect_fails(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(
            credentials=creds,
            reconnect_delay=0.0,
            jitter_factor=0.0,
            max_reconnect_attempts=1,
        )
        client._sleep = SleepRecorder()
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        # The failed attempt ends the generator without yielding.
        assert [e async for e in client.stream()] == []
        # Attempts exhausted: the next stream() ends immediately with no new attempt.
        assert [e async for e in client.stream()] == []
        assert client._running is False
        assert client.connected is False


# =============================================================================
# BarStreamClient.stream() — the real run loop over FakeWebSocket
# =============================================================================


class TestBarStreamLoop:
    async def test_yields_bars_and_survives_error_items(self, creds: AlpacaCredentials) -> None:
        client = BarStreamClient(credentials=creds)
        attach_ws(
            client,
            FakeWebSocket(
                [[_bar_item("AAPL", 1.5), {"T": "error", "msg": "bad"}, _bar_item("MSFT", 2.5)]]
            ),
        )
        client._authenticated = True

        gen = client.stream()
        first = await anext(gen)
        second = await anext(gen)
        await gen.aclose()

        assert (first.symbol, first.close) == ("AAPL", 1.5)
        assert (second.symbol, second.close) == ("MSFT", 2.5)

    async def test_reconnects_and_resubscribes_after_drop(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = BarStreamClient(credentials=creds, reconnect_delay=0.0, jitter_factor=0.0)
        client._sleep = SleepRecorder()
        attach_ws(client, FakeWebSocket([ConnectionClosed(None, None)]))
        client._authenticated = True
        client._subscribed_symbols = {"AAPL"}

        fresh = FakeWebSocket(
            [
                [{"T": MessageType.SUCCESS, "msg": "connected"}],
                [{"T": MessageType.SUCCESS}],
                [{"T": MessageType.SUBSCRIPTION, "bars": ["AAPL"]}],
                [_bar_item("AAPL", 3.0)],
            ]
        )
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(fresh))

        gen = client.stream()
        bar = await anext(gen)
        await gen.aclose()

        assert bar.close == 3.0
        assert client.subscribed_symbols == {"AAPL"}
        assert fresh.sent[0]["action"] == "auth"
        assert fresh.sent[1] == {"action": "subscribe", "bars": ["AAPL"]}

    async def test_gives_up_and_exhausts_when_reconnect_fails(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = BarStreamClient(
            credentials=creds,
            reconnect_delay=0.0,
            jitter_factor=0.0,
            max_reconnect_attempts=1,
        )
        client._sleep = SleepRecorder()
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        assert [b async for b in client.stream()] == []
        assert [b async for b in client.stream()] == []
        assert client._running is False


# =============================================================================
# MarketDataStreamClient.run() — message pump to callback dispatch
# =============================================================================


class TestMarketDataRunLoop:
    async def test_run_pumps_batches_to_callbacks(self, creds: AlpacaCredentials) -> None:
        client = MarketDataStreamClient(credentials=creds)
        received: list[tuple[str, str, float]] = []

        async def on_trade(symbol: str, trade: TradeData) -> None:
            received.append(("trade", symbol, trade["price"]))

        async def on_quote(symbol: str, quote: QuoteData) -> None:
            received.append(("quote", symbol, quote["ask_price"]))

        async def on_bar(symbol: str, bar: BarData) -> None:
            received.append(("bar", symbol, bar["close"]))
            await client.disconnect()  # last item: stop the pump

        client.set_callbacks(on_trade=on_trade, on_quote=on_quote, on_bar=on_bar)
        attach_ws(
            client,
            FakeWebSocket(
                [
                    [
                        {"T": MessageType.SUCCESS, "msg": "connected"},
                        {"T": "t", "S": "AAPL", "p": 10.5, "s": 100, "x": "V", "t": "ts"},
                        {"T": "q", "S": "MSFT", "bp": 1.0, "bs": 2, "ap": 3.0, "as": 4, "t": "ts"},
                        {"T": "error", "msg": "bad"},
                        {"T": "b", "S": "TSLA", "o": 1, "h": 2, "l": 1, "c": 2, "v": 5, "t": "ts"},
                    ]
                ]
            ),
        )
        client._authenticated = True

        await asyncio.wait_for(client.run(), timeout=1.0)

        assert received == [
            ("trade", "AAPL", 10.5),
            ("quote", "MSFT", 3.0),
            ("bar", "TSLA", 2.0),
        ]

    async def test_run_returns_when_reconnect_gives_up(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = MarketDataStreamClient(
            credentials=creds, reconnect_delay=0.0, max_reconnect_attempts=1
        )
        client._sleep = SleepRecorder()
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        await asyncio.wait_for(client.run(), timeout=1.0)

        assert client.connected is False


# =============================================================================
# MockTradeStream give-up (exhaustion) mode
# =============================================================================


class TestMockTradeStreamGiveUp:
    async def test_give_up_exhausts_active_stream(self) -> None:
        mock = MockTradeStream()
        await mock.connect()
        await mock.subscribe()
        mock.add_fill("o1", "AAPL", "buy", Decimal("5"), Decimal("10"))

        received: list[TradeEvent] = []

        async def consume() -> None:
            async for event in mock.stream():
                received.append(event)

        task = asyncio.create_task(consume())
        async with asyncio.timeout(1.0):
            while not received:
                await asyncio.sleep(0.001)

        mock.give_up()
        await asyncio.wait_for(task, timeout=1.0)  # the async for ended by itself

        assert [e.order_id for e in received] == ["o1"]
        assert mock.gave_up is True
        assert mock.connected is False
        assert mock.subscribed is False

    async def test_give_up_before_stream_yields_nothing(self) -> None:
        mock = MockTradeStream(events=[_trade_event("preloaded")])
        await mock.connect()
        mock.give_up()

        assert [e async for e in mock.stream()] == []
        assert mock.gave_up is True

    async def test_reconnect_after_give_up_streams_again(self) -> None:
        mock = MockTradeStream()
        await mock.connect()
        await mock.subscribe()
        mock.give_up()
        assert [e async for e in mock.stream()] == []

        assert await mock.connect() is True
        assert mock.gave_up is False
        assert await mock.subscribe() is True
        mock.add_fill("o2", "MSFT", "sell", Decimal("1"), Decimal("20"))

        received: list[TradeEvent] = []
        async for event in mock.stream():
            received.append(event)
            await mock.disconnect()
            break

        assert received[0].order_id == "o2"

    async def test_models_connected_but_unauthenticated(self) -> None:
        mock = MockTradeStream()
        await mock.connect()
        assert mock.connected is True
        assert mock.authenticated is True

        mock._authenticated = False
        assert mock.connected is True
        assert mock.authenticated is False


# =============================================================================
# Unsubscribe paths
# =============================================================================


class TestMarketDataUnsubscribe:
    async def test_unsubscribe_discards_confirmed_symbols(self, creds: AlpacaCredentials) -> None:
        c = MarketDataStreamClient(credentials=creds)
        c._subscribed_trades = {"AAPL"}
        c._subscribed_quotes = {"MSFT"}
        c._subscribed_bars = {"TSLA"}
        ws = attach_ws(c, FakeWebSocket([[{"T": MessageType.SUBSCRIPTION}]]))
        c._authenticated = True

        assert await c.unsubscribe(trades=["aapl"], quotes=["msft"], bars=["tsla"]) is True
        assert c.subscribed_symbols == {"trades": set(), "quotes": set(), "bars": set()}
        assert ws.sent[0] == {
            "action": "unsubscribe",
            "trades": ["AAPL"],
            "quotes": ["MSFT"],
            "bars": ["TSLA"],
        }

    async def test_unsubscribe_disconnected_is_noop_success(self, creds: AlpacaCredentials) -> None:
        c = MarketDataStreamClient(credentials=creds)
        assert await c.unsubscribe(bars=["AAPL"]) is True

    async def test_unsubscribe_with_no_symbols_sends_nothing(
        self, creds: AlpacaCredentials
    ) -> None:
        c = MarketDataStreamClient(credentials=creds)
        ws = attach_ws(c, FakeWebSocket())
        assert await c.unsubscribe() is True
        assert ws.sent == []

    async def test_unsubscribe_failure_reply_keeps_subscriptions(
        self, creds: AlpacaCredentials
    ) -> None:
        c = MarketDataStreamClient(credentials=creds)
        c._subscribed_bars = {"AAPL"}
        attach_ws(c, FakeWebSocket([[{"T": MessageType.ERROR, "msg": "no"}]]))

        assert await c.unsubscribe(bars=["AAPL"]) is False
        assert c.subscribed_symbols["bars"] == {"AAPL"}


class TestBarStreamUnsubscribe:
    async def test_unsubscribe_all_when_no_symbols_given(self, creds: AlpacaCredentials) -> None:
        c = BarStreamClient(credentials=creds)
        c._subscribed_symbols = {"AAPL", "MSFT"}
        ws = attach_ws(c, FakeWebSocket([[{"T": MessageType.SUBSCRIPTION, "bars": []}]]))

        assert await c.unsubscribe() is True
        assert c.subscribed_symbols == set()
        sent = ws.sent[0]
        assert sent["action"] == "unsubscribe"
        assert set(cast(list[str], sent["bars"])) == {"AAPL", "MSFT"}

    async def test_unsubscribe_specific_symbols(self, creds: AlpacaCredentials) -> None:
        c = BarStreamClient(credentials=creds)
        c._subscribed_symbols = {"AAPL", "MSFT"}
        attach_ws(c, FakeWebSocket([[{"T": MessageType.SUBSCRIPTION, "bars": ["MSFT"]}]]))

        assert await c.unsubscribe(["aapl"]) is True
        assert c.subscribed_symbols == {"MSFT"}

    async def test_unsubscribe_disconnected_or_empty_is_noop_success(
        self, creds: AlpacaCredentials
    ) -> None:
        c = BarStreamClient(credentials=creds)
        assert await c.unsubscribe(["AAPL"]) is True  # not connected

        ws = attach_ws(c, FakeWebSocket())
        assert await c.unsubscribe() is True  # nothing subscribed
        assert ws.sent == []

    async def test_unsubscribe_failure_reply_keeps_subscriptions(
        self, creds: AlpacaCredentials
    ) -> None:
        c = BarStreamClient(credentials=creds)
        c._subscribed_symbols = {"AAPL"}
        attach_ws(c, FakeWebSocket([[{"T": MessageType.ERROR, "msg": "no"}]]))

        assert await c.unsubscribe(["AAPL"]) is False
        assert c.subscribed_symbols == {"AAPL"}


# =============================================================================
# Market-data stream singletons
# =============================================================================


class TestMarketDataStreamSingletons:
    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> Iterator[None]:
        mds_module._stream_client = None
        mds_module._stream_lock = None
        yield
        mds_module._stream_client = None
        mds_module._stream_lock = None

    def test_get_creates_then_caches(self) -> None:
        first = get_market_data_stream()
        assert isinstance(first, MarketDataStreamClient)
        assert get_market_data_stream() is first

    async def test_init_failed_connect_clears_singleton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        assert await init_market_data_stream() is None
        assert mds_module._stream_client is None

    async def test_init_reuses_connected_client(self) -> None:
        existing = MarketDataStreamClient(api_key="k", api_secret="s")
        attach_ws(existing, FakeWebSocket())
        mds_module._stream_client = existing

        assert await init_market_data_stream() is existing

    async def test_init_connects_new_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ws = FakeWebSocket(
            [[{"T": MessageType.SUCCESS, "msg": "connected"}], [{"T": MessageType.SUCCESS}]]
        )
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(ws))

        client = await init_market_data_stream()

        assert client is not None
        assert client.connected is True
        assert client.authenticated is True
        assert mds_module._stream_client is client

    async def test_close_disconnects_and_clears(self) -> None:
        client = MarketDataStreamClient(api_key="k", api_secret="s")
        ws = attach_ws(client, FakeWebSocket())
        client._authenticated = True
        mds_module._stream_client = client

        await close_market_data_stream()

        assert mds_module._stream_client is None
        assert ws.state == State.CLOSED
        assert client.authenticated is False

    async def test_close_when_absent_is_noop(self) -> None:
        await close_market_data_stream()
        assert mds_module._stream_client is None


# =============================================================================
# on_connection_change hook
# =============================================================================


class TestConnectionChangeHook:
    async def test_fires_true_on_connect_and_false_on_disconnect(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        states: list[bool] = []
        client = TradingStreamClient(credentials=creds, on_connection_change=states.append)
        ws = FakeWebSocket([{"stream": "authorization", "data": {"status": "authorized"}}])
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(ws))

        assert await client.connect() is True
        assert states == [True]

        await client.disconnect()
        assert states == [True, False]

    async def test_fires_false_on_failed_connect(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        states: list[bool] = []
        client = TradingStreamClient(credentials=creds, on_connection_change=states.append)
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        assert await client.connect() is False
        assert states == [False]


# =============================================================================
# ConnectionClosed recovery (base._recv re-raises so run loops recover explicitly)
# =============================================================================


class TestConnectionClosedRecovery:
    """The run loops' ConnectionClosed handlers drive recovery even when the
    transport still reports OPEN — recovery must not depend on the state flag."""

    async def test_market_data_run_recovers_when_state_stays_open(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = MarketDataStreamClient(
            credentials=creds, reconnect_delay=0.0, max_reconnect_attempts=1
        )
        client._sleep = SleepRecorder()
        attach_ws(client, StuckOpenWebSocket())
        client._authenticated = True
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        await asyncio.wait_for(client.run(), timeout=1.0)

        assert client._ws is None  # the handler cleared the stale socket
        assert client.authenticated is False

    async def test_trading_stream_recovers_when_state_stays_open(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(
            credentials=creds, reconnect_delay=0.0, jitter_factor=0.0, max_reconnect_attempts=1
        )
        client._sleep = SleepRecorder()
        attach_ws(client, StuckOpenWebSocket())
        client._authenticated = True
        client._subscribed = True
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        async with asyncio.timeout(1.0):
            events = [e async for e in client.stream()]

        assert events == []
        assert client._ws is None
        assert client.subscribed is False

    async def test_bar_stream_recovers_when_state_stays_open(
        self, monkeypatch: pytest.MonkeyPatch, creds: AlpacaCredentials
    ) -> None:
        client = BarStreamClient(
            credentials=creds, reconnect_delay=0.0, jitter_factor=0.0, max_reconnect_attempts=1
        )
        client._sleep = SleepRecorder()
        attach_ws(client, StuckOpenWebSocket())
        client._authenticated = True
        monkeypatch.setattr(streaming_base.websockets, "connect", refuse_connect)

        async with asyncio.timeout(1.0):
            bars = [b async for b in client.stream()]

        assert bars == []
        assert client._ws is None
        assert client.authenticated is False


# =============================================================================
# Dispatch/parse error pacing (the 1s sleep in the generic exception handlers)
# =============================================================================


class TestDispatchErrorPacing:
    async def test_raising_callback_is_paced_and_loop_survives(
        self, creds: AlpacaCredentials
    ) -> None:
        client = MarketDataStreamClient(credentials=creds)
        sleeper = SleepRecorder()
        client._sleep = sleeper
        seen: list[float] = []

        async def on_trade(symbol: str, trade: TradeData) -> None:
            if not seen:
                seen.append(trade["price"])
                raise RuntimeError("callback boom")
            seen.append(trade["price"])
            await client.disconnect()

        client.set_callbacks(on_trade=on_trade)
        trade1 = {"T": "t", "S": "AAPL", "p": 1.0, "s": 1, "x": "V", "t": "ts"}
        trade2 = {"T": "t", "S": "AAPL", "p": 2.0, "s": 1, "x": "V", "t": "ts"}
        attach_ws(client, FakeWebSocket([[trade1], [trade2]]))
        client._authenticated = True

        await asyncio.wait_for(client.run(), timeout=1.0)

        assert seen == [1.0, 2.0]
        assert sleeper.delays == [1.0]

    async def test_malformed_batch_item_is_paced_in_bar_stream(
        self, creds: AlpacaCredentials
    ) -> None:
        client = BarStreamClient(credentials=creds)
        sleeper = SleepRecorder()
        client._sleep = sleeper
        attach_ws(client, FakeWebSocket([[42], [_bar_item("AAPL", 1.5)]]))
        client._authenticated = True

        gen = client.stream()
        bar = await asyncio.wait_for(anext(gen), timeout=1.0)
        await gen.aclose()

        assert (bar.symbol, bar.close) == ("AAPL", 1.5)
        assert sleeper.delays == [1.0]

    async def test_malformed_message_is_paced_in_trade_stream(
        self, creds: AlpacaCredentials
    ) -> None:
        client = TradingStreamClient(credentials=creds)
        sleeper = SleepRecorder()
        client._sleep = sleeper
        attach_ws(client, FakeWebSocket([["wrong-shape"], _fill_msg("o1")]))
        client._authenticated = True

        gen = client.stream()
        event = await asyncio.wait_for(anext(gen), timeout=1.0)
        await gen.aclose()

        assert event.order_id == "o1"
        assert sleeper.delays == [1.0]


# =============================================================================
# Fake/mock fidelity contracts
# =============================================================================


def _param_shape(fn: Callable[..., object]) -> list[tuple[str, object, object]]:
    return [(p.name, p.kind, p.default) for p in inspect.signature(fn).parameters.values()]


class TestFakeWebSocketContract:
    """Pin FakeWebSocket's four members to the real ClientConnection surface."""

    @pytest.mark.parametrize(
        ("member", "args"),
        [("send", ("payload",)), ("recv", ()), ("close", ())],
    )
    def test_lib_call_shapes_bind_on_real_and_fake(
        self, member: str, args: tuple[object, ...]
    ) -> None:
        for cls in (ClientConnection, FakeWebSocket):
            sig = inspect.signature(getattr(cls, member))
            sig.bind(object(), *args)  # raises TypeError on drift

    def test_state_exposed_on_both(self) -> None:
        assert isinstance(inspect.getattr_static(ClientConnection, "state"), property)
        assert FakeWebSocket().state is State.OPEN


class TestMockStreamContract:
    """Pin the in-memory mocks to their real clients' surfaces."""

    @pytest.mark.parametrize(
        ("real_cls", "mock_cls", "methods", "props"),
        [
            (
                BarStreamClient,
                MockBarStream,
                ["connect", "disconnect", "subscribe", "unsubscribe", "stream"],
                ["connected", "authenticated", "subscribed_symbols"],
            ),
            (
                TradingStreamClient,
                MockTradeStream,
                ["connect", "disconnect", "subscribe", "stream"],
                ["connected", "authenticated", "subscribed"],
            ),
        ],
    )
    def test_mock_matches_real_surface(
        self,
        real_cls: type[object],
        mock_cls: type[object],
        methods: list[str],
        props: list[str],
    ) -> None:
        for name in methods:
            assert _param_shape(getattr(mock_cls, name)) == _param_shape(getattr(real_cls, name)), (
                name
            )
        for name in props:
            assert isinstance(inspect.getattr_static(mock_cls, name), property), name
            assert hasattr(real_cls, name), name


class TestMockBarStreamFidelity:
    async def test_connected_tracks_lifecycle(self) -> None:
        mock = MockBarStream()
        assert mock.connected is False
        assert mock.authenticated is False
        assert await mock.subscribe(["AAPL"]) is False  # refuses while disconnected

        assert await mock.connect() is True
        assert mock.connected is True
        assert mock.authenticated is True
        assert await mock.subscribe(["AAPL"]) is True

        await mock.disconnect()
        assert mock.connected is False
        assert mock.authenticated is False

    async def test_give_up_ends_active_stream_and_clears_state(self) -> None:
        bars = [_stream_bar("AAPL", float(i)) for i in range(50)]
        mock = MockBarStream(bars={"AAPL": bars})
        await mock.connect()
        await mock.subscribe(["AAPL"])

        received: list[StreamBar] = []
        async with asyncio.timeout(1.0):
            async for bar in mock.stream():
                received.append(bar)
                mock.give_up()

        assert len(received) == 1
        assert mock.gave_up is True
        assert mock.connected is False
        assert mock.authenticated is False
        assert mock.subscribed_symbols == set()

    async def test_give_up_before_stream_yields_nothing(self) -> None:
        mock = MockBarStream(bars={"AAPL": [_stream_bar("AAPL", 1.0)]})
        await mock.connect()
        await mock.subscribe(["AAPL"])
        mock.give_up()

        assert [b async for b in mock.stream()] == []
        assert mock.gave_up is True

    async def test_reconnect_after_give_up_streams_again(self) -> None:
        mock = MockBarStream(bars={"AAPL": [_stream_bar("AAPL", 1.0)]})
        await mock.connect()
        await mock.subscribe(["AAPL"])
        mock.give_up()
        assert [b async for b in mock.stream()] == []

        assert await mock.connect() is True
        assert mock.gave_up is False
        assert await mock.subscribe(["AAPL"]) is True

        received = [b async for b in mock.stream()]
        assert [b.close for b in received] == [1.0]
