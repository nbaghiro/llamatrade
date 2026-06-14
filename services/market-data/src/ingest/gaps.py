"""Gap detection + repair for the recent window.

Edge gaps (before the first / after the last stored bar) come from the store;
interior holes (e.g. a stream outage mid-session) are found by scanning the
stored timestamps. ``max_gap`` filters out *expected* overnight/weekend gaps
without needing a full trading calendar — anything larger than that is assumed
to be a session boundary, not a hole.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.ingest.backfill import BackfillController, backfill_window
from src.models import Timeframe
from src.store.intervals import Interval
from src.store.models import bar_row_from_alpaca

logger = logging.getLogger(__name__)


def find_interior_gaps(
    times: list[datetime], step: timedelta, max_gap: timedelta
) -> list[Interval]:
    """Holes between consecutive bars wider than ``step`` and within ``max_gap``.

    ``times`` must be sorted ascending. A returned ``(a, b)`` is the missing
    sub-range; ``max_gap`` excludes session boundaries (overnight/weekends).
    """
    gaps: list[Interval] = []
    for earlier, later in zip(times, times[1:], strict=False):
        delta = later - earlier
        if step < delta <= max_gap:
            gaps.append((earlier + step, later))
    return gaps


class GapRepairer:
    """Refetches edge + interior gaps in the recent window for the universe."""

    def __init__(
        self,
        controller: BackfillController,
        *,
        step: timedelta,
        max_gap: timedelta,
        recent_lookback_days: float,
    ) -> None:
        self._controller = controller
        self._step = step
        self._max_gap = max_gap
        self._recent_lookback_days = recent_lookback_days

    async def repair(self, symbols: list[str], timeframe: str, now: datetime) -> int:
        """Fill recent edge + interior gaps. Returns rows written."""
        store = self._controller.store
        alpaca = self._controller.alpaca
        start, end = backfill_window(now, self._recent_lookback_days)
        written = 0

        for symbol in symbols:
            stored = await store.select_bars(symbol, timeframe, start, end)
            times = [b.time for b in stored]
            interior = find_interior_gaps(times, self._step, self._max_gap)
            edges = await store.missing_ranges(symbol, timeframe, start, end)
            for gap_start, gap_end in [*edges, *interior]:
                bars = await alpaca.get_bars(
                    symbol=symbol, timeframe=Timeframe(timeframe), start=gap_start, end=gap_end
                )
                if bars:
                    written += await store.upsert_bars(
                        [bar_row_from_alpaca(symbol, b) for b in bars], timeframe
                    )
        if written:
            logger.info("Gap repair wrote %d bars for %s", written, timeframe)
        return written
