"""E2E: stopping an execution WITHOUT flattening re-homes lots, not cash.

The differentiator from the flattened stop (test_trading_lifecycle): when the
sleeve still holds an open position, StopExecution must release only the
sleeve's FREE cash to Unallocated and move the open lot to the Unmanaged sleeve
at cost — a re-home is not a sale, so no P&L is realized and the account-level
position is unchanged. Runs entirely on a throwaway tenant via the scaffold.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest

from . import _ledger, _scaffold
from .client import MeshClient, decimal_val, publish_ledger_fill, status_is

pytestmark = pytest.mark.e2e

_SYMBOL = "E2EHOLD"
_ALLOCATION = "2000"


def test_stop_with_open_position_rehomes_to_unmanaged_at_cost(
    demo: MeshClient, throwaway_tenant: Callable[[str], MeshClient]
) -> None:
    client = throwaway_tenant("rehome")
    funded = _scaffold.fund_tenant_execution(
        client, demo, "E2E open-position stop", allocation=_ALLOCATION
    )

    stopped = False
    try:
        # Buy 5 @ 100: the sleeve holds a $500 lot and $1500 free cash. The fill
        # id is globally deduped, so it must be unique per run.
        publish_ledger_fill(
            client.ctx["tenantId"],
            funded.account_id,
            funded.sleeve_id,
            f"e2e-rehome-{uuid.uuid4().hex[:10]}",
            _SYMBOL,
            "buy",
            "5",
            "100",
        )
        assert abs(_ledger.wait_position(client, _SYMBOL, 5) - 5) < 1e-6

        unallocated_before = _ledger.unallocated_free(client, funded.account_id)
        sleeve_row = _ledger.sleeve_in_account(client, funded.account_id, funded.sleeve_id)
        assert sleeve_row is not None
        free_cash = _ledger.sleeve_free(sleeve_row)
        assert abs(free_cash - (float(_ALLOCATION) - 500)) < 0.01

        client.call(
            "strategy",
            "StopExecution",
            {"executionId": funded.execution_id, "reason": "e2e stop without flatten"},
        )
        stopped = True

        closed = _ledger.wait_sleeve_closed(client, funded.account_id, funded.sleeve_id)
        assert closed and status_is(closed.get("status"), "SLEEVE_STATUS_CLOSED", 3)
        assert abs(decimal_val(closed.get("cash", {}).get("balance"))) < 1e-6, (
            "a closed sleeve must hold no cash"
        )

        # Only the free cash returns to Unallocated; the lot's cost stays invested.
        released = _ledger.unallocated_free(client, funded.account_id) - unallocated_before
        assert abs(released - free_cash) < 0.01, (
            f"released {released}, expected only the free cash {free_cash}"
        )

        # The open lot re-homed to Unmanaged at cost basis.
        sleeves = client.call("ledger", "ListSleeves", {"accountId": funded.account_id})["sleeves"]
        unmanaged = next(s for s in sleeves if status_is(s.get("type"), "SLEEVE_TYPE_UNMANAGED", 3))
        lot = _scaffold.open_lot(client, unmanaged["id"], _SYMBOL)
        assert lot, "the open lot did not re-home to the Unmanaged sleeve"
        assert abs(decimal_val(lot.get("qty")) - 5) < 1e-6
        assert abs(decimal_val(lot.get("costBasis")) - 500) < 1e-6
        assert abs(decimal_val(lot.get("avgPrice")) - 100) < 1e-6

        # A re-home is not a sale: nothing was realized and the position survives.
        assert abs(decimal_val(closed.get("realizedPnl"))) < 1e-6
        assert abs(_ledger.position_qty(client, _SYMBOL) - 5) < 1e-6
    finally:
        if not stopped:
            client.try_call(
                "strategy",
                "StopExecution",
                {"executionId": funded.execution_id, "reason": "e2e failed run"},
            )
        # Retire the placeholder credential so the reconciliation sweep skips
        # this dead account on future runs.
        client.try_call("auth", "DeleteAlpacaCredentials", {"credentialsId": funded.credentials_id})
