"""Per-request read-cache tests: fold each account once, price each symbol once."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from src.ledger.projection import AccountProjection
from src.services.read_context import AccountProjectionCache, LedgerReadBase, PriceCache

TENANT = uuid4()
D = Decimal


class _CountingProjector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def project_account(self, tenant_id: Any, account_id: Any) -> AccountProjection:
        self.calls.append((str(tenant_id), str(account_id)))
        return AccountProjection()


class _CountingPrices:
    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices
        self.fetches: list[list[str]] = []

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        self.fetches.append(list(symbols))
        return {s: self._prices[s] for s in symbols if s in self._prices}

    async def get_daily_closes(self, symbol: Any, start: Any, end: Any) -> dict[Any, float]:
        return {}


async def test_projection_cache_folds_each_account_once() -> None:
    projector = _CountingProjector()
    cache = AccountProjectionCache(cast(Any, projector))
    account_a, account_b = uuid4(), uuid4()

    first = await cache.project(TENANT, account_a)
    second = await cache.project(TENANT, account_a)
    await cache.project(TENANT, account_b)

    assert first is second  # memoized object, not a re-fold
    assert projector.calls == [(str(TENANT), str(account_a)), (str(TENANT), str(account_b))]


async def test_read_base_uses_the_shared_cache_when_present() -> None:
    projector = _CountingProjector()
    shared = AccountProjectionCache(cast(Any, projector))
    base = LedgerReadBase(cast(Any, projector), shared)
    account_id = uuid4()

    await base._project(TENANT, account_id)
    await base._project(TENANT, account_id)

    assert len(projector.calls) == 1


async def test_read_base_memoizes_locally_without_a_shared_cache() -> None:
    projector = _CountingProjector()
    base = LedgerReadBase(cast(Any, projector), None)
    account_id = uuid4()

    first = await base._project(TENANT, account_id)
    second = await base._project(TENANT, account_id)

    assert first is second
    assert len(projector.calls) == 1


async def test_price_cache_fetches_only_the_misses() -> None:
    provider = _CountingPrices({"AAPL": D("150"), "MSFT": D("300")})
    cache = PriceCache(cast(Any, provider))

    first = await cache.get(["AAPL"])
    second = await cache.get(["MSFT", "AAPL"])

    assert first == {"AAPL": D("150")}
    assert second == {"MSFT": D("300"), "AAPL": D("150")}
    assert provider.fetches == [["AAPL"], ["MSFT"]]  # AAPL never re-fetched


async def test_price_cache_returns_only_the_requested_subset() -> None:
    provider = _CountingPrices({"AAPL": D("150"), "MSFT": D("300")})
    cache = PriceCache(cast(Any, provider))
    await cache.get(["AAPL", "MSFT"])

    assert await cache.get(["MSFT"]) == {"MSFT": D("300")}


async def test_price_cache_priceless_symbol_stays_a_miss() -> None:
    """An unpriced symbol is omitted from the result (cost-basis fallback upstream)."""
    provider = _CountingPrices({"AAPL": D("150")})
    cache = PriceCache(cast(Any, provider))

    prices = await cache.get(["AAPL", "GOOG"])

    assert prices == {"AAPL": D("150")}


async def test_price_cache_does_not_refetch_an_unpriced_symbol() -> None:
    """Each strategy row asking again for an unpriced symbol must not re-hit market-data."""
    provider = _CountingPrices({"AAPL": D("150")})
    cache = PriceCache(cast(Any, provider))

    await cache.get(["AAPL", "GOOG"])
    await cache.get(["GOOG"])
    await cache.get(["GOOG", "AAPL"])

    assert provider.fetches == [["AAPL", "GOOG"]]


async def test_price_cache_without_a_provider_returns_empty() -> None:
    cache = PriceCache(None)
    assert await cache.get(["AAPL"]) == {}
