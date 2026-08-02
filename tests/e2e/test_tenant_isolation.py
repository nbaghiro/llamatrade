"""E2E: cross-tenant isolation at the live auth/servicer boundary.

The DB-level RLS suites prove isolation at the session-variable layer; this proves
it over the wire with two REAL registered tenants holding REAL login tokens. Each
call carries the calling client's own resolved identity (never a hand-minted JWT or
a forged wire context), so an attempt by tenant B to read or mutate tenant A's
resource travels with B's identity — exactly the attack a leaking servicer would
let through. The invariant asserted throughout: B never receives A's data, and a
cross-tenant mutation never succeeds.

Observed denial on this mesh: cross-tenant strategy access returns Connect
``not_found`` (HTTP 404) rather than ``permission_denied`` — the servicer scopes
its lookup by tenant, so another tenant's row simply does not exist. The assertions
accept any fail-closed denial (not_found / permission_denied / 403 / 404).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .client import JSON, MeshClient, MeshError, status_is

pytestmark = pytest.mark.e2e

# proto3 StrategyStatus integers (client.py note 2): DRAFT=1 ACTIVE=2 PAUSED=3.
_STATUS_ACTIVE = 2
_DENIAL_CODES = frozenset({"not_found", "permission_denied"})


def _assert_denied(exc: MeshError) -> None:
    """A cross-tenant access must fail closed, never silently return the row."""
    assert exc.http_status in (403, 404) or exc.code in _DENIAL_CODES, (
        f"expected a cross-tenant denial, got HTTP {exc.http_status} [{exc.code}]: {exc.message}"
    )


def _create_strategy(client: MeshClient, dsl: str, name: str) -> JSON:
    resp = client.call(
        "strategy",
        "CreateStrategy",
        {"name": name, "description": "cross-tenant isolation fixture", "dslCode": dsl},
    )
    strategy = resp.get("strategy", {})
    assert strategy.get("id"), f"CreateStrategy returned no id: {resp}"
    return strategy


def _list_strategy_ids(client: MeshClient) -> list[str]:
    resp = client.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    return [s["id"] for s in resp.get("strategies", []) if s.get("id")]


@pytest.fixture(scope="session")
def seeded_dsl(demo: MeshClient) -> str:
    """A real, non-trivial DSL sourced from the seeded demo (the strategies A/B create).

    The demo tenant owns it, so reusing its DSL text (not its rows) keeps the
    throwaway tenants' strategies genuine without touching seeded data.
    """
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    for summary in listing.get("strategies", []):
        if not summary.get("symbols"):
            continue
        full = demo.call("strategy", "GetStrategy", {"strategyId": summary["id"]})
        dsl = full.get("strategy", {}).get("dslCode", "")
        if dsl:
            return dsl
    pytest.skip("seed provides no strategy with a DSL to source from (run make seed-demo)")


def test_tenant_cannot_list_another_tenants_strategies(
    throwaway_tenant: Callable[[str], MeshClient], seeded_dsl: str
) -> None:
    a = throwaway_tenant("iso-a")
    b = throwaway_tenant("iso-b")
    a_strategy = _create_strategy(a, seeded_dsl, "A-only strategy")
    b_strategy = _create_strategy(b, seeded_dsl, "B-only strategy")

    a_ids = _list_strategy_ids(a)
    b_ids = _list_strategy_ids(b)

    assert a_strategy["id"] in a_ids
    assert b_strategy["id"] in b_ids
    assert b_strategy["id"] not in a_ids, "A's listing leaked B's strategy"
    assert a_strategy["id"] not in b_ids, "B's listing leaked A's strategy"


def test_tenant_cannot_read_another_tenants_strategy(
    throwaway_tenant: Callable[[str], MeshClient], seeded_dsl: str
) -> None:
    a = throwaway_tenant("iso-a")
    b = throwaway_tenant("iso-b")
    a_strategy = _create_strategy(a, seeded_dsl, "A-secret strategy")
    a_id = a_strategy["id"]

    # Positive control: the owner reads its own strategy.
    owner_read = a.call("strategy", "GetStrategy", {"strategyId": a_id})
    assert owner_read.get("strategy", {}).get("id") == a_id

    with pytest.raises(MeshError) as excinfo:
        b.call("strategy", "GetStrategy", {"strategyId": a_id})
    _assert_denied(excinfo.value)


def test_tenant_cannot_mutate_another_tenants_strategy(
    throwaway_tenant: Callable[[str], MeshClient], seeded_dsl: str
) -> None:
    a = throwaway_tenant("iso-a")
    b = throwaway_tenant("iso-b")
    a_strategy = _create_strategy(a, seeded_dsl, "A-untouchable strategy")
    a_id = a_strategy["id"]
    original_status = a_strategy.get("status")

    with pytest.raises(MeshError) as status_exc:
        b.call(
            "strategy",
            "UpdateStrategyStatus",
            {"strategyId": a_id, "status": _STATUS_ACTIVE},
        )
    _assert_denied(status_exc.value)

    with pytest.raises(MeshError) as delete_exc:
        b.call("strategy", "DeleteStrategy", {"strategyId": a_id})
    _assert_denied(delete_exc.value)

    # A's strategy survives B's attacks unchanged.
    after = a.call("strategy", "GetStrategy", {"strategyId": a_id})
    strategy = after.get("strategy", {})
    assert strategy.get("id") == a_id, "B's DeleteStrategy removed A's strategy"
    assert strategy.get("status") == original_status, (
        "B's UpdateStrategyStatus altered A's strategy"
    )
    # The status must not have flipped to ACTIVE regardless of how it is rendered.
    assert not status_is(strategy.get("status"), "STRATEGY_STATUS_ACTIVE", _STATUS_ACTIVE)


def test_tenant_cannot_read_another_tenants_ledger_sleeves(
    demo: MeshClient, throwaway_tenant: Callable[[str], MeshClient]
) -> None:
    """A throwaway tenant cannot enumerate or fetch the seeded demo's ledger sleeves.

    Throwaway tenants hold no Alpaca credential, so they cannot bootstrap their own
    ledger account; the demo tenant (real seeded account + sleeves) is the victim and
    a fresh tenant is the attacker. Both calls here are read-only, so the seed is not
    mutated. Skips cleanly when the demo ledger is not seeded.
    """
    creds = demo.call("auth", "ListAlpacaCredentials", {})
    cred_id = next((c["id"] for c in creds.get("credentials", []) if c.get("isActive")), None)
    if not cred_id:
        pytest.skip("demo has no active Alpaca credential — ledger isolation not exercisable")

    account = demo.call("ledger", "GetOrCreateAccount", {"credentialsId": cred_id})
    account_id = account.get("account", {}).get("id")
    if not account_id:
        pytest.skip("demo has no ledger account to probe against")
    demo_sleeves = demo.call("ledger", "ListSleeves", {"accountId": account_id}).get("sleeves", [])
    assert demo_sleeves, "demo ledger account exposes no sleeves — seed drift"
    victim_sleeve_id = demo_sleeves[0]["id"]

    attacker = throwaway_tenant("iso-ledger")

    # Scoped enumeration returns the attacker's own (empty) sleeve set, not demo's.
    leaked = attacker.call("ledger", "ListSleeves", {"accountId": account_id}).get("sleeves", [])
    assert leaked == [], f"attacker enumerated demo's sleeves via its account id: {leaked}"

    with pytest.raises(MeshError) as excinfo:
        attacker.call("ledger", "GetSleeve", {"sleeveId": victim_sleeve_id})
    _assert_denied(excinfo.value)
