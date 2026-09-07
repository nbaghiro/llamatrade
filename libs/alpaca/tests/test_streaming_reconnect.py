"""Tests for AlpacaWebSocketBase._reconnect (backoff, give-up, hooks, resubscribe)."""

import asyncio
from collections import deque
from collections.abc import Callable

import pytest
from websockets.exceptions import ConnectionClosed

from llamatrade_alpaca import AlpacaCredentials, BarData, MarketDataStreamClient
from llamatrade_alpaca.streaming import base as streaming_base
from llamatrade_alpaca.streaming.base import AlpacaWebSocketBase
from llamatrade_alpaca.streaming.market_data_stream import MessageType
from tests.streaming_fakes import FakeWebSocket, SleepRecorder, attach_ws, make_connect


class StubStream(AlpacaWebSocketBase):
    """Concrete stream whose connect outcomes are scripted; no network, no sleep."""

    def __init__(
        self,
        connect_results: list[bool],
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
        jitter_factor: float = 0.1,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            url="wss://test.invalid/stream",
            credentials=AlpacaCredentials(api_key="k", api_secret="s"),
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            max_reconnect_attempts=max_reconnect_attempts,
            jitter_factor=jitter_factor,
            on_reconnect=on_reconnect,
        )
        self._connect_results = deque(connect_results)
        self.connect_calls = 0
        self.resubscribe_calls = 0
        self.sleeps: list[float] = []
        self._sleep = self._record_sleep

    async def _record_sleep(self, delay: float) -> None:
        self.sleeps.append(delay)

    async def connect(self) -> bool:
        self.connect_calls += 1
        ok = self._connect_results.popleft() if self._connect_results else False
        if ok:
            self._authenticated = True
            self._reconnect_attempts = 0
        return ok

    async def _authenticate(self) -> bool:
        return True

    async def _resubscribe(self) -> None:
        self.resubscribe_calls += 1


@pytest.fixture
def upper_bound_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make jitter deterministic: random.uniform(0, x) -> x."""
    monkeypatch.setattr(streaming_base.random, "uniform", lambda a, b: b)


class TestReconnectBackoff:
    async def test_backoff_doubles_with_jitter_and_caps(self, upper_bound_jitter: None) -> None:
        stream = StubStream(
            connect_results=[False] * 5,
            reconnect_delay=1.0,
            max_reconnect_delay=4.0,
            max_reconnect_attempts=10,
            jitter_factor=0.1,
        )
        for _ in range(5):
            assert await stream._reconnect() is False

        # base 1, 2, 4, 8, 16 doubled; +10% jitter; capped at max_reconnect_delay.
        assert stream.sleeps == [
            pytest.approx(1.1),
            pytest.approx(2.2),
            pytest.approx(4.0),
            pytest.approx(4.0),
            pytest.approx(4.0),
        ]

    async def test_gives_up_after_max_attempts_without_sleeping(self) -> None:
        stream = StubStream(connect_results=[False] * 2, max_reconnect_attempts=2)
        stream._running = True

        assert await stream._reconnect() is False
        assert await stream._reconnect() is False
        assert stream._running is True

        # Third call is over the limit: no attempt, no sleep, loop told to stop.
        assert await stream._reconnect() is False
        assert stream.connect_calls == 2
        assert len(stream.sleeps) == 2
        assert stream._running is False

    async def test_on_reconnect_hook_fires_with_attempt_number(self) -> None:
        attempts_seen: list[int] = []
        holder: list[StubStream] = []

        def on_reconnect() -> None:
            attempts_seen.append(holder[0]._reconnect_attempts)

        stream = StubStream(connect_results=[False, False, True], on_reconnect=on_reconnect)
        holder.append(stream)

        await stream._reconnect()
        await stream._reconnect()
        await stream._reconnect()

        assert attempts_seen == [1, 2, 3]

    async def test_resubscribe_runs_only_after_successful_reconnect(self) -> None:
        stream = StubStream(connect_results=[False, True])

        assert await stream._reconnect() is False
        assert stream.resubscribe_calls == 0

        assert await stream._reconnect() is True
        assert stream.resubscribe_calls == 1

    async def test_successful_connect_resets_attempt_counter(self) -> None:
        stream = StubStream(connect_results=[False, True, False])

        await stream._reconnect()
        assert stream._reconnect_attempts == 1

        assert await stream._reconnect() is True
        assert stream._reconnect_attempts == 0

        # The next failure backs off from the base delay again.
        stream.sleeps.clear()
        await stream._reconnect()
        assert stream.sleeps[0] <= stream.reconnect_delay * (1 + stream.jitter_factor)


class TestRunLoopReconnects:
    async def test_run_reconnects_resubscribes_and_redispatches_after_drop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dropped connection is rebuilt by run(): auth, resubscribe, dispatch."""
        client = MarketDataStreamClient(api_key="k", api_secret="s", reconnect_delay=0.0)
        sleeper = SleepRecorder()
        client._sleep = sleeper
        attach_ws(client, FakeWebSocket([ConnectionClosed(None, None)]))
        client._authenticated = True
        client._subscribed_bars = {"AAPL"}

        received: list[tuple[str, float]] = []
        resubscribed: list[set[str]] = []

        async def on_bar(symbol: str, bar: BarData) -> None:
            received.append((symbol, bar["close"]))
            resubscribed.append(client.subscribed_symbols["bars"])
            await client.disconnect()

        client.set_callbacks(on_bar=on_bar)

        fresh = FakeWebSocket(
            [
                [{"T": MessageType.SUCCESS, "msg": "connected"}],
                [{"T": MessageType.SUCCESS}],
                [{"T": MessageType.SUBSCRIPTION, "bars": ["AAPL"]}],
                [{"T": "b", "S": "AAPL", "o": 1, "h": 2, "l": 1, "c": 3.0, "v": 5, "t": "ts"}],
            ]
        )
        monkeypatch.setattr(streaming_base.websockets, "connect", make_connect(fresh))

        await asyncio.wait_for(client.run(), timeout=1.0)

        assert received == [("AAPL", 3.0)]
        assert resubscribed == [{"AAPL"}]
        assert fresh.sent[0]["action"] == "auth"
        assert fresh.sent[1] == {"action": "subscribe", "bars": ["AAPL"]}
        assert len(sleeper.delays) == 1  # one backoff sleep for the one reconnect
