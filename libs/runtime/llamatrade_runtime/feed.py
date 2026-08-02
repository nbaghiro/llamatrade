"""Bar feeds — the per-tick market-data source driving a run.

``HistoricalBarFeed`` replays stored bars in time order (backtest). ``FormingBarFeed`` folds an
unbounded intraday stream into the same one-bar-per-period grid (live). Each tick yields
``(timestamp, {symbol: Bar}, is_warmup)``; warm-up ticks prime indicators without trading. The
feed is async so one seam covers both a synchronous historical replay and a live stream.
"""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from llamatrade_runtime.aggregation import FormingBarAggregator
from llamatrade_runtime.types import Bar


class BarFeed(Protocol):
    """A source of per-tick bars. ``total_ticks`` is the tradable count, or None if unbounded."""

    @property
    def total_ticks(self) -> int | None: ...

    def __aiter__(self) -> AsyncIterator[tuple[datetime, dict[str, Bar], bool]]: ...


class HistoricalBarFeed:
    """Replays stored bars grouped by timestamp; dates before ``start_date`` are warm-up."""

    def __init__(
        self,
        bars: Mapping[str, list[Bar]],
        start_date: datetime,
        end_date: datetime,
    ) -> None:
        bars_by_date: dict[datetime, dict[str, Bar]] = {}
        for symbol, symbol_bars in bars.items():
            for bar in symbol_bars:
                bar_date = bar.timestamp
                if bar_date <= end_date:
                    bars_by_date.setdefault(bar_date, {})[symbol] = bar

        self._bars_by_date = bars_by_date
        self._sorted_dates: list[datetime] = sorted(bars_by_date)
        self._start_date = start_date

    @property
    def total_ticks(self) -> int | None:
        return sum(1 for d in self._sorted_dates if d >= self._start_date)

    def __aiter__(self) -> AsyncIterator[tuple[datetime, dict[str, Bar], bool]]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[tuple[datetime, dict[str, Bar], bool]]:
        for date in self._sorted_dates:
            yield date, self._bars_by_date[date], date < self._start_date


class IntradayBarSource(Protocol):
    """An unbounded ``(symbol, bar)`` stream at a finer resolution than the strategy's grid."""

    def __aiter__(self) -> AsyncIterator[tuple[str, Bar]]: ...


class FormingBarFeed:
    """Live ``BarFeed`` that folds an intraday source into forming period bars.

    Each incoming bar updates its symbol's forming bar; a snapshot of every subscribed symbol's
    forming bar is yielded once they have all reported for the same source timestamp, at most
    once per source timestamp, and only when ``gate`` allows (market hours, circuit breaker, or
    any other caller policy). ``is_running`` ends the loop when the session stops.

    The tick timestamp is the source (wall-clock) timestamp so callers can gate and stamp orders
    on real time, while the bars themselves carry their period start — the session therefore
    reads exactly one bar per period per symbol, as a backtest does.
    """

    def __init__(
        self,
        source: IntradayBarSource,
        symbols: Sequence[str],
        *,
        aggregator: FormingBarAggregator | None = None,
        gate: Callable[[datetime], bool] | None = None,
        is_running: Callable[[], bool] | None = None,
    ) -> None:
        self._source = source
        self._symbols = list(symbols)
        self._aggregator = aggregator or FormingBarAggregator()
        self._gate = gate
        self._is_running = is_running
        self._latest: dict[str, Bar] = {}
        self._latest_ts: dict[str, datetime] = {}
        self._last_evaluated_ts: datetime | None = None

    @property
    def total_ticks(self) -> int | None:
        return None  # unbounded live feed

    @property
    def aggregator(self) -> FormingBarAggregator:
        """The forming-bar state this feed maintains."""
        return self._aggregator

    def __aiter__(self) -> AsyncIterator[tuple[datetime, dict[str, Bar], bool]]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[tuple[datetime, dict[str, Bar], bool]]:
        async for symbol, bar in self._source:
            if self._is_running is not None and not self._is_running():
                break
            if symbol not in self._symbols:
                continue

            self._latest[symbol] = self._aggregator.update(symbol, bar)
            ts = bar.timestamp
            self._latest_ts[symbol] = ts

            # Wait until every subscribed symbol has this source period's bar, then act once.
            if any(self._latest_ts.get(s) != ts for s in self._symbols):
                continue
            if ts == self._last_evaluated_ts:
                continue
            self._last_evaluated_ts = ts

            if self._gate is not None and not self._gate(ts):
                continue

            yield ts, dict(self._latest), False
