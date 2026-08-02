"""Tests for Connect streaming in the market-data service.

Drives the real servicer stream methods against a fresh StreamManager: the
generator is consumed in a task, data is injected via manager broadcasts, and
cancellation exercises the cleanup path.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import cast

import pytest
from connectrpc.request import RequestContext

from llamatrade_proto.generated import market_data_pb2

from src.grpc.servicer import MarketDataServicer
from src.models import BarData, QuoteData, TradeData
from src.streaming.manager import StreamManager, StreamMessage, StreamType


def _ctx() -> RequestContext[object, object]:
    """A stand-in Connect context: the servicer only uses it for identity (id())."""
    return cast(RequestContext[object, object], object())


_TS = "2026-01-05T15:00:00+00:00"
_TS_SECONDS = 1767625200

_BAR: BarData = {
    "timestamp": _TS,
    "open": 150.0,
    "high": 151.0,
    "low": 149.0,
    "close": 150.5,
    "volume": 1000,
}
_QUOTE: QuoteData = {
    "timestamp": _TS,
    "bid_price": 150.0,
    "bid_size": 100,
    "ask_price": 150.1,
    "ask_size": 200,
}
_TRADE: TradeData = {
    "timestamp": _TS,
    "price": 150.25,
    "size": 100,
    "exchange": "NASDAQ",
}


async def _wait_until(condition: Callable[[], bool], timeout: float = 1.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=timeout)


async def _consume[T](stream: AsyncIterator[T], out: list[T]) -> None:
    async for item in stream:
        out.append(item)


async def _cancel(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
        await asyncio.wait_for(task, timeout=1.0)


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> StreamManager:
    """A fresh StreamManager wired into the servicer module."""
    fresh = StreamManager()
    monkeypatch.setattr("src.grpc.servicer.get_stream_manager", lambda: fresh)
    return fresh


@pytest.fixture
def servicer() -> MarketDataServicer:
    return MarketDataServicer()


class TestStreamBars:
    async def test_subscribes_normalized_symbols_and_yields_bars(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        request = market_data_pb2.StreamBarsRequest(symbols=["aapl", "tsla"])
        out: list[market_data_pb2.Bar] = []
        task = asyncio.create_task(_consume(servicer.stream_bars(request, _ctx()), out))

        try:
            await _wait_until(lambda: manager.connection_count == 1)
            assert manager.subscribed_symbols["bars"] == {"AAPL", "TSLA"}

            await manager.broadcast_bar("AAPL", _BAR)
            await _wait_until(lambda: len(out) == 1)

            bar = out[0]
            assert bar.symbol == "AAPL"
            assert bar.timestamp.seconds == _TS_SECONDS
            assert bar.open.value == "150.0"
            assert bar.close.value == "150.5"
            assert bar.volume == 1000
        finally:
            await _cancel(task)

    async def test_cancel_disconnects_and_unsubscribes(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        request = market_data_pb2.StreamBarsRequest(symbols=["AAPL"])
        out: list[market_data_pb2.Bar] = []
        task = asyncio.create_task(_consume(servicer.stream_bars(request, _ctx()), out))

        await _wait_until(lambda: manager.connection_count == 1)
        await _cancel(task)

        assert manager.connection_count == 0
        assert "AAPL" not in manager.subscribed_symbols["bars"]

    async def test_invalid_symbol_rejected_before_connecting(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        from connectrpc.errors import ConnectError

        request = market_data_pb2.StreamBarsRequest(symbols=["not a symbol"])
        with pytest.raises(ConnectError):
            async for _ in servicer.stream_bars(request, _ctx()):
                pass

        assert manager.connection_count == 0


class TestStreamQuotes:
    async def test_subscribes_and_yields_quotes(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        request = market_data_pb2.StreamQuotesRequest(symbols=["AAPL"])
        out: list[market_data_pb2.Quote] = []
        task = asyncio.create_task(_consume(servicer.stream_quotes(request, _ctx()), out))

        try:
            await _wait_until(lambda: manager.connection_count == 1)
            assert manager.subscribed_symbols["quotes"] == {"AAPL"}

            await manager.broadcast_quote("AAPL", _QUOTE)
            await _wait_until(lambda: len(out) == 1)

            quote = out[0]
            assert quote.symbol == "AAPL"
            assert quote.bid_price.value == "150.0"
            assert quote.ask_price.value == "150.1"
            assert quote.bid_size == 100
            assert quote.ask_size == 200
        finally:
            await _cancel(task)

        assert manager.connection_count == 0
        assert "AAPL" not in manager.subscribed_symbols["quotes"]


class TestStreamTrades:
    async def test_subscribes_and_yields_trades(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        request = market_data_pb2.StreamTradesRequest(symbols=["AAPL"])
        out: list[market_data_pb2.Trade] = []
        task = asyncio.create_task(_consume(servicer.stream_trades(request, _ctx()), out))

        try:
            await _wait_until(lambda: manager.connection_count == 1)
            assert manager.subscribed_symbols["trades"] == {"AAPL"}

            await manager.broadcast_trade("AAPL", _TRADE)
            await _wait_until(lambda: len(out) == 1)

            trade = out[0]
            assert trade.symbol == "AAPL"
            assert trade.price.value == "150.25"
            assert trade.size == 100
            assert trade.exchange == "NASDAQ"
        finally:
            await _cancel(task)

    async def test_ignores_non_trade_messages(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        request = market_data_pb2.StreamTradesRequest(symbols=["AAPL"])
        out: list[market_data_pb2.Trade] = []
        task = asyncio.create_task(_consume(servicer.stream_trades(request, _ctx()), out))

        try:
            await _wait_until(lambda: manager.connection_count == 1)

            # A bar lands on this client's queue first; the servicer must skip it.
            queue = next(iter(manager._queues.values()))
            queue.put_nowait(StreamMessage(stream_type=StreamType.BAR, symbol="AAPL", data=_BAR))
            await manager.broadcast_trade("AAPL", _TRADE)

            await _wait_until(lambda: len(out) == 1)
            assert out[0].price.value == "150.25"
        finally:
            await _cancel(task)


class TestMultipleStreams:
    async def test_streams_are_independent_and_clean_up_separately(
        self, servicer: MarketDataServicer, manager: StreamManager
    ) -> None:
        out_a: list[market_data_pb2.Bar] = []
        out_b: list[market_data_pb2.Bar] = []
        task_a = asyncio.create_task(
            _consume(
                servicer.stream_bars(market_data_pb2.StreamBarsRequest(symbols=["AAPL"]), _ctx()),
                out_a,
            )
        )
        task_b = asyncio.create_task(
            _consume(
                servicer.stream_bars(market_data_pb2.StreamBarsRequest(symbols=["GOOGL"]), _ctx()),
                out_b,
            )
        )

        try:
            await _wait_until(lambda: manager.connection_count == 2)
            assert manager.subscribed_symbols["bars"] == {"AAPL", "GOOGL"}

            await manager.broadcast_bar("AAPL", _BAR)
            await _wait_until(lambda: len(out_a) == 1)
            assert out_b == []  # only the AAPL subscriber received it

            await _cancel(task_a)
            assert manager.connection_count == 1
            assert manager.subscribed_symbols["bars"] == {"GOOGL"}
        finally:
            await _cancel(task_a)
            await _cancel(task_b)

        assert manager.connection_count == 0


class TestStreamManagerIntegration:
    """Integration tests for StreamManager with gRPC streaming."""

    async def test_full_flow_with_stream_manager(self) -> None:
        """Test the full flow from connection to message delivery."""
        stream_manager = StreamManager()

        queue = await stream_manager.connect(1)
        assert stream_manager.connection_count == 1

        await stream_manager.subscribe(1, trades=["AAPL"], quotes=[], bars=[])
        assert "AAPL" in stream_manager.subscribed_symbols["trades"]

        await stream_manager.broadcast_trade("AAPL", _TRADE)

        message = queue.get_nowait()
        assert message.stream_type == StreamType.TRADE
        assert message.symbol == "AAPL"
        assert message.data == _TRADE

        await stream_manager.disconnect(1)
        assert stream_manager.connection_count == 0
        assert "AAPL" not in stream_manager.subscribed_symbols["trades"]
