"""E2E: the refusals a real user hits, asserted at the wire.

Every flow here is a path the UI surfaces as an error dialog rather than a bug:
over-allocating a deploy, tripping the free-tier live-strategy limit, saving a
broken strategy, and asking for an impossible backtest. The suite otherwise works
*around* these (it stops one execution before starting another, for instance), so
their error shapes were never pinned. Each runs on its own throwaway tenant.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from . import _scaffold
from .client import MeshClient, MeshError, epoch

pytestmark = pytest.mark.e2e

_EARLIER = datetime(2026, 1, 2, tzinfo=UTC)
_LATER = datetime(2026, 6, 30, tzinfo=UTC)


def test_start_execution_over_free_cash_is_refused(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """Allocating more than the account holds must fail closed, leaving cash intact.

    The deploy dialog pre-checks client-side; this pins that the server refuses
    independently and that a refused start funds nothing.
    """
    client = throwaway_tenant("overalloc")
    credentials_id = _scaffold.create_paper_credential(client)
    account_id = _scaffold.open_funded_account(client, credentials_id, deposit="1000")
    strategy_id = _scaffold.create_active_strategy(
        client, _scaffold.sourced_dsl(demo), "Over-allocated"
    )

    created = client.call(
        "strategy",
        "CreateExecution",
        {
            "strategyId": strategy_id,
            "mode": "EXECUTION_MODE_PAPER",
            "allocatedCapital": {"value": "999999"},
            "credentialsId": credentials_id,
        },
    )
    execution_id = created["execution"]["id"]

    with pytest.raises(MeshError) as exc:
        client.call("strategy", "StartExecution", {"executionId": execution_id})
    assert "insufficient" in str(exc.value).lower() or "cash" in str(exc.value).lower()

    # The refusal must not have moved money: Unallocated still holds the deposit.
    sleeves = client.call("ledger", "ListSleeves", {"accountId": account_id})["sleeves"]
    unallocated = next(s for s in sleeves if s["type"] == "SLEEVE_TYPE_UNALLOCATED")
    assert unallocated["cash"]["balance"]["value"].startswith("1000")


def test_second_live_execution_hits_the_free_tier_limit(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """The free tier allows one running execution; the second start is refused."""
    client = throwaway_tenant("planlimit")
    funded = _scaffold.fund_tenant_execution(client, demo, "Plan Limit A")

    second = client.call(
        "strategy",
        "CreateExecution",
        {
            "strategyId": funded.strategy_id,
            "mode": "EXECUTION_MODE_PAPER",
            "allocatedCapital": {"value": "1000"},
            "credentialsId": funded.credentials_id,
        },
    )

    with pytest.raises(MeshError) as exc:
        client.call("strategy", "StartExecution", {"executionId": second["execution"]["id"]})
    message = str(exc.value).lower()
    assert "limit" in message or "plan" in message


def test_create_strategy_with_broken_dsl_is_invalid_argument(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    """A save with unparseable DSL is refused, not stored for a later crash."""
    client = throwaway_tenant("baddsl")

    with pytest.raises(MeshError) as exc:
        client.call(
            "strategy",
            "CreateStrategy",
            {"name": "Broken", "dslCode": '(strategy "Broken" (asset'},
        )
    assert "invalid_argument" in str(exc.value).lower()

    listed = client.call("strategy", "ListStrategies", {})
    assert not [s for s in listed.get("strategies", []) if s.get("name") == "Broken"]


def test_backtest_rejects_an_inverted_window(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """end before start is refused at submission rather than queued to fail later."""
    client = throwaway_tenant("badwindow")
    strategy_id = _scaffold.create_active_strategy(
        client, _scaffold.sourced_dsl(demo), "Bad Window"
    )

    with pytest.raises(MeshError) as exc:
        client.call(
            "backtest",
            "RunBacktest",
            {
                "config": {
                    "strategyId": strategy_id,
                    "startDate": {"seconds": epoch(_LATER)},
                    "endDate": {"seconds": epoch(_EARLIER)},
                    "initialCapital": {"value": "10000"},
                }
            },
        )
    assert "invalid_argument" in str(exc.value).lower()
