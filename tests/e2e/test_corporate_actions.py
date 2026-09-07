"""E2E: corporate actions over the wire (LedgerService/ApplyCorporateAction).

Only APPLY is reachable over the wire: the propose side is an internal
leader-elected loop that reads Alpaca's announcement feed (a real third party),
so the CORPORATE_ACTION_PROPOSED notification cannot be driven here and stays a
documented external seam (see README). The apply path runs entirely on a
throwaway tenant: the scaffold funds an execution, injects fills (the Alpaca
seam), and stops one execution first so its lots re-home to Unmanaged — giving
TWO sleeves holding the symbol, which proves the split fans across sleeves.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import pytest

from . import _ledger, _scaffold
from .client import MeshClient, MeshError, decimal_val, publish_ledger_fill

pytestmark = pytest.mark.e2e

_SYMBOL = "E2ESPLIT"


def _corporate_rows(client: MeshClient) -> list[dict[str, object]]:
    resp = client.call("notification", "ListNotifications", {})
    rows = resp.get("notifications", [])
    return [r for r in rows if r.get("title") == "Corporate action applied"]


def test_split_fans_across_sleeves_and_notifies(
    demo: MeshClient, throwaway_tenant: Callable[[str], MeshClient]
) -> None:
    client = throwaway_tenant("corp")
    # Fill ids are globally deduped (derive_event_id(client_order_id)), so they
    # must be unique per run or re-runs silently drop the fill.
    run_id = uuid.uuid4().hex[:10]

    # Sleeve 1: fund an execution, buy 10 @ 100, then stop WITHOUT flattening —
    # the open lot re-homes to the Unmanaged sleeve at cost (10 sh, $1000 basis).
    first = _scaffold.fund_tenant_execution(client, demo, "E2E corp holder A")
    publish_ledger_fill(
        client.ctx["tenantId"],
        first.account_id,
        first.sleeve_id,
        f"e2e-corp-a-{run_id}",
        _SYMBOL,
        "buy",
        "10",
        "100",
    )
    assert abs(_ledger.wait_position(client, _SYMBOL, 10) - 10) < 1e-6
    client.call(
        "strategy", "StopExecution", {"executionId": first.execution_id, "reason": "re-home lots"}
    )
    assert _ledger.wait_sleeve_closed(client, first.account_id, first.sleeve_id)

    sleeves = client.call("ledger", "ListSleeves", {"accountId": first.account_id})["sleeves"]
    unmanaged = next(s for s in sleeves if s.get("name") == "Unmanaged")

    # Sleeve 2: a second execution (free tier allows one RUNNING at a time, and
    # the first one is stopped) holding 4 @ 50 ($200 basis).
    second = _scaffold.start_funded_execution(
        client, first.account_id, first.strategy_id, first.credentials_id
    )
    stopped = False
    try:
        publish_ledger_fill(
            client.ctx["tenantId"],
            second.account_id,
            second.sleeve_id,
            f"e2e-corp-b-{run_id}",
            _SYMBOL,
            "buy",
            "4",
            "50",
        )
        assert abs(_ledger.wait_position(client, _SYMBOL, 14) - 14) < 1e-6

        external_id = f"e2e-split-{uuid.uuid4().hex[:12]}"
        resp = client.call(
            "ledger",
            "ApplyCorporateAction",
            {
                "accountId": first.account_id,
                "kind": "CORPORATE_ACTION_KIND_SPLIT",
                "symbol": _SYMBOL,
                "ratio": {"value": "2"},
                "externalId": external_id,
            },
        )
        assert int(resp.get("eventsAppended", 0)) == 2, (
            f"a 2-for-1 split over two holder sleeves should append 2 events: {resp}"
        )

        # Both sleeves: qty doubled, cost basis preserved, avg price halved.
        unmanaged_lot = _scaffold.open_lot(client, unmanaged["id"], _SYMBOL)
        assert unmanaged_lot, "Unmanaged sleeve lost its lot on split"
        assert abs(decimal_val(unmanaged_lot.get("qty")) - 20) < 1e-6
        assert abs(decimal_val(unmanaged_lot.get("costBasis")) - 1000) < 1e-6
        assert abs(decimal_val(unmanaged_lot.get("avgPrice")) - 50) < 1e-6

        strategy_lot = _scaffold.open_lot(client, second.sleeve_id, _SYMBOL)
        assert strategy_lot, "strategy sleeve lost its lot on split"
        assert abs(decimal_val(strategy_lot.get("qty")) - 8) < 1e-6
        assert abs(decimal_val(strategy_lot.get("costBasis")) - 200) < 1e-6
        assert abs(decimal_val(strategy_lot.get("avgPrice")) - 25) < 1e-6

        # The portfolio-level projection reflects the doubled quantity.
        assert abs(_ledger.wait_position(client, _SYMBOL, 28) - 28) < 1e-6

        # The CORPORATE_ACTION_APPLIED notification lands in the tenant inbox.
        deadline = time.monotonic() + 30
        rows: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            rows = _corporate_rows(client)
            if rows:
                break
            time.sleep(2)
        assert rows, "CORPORATE_ACTION_APPLIED never surfaced in ListNotifications"
        assert _SYMBOL in str(rows[0].get("message", ""))

        # Idempotency: re-applying the same announcement id changes nothing.
        client.call(
            "ledger",
            "ApplyCorporateAction",
            {
                "accountId": first.account_id,
                "kind": "CORPORATE_ACTION_KIND_SPLIT",
                "symbol": _SYMBOL,
                "ratio": {"value": "2"},
                "externalId": external_id,
            },
        )
        replay_lot = _scaffold.open_lot(client, unmanaged["id"], _SYMBOL)
        assert replay_lot is not None
        assert abs(decimal_val(replay_lot.get("qty")) - 20) < 1e-6, "replayed split re-applied"

        # The apply is invalid without the announcement id keying the dedup.
        with pytest.raises(MeshError) as excinfo:
            client.call(
                "ledger",
                "ApplyCorporateAction",
                {
                    "accountId": first.account_id,
                    "kind": "CORPORATE_ACTION_KIND_SPLIT",
                    "symbol": _SYMBOL,
                    "ratio": {"value": "2"},
                },
            )
        assert excinfo.value.code == "invalid_argument"

        client.call(
            "strategy", "StopExecution", {"executionId": second.execution_id, "reason": "e2e done"}
        )
        stopped = True
    finally:
        if not stopped:
            client.try_call(
                "strategy",
                "StopExecution",
                {"executionId": second.execution_id, "reason": "e2e failed run"},
            )
        # Retire the placeholder credential so the reconciliation sweep skips
        # this dead account on future runs.
        client.try_call("auth", "DeleteAlpacaCredentials", {"credentialsId": first.credentials_id})


def test_apply_rejects_an_unspecified_kind(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("corp-neg")
    with pytest.raises(MeshError) as excinfo:
        client.call(
            "ledger",
            "ApplyCorporateAction",
            {"accountId": str(uuid.uuid4()), "symbol": "AAPL", "ratio": {"value": "2"}},
        )
    assert excinfo.value.code == "invalid_argument"
