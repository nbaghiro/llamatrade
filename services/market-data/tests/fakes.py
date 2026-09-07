"""Deterministic in-memory fakes for the Alpaca client boundary.

Used instead of mocking internal methods: the whole client is swapped for a
fake that generates reproducible bars and records exactly which ranges were
requested, so tests can assert "the store served this; Alpaca was only hit for
the gap". Raise modes simulate upstream failures per symbol or per endpoint so
degradation paths (partial backfill, store-fallback snapshots) are testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from llamatrade_alpaca import AlpacaServerError

from src.models import Bar, Snapshot, Timeframe

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
    assertable; OHLCV is otherwise constant. Symbols in ``fail_symbols`` (or
    ``fail_snapshot_symbols`` / ``fail_multi_snapshots``) raise
    :class:`AlpacaServerError` to drive the failure tiers.
    """

    calls: list[tuple[str, datetime, datetime]] = field(default_factory=list)
    multi_calls: list[tuple[tuple[str, ...], datetime, datetime]] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    snapshot_calls: list[str] = field(default_factory=list)
    multi_snapshot_calls: list[tuple[str, ...]] = field(default_factory=list)
    snapshots: dict[str, Snapshot] = field(default_factory=dict)
    fail_symbols: set[str] = field(default_factory=set)
    fail_snapshot_symbols: set[str] = field(default_factory=set)
    fail_multi_snapshots: bool = False

    async def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = None,
        limit: int = 1000,
        adjustment: str = "raw",
    ) -> list[Bar]:
        self.calls.append((symbol, start, end or start))
        self.adjustments.append(adjustment)
        if symbol in self.fail_symbols:
            raise AlpacaServerError(f"injected get_bars failure for {symbol}")
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

    async def get_snapshot(self, symbol: str) -> Snapshot | None:
        self.snapshot_calls.append(symbol)
        if symbol in self.fail_snapshot_symbols:
            raise AlpacaServerError(f"injected get_snapshot failure for {symbol}")
        return self.snapshots.get(symbol)

    async def get_multi_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        self.multi_snapshot_calls.append(tuple(symbols))
        if self.fail_multi_snapshots:
            raise AlpacaServerError("injected get_multi_snapshots failure")
        return {s: self.snapshots[s] for s in symbols if s in self.snapshots}

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
