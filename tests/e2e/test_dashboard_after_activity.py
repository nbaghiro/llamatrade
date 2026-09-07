"""E2E: the dashboard read model rebuilt from activity this test created.

``test_portfolio_dashboard.py`` reads the seeded demo, so it can only assert that
the panels are structurally sound: the rows it sees were produced by the seeder,
not by a flow under test. Here a throwaway tenant is funded, deployed and filled
from empty, and the same dashboard RPCs are read before and after, so each
assertion is a delta this test caused.

That makes the projector load-bearing: a fill that never reaches the read model,
an allocation that ignores holdings, or an activity feed that drops the trade all
fail here rather than hiding behind seeded rows.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from . import _ledger, _scaffold
from .client import JSON, MeshClient, decimal_val, publish_ledger_fill

pytestmark = pytest.mark.e2e

QTY = 10
PRICE = 100
EQUITY_CATEGORY = "Stocks"


def _allocation(client: MeshClient) -> dict[str, float]:
    """Asset-allocation slices keyed by category."""
    resp = client.call("portfolio", "GetAssetAllocation", {})
    return {a["category"]: decimal_val(a.get("percentage")) for a in resp.get("allocations", [])}


def _transactions(client: MeshClient) -> list[JSON]:
    return client.call(
        "portfolio", "ListTransactions", {"pagination": {"page": 1, "pageSize": 50}}
    ).get("transactions", [])


def _total_value(client: MeshClient) -> float:
    portfolios = client.call("portfolio", "ListPortfolios", {}).get("portfolios", [])
    return sum(decimal_val(p.get("totalValue")) for p in portfolios)


@pytest.fixture
def filled_tenant(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> Iterator[tuple[MeshClient, _scaffold.FundedExecution, str]]:
    """A funded tenant whose sleeve has one open lot, built from empty.

    The execution is stopped on the way out: a RUNNING execution left behind is
    picked up by trading's orphan-adoption sweep on every tick forever, so the
    debris from repeated runs compounds until the mesh is unusable.
    """
    client = throwaway_tenant("dash")
    funded = _scaffold.fund_tenant_execution(client, demo, "Dashboard Activity")
    strategy = client.call("strategy", "GetStrategy", {"strategyId": funded.strategy_id})[
        "strategy"
    ]
    symbol = strategy["symbols"][0]

    publish_ledger_fill(
        client.ctx["tenantId"],
        funded.account_id,
        funded.sleeve_id,
        f"e2e-dash-{funded.execution_id[:8]}",
        symbol,
        "buy",
        str(QTY),
        str(PRICE),
    )
    _ledger.wait_position(client, symbol, QTY)

    yield client, funded, symbol

    client.try_call(
        "strategy", "StopExecution", {"executionId": funded.execution_id, "reason": "e2e cleanup"}
    )


def test_cash_only_tenant_allocates_entirely_to_cash(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """The baseline the next tests measure against: deposited, deployed, unfilled."""
    client = throwaway_tenant("dash-base")
    _scaffold.fund_tenant_execution(client, demo, "Dashboard Baseline")

    assert _allocation(client) == {"Cash": pytest.approx(100)}
    assert _total_value(client) > 0, "a deposited account carries value before any fill"


def test_a_fill_moves_the_allocation_off_pure_cash(
    filled_tenant: tuple[MeshClient, _scaffold.FundedExecution, str],
) -> None:
    """Holdings must displace cash in the allocation ring once a fill lands.

    The ring buckets by asset class rather than by symbol, so the equity slice is
    what a filled position surfaces as.
    """
    client, _funded, _symbol = filled_tenant

    allocation = _allocation(client)
    assert allocation.get(EQUITY_CATEGORY, 0) > 0, (
        f"no equity slice after a fill: {sorted(allocation.items())}"
    )
    assert allocation.get("Cash", 0) < 100, "cash must no longer be the whole portfolio"
    assert sum(allocation.values()) == pytest.approx(100, abs=0.5)


def test_the_fill_appears_in_the_activity_feed(
    filled_tenant: tuple[MeshClient, _scaffold.FundedExecution, str],
) -> None:
    """The activity panel is a projection: the trade must surface as a typed row."""
    client, _funded, symbol = filled_tenant

    buys = [
        t
        for t in _transactions(client)
        if t.get("symbol") == symbol and "BUY" in str(t.get("type", ""))
    ]
    assert buys, f"no BUY transaction for {symbol} in the activity feed"
    assert decimal_val(buys[0].get("quantity")) == pytest.approx(QTY)


def test_holdings_and_performance_read_back_the_position(
    filled_tenant: tuple[MeshClient, _scaffold.FundedExecution, str],
) -> None:
    """The holdings panel and the deployment card both resolve the new position."""
    client, funded, symbol = filled_tenant

    positions = client.call("portfolio", "GetPositions", {}).get("positions", [])
    held = [p for p in positions if p.get("symbol") == symbol]
    assert held, f"{symbol} missing from holdings: {[p.get('symbol') for p in positions]}"
    assert decimal_val(held[0].get("quantity")) == pytest.approx(QTY)

    cards = client.call(
        "portfolio", "ListStrategyPerformance", {"pagination": {"page": 1, "pageSize": 50}}
    ).get("strategies", [])
    mine = [c for c in cards if c.get("executionId") == funded.execution_id]
    assert mine, "the running deployment should have a performance card"
    assert decimal_val(mine[0].get("currentValue")) > 0


def test_selling_the_lot_returns_the_allocation_to_cash(
    filled_tenant: tuple[MeshClient, _scaffold.FundedExecution, str],
) -> None:
    """Flattening must unwind the read model, not leave a stale holding behind."""
    client, funded, symbol = filled_tenant

    publish_ledger_fill(
        client.ctx["tenantId"],
        funded.account_id,
        funded.sleeve_id,
        f"e2e-dash-sell-{funded.execution_id[:8]}",
        symbol,
        "sell",
        str(QTY),
        str(PRICE + 1),
    )
    _ledger.wait_position(client, symbol, 0)

    allocation = _allocation(client)
    assert allocation.get(EQUITY_CATEGORY, 0) == pytest.approx(0, abs=0.01)
    assert allocation.get("Cash", 0) == pytest.approx(100, abs=0.5)

    sells = [
        t
        for t in _transactions(client)
        if t.get("symbol") == symbol and "SELL" in str(t.get("type", ""))
    ]
    assert sells, "the closing trade must also reach the activity feed"
