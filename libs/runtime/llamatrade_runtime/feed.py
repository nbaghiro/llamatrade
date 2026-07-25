"""Bar feeds — the per-tick market-data source driving a run.

``HistoricalBarFeed`` replays stored bars in time order (backtest). Live trading provides a
real-time async feed over the same ``BarFeed`` seam. Each tick yields ``(timestamp,
{symbol: Bar}, is_warmup)``; warm-up ticks prime indicators without trading. The feed is async
so one seam covers both a synchronous historical replay and an unbounded live stream.
"""

from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Protocol

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
