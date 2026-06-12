"""Position-enrichment flow tests using a fake PriceProvider.

Exercises PortfolioService's live-price valuation path end-to-end with **no DB,
no network, no live market data** — the market-data boundary is a fake.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.services.portfolio_service import PortfolioService


class FakePriceProvider:
    """In-memory PriceProvider (satisfies src.ports.PriceProvider structurally)."""

    def __init__(self, prices: dict[str, Decimal]) -> None:
        self._prices = prices

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        return {s: self._prices.get(s, Decimal("0")) for s in symbols}

    async def get_daily_closes(
        self, symbol: str, start: datetime, end: datetime
    ) -> dict[date, float]:
        return {}


def _service(prices: dict[str, Decimal] | None) -> PortfolioService:
    md = FakePriceProvider(prices) if prices is not None else None
    # db is unused by _enrich_positions_with_prices; a MagicMock keeps types happy.
    return PortfolioService(db=MagicMock(), market_data=md)


async def test_enrich_long_uses_live_prices() -> None:
    svc = _service({"AAPL": Decimal("110")})
    out = await svc._enrich_positions_with_prices(
        [
            {
                "symbol": "AAPL",
                "qty": 10,
                "side": "long",
                "avg_entry_price": 100.0,
                "cost_basis": 1000.0,
            }
        ]
    )
    assert len(out) == 1
    p = out[0]
    assert p.current_price == pytest.approx(110.0)
    assert p.market_value == pytest.approx(1100.0)
    assert p.unrealized_pnl == pytest.approx(100.0)
    assert p.unrealized_pnl_percent == pytest.approx(10.0)


async def test_enrich_short_pnl() -> None:
    svc = _service({"TSLA": Decimal("180")})
    out = await svc._enrich_positions_with_prices(
        [
            {
                "symbol": "TSLA",
                "qty": 5,
                "side": "short",
                "avg_entry_price": 200.0,
                "cost_basis": 1000.0,
            }
        ]
    )
    assert out[0].unrealized_pnl == pytest.approx(100.0)  # (200 - 180) * 5


async def test_enrich_falls_back_to_entry_without_market_data() -> None:
    svc = _service(None)
    out = await svc._enrich_positions_with_prices(
        [{"symbol": "AAPL", "qty": 10, "side": "long", "avg_entry_price": 100.0}]
    )
    assert out[0].current_price == pytest.approx(100.0)
    assert out[0].unrealized_pnl == pytest.approx(0.0)


async def test_enrich_empty_positions() -> None:
    svc = _service({"AAPL": Decimal("110")})
    assert await svc._enrich_positions_with_prices([]) == []


async def test_enrich_unavailable_price_falls_back_not_zero() -> None:
    """A provider price of 0 (unavailable) must fall back, not value at $0."""
    svc = _service({})  # provider returns 0 for unknown symbols
    out = await svc._enrich_positions_with_prices(
        [
            {
                "symbol": "NVDA",
                "qty": 2,
                "side": "long",
                "avg_entry_price": 50.0,
                "cost_basis": 100.0,
                "current_price": 55.0,
            }
        ]
    )
    # 0 from the provider is treated as "no data" -> stored current_price (55) used.
    assert out[0].current_price == pytest.approx(55.0)
    assert out[0].market_value == pytest.approx(110.0)
