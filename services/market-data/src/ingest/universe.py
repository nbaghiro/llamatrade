"""Derived ingest universe: the configured baseline plus what live execution needs.

The ingest role owns the platform's single Alpaca bar subscription, so the set it
streams has to follow what is actually deployed rather than a static env list. A
refresh loop recomputes ``baseline | live-session symbols`` and reconciles the
stream: symbols that appeared are subscribed, symbols no active session needs any
more are unsubscribed. The baseline is always part of the union, so it is never
unsubscribed.

Failure posture is deliberately conservative. A failed database read or a refused
subscribe keeps the previous set and only warns: dropping the fan-out because the
platform database blipped would stop every consumer of live bars. Removals are
lazy for the same reason — a symbol leaves on the first refresh after the last
session needing it stopped, and late bars for it are harmless (writes upsert).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from llamatrade_db.live_session_symbols import get_live_session_symbols
from llamatrade_db.session import system_session

from src.metrics import record_ingest_universe_refresh_failure, record_ingest_universe_size

logger = logging.getLogger(__name__)

# Async source of the symbols live execution needs (injected in tests).
SymbolSource = Callable[[], Awaitable[frozenset[str]]]

# A stalled read is treated like a failed one: the ingestor keeps its current set
# rather than parking a loop (or startup) on an unresponsive database.
REFRESH_TIMEOUT_S = 30.0


class BarSubscriber(Protocol):
    """The bar subscribe/unsubscribe surface the reconciler needs from a stream."""

    def subscribe(self, *, bars: list[str]) -> Awaitable[bool]: ...

    def unsubscribe(self, *, bars: list[str]) -> Awaitable[bool]: ...


@dataclass(frozen=True, slots=True)
class UniverseChange:
    """Symbols subscribed and unsubscribed by one refresh (both empty when unchanged)."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.added or self.removed)


async def load_live_session_symbols() -> frozenset[str]:
    """Read the live symbol set from the platform database (cross-tenant, audited)."""
    async with system_session(reason="market-data ingest universe refresh") as db:
        return await get_live_session_symbols(db)


def normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    """Trim, upper-case, and de-duplicate ``symbols``, keeping first-seen order."""
    return tuple(dict.fromkeys(stripped for s in symbols if (stripped := s.strip().upper())))


class IngestUniverse:
    """The symbol set the ingestor maintains, reconciled against the live stream."""

    def __init__(self, baseline: Iterable[str], *, source: SymbolSource | None = None) -> None:
        self._baseline = normalize_symbols(baseline)
        self._source = source or load_live_session_symbols
        self._symbols = self._baseline
        self._stream: BarSubscriber | None = None
        record_ingest_universe_size(baseline=len(self._baseline), live=0, total=len(self._baseline))

    @property
    def baseline(self) -> tuple[str, ...]:
        """The configured symbols, which stay subscribed regardless of live sessions."""
        return self._baseline

    @property
    def symbols(self) -> tuple[str, ...]:
        """The current universe: baseline first, then the live-derived symbols."""
        return self._symbols

    def attach(self, stream: BarSubscriber | None) -> None:
        """Point reconciliation at the live stream (``None`` while it is down)."""
        self._stream = stream

    async def refresh(self) -> UniverseChange:
        """Recompute the union and reconcile the stream subscription."""
        loaded = await self._load_live_symbols()
        if loaded is None:
            return UniverseChange()

        live = frozenset(normalize_symbols(loaded))
        desired = self._baseline + tuple(sorted(live - set(self._baseline)))
        current, wanted = set(self._symbols), set(desired)
        added = tuple(symbol for symbol in desired if symbol not in current)
        removed = tuple(symbol for symbol in self._symbols if symbol not in wanted)

        if not await self._reconcile(added, removed):
            return UniverseChange()

        self._symbols = desired
        record_ingest_universe_size(
            baseline=len(self._baseline), live=len(live), total=len(desired)
        )
        return UniverseChange(added=added, removed=removed)

    async def _load_live_symbols(self) -> frozenset[str] | None:
        """The live symbol set, or ``None`` when the read failed or stalled."""
        try:
            async with asyncio.timeout(REFRESH_TIMEOUT_S):
                return await self._source()
        except Exception:
            record_ingest_universe_refresh_failure("query")
            logger.warning(
                "Live-session symbol read failed; keeping %d ingest symbols",
                len(self._symbols),
                exc_info=True,
            )
            return None

    async def _reconcile(self, added: tuple[str, ...], removed: tuple[str, ...]) -> bool:
        """Apply the diff to the attached stream; False leaves the set for the next pass."""
        if not added and not removed:
            return True
        if self._stream is None:
            logger.info(
                "Ingest universe changed while the stream is down: +%d -%d",
                len(added),
                len(removed),
            )
            return True
        try:
            if added and not await self._stream.subscribe(bars=list(added)):
                record_ingest_universe_refresh_failure("subscribe")
                logger.warning("Stream refused to subscribe %s; retrying next refresh", added)
                return False
            if removed:
                await self._stream.unsubscribe(bars=list(removed))
        except Exception:
            record_ingest_universe_refresh_failure("subscribe")
            logger.warning(
                "Ingest subscription reconcile failed; keeping current set", exc_info=True
            )
            return False
        logger.info("Ingest universe reconciled: subscribed %s, unsubscribed %s", added, removed)
        return True
