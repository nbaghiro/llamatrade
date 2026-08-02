"""E2E: the market-data read flow behind the markets and chart views.

Mirrors what the markets store (apps/core stores/markets.ts) fires: the header
reads ``GetMarketStatus``; the price chart reads ``GetHistoricalBars`` and a
``GetSnapshots`` quote; the watchlist reads ``GetAssets`` for display names. These
are reference/quote reads authenticated by the JWT alone, so the UI sends no
tenant ``context`` on them (only the portfolio reads carry one). Passing
``context=False`` here matches that: the client injects the tenant context by
default, but these MarketDataService requests reject it.

Bars are seeded globally (not tenant-scoped), so a symbol is sourced from a
seeded strategy and the data is asserted structurally, not by exact price.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from .client import JSON, MeshClient, decimal_val, epoch, status_is

pytestmark = pytest.mark.e2e

_MARKET_STATUSES = (
    ("MARKET_STATUS_OPEN", 1),
    ("MARKET_STATUS_CLOSED", 2),
    ("MARKET_STATUS_PRE_MARKET", 3),
    ("MARKET_STATUS_AFTER_HOURS", 4),
)


@pytest.fixture(scope="module")
def demo_symbol(demo: MeshClient) -> str:
    """A symbol that has seeded bars: the first symbol of a seeded strategy."""
    strategies = demo.call(
        "strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}}
    ).get("strategies", [])
    for s in strategies:
        symbols = s.get("symbols")
        if symbols:
            return symbols[0]
    pytest.skip("no seeded strategy with symbols to source a market-data symbol")


def _snapshot_price(snapshot: JSON) -> float:
    """The price the quote card shows, probing the fields a snapshot may carry."""
    latest_trade = snapshot.get("latestTrade") or {}
    if latest_trade.get("price"):
        return decimal_val(latest_trade["price"])
    quote = snapshot.get("latestQuote") or {}
    if quote.get("askPrice") or quote.get("bidPrice"):
        return decimal_val(quote.get("askPrice") or quote.get("bidPrice"))
    for bar_field in ("dailyBar", "latestBar", "previousDailyBar"):
        bar = snapshot.get(bar_field) or {}
        if bar.get("close"):
            return decimal_val(bar["close"])
    return 0.0


def test_market_status_recognized(demo: MeshClient) -> None:
    resp = demo.call("market_data", "GetMarketStatus", {})
    status = resp.get("status")
    assert status is not None, "a set MarketStatus is never the omitted UNSPECIFIED default"
    assert any(status_is(status, name, num) for name, num in _MARKET_STATUSES)


def test_snapshot_has_price(demo: MeshClient, demo_symbol: str) -> None:
    resp = demo.call("market_data", "GetSnapshots", {"symbols": [demo_symbol]}, context=False)
    snapshots = resp.get("snapshots", {})
    assert demo_symbol in snapshots, "the requested symbol should have a snapshot"
    snapshot = snapshots[demo_symbol]
    assert snapshot.get("symbol") == demo_symbol
    assert _snapshot_price(snapshot) > 0, "the quote card needs a positive price"


def test_historical_bars_present(demo: MeshClient, demo_symbol: str) -> None:
    resp = demo.call(
        "market_data",
        "GetHistoricalBars",
        {
            "symbol": demo_symbol,
            "start": {"seconds": epoch(datetime(2026, 1, 2, tzinfo=UTC))},
            "end": {"seconds": epoch(datetime(2026, 6, 30, tzinfo=UTC))},
            "timeframe": "TIMEFRAME_1DAY",
            "adjustForSplits": True,
            "pagination": {"page": 1, "pageSize": 1000},
        },
        context=False,
    )
    bars = resp.get("bars", [])
    assert bars, "the chart needs seeded daily bars for the symbol"
    for bar in bars:
        assert bar.get("symbol") == demo_symbol
        assert bar.get("timestamp")
        assert decimal_val(bar.get("close")) > 0
        assert decimal_val(bar.get("high")) >= decimal_val(bar.get("low")) > 0


def test_assets_reference_lookup(demo: MeshClient, demo_symbol: str) -> None:
    # The watchlist resolves display names via GetAssets. Reference data comes
    # from the broker and may be unavailable in this environment, so the map can
    # be empty; when the symbol resolves, assert its shape.
    resp = demo.call("market_data", "GetAssets", {"symbols": [demo_symbol]}, context=False)
    assets = resp.get("assets", {})
    assert isinstance(assets, dict)
    if demo_symbol in assets:
        asset = assets[demo_symbol]
        assert asset.get("symbol") == demo_symbol
        assert asset.get("name")
