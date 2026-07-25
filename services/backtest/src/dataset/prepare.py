"""prepare_dataset — the warm-ahead gate.

Guarantees a run's bars exist as a complete, content-addressed snapshot before the sim starts:

1. **Warm hit** — snapshot already in the store → read it (zero market-data, zero Alpaca).
2. **Single-flight** — otherwise take a Redis lock keyed by the dataset hash so N concurrent runs
   over overlapping assets materialize the dataset ONCE; the others await the snapshot.
3. **Materialize** — fetch via the market-data service, fill interior gaps the read path misses,
   then publish the snapshot.

The sim then reads pure warm data — it never talks to market-data or Alpaca itself.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Protocol

from src.dataset.spec import DatasetSpec
from src.dataset.store import DatasetStore
from src.engine.bars import BarData

logger = logging.getLogger(__name__)

# Fetches bars for (symbols, timeframe, start, end) — the market-data service boundary.
Fetcher = Callable[[list[str], str, date, date], Awaitable[dict[str, list[BarData]]]]

_LOCK_TTL_SECONDS = 300
_POLL_INTERVAL_SECONDS = 0.5
_WAIT_TIMEOUT_SECONDS = 300.0

# A gap larger than this many calendar days between consecutive bars is treated as an interior
# hole to backfill. Daily uses 6 so normal weekends/holidays never false-positive; weekly/monthly
# bars are naturally further apart; intraday holes span at most a long weekend.
_GAP_THRESHOLD_DAYS: dict[str, int] = {"1D": 6, "1d": 6, "1W": 14, "1Month": 45}


class RedisLike(Protocol):
    """The subset of the async Redis client prepare_dataset needs for its single-flight lock."""

    async def set(
        self, name: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None: ...

    async def delete(self, *names: str) -> int: ...


async def prepare_dataset(
    spec: DatasetSpec,
    fetch: Fetcher,
    store: DatasetStore,
    redis: RedisLike | None = None,
    *,
    wait_timeout: float = _WAIT_TIMEOUT_SECONDS,
) -> dict[str, list[BarData]]:
    """Return the run's bars, materializing + caching the snapshot exactly once across workers.

    With no ``redis`` the cross-worker single-flight lock is skipped (warm-hit caching still
    applies) — fine for local/single-node; prod passes a client to coalesce concurrent prepares.
    """
    if await asyncio.to_thread(store.exists, spec):
        return await asyncio.to_thread(store.read, spec)

    if redis is None:
        return await _materialize(spec, fetch, store)

    lock_key = f"backtest:dataset:lock:{spec.dataset_hash}"
    try:
        got_lock = bool(await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception:
        # Coalescing is an optimization — if Redis is unreachable, materialize directly.
        logger.warning("dataset lock unavailable for %s; skipping coalescing", spec.dataset_hash)
        return await _materialize(spec, fetch, store)

    if got_lock:
        try:
            return await _materialize(spec, fetch, store)
        finally:
            try:
                await redis.delete(lock_key)
            except Exception:
                logger.debug("failed to release dataset lock %s", lock_key)

    # Another worker holds the lock — await the snapshot it is producing.
    waited = 0.0
    while waited < wait_timeout:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        waited += _POLL_INTERVAL_SECONDS
        if await asyncio.to_thread(store.exists, spec):
            return await asyncio.to_thread(store.read, spec)

    # The producer died or stalled past the deadline: materialize directly rather than hang.
    logger.warning(
        "dataset %s not ready after %.0fs; materializing directly", spec.dataset_hash, wait_timeout
    )
    return await _materialize(spec, fetch, store)


async def _materialize(
    spec: DatasetSpec, fetch: Fetcher, store: DatasetStore
) -> dict[str, list[BarData]]:
    bars = await fetch(list(spec.symbols), spec.timeframe, spec.fetch_start, spec.end)
    bars = await _fill_interior_gaps(spec, bars, fetch)
    await asyncio.to_thread(store.write, spec, bars)
    return bars


async def _fill_interior_gaps(
    spec: DatasetSpec, bars: dict[str, list[BarData]], fetch: Fetcher
) -> dict[str, list[BarData]]:
    """Backfill interior holes the market-data read path leaves (it fills only edge gaps)."""
    threshold = _GAP_THRESHOLD_DAYS.get(spec.timeframe, 2)
    for symbol, series in list(bars.items()):
        gaps = _find_gaps(series, threshold)
        if not gaps:
            continue
        for gap_start, gap_end in gaps:
            # Re-fetch the STRICTLY interior range: with the stored edges excluded, market-data
            # sees an empty range and edge-fills the whole hole from Alpaca, then persists it.
            patch = await fetch([symbol], spec.timeframe, gap_start, gap_end)
            series = _merge_dedup(series, patch.get(symbol, []))
        bars[symbol] = series
        logger.info(
            "backfilled %d interior gap(s) for %s in %s", len(gaps), symbol, spec.dataset_hash
        )
    return bars


def _find_gaps(series: list[BarData], threshold_days: int) -> list[tuple[date, date]]:
    """Interior ranges (exclusive of the stored edges) where consecutive bars are too far apart."""
    gaps: list[tuple[date, date]] = []
    for i in range(len(series) - 1):
        cur = series[i]["timestamp"].date()
        nxt = series[i + 1]["timestamp"].date()
        if (nxt - cur).days > threshold_days:
            gaps.append((cur + timedelta(days=1), nxt - timedelta(days=1)))
    return gaps


def _merge_dedup(existing: list[BarData], patch: list[BarData]) -> list[BarData]:
    """Merge patch bars into existing, keeping existing on timestamp conflict, sorted by time."""
    merged: dict[datetime, BarData] = {}
    for bar in existing:
        merged[bar["timestamp"]] = bar
    for bar in patch:
        merged.setdefault(bar["timestamp"], bar)
    return [merged[ts] for ts in sorted(merged)]
