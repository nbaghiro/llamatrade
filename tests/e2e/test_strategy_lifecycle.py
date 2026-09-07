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


def _rename_in_dsl(dsl: str, new_name: str) -> str:
    """Rewrite the quoted strategy name, the smallest edit that is still valid DSL."""
    head, _, rest = dsl.partition('"')
    _, _, tail = rest.partition('"')
    return f'{head}"{new_name}"{tail}'


def test_edited_dsl_round_trips_through_save_and_reopen(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    """The builder's core loop: edit the DSL, save, reopen, get the same text back.

    A save that normalizes or re-serializes the DSL would silently rewrite the
    user's source, so this compares the reopened text byte for byte.
    """
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Round Trip")
    edited = _rename_in_dsl(sourced_dsl["dslCode"], "Renamed By E2E")
    assert edited != sourced_dsl["dslCode"], "the edit must actually change the DSL"

    client.call(
        "strategy",
        "UpdateStrategy",
        {
            "strategyId": created["id"],
            "name": "E2E Round Trip",
            "dslCode": edited,
            "symbols": sourced_dsl.get("symbols", []),
            "changeSummary": "renamed the strategy",
        },
    )

    reopened = client.call("strategy", "GetStrategy", {"strategyId": created["id"]}).get(
        "strategy", {}
    )
    assert reopened.get("dslCode") == edited
    assert reopened.get("symbols"), "symbols stay derived after an edit"


def test_version_history_records_each_save(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    """The builder's history pane: every save adds a version carrying its DSL."""
    client = throwaway_tenant("strat")
    created = _create(client, sourced_dsl["dslCode"], "E2E Versioned")
    edited = _rename_in_dsl(sourced_dsl["dslCode"], "Second Revision")

    client.call(
        "strategy",
        "UpdateStrategy",
        {
            "strategyId": created["id"],
            "name": "E2E Versioned",
            "dslCode": edited,
            "symbols": sourced_dsl.get("symbols", []),
            "changeSummary": "second revision",
        },
    )

    versions = client.call("strategy", "ListStrategyVersions", {"strategyId": created["id"]}).get(
        "versions", []
    )

    assert versions, "a saved edit must leave a version behind"
    numbers = [v.get("version") for v in versions]
    assert len(set(numbers)) == len(numbers), f"version numbers must be unique: {numbers}"
    assert any(v.get("dslCode") == edited for v in versions), (
        "the edited DSL must be recoverable from history"
    )
    assert any("second revision" in (v.get("changeSummary") or "") for v in versions)


def test_version_history_never_leaks_across_tenants(
    throwaway_tenant: Callable[[str], MeshClient], sourced_dsl: JSON
) -> None:
    """History carries the full DSL, so a missing tenant filter would leak source.

    The handler resolves the parent strategy under the caller's tenant first, so a
    foreign id yields an empty list rather than NOT_FOUND. Emptiness is the
    security property worth pinning; the shape differs from GetStrategy.
    """
    owner = throwaway_tenant("strat-owner")
    intruder = throwaway_tenant("strat-intruder")
    created = _create(owner, sourced_dsl["dslCode"], "E2E Private History")
    owner.call(
        "strategy",
        "UpdateStrategy",
        {
            "strategyId": created["id"],
            "name": "E2E Private History",
            "dslCode": _rename_in_dsl(sourced_dsl["dslCode"], "Owner Revision"),
            "symbols": sourced_dsl.get("symbols", []),
            "changeSummary": "owner-only revision",
        },
    )
    assert owner.call("strategy", "ListStrategyVersions", {"strategyId": created["id"]}).get(
        "versions"
    ), "the owner must see the history this test is checking is private"

    stolen = intruder.call("strategy", "ListStrategyVersions", {"strategyId": created["id"]})
    assert stolen.get("versions", []) == []


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

    clone = client.call(
        "strategy",
        "CloneStrategy",
        {"strategyId": original["id"], "newName": "E2E Original clone", "version": 0},
    ).get("strategy", {})

    assert clone.get("id")
    assert clone["id"] != original["id"]
    assert clone.get("name") == "E2E Original clone"
    assert status_is(clone.get("status"), "STRATEGY_STATUS_DRAFT", 1)
    assert clone.get("description") == "Cloned from: E2E Original"

    # The clone carries the source DSL and re-derived symbols.
    fetched = client.call("strategy", "GetStrategy", {"strategyId": clone["id"]}).get(
        "strategy", {}
    )
    assert fetched.get("dslCode") == sourced_dsl["dslCode"]
    # Symbols are re-derived from the DSL, so ordering may differ from the source row.
    assert set(fetched.get("symbols", [])) == set(sourced_dsl.get("symbols", []))


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
