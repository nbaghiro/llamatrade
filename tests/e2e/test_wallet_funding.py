"""E2E: wallet funding — resolve the ledger account, deposit, and withdraw.

Mirrors the Wallet / AddFunds UI flow: resolve the paper account
(ListAlpacaCredentials -> LedgerService/GetOrCreateAccount), DepositFunds, see the
row surface in ListTransactions, then WithdrawFunds. The deposit/withdraw pair is
balance-neutral, so this runs against the seeded demo account repeatably. Every
call is a real ledger event through the running portfolio process.
"""

from __future__ import annotations

import time

import pytest

from . import _ledger
from .client import MeshClient, decimal_val, status_is

pytestmark = pytest.mark.e2e

DEPOSIT = "5000"


def _paper_account_id(demo: MeshClient) -> str:
    """Resolve the demo's paper ledger account the way the wallet UI does."""
    return _ledger.account_id_for(demo, _ledger.paper_credential_id(demo))


def test_deposit_credits_free_cash_then_withdraw_restores(demo: MeshClient) -> None:
    account_id = _paper_account_id(demo)
    before = _ledger.unallocated_free(demo, account_id)

    dep = demo.call(
        "ledger", "DepositFunds", {"accountId": account_id, "amount": {"value": DEPOSIT}}
    )
    after = decimal_val(dep.get("unallocated", {}).get("cash", {}).get("balance"))
    assert abs(after - (before + float(DEPOSIT))) < 1e-6

    wd = demo.call(
        "ledger", "WithdrawFunds", {"accountId": account_id, "amount": {"value": DEPOSIT}}
    )
    final = decimal_val(wd.get("unallocated", {}).get("cash", {}).get("balance"))
    assert abs(final - before) < 1e-6


def test_deposit_surfaces_as_newest_wallet_activity(demo: MeshClient) -> None:
    account_id = _paper_account_id(demo)
    try:
        demo.call("ledger", "DepositFunds", {"accountId": account_id, "amount": {"value": DEPOSIT}})
        # The just-made deposit is the most recent ledger event, so the newest
        # ListTransactions row is ours — proves the funding op reached the read model.
        surfaced = False
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = demo.call(
                "portfolio", "ListTransactions", {"pagination": {"page": 1, "pageSize": 5}}
            ).get("transactions", [])
            if rows:
                top = rows[0]
                if status_is(top.get("type"), "TRANSACTION_TYPE_DEPOSIT", 1) and (
                    abs(decimal_val(top.get("amount")) - float(DEPOSIT)) < 1e-6
                ):
                    surfaced = True
                    break
            time.sleep(0.5)
        assert surfaced, "deposit should be the newest wallet-activity row"
    finally:
        # Keep the leg balance-neutral even if the assertion above fails.
        demo.try_call(
            "ledger", "WithdrawFunds", {"accountId": account_id, "amount": {"value": DEPOSIT}}
        )
