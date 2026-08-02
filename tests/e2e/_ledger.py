"""Shared ledger/portfolio read helpers for the money-path e2e flows.

These wrap the same LedgerService/PortfolioService calls the wallet and trading
UIs make, so the trading, wallet, and whole-life flows stay DRY. Everything runs
against the live mesh; the only external substitution is the injected LedgerFill
(see ``client.publish_ledger_fill``), which stands in for the Alpaca fill emitter.
"""

from __future__ import annotations

import time

from .client import JSON, MeshClient, decimal_val, status_is


def paper_credential_id(client: MeshClient) -> str:
    """The active paper Alpaca credential id (raises if none)."""
    creds = client.call("auth", "ListAlpacaCredentials", {})
    paper = next(
        (c for c in creds.get("credentials", []) if c.get("isPaper") and c.get("isActive")), None
    )
    assert paper, "expected an active paper Alpaca credential"
    return paper["id"]


def account_id_for(client: MeshClient, credentials_id: str) -> str:
    """Resolve (or open) the ledger account for a credential."""
    acct = client.call("ledger", "GetOrCreateAccount", {"credentialsId": credentials_id})
    account_id = acct.get("account", {}).get("id")
    assert account_id
    return account_id


def unallocated_free(client: MeshClient, account_id: str) -> float:
    """Free cash in the account's Unallocated sleeve (balance - reserved)."""
    resp = client.call("ledger", "ListSleeves", {"accountId": account_id})
    for sleeve in resp.get("sleeves", []):
        if status_is(sleeve.get("type"), "SLEEVE_TYPE_UNALLOCATED", 4):
            return sleeve_free(sleeve)
    return 0.0


def sleeve_free(sleeve: JSON) -> float:
    """Free cash of a sleeve (balance - reserved; free is derived, not stored)."""
    cash = sleeve.get("cash", {})
    return decimal_val(cash.get("balance")) - decimal_val(cash.get("reserved"))


def sleeve_in_account(client: MeshClient, account_id: str, sleeve_id: str) -> JSON | None:
    resp = client.call("ledger", "ListSleeves", {"accountId": account_id})
    return next((s for s in resp.get("sleeves", []) if s.get("id") == sleeve_id), None)


def sleeve_for_execution(client: MeshClient, account_id: str, execution_id: str) -> JSON | None:
    resp = client.call("ledger", "ListSleeves", {"accountId": account_id})
    return next(
        (s for s in resp.get("sleeves", []) if s.get("strategyExecutionId") == execution_id), None
    )


def position_qty(client: MeshClient, symbol: str) -> float:
    """Portfolio-level qty for ``symbol`` (summed across sleeves; 0 if none)."""
    resp = client.call("portfolio", "GetPositions", {})
    for p in resp.get("positions", []):
        if p.get("symbol") == symbol:
            return decimal_val(p.get("quantity"))
    return 0.0


def wait_position(client: MeshClient, symbol: str, target: float, *, timeout: int = 40) -> float:
    """Poll GetPositions until ``symbol`` qty reaches ~target (fill ingested)."""
    deadline = time.monotonic() + timeout
    q = position_qty(client, symbol)
    while time.monotonic() < deadline and abs(q - target) >= 1e-6:
        time.sleep(2)
        q = position_qty(client, symbol)
    return q


def wait_sleeve_closed(
    client: MeshClient, account_id: str, sleeve_id: str, *, timeout: int = 30
) -> JSON | None:
    """Poll ListSleeves until the sleeve reads CLOSED (StopExecution released it)."""
    deadline = time.monotonic() + timeout
    sleeve = sleeve_in_account(client, account_id, sleeve_id)
    while time.monotonic() < deadline:
        if sleeve is not None and status_is(sleeve.get("status"), "SLEEVE_STATUS_CLOSED", 3):
            return sleeve
        time.sleep(2)
        sleeve = sleeve_in_account(client, account_id, sleeve_id)
    return sleeve


def fill_txn_present(
    client: MeshClient, symbol: str, type_name: str, type_num: int, qty: float
) -> bool:
    """True when a fill row of (symbol, type, qty) is in recent wallet activity."""
    txns = client.call("portfolio", "ListTransactions", {"pagination": {"page": 1, "pageSize": 25}})
    for t in txns.get("transactions", []):
        if t.get("symbol") != symbol or not status_is(t.get("type"), type_name, type_num):
            continue
        if abs(decimal_val(t.get("quantity")) - qty) < 1e-6:
            return True
    return False
