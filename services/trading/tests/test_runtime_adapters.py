"""Tests for the live-execution runtime adapters (feed buffering/gating, execution delegation).

These lock ``StreamBarFeed``'s per-period all-symbols buffering + once-per-period + gate against
``_evaluate_session``'s semantics, and its translation of stream bars into period bars.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from llamatrade_runtime import Bar, Holding, IntendedOrder, Portfolio

from src.runner.runtime_adapters import LedgerPortfolio, RunnerExecution, StreamBarFeed


@dataclass
class _FakeBar:
    symbol: str
    timestamp: datetime
    open: float = 100.0
    high: float = 100.0
    low: float = 100.0
    close: float = 100.0
    volume: float = 1000.0


class _FakeStream:
    def __init__(self, bars: list[_FakeBar]) -> None:
        self._bars = bars

    async def stream(self) -> AsyncIterator[_FakeBar]:
        for bar in self._bars:
            yield bar


async def _collect(feed: StreamBarFeed) -> list[tuple[datetime, dict[str, Bar], bool]]:
    return [tick async for tick in feed]


@pytest.mark.asyncio
async def test_feed_yields_only_when_all_symbols_present() -> None:
    t0 = datetime(2024, 1, 1, 15, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=1)
    bars = [
        _FakeBar("SPY", t0),  # period t0 incomplete (QQQ missing) → no yield
        _FakeBar("SPY", t1),
        _FakeBar("QQQ", t1),  # period t1 now complete → yields
    ]
    ticks = await _collect(StreamBarFeed(_FakeStream(bars), ["SPY", "QQQ"]))
    assert len(ticks) == 1
    ts, snapshot, warmup = ticks[0]
    assert ts == t1
    assert set(snapshot) == {"SPY", "QQQ"}
    assert warmup is False


@pytest.mark.asyncio
async def test_feed_evaluates_each_period_at_most_once() -> None:
    t0 = datetime(2024, 1, 1, 15, 0, tzinfo=UTC)
    bars = [_FakeBar("SPY", t0), _FakeBar("QQQ", t0), _FakeBar("SPY", t0)]  # extra SPY, same period
    ticks = await _collect(StreamBarFeed(_FakeStream(bars), ["SPY", "QQQ"]))
    assert len(ticks) == 1


@pytest.mark.asyncio
async def test_feed_gate_skips_period() -> None:
    t0 = datetime(2024, 1, 1, 15, 0, tzinfo=UTC)
    bars = [_FakeBar("SPY", t0), _FakeBar("QQQ", t0)]
    feed = StreamBarFeed(_FakeStream(bars), ["SPY", "QQQ"], gate=lambda ts: False)
    assert await _collect(feed) == []


@pytest.mark.asyncio
async def test_feed_on_bar_sees_all_bars_but_snapshot_excludes_untracked() -> None:
    t0 = datetime(2024, 1, 1, 15, 0, tzinfo=UTC)
    seen: list[str] = []
    bars = [_FakeBar("SPY", t0), _FakeBar("XXX", t0), _FakeBar("QQQ", t0)]
    feed = StreamBarFeed(_FakeStream(bars), ["SPY", "QQQ"], on_bar=lambda b: seen.append(b.symbol))
    ticks = await _collect(feed)
    assert seen == ["SPY", "XXX", "QQQ"]  # on_bar hook sees every raw bar (history/metrics)
    assert len(ticks) == 1
    assert set(ticks[0][1]) == {"SPY", "QQQ"}  # untracked XXX never enters the snapshot


@pytest.mark.asyncio
async def test_feed_snapshot_carries_folded_period_bars() -> None:
    """Stream bars are folded into the strategy's period, not passed through one per minute."""
    t0 = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=1)
    bars = [
        _FakeBar("SPY", t0, open=100.0, high=101.0, low=99.0, close=100.5, volume=10),
        _FakeBar("SPY", t1, open=100.5, high=104.0, low=100.0, close=103.0, volume=20),
    ]
    ticks = await _collect(StreamBarFeed(_FakeStream(bars), ["SPY"]))

    assert len(ticks) == 2
    first, second = ticks[0][1]["SPY"], ticks[1][1]["SPY"]
    assert first.timestamp == second.timestamp  # one slot for the period
    assert (second.open, second.high, second.low, second.close) == (100.0, 104.0, 99.0, 103.0)
    assert second.volume == 30


@pytest.mark.asyncio
async def test_feed_is_running_false_stops_immediately() -> None:
    t0 = datetime(2024, 1, 1, 15, 0, tzinfo=UTC)
    bars = [_FakeBar("SPY", t0), _FakeBar("QQQ", t0)]
    feed = StreamBarFeed(_FakeStream(bars), ["SPY", "QQQ"], is_running=lambda: False)
    assert await _collect(feed) == []


@pytest.mark.asyncio
async def test_runner_execution_delegates_and_returns_accepted() -> None:
    submitted: list[tuple[str, str, float, float]] = []

    async def submit(side: str, symbol: str, qty: float, price: float, ts: datetime) -> None:
        submitted.append((side, symbol, qty, price))

    ex = RunnerExecution(submit)
    bar = Bar(timestamp=datetime(2024, 1, 1, tzinfo=UTC), open=1, high=1, low=1, close=1, volume=1)
    out = await ex.execute(
        IntendedOrder("SPY", "buy", 10.0, 100.0),
        bar,
        Portfolio(0.0),
        datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert out.fill is None and out.trade is None  # accepted; fill arrives out-of-band
    assert submitted == [("buy", "SPY", 10.0, 100.0)]
    assert await ex.liquidate(Portfolio(0.0), datetime(2024, 1, 1, tzinfo=UTC)) == []


def test_ledger_portfolio_delegates_to_providers() -> None:
    holdings = {"SPY": Holding("SPY", 5.0)}
    portfolio = LedgerPortfolio(lambda: holdings, lambda: 123456.0)
    assert portfolio.holdings() == holdings
    assert portfolio.equity() == 123456.0
    portfolio.update_prices({"SPY": 999.0})  # no-op; must not raise or change equity
    assert portfolio.equity() == 123456.0
