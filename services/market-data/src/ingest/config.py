"""Ingest configuration — symbol universe, feed, and backfill/retention windows.

All env-driven; defaults are conservative and IEX-friendly so the ingestor runs
on free credentials. Widen the universe / windows (and switch to SIP) via env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Timeframes the ingestor maintains. Minute is the raw base (recent window);
# daily is the adjusted base (deep history). Intraday/weekly/monthly are derived
# continuous aggregates — never ingested directly.
BACKFILL_TIMEFRAMES: tuple[str, ...] = ("1Day", "1Min")


@dataclass(frozen=True)
class IngestConfig:
    """Tunables for the ingest role."""

    daily_lookback_days: int = 365 * 5
    minute_lookback_days: int = 90
    max_concurrency: int = 4
    fetch_limit: int = 10_000
    # Loop cadences (seconds)
    backfill_interval_s: float = 24 * 3600
    gap_repair_interval_s: float = 3600
    corporate_action_interval_s: float = 24 * 3600
    # Trailing window the corporate-action job re-pulls each night (days)
    corporate_action_window_days: int = 10

    @classmethod
    def from_env(cls) -> IngestConfig:
        def _int(name: str, default: int) -> int:
            return int(os.getenv(name, str(default)))

        return cls(
            daily_lookback_days=_int("MARKET_DATA_DAILY_LOOKBACK_DAYS", cls.daily_lookback_days),
            minute_lookback_days=_int("MARKET_DATA_MINUTE_LOOKBACK_DAYS", cls.minute_lookback_days),
            max_concurrency=_int("MARKET_DATA_INGEST_CONCURRENCY", cls.max_concurrency),
        )

    def lookback_days(self, timeframe: str) -> int:
        return self.daily_lookback_days if timeframe == "1Day" else self.minute_lookback_days


def get_universe() -> list[str]:
    """Symbols to maintain. From ``MARKET_DATA_UNIVERSE`` (comma-separated).

    A placeholder for the future Alpaca ``/v2/assets`` sync — kept explicit and
    env-driven so QA can scope it to a handful of symbols.
    """
    raw = os.getenv("MARKET_DATA_UNIVERSE", "")
    seen: set[str] = set()
    universe: list[str] = []
    for token in raw.split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            universe.append(symbol)
    return universe
