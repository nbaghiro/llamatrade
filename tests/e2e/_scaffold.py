"""Self-contained money-path scaffold for throwaway tenants.

A freshly registered tenant can reach the full funded-execution path with no
external dependency: ``CreateAlpacaCredentials`` stores placeholder keys without
a broker check (validation is the separate ``ValidateAlpacaCredentials`` RPC the
UI calls first), ``GetOrCreateAccount`` creates the ledger account unseeded when
the broker backfill fails, and ``DepositFunds`` / ``StartExecution`` are pure
ledger operations. Fills are injected on the real Kafka fills stream (the one
Alpaca seam). This keeps every mutating money-path journey off the shared demo
tenant.

The free tier allows ONE running execution per tenant, so flows that need two
holder sleeves stop the first execution (re-homing its open lots to Unmanaged)
before starting the second.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from . import _ledger
from .client import JSON, MeshClient, pick_strategy

# Placeholder Alpaca keys: stored unvalidated, but they must satisfy the create
# model's minimum lengths (api_key >= 20 chars, api_secret >= 40 chars).
PLACEHOLDER_KEY = "PKE2EPLACEHOLDER0000"
PLACEHOLDER_SECRET = "e2e-placeholder-secret-0000000000000000000000"


@dataclass
class FundedExecution:
    """Handles for a funded strategy execution on a throwaway tenant."""

    credentials_id: str
    account_id: str
    strategy_id: str
    execution_id: str
    sleeve_id: str


def sourced_dsl(demo: MeshClient) -> str:
    """A valid, backtestable DSL sourced (read-only) from the seeded demo tenant."""
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    seed = pick_strategy(listing.get("strategies", []))
    assert seed, "seed must expose a backtestable strategy to source DSL from"
    src = demo.call("strategy", "GetStrategy", {"strategyId": seed["id"]}).get("strategy", {})
    dsl = src.get("dslCode", "")
    assert dsl, "sourced strategy must carry DSL"
    return dsl


def create_paper_credential(client: MeshClient, name: str = "e2e paper") -> str:
    """Store a placeholder paper credential; returns the credential id."""
    resp = client.call(
        "auth",
        "CreateAlpacaCredentials",
        {"name": name, "apiKey": PLACEHOLDER_KEY, "apiSecret": PLACEHOLDER_SECRET, "isPaper": True},
    )
    credentials_id = resp.get("credentials", {}).get("id")
    assert credentials_id, f"CreateAlpacaCredentials returned no id: {resp}"
    return credentials_id


def open_funded_account(client: MeshClient, credentials_id: str, deposit: str = "10000") -> str:
    """Open the ledger account for a credential and deposit free cash."""
    acct = client.call("ledger", "GetOrCreateAccount", {"credentialsId": credentials_id})
    account_id = acct.get("account", {}).get("id")
    assert account_id, f"GetOrCreateAccount returned no account: {acct}"
    client.call(
        "ledger",
        "DepositFunds",
        {"accountId": account_id, "amount": {"value": deposit}, "requestId": str(uuid4())},
    )
    return account_id


def create_active_strategy(client: MeshClient, dsl: str, name: str) -> str:
    """Create a strategy from DSL and activate it; returns the strategy id."""
    created = client.call(
        "strategy",
        "CreateStrategy",
        {"name": name, "description": "e2e scaffold", "dslCode": dsl},
    )
    strategy_id = created.get("strategy", {}).get("id")
    assert strategy_id, f"CreateStrategy returned no id: {created}"
    client.call("strategy", "UpdateStrategyStatus", {"strategyId": strategy_id, "status": 2})
    return strategy_id


def start_funded_execution(
    client: MeshClient,
    account_id: str,
    strategy_id: str,
    credentials_id: str,
    allocation: str = "2000",
) -> FundedExecution:
    """CreateExecution + StartExecution; returns handles including the funded sleeve."""
    created = client.call(
        "strategy",
        "CreateExecution",
        {
            "strategyId": strategy_id,
            "mode": "EXECUTION_MODE_PAPER",
            "allocatedCapital": {"value": allocation},
            "credentialsId": credentials_id,
        },
    )
    execution_id = created.get("execution", {}).get("id")
    assert execution_id, f"CreateExecution returned no id: {created}"
    client.call("strategy", "StartExecution", {"executionId": execution_id})
    sleeve = _ledger.sleeve_for_execution(client, account_id, execution_id)
    assert sleeve, f"execution {execution_id} did not fund a ledger sleeve"
    return FundedExecution(
        credentials_id=credentials_id,
        account_id=account_id,
        strategy_id=strategy_id,
        execution_id=execution_id,
        sleeve_id=sleeve["id"],
    )


def fund_tenant_execution(
    client: MeshClient,
    demo: MeshClient,
    name: str,
    *,
    deposit: str = "10000",
    allocation: str = "2000",
) -> FundedExecution:
    """The full scaffold: credential -> account -> deposit -> strategy -> execution."""
    credentials_id = create_paper_credential(client)
    account_id = open_funded_account(client, credentials_id, deposit=deposit)
    strategy_id = create_active_strategy(client, sourced_dsl(demo), name)
    return start_funded_execution(client, account_id, strategy_id, credentials_id, allocation)


def open_lot(client: MeshClient, sleeve_id: str, symbol: str) -> JSON | None:
    """The open lot for ``symbol`` in a sleeve (GetSleeve blends one lot per symbol)."""
    resp = client.call("ledger", "GetSleeve", {"sleeveId": sleeve_id})
    return next(
        (lot for lot in resp.get("lots", []) if lot.get("symbol") == symbol and lot.get("isOpen")),
        None,
    )
