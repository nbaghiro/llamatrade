"""Per-request read caches: fold each account once, price each symbol once.

The dashboard reads (``GetPortfolio`` → summary + positions + strategy book) all
project the same accounts and price the same symbols. A cache shared across the
read services for one request collapses that to one fold per account and one
market-data fetch per symbol, instead of a fold and an RPC per strategy. Scoped
to a single request (the servicer builds a fresh cache per call), so it never
serves stale balances across requests.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.ports import PriceProvider


class AccountProjectionCache:
    """Memoizes ``project_account`` by account for the life of one request."""

    def __init__(self, projector: LedgerProjector) -> None:
        self._projector = projector
        self._cache: dict[tuple[str, str], AccountProjection] = {}

    async def project(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        key = (str(tenant_id), str(account_id))
        cached = self._cache.get(key)
        if cached is None:
            cached = await self._projector.project_account(tenant_id, account_id)
            self._cache[key] = cached
        return cached


class LedgerReadBase:
    """Fold-once-per-request projection access shared by the ledger read services.

    Uses the servicer-supplied shared cache when present (so a dashboard load
    folds each account once across both readers), else memoizes locally over its
    own projector so the fold still runs once per request.
    """

    def __init__(
        self, projector: LedgerProjector, projections: AccountProjectionCache | None
    ) -> None:
        self._projector = projector
        self._shared_projections = projections
        self._local_projections: dict[tuple[str, str], AccountProjection] = {}

    async def _project(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        if self._shared_projections is not None:
            return await self._shared_projections.project(tenant_id, account_id)
        key = (str(tenant_id), str(account_id))
        cached = self._local_projections.get(key)
        if cached is None:
            cached = await self._projector.project_account(tenant_id, account_id)
            self._local_projections[key] = cached
        return cached


class PriceCache:
    """Memoizes latest prices by symbol; fetches only the symbols not seen yet."""

    def __init__(self, market_data: PriceProvider | None) -> None:
        self._market_data = market_data
        self._prices: dict[str, Decimal] = {}

    async def get(self, symbols: list[str]) -> dict[str, Decimal]:
        """Prices for ``symbols`` (subset of the shared cache), fetching misses once."""
        if self._market_data is None:
            return {}
        missing = sorted({s for s in symbols if s not in self._prices})
        if missing:
            self._prices.update(await self._market_data.get_prices(missing))
        return {s: self._prices[s] for s in symbols if s in self._prices}
