#!/usr/bin/env python3
"""LlamaTrade paper-mode E2E harness.

Fires REAL runs against the live service mesh as the demo tenant and asserts the
full cross-service flow end-to-end. Three legs:

  1. Backtest  — RunBacktest -> the Celery worker executes the real engine over
     the seeded market bars -> GetBacktest -> assert metrics / equity curve /
     trades were produced and persisted. Exercises: strategy compile -> backtest
     engine -> market-data -> result persistence, all cross-service Connect RPC.

  2. Trading / ledger — funded strategy execution -> sleeve allocation -> a fill
     lands -> assert ledger events, position projection, and portfolio
     reconciliation. Exercises: strategy/trading -> ledger -> portfolio.

  3. Strategy lifecycle + funding/wallet — create -> compile -> activate a
     strategy, then deposit -> assert wallet activity -> withdraw (balance-
     neutral). Exercises: strategy CRUD/compiler and the ledger funding path +
     portfolio transaction read model.

The default (simulated) run is deterministic and needs no external services, so
it can run any time and in CI. `--live-alpaca` swaps in real Alpaca paper
credentials for a genuine socket round-trip (needs real paper keys + market
hours) — see the trading leg.

This module is the reusable harness (a standalone CLI) that the `tests/e2e`
pytest suite wraps (see test_paper_mode.py). Because it targets a *running*
deployment — not testcontainers — the pytest suite skips itself when the mesh
isn't reachable (see conftest.py), so it never breaks a plain `pytest` run.

Usage:
    pytest tests/e2e                            # via the pytest suite (skips if mesh down)
    python tests/e2e/harness.py                 # simulated (default, CI-safe)
    python tests/e2e/harness.py --live-alpaca   # real Alpaca paper round-trip
    python tests/e2e/harness.py --only backtest # run a single leg

Prereqs: the mesh must be up (auth/strategy/backtest/trading/portfolio +
market-data), the backtest Celery worker must be running, and the demo account
must be seeded (`make seed-demo`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

# Decoded Connect-JSON payloads are dynamically shaped (proto→JSON); typed as a
# JSON object at the wire boundary, like the codebase's JSONB columns.
JSON = dict[str, Any]

# --- Service endpoints (env-overridable; default to the local split stack) ----
HOSTS = {
    "auth": os.getenv("E2E_AUTH_URL", "http://localhost:8810"),
    "strategy": os.getenv("E2E_STRATEGY_URL", "http://localhost:8820"),
    "backtest": os.getenv("E2E_BACKTEST_URL", "http://localhost:8830"),
    "trading": os.getenv("E2E_TRADING_URL", "http://localhost:8850"),
    "portfolio": os.getenv("E2E_PORTFOLIO_URL", "http://localhost:8860"),
    # LedgerService is served by the portfolio process.
    "ledger": os.getenv("E2E_PORTFOLIO_URL", "http://localhost:8860"),
}
SERVICE = {
    "auth": "llamatrade.AuthService",
    "strategy": "llamatrade.StrategyService",
    "backtest": "llamatrade.BacktestService",
    "trading": "llamatrade.TradingService",
    "portfolio": "llamatrade.PortfolioService",
    "ledger": "llamatrade.LedgerService",
}

DEMO_EMAIL = os.getenv("E2E_DEMO_EMAIL", "demo@llamatrade.ai")
DEMO_PASSWORD = os.getenv("E2E_DEMO_PASSWORD", "demo1234")

# Frozen at import — BEFORE any pytest session fixture can swap REDIS_URL to a
# throwaway testcontainer (see tests/conftest.py). The harness always publishes
# fills to the *live* mesh's Redis, the one the running portfolio consumer reads.
E2E_REDIS_URL = os.getenv("E2E_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6389"

# ANSI helpers (no-op when not a TTY).
_C = sys.stdout.isatty()
GREEN, RED, DIM, BOLD, RST = (
    ("\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m") if _C else ("", "", "", "", "")
)


class E2EError(Exception):
    pass


def call(host: str, method: str, body: JSON, token: str | None = None) -> JSON:
    """POST a Connect-JSON unary request and return the decoded response."""
    url = f"{HOSTS[host]}/{SERVICE[host]}/{method}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise E2EError(f"{host}.{method} -> HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise E2EError(f"{host}.{method} -> unreachable ({e.reason}); is the mesh up?") from e


def epoch(dt: datetime) -> str:
    # proto3 JSON encodes int64 as a string.
    return str(int(dt.timestamp()))


# --- Assertion / reporting helpers -------------------------------------------
_checks: list[tuple[bool, str]] = []


def reset() -> None:
    """Clear accumulated checks (the pytest wrapper calls this before each leg)."""
    _checks.clear()


def failures() -> list[str]:
    """Labels of checks that failed — empty means the run passed."""
    return [label for ok, label in _checks if not ok]


def check(ok: bool, label: str, detail: str = "") -> bool:
    _checks.append((ok, label))
    mark = f"{GREEN}✓{RST}" if ok else f"{RED}✗{RST}"
    line = f"  {mark} {label}"
    if detail:
        line += f"  {DIM}{detail}{RST}"
    print(line)
    return ok


def section(title: str) -> None:
    print(f"\n{BOLD}▸ {title}{RST}")


def status_is(value: object, name: str, number: int) -> bool:
    """Connect-JSON may render an enum as its NAME or its integer."""
    return value == name or value == number or value == str(number)


def _decimal(d: object) -> float:
    """Parse a proto Decimal ({'value': '...'}) — or a plain number — to float."""
    if isinstance(d, dict):
        return float(d.get("value", 0) or 0)
    if isinstance(d, int | float | str):
        return float(d or 0)
    return 0.0


def pick_strategy(strategies: list[JSON]) -> JSON | None:
    """First ACTIVE/PAUSED strategy with symbols (backtestable; drafts are rejected)."""
    for s in strategies:
        if not s.get("symbols"):
            continue
        st = s.get("status")
        if status_is(st, "STRATEGY_STATUS_ACTIVE", 2) or status_is(st, "STRATEGY_STATUS_PAUSED", 3):
            return s
    return None


def run_async(coro: Coroutine[Any, Any, object]) -> object:
    """Run a coroutine even when a loop is already running (e.g. pytest-asyncio)."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


# --- Login -------------------------------------------------------------------
def login() -> JSON:
    section("Login (demo tenant)")
    d = call("auth", "Login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    user = d.get("user", {})
    ctx = {"tenantId": user.get("tenantId", ""), "userId": user.get("id", "")}
    ok = check(
        bool(d.get("accessToken")) and bool(ctx["tenantId"]),
        "authenticated",
        f"tenant={ctx['tenantId'][:8]}…",
    )
    if not ok:
        raise E2EError("login failed — is the demo account seeded (make seed-demo)?")
    return {"token": d["accessToken"], "ctx": ctx}


# --- Leg 1: backtest ---------------------------------------------------------
def leg_backtest(session: JSON) -> None:
    section("Leg 1 — real backtest through the engine")
    token, ctx = session["token"], session["ctx"]

    strat = call(
        "strategy",
        "ListStrategies",
        {"context": ctx, "pagination": {"page": 1, "pageSize": 50}},
        token,
    )
    strategies = strat.get("strategies", [])
    chosen = pick_strategy(strategies)
    check(chosen is not None, "backtestable strategy present", f"{len(strategies)} total")
    if chosen is None:
        raise E2EError("no seeded ACTIVE/PAUSED strategy has symbols to backtest")
    symbols = chosen["symbols"]
    print(f"  {DIM}strategy: {chosen['name']} · {len(symbols)} symbols{RST}")

    cfg = {
        "strategyId": chosen["id"],
        "strategyVersion": chosen.get("version", 0),
        "startDate": {"seconds": epoch(datetime(2026, 1, 2, tzinfo=UTC))},
        "endDate": {"seconds": epoch(datetime(2026, 6, 30, tzinfo=UTC))},
        "initialCapital": {"value": "100000"},
        "symbols": symbols,
        "commission": {"value": "0.001"},
        "slippagePercent": {"value": "0.001"},
        "timeframe": "1D",
        "benchmarkSymbol": "SPY",
        "includeBenchmark": True,
    }
    run = call("backtest", "RunBacktest", {"context": ctx, "config": cfg}, token)
    bt_id = run.get("backtest", {}).get("id")
    check(bool(bt_id), "backtest enqueued", f"id={str(bt_id)[:8]}…")
    if not bt_id:
        raise E2EError(f"RunBacktest returned no id: {run}")

    # Poll GetBacktest until terminal (the worker executes it).
    deadline = time.monotonic() + 180
    last = {}
    while time.monotonic() < deadline:
        got = call("backtest", "GetBacktest", {"context": ctx, "backtestId": bt_id}, token)
        bt = got.get("backtest", {})
        st = bt.get("status")
        if status_is(st, "BACKTEST_STATUS_COMPLETED", 3):
            last = bt
            break
        if status_is(st, "BACKTEST_STATUS_FAILED", 4):
            raise E2EError(f"backtest FAILED: {bt.get('statusMessage')}")
        time.sleep(2)
    else:
        raise E2EError(f"backtest did not complete within 180s (last status {last.get('status')})")

    check(True, "worker executed backtest", "status COMPLETED")
    results = last.get("results", {})
    metrics = results.get("metrics", {})
    curve = results.get("equityCurve", [])
    trades = results.get("trades", [])
    sharpe = metrics.get("sharpeRatio")
    sharpe_val = sharpe.get("value") if isinstance(sharpe, dict) else sharpe
    check(bool(metrics), "metrics produced", f"sharpe={sharpe_val}")
    check(len(curve) > 1, "equity curve non-empty", f"{len(curve)} points")
    check(len(trades) > 0, "trades recorded", f"{len(trades)} trades")


# --- Leg 2: trading -> ledger -> portfolio -----------------------------------
def _publish_ledger_fill(
    tenant_id: str,
    account_id: str,
    sleeve_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: str,
    price: str,
) -> None:
    """Publish a terminal LedgerFill to the real `lt:ledger:fills` stream.

    This stands in for the ONE Alpaca-dependent piece — the runner's fill emitter
    (which has no service-level sim seam). Everything downstream (portfolio's
    consumer, LedgerWriter, FIFO lots, projection) runs for real.
    """

    redis_url = E2E_REDIS_URL

    async def _pub() -> None:
        from llamatrade_events import EventBus, RedisStreamsTransport
        from llamatrade_events.catalog.fills import FillEvents
        from llamatrade_proto.generated import events_pb2

        bus = EventBus(RedisStreamsTransport(redis_url))
        try:
            fill = events_pb2.LedgerFill(
                tenant_id=tenant_id,
                account_id=account_id,
                sleeve_id=sleeve_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                filled_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            await FillEvents(bus=bus).publish_fill(fill)
        finally:
            await bus.close()

    run_async(_pub())


def _position_qty(session: JSON, symbol: str) -> float:
    """Portfolio-level qty for `symbol` (summed across sleeves; 0 if none)."""
    resp = call("portfolio", "GetPositions", {"context": session["ctx"]}, session["token"])
    for p in resp.get("positions", []):
        if p.get("symbol") == symbol:
            return _decimal(p.get("quantity"))  # proto Decimal: {"value": "10.0"}
    return 0.0


def _wait_position(session: JSON, symbol: str, target: float, *, timeout: int = 40) -> float:
    """Poll GetPositions until `symbol` qty reaches ~target (fill ingested)."""
    deadline = time.monotonic() + timeout
    q = _position_qty(session, symbol)
    while time.monotonic() < deadline and abs(q - target) >= 1e-6:
        time.sleep(2)
        q = _position_qty(session, symbol)
    return q


def _paper_creds_id(session: JSON) -> str:
    """The demo's active paper Alpaca credential id (raises if none)."""
    creds = call("auth", "ListAlpacaCredentials", {}, session["token"])
    paper = next(
        (c for c in creds.get("credentials", []) if c.get("isPaper") and c.get("isActive")), None
    )
    if not paper:
        raise E2EError("no active paper Alpaca credential on the demo")
    return paper["id"]


def _unallocated_free(session: JSON, account_id: str) -> float:
    """Free cash in the account's Unallocated sleeve (SLEEVE_TYPE_UNALLOCATED)."""
    resp = call(
        "ledger",
        "ListSleeves",
        {"context": session["ctx"], "accountId": account_id},
        session["token"],
    )
    for s in resp.get("sleeves", []):
        if status_is(s.get("type"), "SLEEVE_TYPE_UNALLOCATED", 4):
            return _decimal(s.get("cash", {}).get("balance"))
    return 0.0


def _wait_newest_txn(
    session: JSON, type_name: str, type_num: int, amount: str, *, timeout: int = 10
) -> bool:
    """Poll until the newest wallet-activity row matches (type, amount).

    The just-made deposit/withdrawal is the most recent ledger event, so the
    newest ``ListTransactions`` row is *ours* — this proves the funding op
    surfaced in the read model, not merely that some row of that amount exists.
    """
    target = float(amount)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = call(
            "portfolio",
            "ListTransactions",
            {"context": session["ctx"], "pagination": {"page": 1, "pageSize": 5}},
            session["token"],
        )
        rows = resp.get("transactions", [])
        if rows:
            top = rows[0]
            if status_is(top.get("type"), type_name, type_num) and (
                abs(_decimal(top.get("amount")) - target) < 1e-6
            ):
                return True
        time.sleep(0.5)
    return False


def leg_trading(session: JSON, *, live_alpaca: bool = False) -> None:
    section("Leg 2 — trading → ledger → portfolio" + (" (LIVE alpaca)" if live_alpaca else ""))
    token, ctx = session["token"], session["ctx"]

    creds_id = _paper_creds_id(session)
    check(bool(creds_id), "paper credentials resolved")

    strat = call(
        "strategy",
        "ListStrategies",
        {"context": ctx, "pagination": {"page": 1, "pageSize": 50}},
        token,
    )
    chosen = pick_strategy(strat.get("strategies", []))
    if chosen is None:
        raise E2EError("no seeded ACTIVE/PAUSED strategy has symbols")
    symbol = chosen["symbols"][0]

    # 1. Fund a fresh execution (strategy → ledger allocate_capital).
    created = call(
        "strategy",
        "CreateExecution",
        {
            "context": ctx,
            "strategyId": chosen["id"],
            "mode": "EXECUTION_MODE_PAPER",
            "allocatedCapital": {"value": "2000"},
            "credentialsId": creds_id,
        },
        token,
    )
    exec_id = created.get("execution", {}).get("id")
    check(bool(exec_id), "execution created", f"id={str(exec_id)[:8]}…")
    if not exec_id:
        raise E2EError(f"CreateExecution returned no id: {created}")
    call("strategy", "StartExecution", {"context": ctx, "executionId": exec_id}, token)

    # 2. Resolve the funded sleeve + account it opened.
    acct = call("ledger", "GetOrCreateAccount", {"context": ctx, "credentialsId": creds_id}, token)
    account_id = acct.get("account", {}).get("id")
    sleeves = call("ledger", "ListSleeves", {"context": ctx, "accountId": account_id}, token)
    sleeve = next(
        (s for s in sleeves.get("sleeves", []) if s.get("strategyExecutionId") == exec_id), None
    )
    check(bool(sleeve), "sleeve funded via strategy→ledger", sleeve and sleeve.get("name"))
    if not sleeve:
        raise E2EError(f"no ledger sleeve for execution {exec_id}")
    sleeve_id = sleeve["id"]

    if live_alpaca:
        _leg_trading_live(session, chosen, symbol, creds_id, exec_id)
        return

    base_qty = _position_qty(session, symbol)

    # 3. A BUY fill → the portfolio projects a position.
    _publish_ledger_fill(
        ctx["tenantId"], account_id, sleeve_id, f"e2e-buy-{exec_id[:8]}", symbol, "buy", "10", "100"
    )
    q = _wait_position(session, symbol, base_qty + 10)
    check(abs(q - (base_qty + 10)) < 1e-6, "buy fill projected to a position", f"{symbol} qty={q}")

    # 4. A SELL fill (FIFO-matches the lot) → the position flattens.
    _publish_ledger_fill(
        ctx["tenantId"],
        account_id,
        sleeve_id,
        f"e2e-sell-{exec_id[:8]}",
        symbol,
        "sell",
        "10",
        "101",
    )
    q = _wait_position(session, symbol, base_qty)
    check(abs(q - base_qty) < 1e-6, "sell fill flattened the position", f"{symbol} qty={q}")

    # 5. *Our* two fills surfaced in the ledger transaction history (the wallet
    #    activity read model) — matched by symbol + type + qty, not just "some
    #    buy exists", so seed rows can't satisfy this vacuously.
    txns = call(
        "portfolio",
        "ListTransactions",
        {"context": ctx, "pagination": {"page": 1, "pageSize": 25}},
        token,
    )

    def _is_fill(t: JSON, type_name: str, type_num: int) -> bool:
        if t.get("symbol") != symbol or not status_is(t.get("type"), type_name, type_num):
            return False
        q = t.get("quantity")
        qty = float(q.get("value", 0)) if isinstance(q, dict) else float(q or 0)
        return abs(qty - 10) < 1e-6

    rows = txns.get("transactions", [])
    has_buy = any(_is_fill(t, "TRANSACTION_TYPE_BUY", 3) for t in rows)
    has_sell = any(_is_fill(t, "TRANSACTION_TYPE_SELL", 4) for t in rows)
    check(
        has_buy and has_sell, "fills recorded in transaction ledger", f"{symbol} buy+sell @ qty 10"
    )

    # 6. Release the sleeve — returns capital to Unallocated (repeatable).
    call(
        "strategy",
        "StopExecution",
        {"context": ctx, "executionId": exec_id, "reason": "e2e cleanup"},
        token,
    )
    check(True, "sleeve released (StopExecution)", "capital returned to Unallocated")


def _leg_trading_live(
    session: JSON, strategy: JSON, symbol: str, creds_id: str, exec_id: str
) -> None:
    """Real Alpaca paper round-trip — needs real paper keys + market hours."""
    token, ctx = session["token"], session["ctx"]
    call(
        "trading",
        "StartSession",
        {
            "context": ctx,
            "strategyId": strategy["id"],
            "mode": "EXECUTION_MODE_PAPER",
            "credentialsId": creds_id,
            "executionId": exec_id,
        },
        token,
    )
    check(True, "live paper session started", "waiting for a real Alpaca fill (≤120s)…")
    base = _position_qty(session, symbol)
    q = _wait_position(session, symbol, base + 1, timeout=120)  # any fill moves it off baseline
    check(q > base, "real Alpaca fill projected to a position", f"{symbol} qty={q}")
    call(
        "strategy",
        "StopExecution",
        {"context": ctx, "executionId": exec_id, "reason": "e2e cleanup"},
        token,
    )


# --- Leg 3: strategy lifecycle + funding/wallet ------------------------------
def leg_strategy_funding(session: JSON) -> None:
    section("Leg 3 — strategy lifecycle + funding/wallet")
    token, ctx = session["token"], session["ctx"]

    # Part A — create -> compile -> activate a strategy. Source a real DSL from a
    # seeded strategy (drift-proof: the seed keeps its DSL valid/current).
    listing = call(
        "strategy",
        "ListStrategies",
        {"context": ctx, "pagination": {"page": 1, "pageSize": 50}},
        token,
    )
    source = pick_strategy(listing.get("strategies", []))
    if source is None:
        raise E2EError("no seeded strategy to source a valid DSL from")
    got = call("strategy", "GetStrategy", {"context": ctx, "strategyId": source["id"]}, token)
    dsl = got.get("strategy", {}).get("dslCode", "")
    symbols = got.get("strategy", {}).get("symbols", [])
    check(bool(dsl), "sourced a valid DSL from a seeded strategy", source.get("name"))
    if not dsl:
        raise E2EError(f"seeded strategy {source['id']} exposes no dslCode")

    result = call(
        "strategy",
        "CompileStrategy",
        {"context": ctx, "dslCode": dsl, "validateOnly": True},
        token,
    ).get("result", {})
    check(
        bool(result.get("success")),
        "DSL compiles via the real compiler",
        f"{len(result.get('errors', []))} errors",
    )

    created = call(
        "strategy",
        "CreateStrategy",
        {
            "context": ctx,
            "name": "E2E Leg 3 strategy",
            "description": "created by the e2e harness",
            "dslCode": dsl,
            "symbols": symbols,
            "timeframe": "1D",
        },
        token,
    )
    new_id = created.get("strategy", {}).get("id")
    check(bool(new_id), "strategy created (DRAFT)", f"id={str(new_id)[:8]}…")
    if not new_id:
        raise E2EError(f"CreateStrategy returned no id: {created}")

    call(
        "strategy",
        "UpdateStrategyStatus",
        {"context": ctx, "strategyId": new_id, "status": "STRATEGY_STATUS_ACTIVE"},
        token,
    )
    activated = call("strategy", "GetStrategy", {"context": ctx, "strategyId": new_id}, token)
    st = activated.get("strategy", {}).get("status")
    check(status_is(st, "STRATEGY_STATUS_ACTIVE", 2), "strategy activated", f"status={st}")

    # Cleanup — remove the throwaway strategy so the demo stays clean/repeatable.
    try:
        call("strategy", "DeleteStrategy", {"context": ctx, "strategyId": new_id}, token)
        cleaned = "deleted"
    except E2EError:
        call(
            "strategy",
            "UpdateStrategyStatus",
            {"context": ctx, "strategyId": new_id, "status": "STRATEGY_STATUS_ARCHIVED"},
            token,
        )
        cleaned = "archived"
    check(True, "strategy cleaned up", cleaned)

    # Part B — deposit -> wallet activity -> withdraw. Balance-neutral, so the
    # leg is repeatable and leaves the demo's free cash unchanged.
    account_id = (
        call(
            "ledger",
            "GetOrCreateAccount",
            {"context": ctx, "credentialsId": _paper_creds_id(session)},
            token,
        )
        .get("account", {})
        .get("id")
    )
    check(bool(account_id), "ledger account resolved", f"id={str(account_id)[:8]}…")
    if not account_id:
        raise E2EError("GetOrCreateAccount returned no account id")

    amount = "5000"
    free_before = _unallocated_free(session, account_id)

    dep = call(
        "ledger",
        "DepositFunds",
        {"context": ctx, "accountId": account_id, "amount": {"value": amount}},
        token,
    )
    free_after = _decimal(dep.get("unallocated", {}).get("cash", {}).get("balance"))
    check(
        abs(free_after - (free_before + 5000)) < 1e-6,
        "deposit credited free cash",
        f"${free_before:,.0f} → ${free_after:,.0f}",
    )
    check(
        _wait_newest_txn(session, "TRANSACTION_TYPE_DEPOSIT", 1, amount),
        "deposit is the newest wallet-activity row",
        f"+${amount}",
    )

    wd = call(
        "ledger",
        "WithdrawFunds",
        {"context": ctx, "accountId": account_id, "amount": {"value": amount}},
        token,
    )
    free_final = _decimal(wd.get("unallocated", {}).get("cash", {}).get("balance"))
    check(
        abs(free_final - free_before) < 1e-6,
        "withdrawal restored balance (leg is neutral)",
        f"${free_after:,.0f} → ${free_final:,.0f}",
    )
    check(
        _wait_newest_txn(session, "TRANSACTION_TYPE_WITHDRAWAL", 2, amount),
        "withdrawal is the newest wallet-activity row",
        f"-${amount}",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="LlamaTrade paper-mode E2E harness")
    ap.add_argument(
        "--live-alpaca",
        action="store_true",
        help="use real Alpaca paper credentials for the trading leg",
    )
    ap.add_argument("--only", choices=["backtest", "trading", "strategy"], help="run a single leg")
    args = ap.parse_args()

    print(
        f"{BOLD}LlamaTrade E2E paper-mode harness{RST}  "
        f"{DIM}({'LIVE alpaca' if args.live_alpaca else 'simulated'}){RST}"
    )

    try:
        session = login()
        if args.only in (None, "backtest"):
            leg_backtest(session)
        if args.only in (None, "trading"):
            leg_trading(session, live_alpaca=args.live_alpaca)
        if args.only in (None, "strategy"):
            leg_strategy_funding(session)
    except E2EError as e:
        print(f"\n{RED}✗ {e}{RST}")
        _checks.append((False, str(e)))

    passed = sum(1 for ok, _ in _checks if ok)
    total = len(_checks)
    failed = total - passed
    print(
        f"\n{BOLD}Result:{RST} {GREEN}{passed} passed{RST}"
        + (f", {RED}{failed} failed{RST}" if failed else "")
        + f" / {total}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
