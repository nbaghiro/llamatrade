"""Portfolio LedgerService client with a short TTL cache.

Trading reads sleeve state (equity inputs, free cash) on the equity-sync and
risk paths. Sleeve state changes only on fills/fund ops, so a few seconds of
staleness is acceptable — the cache keeps the hot order path off the network.
The runner invalidates after its own fills to converge faster.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from uuid import UUID

from llamatrade_proto.clients.ledger import LedgerClient, SleeveDetail

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 10.0


class PortfolioLedgerClient:
    """Cached reads of sleeve state from the portfolio service."""

    def __init__(
        self,
        target: str | None = None,
        *,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        ledger: LedgerClient | None = None,
    ) -> None:
        self._ledger = ledger or LedgerClient(
            target or os.getenv("PORTFOLIO_GRPC_TARGET", "portfolio:8860")
        )
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, SleeveDetail]] = {}
        self._lock = asyncio.Lock()

    async def get_sleeve(self, tenant_id: UUID, user_id: str, sleeve_id: UUID) -> SleeveDetail:
        """Sleeve + open lots, cached for ``cache_ttl_seconds``."""
        key = str(sleeve_id)
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]

        detail = await self._ledger.get_sleeve(str(tenant_id), user_id, key)
        async with self._lock:
            self._cache[key] = (time.monotonic() + self._cache_ttl, detail)
        return detail

    def invalidate(self, sleeve_id: UUID) -> None:
        """Drop the cached state (call after a fill to converge faster)."""
        self._cache.pop(str(sleeve_id), None)

    async def close(self) -> None:
        await self._ledger.close()


_client: PortfolioLedgerClient | None = None


def get_portfolio_ledger_client() -> PortfolioLedgerClient:
    """Singleton PortfolioLedgerClient (lazy)."""
    global _client
    if _client is None:
        _client = PortfolioLedgerClient()
    return _client
