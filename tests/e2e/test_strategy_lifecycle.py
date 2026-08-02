"""E2E: the strategy-builder lifecycle exactly as the web UI drives it.

Mirrors the builder path: the Compile pane runs ``CompileStrategy`` (validateOnly)
against the real compiler; Save (new) fires ``CreateStrategy {name, description,
dslCode}`` landing a DRAFT that then shows on the list page (``ListStrategies``);
Open reads ``GetStrategy``; the editor Save fires ``UpdateStrategy``; the
Activate/Pause control fires ``UpdateStrategyStatus``; Clone is ``GetStrategy``
then a fresh ``CreateStrategy``; Delete is ``DeleteStrategy`` (a soft archive that
``GetStrategy`` still resolves as ARCHIVED while the default list hides it).

Valid DSL is sourced once from the seeded demo tenant, but every create/update/
delete runs on its own freshly-registered throwaway tenant so the demo account is
never mutated.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from .client import MeshClient, pick_strategy, status_is

pytestmark = pytest.mark.e2e

JSON = dict[str, Any]


@pytest.fixture
def sourced_dsl(demo: MeshClient) -> JSON:
    """A valid, backtestable strategy read from the seeded demo tenant."""
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    seed = pick_strategy(listing.get("strategies", []))
    assert seed, "seeded demo should expose a backtestable strategy to source DSL from"
    src = demo.call("strategy", "GetStrategy", {"strategyId": seed["id"]}).get("strategy", {})
    assert src.get("dslCode"), "sourced strategy must carry DSL"
    return src


def _create(client: MeshClient, dsl: str, name: str, description: str = "e2e strategy") -> JSON:
    """Save a new strategy the way the builder does (name + description + DSL)."""
    resp = client.call(
        "strategy",
        "CreateStrategy",
        {"name": name, "description": description, "dslCode": dsl},
    )
    return resp.get("strategy", {})


def test_compile_accepts_valid_dsl(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    result = client.call(
        "strategy",
        "CompileStrategy",
        {"dslCode": sourced_dsl["dslCode"], "validateOnly": True},
    ).get("result", {})
    assert result.get("success")
    assert not result.get("errors")


def test_compile_reports_errors_on_broken_dsl(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("strat")
    result = client.call(
        "strategy",
        "CompileStrategy",
        {"dslCode": "(this is not valid ", "validateOnly": True},
    ).get("result", {})
    assert not result.get("success")
    assert result.get("errors"), "the real compiler must return at least one error"


def test_create_lands_a_draft_visible_on_the_list(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Builder Save")
    assert created.get("id")
    assert status_is(created.get("status"), "STRATEGY_STATUS_DRAFT", 1)

    listing = client.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    ids = [s.get("id") for s in listing.get("strategies", [])]
    assert created["id"] in ids


def test_get_returns_the_created_strategy(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Open")

    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]}).get(
        "strategy", {}
    )
    assert fetched.get("id") == created["id"]
    assert fetched.get("name") == "E2E Open"
    assert fetched.get("dslCode") == sourced_dsl["dslCode"]


def test_update_reflects_new_name_and_description(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Before Edit")

    client.call(
        "strategy",
        "UpdateStrategy",
        {
            "strategyId": created["id"],
            "name": "E2E After Edit",
            "description": "edited by e2e",
            "dslCode": sourced_dsl["dslCode"],
            "symbols": sourced_dsl.get("symbols", []),
        },
    )

    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]}).get(
        "strategy", {}
    )
    assert fetched.get("name") == "E2E After Edit"
    assert fetched.get("description") == "edited by e2e"


def test_update_status_activates_the_strategy(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Activate")

    client.call("strategy", "UpdateStrategyStatus", {"strategyId": created["id"], "status": 2})

    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]}).get(
        "strategy", {}
    )
    assert status_is(fetched.get("status"), "STRATEGY_STATUS_ACTIVE", 2)


def test_clone_produces_a_distinct_draft(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    original = _create(client, sourced_dsl["dslCode"], "E2E Original")

    source = client.call("strategy", "GetStrategy", {"strategyId": original["id"]}).get(
        "strategy", {}
    )
    clone = _create(client, source["dslCode"], "E2E Original (copy)")

    assert clone.get("id")
    assert clone["id"] != original["id"]
    assert status_is(clone.get("status"), "STRATEGY_STATUS_DRAFT", 1)


def test_delete_soft_archives_and_hides_from_the_list(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E To Delete")

    deleted = client.call("strategy", "DeleteStrategy", {"strategyId": created["id"]})
    assert deleted.get("success")

    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]}).get(
        "strategy", {}
    )
    assert status_is(fetched.get("status"), "STRATEGY_STATUS_ARCHIVED", 4)

    listing = client.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    ids = [s.get("id") for s in listing.get("strategies", [])]
    assert created["id"] not in ids
