"""E2E: trading lifecycle — funded execution, fills, and the live session RPCs.

Two real paths against the running mesh:

  * Funded execution + fill round trip — strategy CreateExecution/StartExecution
    allocates a sleeve via the ledger; a terminal LedgerFill (the Alpaca seam) is
    ingested by the portfolio consumer, projects a position, and StopExecution
    releases the sleeve back to Unallocated. FIFO lots, projection and the
    transaction read model all run for real.

  * Live session lifecycle — TradingService StartSession -> ListSessions ->
    ListOrders/ListPositions -> GetSession -> StopSession, driven directly (the
    web UI wires this only on mobile). Exercises the real session record and
    runtime lifecycle over the wire, including the subscription gate.

Runs against the seeded demo account (it needs the paper credential and funded
Unallocated cash); assertions are delta-based so the leg is repeatable.
"""

from __future__ import annotations

import pytest

from . import _ledger
from .client import MeshClient, MeshError, pick_strategy, publish_ledger_fill, status_is

pytestmark = pytest.mark.e2e

ALLOCATION = "2000"
RELEASE_TOLERANCE = 50.0


def _backtestable_strategy(demo: MeshClient) -> dict:
    strat = pick_strategy(
        demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}}).get(
            "strategies", []
        )
    )
    assert strat, "seed should expose a backtestable ACTIVE/PAUSED strategy with symbols"
    return strat


def test_execution_fill_roundtrip_projects_and_releases(demo: MeshClient) -> None:
    creds_id = _ledger.paper_credential_id(demo)
    strat = _backtestable_strategy(demo)
    symbol = strat["symbols"][0]

    created = demo.call(
        "strategy",
        "CreateExecution",
        {
            "strategyId": strat["id"],
            "mode": "EXECUTION_MODE_PAPER",
            "allocatedCapital": {"value": ALLOCATION},
            "credentialsId": creds_id,
        },
    )
    exec_id = created.get("execution", {}).get("id")
    assert exec_id, f"CreateExecution returned no id: {created}"

    stopped = False
    try:
        demo.call("strategy", "StartExecution", {"executionId": exec_id})
        account_id = _ledger.account_id_for(demo, creds_id)
        sleeve = _ledger.sleeve_for_execution(demo, account_id, exec_id)
        assert sleeve, "the execution should fund a ledger sleeve"
        sleeve_id = sleeve["id"]

        base = _ledger.position_qty(demo, symbol)

        # A BUY fill → the portfolio projects a position.
        publish_ledger_fill(
            demo.ctx["tenantId"],
            account_id,
            sleeve_id,
            f"e2e-buy-{exec_id[:8]}",
            symbol,
            "buy",
            "10",
            "100",
        )
        q = _ledger.wait_position(demo, symbol, base + 10)
        assert abs(q - (base + 10)) < 1e-6, f"buy fill did not project ({symbol} qty={q})"

        # A SELL fill (FIFO-matches the lot) → the position flattens.
        publish_ledger_fill(
            demo.ctx["tenantId"],
            account_id,
            sleeve_id,
            f"e2e-sell-{exec_id[:8]}",
            symbol,
            "sell",
            "10",
            "101",
        )
        q = _ledger.wait_position(demo, symbol, base)
        assert abs(q - base) < 1e-6, f"sell fill did not flatten ({symbol} qty={q})"

        # Both fills surfaced in the transaction read model (matched by symbol+type+qty).
        assert _ledger.fill_txn_present(demo, symbol, "TRANSACTION_TYPE_BUY", 3, 10)
        assert _ledger.fill_txn_present(demo, symbol, "TRANSACTION_TYPE_SELL", 4, 10)

        # StopExecution closes the sleeve and returns capital to Unallocated.
        unallocated_before = _ledger.unallocated_free(demo, account_id)
        row = _ledger.sleeve_in_account(demo, account_id, sleeve_id)
        released_expected = _ledger.sleeve_free(row) if row else 0.0
        demo.call("strategy", "StopExecution", {"executionId": exec_id, "reason": "e2e cleanup"})
        stopped = True

        closed = _ledger.wait_sleeve_closed(demo, account_id, sleeve_id)
        assert closed and status_is(closed.get("status"), "SLEEVE_STATUS_CLOSED", 3)
        released = _ledger.unallocated_free(demo, account_id) - unallocated_before
        assert abs(released - released_expected) < 0.01
        assert abs(released - float(ALLOCATION)) <= RELEASE_TOLERANCE
    finally:
        if not stopped:
            demo.try_call(
                "strategy", "StopExecution", {"executionId": exec_id, "reason": "e2e failed run"}
            )


def test_start_session_validates_broker_credentials(demo: MeshClient) -> None:
    # StartSession drives the real path: subscription gate, then a live Alpaca
    # credential check. The seeded demo keys are placeholders, so a real paper
    # session must fail closed with a precondition error, not open a session on
    # unverified credentials. (The happy path runs under E2E_LIVE_ALPACA.)
    creds_id = _ledger.paper_credential_id(demo)
    strat = _backtestable_strategy(demo)
    with pytest.raises(MeshError) as excinfo:
        demo.call(
            "trading",
            "StartSession",
            {"strategyId": strat["id"], "mode": "EXECUTION_MODE_PAPER", "credentialsId": creds_id},
        )
    err = excinfo.value
    assert err.http_status in (400, 403) or err.code in (
        "failed_precondition",
        "invalid_argument",
        "permission_denied",
    )


@pytest.mark.live_alpaca
def test_live_session_lifecycle(demo: MeshClient) -> None:
    creds_id = _ledger.paper_credential_id(demo)
    strat = _backtestable_strategy(demo)

    started = demo.call(
        "trading",
        "StartSession",
        {"strategyId": strat["id"], "mode": "EXECUTION_MODE_PAPER", "credentialsId": creds_id},
    )
    session_id = started.get("session", {}).get("id")
    assert session_id, f"StartSession returned no session: {started}"

    try:
        listing = demo.call("trading", "ListSessions", {"pagination": {"page": 1, "pageSize": 100}})
        assert session_id in [s.get("id") for s in listing.get("sessions", [])]

        # The blotter reads (orders across all sessions, positions for this one).
        demo.call("trading", "ListOrders", {"pagination": {"page": 1, "pageSize": 50}})
        demo.call("trading", "ListPositions", {"sessionId": session_id})

        got = demo.call("trading", "GetSession", {"sessionId": session_id})
        assert got.get("session", {}).get("id") == session_id
    finally:
        demo.call("trading", "StopSession", {"sessionId": session_id})

    after = demo.call("trading", "GetSession", {"sessionId": session_id}).get("session", {})
    assert not status_is(after.get("status"), "EXECUTION_STATUS_RUNNING", 2), (
        f"session should not be RUNNING after StopSession (status={after.get('status')})"
    )
