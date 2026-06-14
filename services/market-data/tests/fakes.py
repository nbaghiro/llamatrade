"""Deterministic in-memory fakes for the Alpaca client boundary.

Used instead of mocking internal methods: the whole client is swapped for a
fake that generates reproducible bars and records exactly which ranges were
requested, so tests can assert "the store served this; Alpaca was only hit for
the gap".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.models import Bar, Timeframe

_STEP = {
    Timeframe.MINUTE_1: timedelta(minutes=1),
    Timeframe.MINUTE_5: timedelta(minutes=5),
    Timeframe.MINUTE_15: timedelta(minutes=15),
    Timeframe.MINUTE_30: timedelta(minutes=30),
    Timeframe.HOUR_1: timedelta(hours=1),
    Timeframe.HOUR_4: timedelta(hours=4),
    Timeframe.DAY_1: timedelta(days=1),
}


@dataclass
class FakeMarketDataClient:
    """Generates one bar per timeframe-step in ``[start, end)`` and records calls.

    ``close`` encodes the bar index from an epoch so values are stable and
    assertable; OHLCV is otherwise constant.
    """

    calls: list[tuple[str, datetime, datetime]] = field(default_factory=list)
    multi_calls: list[tuple[tuple[str, ...], datetime, datetime]] = field(default_factory=list)

    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Bar]:
        self.calls.append((symbol, start, end or start))
        return self._generate(timeframe, start, end, limit)

    async def get_multi_bars(
        self,
        symbols: list[str],
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        self.multi_calls.append((tuple(symbols), start, end or start))
        return {s: self._generate(timeframe, start, end, limit) for s in symbols}

    @staticmethod
    def _generate(
        timeframe: Timeframe, start: datetime, end: datetime | None, limit: int
    ) -> list[Bar]:
        step = _STEP[timeframe]
        stop = end or (start + step)
        bars: list[Bar] = []
        t = start
        idx = 0
        while t < stop and (not limit or idx < limit):
            bars.append(
                Bar(
                    timestamp=t,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.0 + idx,
                    volume=1000 + idx,
                    vwap=100.5,
                    trade_count=10,
                )
            )
            t += step
            idx += 1
        return bars
