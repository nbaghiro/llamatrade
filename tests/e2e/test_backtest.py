"""E2E: the backtest run/stream/results flow as the Backtest page drives it.

Mirrors the trading UI backtest path: the Run Console builds a BacktestConfig and
fires ``BacktestService/RunBacktest``, subscribes to ``StreamBacktestProgress`` to
drive the live status/progress bar, and on completion loads ``GetBacktest`` for
the metrics, equity curve and trade blotter; the blotter pages through
``GetBacktestTrades``. The Backtests list reads ``ListBacktests`` and the Cancel
control fires ``CancelBacktest``.

Every run executes for real on the Celery worker over the seeded market bars
(~10-40s), so completion is polled with a generous timeout.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import pytest

from .client import MeshClient, decimal_val, epoch, pick_strategy, status_is

pytestmark = pytest.mark.e2e

JSON = dict[str, Any]

# Backtest window inside the seed's daily-bar coverage (see test_seed_contract).
_START = datetime(2026, 1, 2, tzinfo=UTC)
_END = datetime(2026, 6, 30, tzinfo=UTC)

# BacktestStatus (verified from the live stream): the servicer renders enums as
# their proto NAME, but status_is also accepts the integer form.
_RUNNING = ("BACKTEST_STATUS_RUNNING", 2)
_COMPLETED = ("BACKTEST_STATUS_COMPLETED", 3)
_FAILED = ("BACKTEST_STATUS_FAILED", 4)
_CANCELLED = ("BACKTEST_STATUS_CANCELLED", 5)


def _config(strategy: JSON) -> JSON:
    """A RunBacktest config over the harness window for a listed strategy."""
    return {
        "strategyId": strategy["id"],
        "strategyVersion": strategy.get("version", 0),
        "startDate": {"seconds": epoch(_START)},
        "endDate": {"seconds": epoch(_END)},
        "initialCapital": {"value": "100000"},
        "symbols": strategy["symbols"],
        "commission": {"value": "0.001"},
        "slippagePercent": {"value": "0.001"},
        "timeframe": "1D",
        "benchmarkSymbol": "SPY",
        "includeBenchmark": True,
    }


def _backtestable_strategy(demo: MeshClient) -> JSON:
    listing = demo.call("strategy", "ListStrategies", {"pagination": {"page": 1, "pageSize": 50}})
    chosen = pick_strategy(listing.get("strategies", []))
    assert chosen is not None, "seed must expose an ACTIVE/PAUSED strategy with symbols to backtest"
    return chosen


def _poll_until_terminal(demo: MeshClient, backtest_id: str, *, timeout: float = 180.0) -> JSON:
    """Poll GetBacktest until the worker drives the run to a terminal state."""
    deadline = time.monotonic() + timeout
    run: JSON = {}
    while time.monotonic() < deadline:
        run = demo.call("backtest", "GetBacktest", {"backtestId": backtest_id}).get("backtest", {})
        status = run.get("status")
        if any(status_is(status, name, num) for name, num in (_COMPLETED, _FAILED, _CANCELLED)):
            return run
        time.sleep(2)
    raise AssertionError(
        f"backtest {backtest_id} did not reach a terminal state within {timeout:.0f}s "
        f"(last status {run.get('status')})"
    )


@pytest.fixture(scope="module")
def completed_run(demo: MeshClient) -> JSON:
    """One real backtest driven through RunBacktest + StreamBacktestProgress to COMPLETED.

    Streams the live progress trace and then reads the persisted run, so the four
    read-path tests share a single worker execution instead of each running one.
    """
    strategy = _backtestable_strategy(demo)
    started = demo.call("backtest", "RunBacktest", {"config": _config(strategy)})
    backtest_id = started.get("backtest", {}).get("id")
    assert backtest_id, f"RunBacktest returned no id: {started}"

    statuses: list[object] = []
    max_progress = 0
    for frame in demo.stream("backtest", "StreamBacktestProgress", {"backtestId": backtest_id}):
        statuses.append(frame.get("status"))
        # progressPercent is omitted (proto3 default) on the 0% frames.
        max_progress = max(max_progress, int(frame.get("progressPercent") or 0))

    run = _poll_until_terminal(demo, backtest_id)
    assert status_is(run.get("status"), *_COMPLETED), (
        f"backtest did not complete: status={run.get('status')} msg={run.get('statusMessage')}"
    )
    return {"id": backtest_id, "statuses": statuses, "max_progress": max_progress, "run": run}


def test_run_streams_progress_through_to_completion(completed_run: JSON) -> None:
    """The progress stream reports RUNNING, reaches COMPLETED, and hits 100%."""
    statuses = completed_run["statuses"]
    assert statuses, "StreamBacktestProgress yielded no frames"
    assert any(status_is(s, *_RUNNING) for s in statuses), "stream never reported RUNNING"
    assert any(status_is(s, *_COMPLETED) for s in statuses), "stream never reported COMPLETED"
    assert completed_run["max_progress"] == 100, "progress never reached 100%"


def test_completed_run_exposes_metrics_curve_and_trades(completed_run: JSON) -> None:
    """GetBacktest returns the metrics, equity curve and trades the UI renders."""
    results = completed_run["run"].get("results", {})
    metrics = results.get("metrics", {})
    assert metrics, "completed backtest exposes no metrics"
    assert isinstance(decimal_val(metrics.get("sharpeRatio")), float)
    assert len(results.get("equityCurve", [])) > 1, "equity curve should have multiple points"
    assert len(results.get("trades", [])) > 0, "a completed run should record trades"


def test_trades_pagination_returns_the_full_log(demo: MeshClient, completed_run: JSON) -> None:
    """GetBacktestTrades pages the full trade log (GetBacktest returns a preview)."""
    preview = len(completed_run["run"].get("results", {}).get("trades", []))
    resp = demo.call(
        "backtest",
        "GetBacktestTrades",
        {"backtestId": completed_run["id"], "pagination": {"page": 1, "pageSize": 200}},
    )
    trades = resp.get("trades", [])
    assert trades, "GetBacktestTrades returned no trades"
    assert len(trades) >= preview, "paged trade log should cover the GetBacktest preview count"


def test_list_backtests_includes_the_run(demo: MeshClient, completed_run: JSON) -> None:
    """The new run shows up in the tenant's ListBacktests page."""
    listing = demo.call(
        "backtest",
        "ListBacktests",
        {"strategyId": "", "pagination": {"page": 1, "pageSize": 50}},
    )
    ids = [b.get("id") for b in listing.get("backtests", [])]
    assert completed_run["id"] in ids


def test_cancel_moves_a_run_to_a_terminal_state(demo: MeshClient) -> None:
    """CancelBacktest returns cleanly and the run settles CANCELLED (or COMPLETED if it raced)."""
    strategy = _backtestable_strategy(demo)
    started = demo.call("backtest", "RunBacktest", {"config": _config(strategy)})
    backtest_id = started.get("backtest", {}).get("id")
    assert backtest_id, f"RunBacktest returned no id: {started}"

    cancelled = demo.call("backtest", "CancelBacktest", {"backtestId": backtest_id})
    assert cancelled.get("backtest"), "CancelBacktest returned no backtest"

    run = _poll_until_terminal(demo, backtest_id)
    status = run.get("status")
    assert status_is(status, *_CANCELLED) or status_is(status, *_COMPLETED), (
        f"expected a terminal CANCELLED or COMPLETED run, got {status}"
    )
