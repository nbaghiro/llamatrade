"""Tests for ``FormingBarFeed`` — the all-symbols gate, once-per-tick, and period folding."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from llamatrade_runtime import Bar, FormingBarAggregator, FormingBarFeed

ET = ZoneInfo("America/New_York")


def _bar(ts: datetime, close: float, volume: int = 100) -> Bar:
    return Bar(timestamp=ts, open=close, high=close, low=close, close=close, volume=volume)


async def _source(items: list[tuple[str, Bar]]) -> AsyncIterator[tuple[str, Bar]]:
    for item in items:
        yield item


async def _collect(feed: FormingBarFeed) -> list[tuple[datetime, dict[str, Bar], bool]]:
    return [tick async for tick in feed]


async def test_yields_only_when_every_symbol_has_the_source_period() -> None:
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=1)
    ticks = await _collect(
        FormingBarFeed(
            _source([("SPY", _bar(t0, 100.0)), ("SPY", _bar(t1, 101.0)), ("TLT", _bar(t1, 50.0))]),
            ["SPY", "TLT"],
        )
    )
    assert len(ticks) == 1
    ts, snapshot, warm_up = ticks[0]
    assert ts == t1  # the tick carries wall-clock time
    assert set(snapshot) == {"SPY", "TLT"}
    assert warm_up is False


async def test_snapshot_bars_carry_the_period_start_not_the_source_timestamp() -> None:
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    ticks = await _collect(
        FormingBarFeed(_source([("SPY", _bar(t0, 100.0))]), ["SPY"]),
    )
    assert ticks[0][1]["SPY"].timestamp == datetime(2025, 7, 15, tzinfo=ET)


async def test_each_source_period_is_yielded_at_most_once() -> None:
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    items = [("SPY", _bar(t0, 100.0)), ("TLT", _bar(t0, 50.0)), ("SPY", _bar(t0, 101.0))]
    assert len(await _collect(FormingBarFeed(_source(items), ["SPY", "TLT"]))) == 1


async def test_successive_minutes_extend_one_forming_bar() -> None:
    day = datetime(2025, 7, 15, 13, 30, tzinfo=UTC)
    items: list[tuple[str, Bar]] = []
    for i, close in enumerate([100.0, 103.0, 98.0, 99.0]):
        items.append(("SPY", _bar(day + timedelta(minutes=i), close, volume=10)))
    ticks = await _collect(FormingBarFeed(_source(items), ["SPY"]))

    assert len(ticks) == 4  # one per source minute
    assert all(t[1]["SPY"].timestamp == ticks[0][1]["SPY"].timestamp for t in ticks)
    final = ticks[-1][1]["SPY"]
    assert (final.open, final.high, final.low, final.close) == (100.0, 103.0, 98.0, 99.0)
    assert final.volume == 40


async def test_gate_suppresses_the_yield_but_not_the_fold() -> None:
    """A closed gate must not lose price action — the forming bar keeps accumulating."""
    day = datetime(2025, 7, 15, 13, 30, tzinfo=UTC)
    last = day + timedelta(minutes=2)
    items = [
        ("SPY", _bar(day, 100.0, volume=10)),
        ("SPY", _bar(day + timedelta(minutes=1), 105.0, volume=10)),
        ("SPY", _bar(last, 102.0, volume=10)),
    ]
    ticks = await _collect(FormingBarFeed(_source(items), ["SPY"], gate=lambda ts: ts == last))

    assert len(ticks) == 1
    bar = ticks[0][1]["SPY"]
    assert (bar.open, bar.high, bar.low, bar.close) == (100.0, 105.0, 100.0, 102.0)
    assert bar.volume == 30


async def test_untracked_symbols_never_enter_the_snapshot() -> None:
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    items = [("SPY", _bar(t0, 100.0)), ("XXX", _bar(t0, 1.0)), ("TLT", _bar(t0, 50.0))]
    ticks = await _collect(FormingBarFeed(_source(items), ["SPY", "TLT"]))
    assert set(ticks[0][1]) == {"SPY", "TLT"}


async def test_is_running_false_stops_the_feed() -> None:
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    items = [("SPY", _bar(t0, 100.0))]
    assert await _collect(FormingBarFeed(_source(items), ["SPY"], is_running=lambda: False)) == []


async def test_supplied_aggregator_is_used_and_exposed() -> None:
    seed = {"SPY": Bar(datetime(2025, 7, 15, tzinfo=ET), 90.0, 90.0, 90.0, 90.0, 5_000)}
    aggregator = FormingBarAggregator(seed=seed)
    t0 = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
    feed = FormingBarFeed(
        _source([("SPY", _bar(t0, 100.0, volume=10))]), ["SPY"], aggregator=aggregator
    )

    ticks = await _collect(feed)
    assert feed.aggregator is aggregator
    assert ticks[0][1]["SPY"].open == 90.0  # seeded open survived
    assert ticks[0][1]["SPY"].volume == 5_010


def test_total_ticks_is_unbounded() -> None:
    assert FormingBarFeed(_source([]), ["SPY"]).total_ticks is None
