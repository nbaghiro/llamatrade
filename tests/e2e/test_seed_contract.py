"""E2E seed contract: the demo seed provides a testable baseline for the flows.

The backtest and paper-execution flows assume ``scripts/seed_demo_account.py``
left the demo tenant with a backtestable strategy, an active paper Alpaca
credential, and daily market bars spanning the backtest window. When the seed
drifts, these assertions fail with a precise reason instead of a downstream flow
failing obscurely mid-run.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from .client import MeshClient, epoch, pick_strategy

pytestmark = pytest.mark.e2e

# Backtest window the flows exercise (mirrors test_backtest).
_START = datetime(2026, 1, 2, tzinfo=UTC)
_END = datetime(2026, 6, 30, tzinfo=UTC)

# Bars land on trading sessions only, so tolerate a week of holidays/weekends at
# either window edge when asserting coverage.
_EDGE_SECONDS = 7 * 24 * 3600


def test_seed_provides_a_backtestable_strategy(demo: MeshClient) -> None:
    """At least one ACTIVE/PAUSED strategy with symbols (what pick_strategy needs)."""
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    strategies = listing.get("strategies", [])
    chosen = pick_strategy(strategies)
    assert chosen is not None, (
        f"seed must expose an ACTIVE/PAUSED strategy with symbols ({len(strategies)} listed)"
    )
    assert chosen.get("symbols"), f"seed strategy {chosen.get('name')} declares no symbols"


def test_seed_provides_an_active_paper_credential(demo: MeshClient) -> None:
    """An active paper Alpaca credential (paper execution funds against it)."""
    creds = demo.call("auth", "ListAlpacaCredentials", {})
    paper = [c for c in creds.get("credentials", []) if c.get("isPaper") and c.get("isActive")]
    assert paper, "seed must expose an active paper Alpaca credential"


def test_seed_bars_cover_the_backtest_window(demo: MeshClient) -> None:
    """Daily bars span the backtest window at both edges for a seeded symbol."""
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    chosen = pick_strategy(listing.get("strategies", []))
    assert chosen is not None, "seed must expose a backtestable strategy to source a symbol from"
    symbol = chosen["symbols"][0]

    # GetHistoricalBarsRequest carries no context field, so the tenant context
    # must not be attached (it authenticates on the bearer token alone).
    resp = demo.call(
        "market_data",
        "GetHistoricalBars",
        {
            "symbol": symbol,
            "start": {"seconds": epoch(_START)},
            "end": {"seconds": epoch(_END)},
            "timeframe": "TIMEFRAME_1DAY",
            "pagination": {"page": 1, "pageSize": 1000},
        },
        context=False,
    )
    bars = resp.get("bars", [])
    assert bars, f"seed must provide daily {symbol} bars across the backtest window"

    seconds = sorted(int(b["timestamp"]["seconds"]) for b in bars)
    start_s, end_s = int(epoch(_START)), int(epoch(_END))
    assert seconds[0] - start_s <= _EDGE_SECONDS, (
        f"first {symbol} bar lands too late to cover the backtest window start"
    )
    assert end_s - seconds[-1] <= _EDGE_SECONDS, (
        f"last {symbol} bar lands too early to cover the backtest window end"
    )
