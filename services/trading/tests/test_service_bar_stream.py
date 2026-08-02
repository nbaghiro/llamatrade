"""Tests for the market-data-service-backed live bar stream adapter."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.runner import service_bar_stream
from src.runner.service_bar_stream import ServiceBarStream


def _bar(symbol: str) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        timestamp=datetime(2026, 1, 5, 14, 31, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        volume=12345,
        vwap=100.25,
        trade_count=42,
    )


class _FakeClient:
    """Stand-in for llamatrade_proto MarketDataClient; scripts stream_bars behavior."""

    def __init__(self, target: str, *, scripts: list) -> None:
        self.target = target
        self._scripts = scripts
        self.calls = 0

    async def stream_bars(self, symbols, timeframe="1MIN"):
        script = self._scripts[min(self.calls, len(self._scripts) - 1)]
        self.calls += 1
        if isinstance(script, Exception):
            raise script
        for bar in script:
            yield bar


@pytest.mark.asyncio
async def test_stream_yields_converted_bars(monkeypatch):
    monkeypatch.setattr(
        service_bar_stream,
        "MarketDataClient",
        lambda target: _FakeClient(target, scripts=[[_bar("AAPL"), _bar("MSFT")]]),
    )
    changes: list[bool] = []
    stream = ServiceBarStream("market-data:8840", on_connection_change=changes.append)

    assert await stream.connect() is True
    assert stream.connected is True
    assert changes == [True]
    assert await stream.subscribe(["aapl", "msft"]) is True

    collected = []
    async for bar in stream.stream():
        collected.append(bar)
        if len(collected) == 2:
            break

    assert [b.symbol for b in collected] == ["AAPL", "MSFT"]
    b = collected[0]
    assert (b.open, b.high, b.low, b.close, b.volume) == (100.0, 101.0, 99.5, 100.5, 12345)
    assert b.vwap == 100.25 and b.trade_count == 42
    assert isinstance(b.volume, int)


@pytest.mark.asyncio
async def test_reconnects_on_drop(monkeypatch):
    # First stream_bars call raises (drop); second yields a bar.
    monkeypatch.setattr(
        service_bar_stream,
        "MarketDataClient",
        lambda target: _FakeClient(target, scripts=[RuntimeError("dropped"), [_bar("AAPL")]]),
    )

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(service_bar_stream.asyncio, "sleep", _no_sleep)

    reconnects: list[int] = []
    stream = ServiceBarStream("market-data:8840", on_reconnect=lambda: reconnects.append(1))
    await stream.subscribe(["AAPL"])

    collected = []
    async for bar in stream.stream():
        collected.append(bar)
        break

    assert [b.symbol for b in collected] == ["AAPL"]
    assert len(reconnects) == 1  # one reconnect after the initial drop


@pytest.mark.asyncio
async def test_disconnect_marks_not_connected(monkeypatch):
    monkeypatch.setattr(
        service_bar_stream, "MarketDataClient", lambda target: _FakeClient(target, scripts=[[]])
    )
    changes: list[bool] = []
    stream = ServiceBarStream("market-data:8840", on_connection_change=changes.append)
    await stream.connect()
    await stream.disconnect()
    assert stream.connected is False
    assert changes == [True, False]
