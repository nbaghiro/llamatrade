"""E2E: the whole life of one strategy id.

Follows a SINGLE strategy id through the entire chain — create -> compile ->
activate -> backtest -> funded execution -> fill round trip -> release -> archive
— asserting ledger state at each boundary. RunBacktest rejects DRAFT strategies,
so activation precedes the backtest. Runs on the demo account (paper credential +
seeded bars); the fill uses qty 7 (distinct from the trading leg's 10) and the
strategy is archived on the way out, so the leg is self-contained.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from . import _ledger
from .client import (
    JSON,
    MeshClient,
    decimal_val,
    epoch,
    pick_strategy,
    publish_ledger_fill,
    status_is,
)

pytestmark = pytest.mark.e2e

BT_START = datetime(2026, 1, 2, tzinfo=UTC)
BT_END = datetime(2026, 6, 30, tzinfo=UTC)
ALLOCATION = "2000"
RELEASE_TOLERANCE = 50.0


def _backtest_config(strategy: JSON) -> JSON:
    return {
        "strategyId": strategy["id"],
        "strategyVersion": strategy.get("version", 0),
        "startDate": {"seconds": epoch(BT_START)},
        "endDate": {"seconds": epoch(BT_END)},
        "initialCapital": {"value": "100000"},
        "symbols": strategy["symbols"],
        "commission": {"value": "0.001"},
        "slippagePercent": {"value": "0.001"},
        "timeframe": "1D",
        "benchmarkSymbol": "SPY",
        "includeBenchmark": True,
    }


def _await_backtest(demo: MeshClient, backtest_id: str, *, timeout: int = 180) -> JSON:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        bt = demo.call("backtest", "GetBacktest", {"backtestId": backtest_id}).get("backtest", {})
        if status_is(bt.get("status"), "BACKTEST_STATUS_COMPLETED", 3):
            return bt
        if status_is(bt.get("status"), "BACKTEST_STATUS_FAILED", 4):
            raise AssertionError(f"backtest FAILED: {bt.get('statusMessage')}")
        time.sleep(2)
    raise AssertionError(f"backtest did not complete within {timeout}s")


def test_single_strategy_whole_life(demo: MeshClient) -> None:
    # Source a valid DSL from a seeded strategy (drift-proof: the seed keeps it current).
    source = pick_strategy(
        demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}}).get(
            "strategies", []
        )
    )
    assert source, "seed should expose a backtestable strategy to source a DSL from"
    src = demo.call("strategy", "GetStrategy", {"strategyId": source["id"]}).get("strategy", {})
    dsl, symbols = src.get("dslCode", ""), src.get("symbols", [])
    assert dsl and symbols

    compiled = demo.call("strategy", "CompileStrategy", {"dslCode": dsl, "validateOnly": True}).get(
        "result", {}
    )
    assert compiled.get("success"), f"sourced DSL should compile: {compiled.get('errors')}"

    created = demo.call(
        "strategy",
        "CreateStrategy",
        {"name": f"E2E whole-life {int(time.time())}", "description": "e2e", "dslCode": dsl},
    )
    strategy_id = created.get("strategy", {}).get("id")
    assert strategy_id, f"CreateStrategy returned no id: {created}"

    exec_id: str | None = None
    stopped = False
    archived = False
    try:
        demo.call(
            "strategy",
            "UpdateStrategyStatus",
            {"strategyId": strategy_id, "status": "STRATEGY_STATUS_ACTIVE"},
        )
        active = demo.call("strategy", "GetStrategy", {"strategyId": strategy_id}).get(
            "strategy", {}
        )
        assert status_is(active.get("status"), "STRATEGY_STATUS_ACTIVE", 2)

        bt = _await_backtest(
            demo,
            demo.call("backtest", "RunBacktest", {"config": _backtest_config(active)})
            .get("backtest", {})
            .get("id"),
        )
        assert bt.get("results", {}).get("metrics"), "backtest should complete with metrics"

        creds_id = _ledger.paper_credential_id(demo)
        account_id = _ledger.account_id_for(demo, creds_id)
        unallocated_before_alloc = _ledger.unallocated_free(demo, account_id)

        exec_id = (
            demo.call(
                "strategy",
                "CreateExecution",
                {
                    "strategyId": strategy_id,
                    "mode": "EXECUTION_MODE_PAPER",
                    "allocatedCapital": {"value": ALLOCATION},
                    "credentialsId": creds_id,
                },
            )
            .get("execution", {})
            .get("id")
        )
        assert exec_id
        demo.call("strategy", "StartExecution", {"executionId": exec_id})

        sleeve = _ledger.sleeve_for_execution(demo, account_id, exec_id)
        assert sleeve, "execution should fund a sleeve"
        sleeve_id = sleeve["id"]
        debited = unallocated_before_alloc - _ledger.unallocated_free(demo, account_id)
        assert abs(debited - float(ALLOCATION)) < 1e-6, (
            f"Unallocated should be debited by {ALLOCATION}"
        )

        symbol = symbols[0]
        base = _ledger.position_qty(demo, symbol)
        publish_ledger_fill(
            demo.ctx["tenantId"],
            account_id,
            sleeve_id,
            f"e2e-life-buy-{exec_id[:8]}",
            symbol,
            "buy",
            "7",
            "100",
        )
        assert abs(_ledger.wait_position(demo, symbol, base + 7) - (base + 7)) < 1e-6
        publish_ledger_fill(
            demo.ctx["tenantId"],
            account_id,
            sleeve_id,
            f"e2e-life-sell-{exec_id[:8]}",
            symbol,
            "sell",
            "7",
            "101",
        )
        assert abs(_ledger.wait_position(demo, symbol, base) - base) < 1e-6

        realized = decimal_val(
            demo.call("ledger", "GetSleeve", {"sleeveId": sleeve_id})
            .get("sleeve", {})
            .get("realizedPnl")
        )
        assert abs(realized - 7.0) < 0.01, (
            f"realized P&L should be 7 (7 shares 100->101), got {realized}"
        )

        unallocated_before_stop = _ledger.unallocated_free(demo, account_id)
        row = _ledger.sleeve_in_account(demo, account_id, sleeve_id)
        released_expected = _ledger.sleeve_free(row) if row else 0.0
        demo.call("strategy", "StopExecution", {"executionId": exec_id, "reason": "e2e whole-life"})
        stopped = True

        closed = _ledger.wait_sleeve_closed(demo, account_id, sleeve_id)
        assert closed and status_is(closed.get("status"), "SLEEVE_STATUS_CLOSED", 3)
        released = _ledger.unallocated_free(demo, account_id) - unallocated_before_stop
        assert abs(released - released_expected) < 0.01
        assert abs(released - float(ALLOCATION)) <= RELEASE_TOLERANCE

        demo.call("strategy", "DeleteStrategy", {"strategyId": strategy_id})
        archived = True
        got = demo.call("strategy", "GetStrategy", {"strategyId": strategy_id}).get("strategy", {})
        assert status_is(got.get("status"), "STRATEGY_STATUS_ARCHIVED", 4)
    finally:
        if exec_id and not stopped:
            demo.try_call(
                "strategy", "StopExecution", {"executionId": exec_id, "reason": "e2e failed run"}
            )
        if not archived:
            demo.try_call("strategy", "DeleteStrategy", {"strategyId": strategy_id})
