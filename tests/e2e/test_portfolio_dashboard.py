"""E2E: the dashboard and portfolio read flow.

Mirrors what DashboardPage and PortfolioPage fire on load. The dashboard reads
``PortfolioService/ListStrategyPerformance`` (deployment cards, each keyed by an
``executionId``), ``StrategyService/ListStrategies`` (the strategy table),
``ListPortfolios`` (the account summary) and ``MarketDataService/GetMarketStatus``
(the header pill). Selecting a deployment then reads its equity curve
(``GetStrategyEquityCurve``) and detail (``GetStrategyPerformance``), while the
holdings and activity panels read ``GetPositions`` and ``ListTransactions``.

Everything runs against the seeded demo tenant. The demo's positions, equity and
transactions are mutated by the concurrent trading flows, so these tests assert
structural presence (non-empty collections, fields present, typed values), never
exact quantities or balances.
"""

from __future__ import annotations

import pytest

from .client import JSON, MeshClient, decimal_val, status_is

pytestmark = pytest.mark.e2e

_MARKET_STATUSES = (
    ("MARKET_STATUS_OPEN", 1),
    ("MARKET_STATUS_CLOSED", 2),
    ("MARKET_STATUS_PRE_MARKET", 3),
    ("MARKET_STATUS_AFTER_HOURS", 4),
)


def _deployments(demo: MeshClient) -> list[JSON]:
    """The dashboard's strategy-performance cards (each carries an executionId)."""
    resp = demo.call(
        "portfolio", "ListStrategyPerformance", {"pagination": {"page": 1, "pageSize": 50}}
    )
    return resp.get("strategies", [])


def test_dashboard_loads_strategy_performance(demo: MeshClient) -> None:
    perf = demo.call(
        "portfolio", "ListStrategyPerformance", {"pagination": {"page": 1, "pageSize": 50}}
    )
    deployments = perf.get("strategies", [])
    assert deployments, "dashboard should list at least one running deployment"
    for d in deployments:
        assert d.get("executionId"), "each deployment card is keyed by an executionId"
        assert d.get("strategyId")
        assert d.get("strategyName")
    # Portfolio-wide totals back the aggregate header tiles.
    assert decimal_val(perf.get("totalAllocated")) > 0
    assert decimal_val(perf.get("totalCurrentValue")) > 0

    strategies = demo.call(
        "strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 100}}
    ).get("strategies", [])
    assert strategies, "the strategy table should show the seeded strategies"
    assert all(s.get("id") and s.get("name") for s in strategies)
    assert any(s.get("symbols") for s in strategies)

    portfolios = demo.call(
        "portfolio", "ListPortfolios", {"pagination": {"page": 1, "pageSize": 1}}
    ).get("portfolios", [])
    assert portfolios, "the account summary needs a portfolio"
    account = portfolios[0]
    assert account.get("id")
    assert account.get("name")
    assert decimal_val(account.get("totalValue")) > 0


def test_dashboard_shows_market_status(demo: MeshClient) -> None:
    # The header market pill. GetMarketStatus takes no tenant context; the client
    # already skips it, so this is a plain call.
    resp = demo.call("market_data", "GetMarketStatus", {})
    status = resp.get("status")
    assert status is not None, "proto3 omits UNSPECIFIED, so a set status must be present"
    assert any(status_is(status, name, num) for name, num in _MARKET_STATUSES)


def test_portfolio_has_positions(demo: MeshClient) -> None:
    resp = demo.call("portfolio", "GetPositions", {})
    positions = resp.get("positions", [])
    assert positions, "the seeded demo holds positions"
    for p in positions:
        assert isinstance(p.get("symbol"), str) and p["symbol"]
        assert abs(decimal_val(p.get("quantity"))) > 0
        assert p.get("side"), "each holding reports a long/short side"


def test_strategy_equity_curve_present(demo: MeshClient) -> None:
    # The chart plots the first deployment that has a curve; a freshly-started
    # execution may not have any samples yet, so scan for the first non-empty one.
    curve: list[JSON] = []
    benchmark: JSON = {}
    for d in _deployments(demo):
        resp = demo.call(
            "portfolio",
            "GetStrategyEquityCurve",
            {
                "executionId": d["executionId"],
                "benchmarkSymbol": "SPY",
                "sampleIntervalMinutes": 0,
            },
        )
        points = resp.get("equityCurve", [])
        if points:
            curve = points
            benchmark = resp.get("benchmark", {})
            break
    assert curve, "at least one deployment should have a plottable equity curve"
    for point in curve:
        assert point.get("timestamp")
        assert decimal_val(point.get("equity")) > 0
    # The benchmark overlay is requested alongside the strategy curve.
    assert benchmark.get("equityCurve"), "the SPY benchmark overlay should be populated"


def test_strategy_performance_detail(demo: MeshClient) -> None:
    deployments = _deployments(demo)
    assert deployments
    execution_id = deployments[0]["executionId"]
    resp = demo.call("portfolio", "GetStrategyPerformance", {"executionId": execution_id})
    summary = resp.get("summary", {})
    assert summary.get("executionId") == execution_id
    assert summary.get("strategyName")
    # currentValue is present and non-negative; a stopped/flat execution reads 0.
    assert decimal_val(summary.get("currentValue")) >= 0
    assert resp.get("metrics"), "the detail drawer renders computed metrics"
    assert isinstance(resp.get("positions", []), list)


def test_transactions_present(demo: MeshClient) -> None:
    resp = demo.call("portfolio", "ListTransactions", {"pagination": {"page": 1, "pageSize": 15}})
    transactions = resp.get("transactions", [])
    assert transactions, "the activity panel should show seeded transactions"
    for tx in transactions:
        assert tx.get("id")
        assert tx.get("type"), "each transaction carries a type (buy/sell/transfer)"
        assert "amount" in tx
