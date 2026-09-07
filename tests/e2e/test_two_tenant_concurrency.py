"""E2E: two tenants trading at the same time must not see each other.

``test_tenant_isolation.py`` checks that one tenant cannot reach another's rows by
id, which is the authorization question. This asks the concurrency question
instead: when two tenants run the same journey simultaneously, does anything
downstream of the write path mix them up? The fills share a Kafka topic, the
projector consumes both, and the read models are separated only by a predicate,
so a partition-keying or session-scoping mistake shows up here and nowhere else.

Both tenants fill the *same* symbol with *different* quantities, which is what
makes a leak legible: a swapped or shared projection reads as the wrong quantity
rather than as a missing row.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from . import _ledger, _scaffold
from .client import JSON, MeshClient, decimal_val, pick_strategy, publish_ledger_fill

pytestmark = pytest.mark.e2e

# Distinct per tenant so a crossed projection is a wrong number, not a missing row.
QUANTITIES = {"alpha": 7, "beta": 13}
PRICE = "100"


def _run_journey(
    client: MeshClient, demo: MeshClient, label: str, symbol: str
) -> _scaffold.FundedExecution:
    """Fund, deploy and fill one tenant end to end."""
    funded = _scaffold.fund_tenant_execution(client, demo, f"Concurrent {label}")
    publish_ledger_fill(
        client.ctx["tenantId"],
        funded.account_id,
        funded.sleeve_id,
        f"e2e-conc-{label}-{funded.execution_id[:8]}",
        symbol,
        "buy",
        str(QUANTITIES[label]),
        PRICE,
    )
    return funded


def _positions(client: MeshClient) -> list[JSON]:
    return client.call("portfolio", "GetPositions", {}).get("positions", [])


@pytest.fixture
def concurrent_tenants(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> Iterator[tuple[dict[str, MeshClient], dict[str, _scaffold.FundedExecution], str]]:
    """Two tenants that ran the same journey at the same time on one symbol."""
    seed = pick_strategy(
        demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}}).get(
            "strategies", []
        )
    )
    assert seed and seed.get("symbols"), "need a seeded strategy to borrow a symbol from"
    symbol = seed["symbols"][0]

    clients = {label: throwaway_tenant(f"conc-{label}") for label in QUANTITIES}

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        futures = {
            label: pool.submit(_run_journey, client, demo, label, symbol)
            for label, client in clients.items()
        }
        funded = {label: future.result() for label, future in futures.items()}

    for label, client in clients.items():
        _ledger.wait_position(client, symbol, QUANTITIES[label])

    yield clients, funded, symbol

    # A RUNNING execution left behind is re-adopted by trading on every tick.
    for label, client in clients.items():
        client.try_call(
            "strategy",
            "StopExecution",
            {"executionId": funded[label].execution_id, "reason": "e2e cleanup"},
        )


def test_each_tenant_projects_only_its_own_quantity(
    concurrent_tenants: tuple[dict[str, MeshClient], dict[str, _scaffold.FundedExecution], str],
) -> None:
    """The projector must key by tenant, not merge two streams into one position."""
    clients, _funded, symbol = concurrent_tenants

    for label, client in clients.items():
        held = [p for p in _positions(client) if p.get("symbol") == symbol]
        assert len(held) == 1, f"{label} should hold exactly one {symbol} position, got {held}"
        assert decimal_val(held[0].get("quantity")) == pytest.approx(QUANTITIES[label]), (
            f"{label} read a quantity that is not its own"
        )


def test_neither_tenant_sees_the_others_sleeve_or_execution(
    concurrent_tenants: tuple[dict[str, MeshClient], dict[str, _scaffold.FundedExecution], str],
) -> None:
    """Ledger and execution handles created concurrently must stay private."""
    clients, funded, _symbol = concurrent_tenants

    alpha_sleeves = {
        s["id"]
        for s in clients["alpha"]
        .call("ledger", "ListSleeves", {"accountId": funded["alpha"].account_id})
        .get("sleeves", [])
    }
    assert funded["alpha"].sleeve_id in alpha_sleeves
    assert funded["beta"].sleeve_id not in alpha_sleeves

    beta_executions = {
        c.get("executionId")
        for c in clients["beta"]
        .call("portfolio", "ListStrategyPerformance", {"pagination": {"page": 1, "pageSize": 50}})
        .get("strategies", [])
    }
    assert funded["beta"].execution_id in beta_executions
    assert funded["alpha"].execution_id not in beta_executions


def test_activity_feeds_stay_separate(
    concurrent_tenants: tuple[dict[str, MeshClient], dict[str, _scaffold.FundedExecution], str],
) -> None:
    """Interleaved fills on one topic must land in the right activity feed."""
    clients, _funded, symbol = concurrent_tenants

    for label, client in clients.items():
        quantities = [
            decimal_val(t.get("quantity"))
            for t in client.call(
                "portfolio", "ListTransactions", {"pagination": {"page": 1, "pageSize": 50}}
            ).get("transactions", [])
            if t.get("symbol") == symbol and "BUY" in str(t.get("type", ""))
        ]
        assert quantities, f"{label} has no BUY row for {symbol}"
        other = float(QUANTITIES["beta" if label == "alpha" else "alpha"])
        assert other not in quantities, f"{label} sees the other tenant's fill quantity"
