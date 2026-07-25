"""Seed a live ``StrategySession``'s indicator history from the market-data store so it can trade
from the first live bar instead of warming up over real time."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from llamatrade_runtime import Bar, StrategySession

from src.clients.market_data import MarketDataClient

logger = logging.getLogger(__name__)

WARMUP_PRELOAD_BUFFER = 10


async def preload_session_history(
    session: StrategySession,
    symbols: list[str],
    timeframe: str,
    market_data: MarketDataClient,
) -> int:
    """Feed ``min_bars`` of historical bars per required symbol as warm-up. Best-effort (starts
    cold on failure); returns the number of periods primed."""
    required = sorted(set(symbols) | set(session.symbols))
    limit = session.min_bars + WARMUP_PRELOAD_BUFFER

    try:
        fetched = await asyncio.gather(
            *(market_data.get_bars(sym, timeframe=timeframe, limit=limit) for sym in required)
        )
    except Exception as e:
        logger.warning("Warm-up preload fetch failed; session starts cold: %s", e)
        return 0

    by_ts: dict[datetime, dict[str, Bar]] = defaultdict(dict)
    for sym, raw_bars in zip(required, fetched, strict=True):
        for rb in raw_bars:
            try:
                ts = datetime.fromisoformat(rb["timestamp"])
                by_ts[ts][sym] = Bar(
                    timestamp=ts,
                    open=float(rb["open"]),
                    high=float(rb["high"]),
                    low=float(rb["low"]),
                    close=float(rb["close"]),
                    volume=int(rb["volume"]),
                )
            except KeyError, ValueError, TypeError:
                continue  # skip a malformed bar rather than abort the whole preload

    primed = 0
    for ts in sorted(by_ts):
        session.evaluate(by_ts[ts], {}, 0.0, warm_up=True)
        primed += 1

    if primed:
        logger.info(
            "Warm-up preloaded %d periods for %d symbol(s) at %s", primed, len(required), timeframe
        )
    return primed
