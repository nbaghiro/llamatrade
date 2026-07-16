#!/usr/bin/env python3
"""LlamaTrade paper-mode E2E harness.

Fires REAL runs against the live service mesh as the demo tenant and asserts the
full cross-service flow end-to-end. Two legs:

  1. Backtest  — RunBacktest -> the Celery worker executes the real engine over
     the seeded market bars -> GetBacktest -> assert metrics / equity curve /
     trades were produced and persisted. Exercises: strategy compile -> backtest
     engine -> market-data -> result persistence, all cross-service Connect RPC.

  2. Trading / ledger — funded strategy execution -> sleeve allocation -> a fill
     lands -> assert ledger events, position projection, and portfolio
     reconciliation. Exercises: strategy/trading -> ledger -> portfolio.

The default (simulated) run is deterministic and needs no external services, so
it can run any time and in CI. `--live-alpaca` swaps in real Alpaca paper
credentials for a genuine socket round-trip (needs real paper keys + market
hours) — see the trading leg.

Usage:
    python scripts/e2e_paper.py                 # simulated (default, CI-safe)
    python scripts/e2e_paper.py --live-alpaca   # real Alpaca paper round-trip
    python scripts/e2e_paper.py --only backtest # run a single leg

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
from datetime import UTC, datetime

# --- Service endpoints (env-overridable; default to the local split stack) ----
HOSTS = {
    "auth": os.getenv("E2E_AUTH_URL", "http://localhost:8810"),
    "strategy": os.getenv("E2E_STRATEGY_URL", "http://localhost:8820"),
    "backtest": os.getenv("E2E_BACKTEST_URL", "http://localhost:8830"),
    "trading": os.getenv("E2E_TRADING_URL", "http://localhost:8850"),
    "portfolio": os.getenv("E2E_PORTFOLIO_URL", "http://localhost:8860"),
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

# ANSI helpers (no-op when not a TTY).
_C = sys.stdout.isatty()
GREEN, RED, DIM, BOLD, RST = (
    ("\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m") if _C else ("", "", "", "", "")
)


class E2EError(Exception):
    pass


def call(host: str, method: str, body: dict, token: str | None = None) -> dict:
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


def status_is(value, name: str, number: int) -> bool:
    """Connect-JSON may render an enum as its NAME or its integer."""
    return value == name or value == number or value == str(number)


# --- Login -------------------------------------------------------------------
def login() -> dict:
    section("Login (demo tenant)")
    d = call("auth", "Login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    user = d.get("user", {})
    ctx = {"tenantId": user.get("tenantId", ""), "userId": user.get("id", "")}
    ok = check(bool(d.get("accessToken")) and bool(ctx["tenantId"]), "authenticated",
               f"tenant={ctx['tenantId'][:8]}…")
    if not ok:
        raise E2EError("login failed — is the demo account seeded (make seed-demo)?")
    return {"token": d["accessToken"], "ctx": ctx}


# --- Leg 1: backtest ---------------------------------------------------------
def leg_backtest(session: dict) -> None:
    section("Leg 1 — real backtest through the engine")
    token, ctx = session["token"], session["ctx"]

    strat = call("strategy", "ListStrategies",
                 {"context": ctx, "pagination": {"page": 1, "pageSize": 50}}, token)
    strategies = strat.get("strategies", [])
    with_symbols = [s for s in strategies if s.get("symbols")]
    check(bool(with_symbols), "demo strategies present", f"{len(strategies)} total")
    if not with_symbols:
        raise E2EError("no seeded strategy has symbols to backtest")
    chosen = with_symbols[0]
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
    check(bool(metrics), "metrics produced",
          f"sharpe={metrics.get('sharpeRatio', {}).get('value', '?') if isinstance(metrics.get('sharpeRatio'), dict) else metrics.get('sharpeRatio', '?')}")
    check(len(curve) > 1, "equity curve non-empty", f"{len(curve)} points")
    check(len(trades) > 0, "trades recorded", f"{len(trades)} trades")


def main() -> int:
    ap = argparse.ArgumentParser(description="LlamaTrade paper-mode E2E harness")
    ap.add_argument("--live-alpaca", action="store_true",
                    help="use real Alpaca paper credentials for the trading leg")
    ap.add_argument("--only", choices=["backtest", "trading"], help="run a single leg")
    args = ap.parse_args()

    print(f"{BOLD}LlamaTrade E2E paper-mode harness{RST}  "
          f"{DIM}({'LIVE alpaca' if args.live_alpaca else 'simulated'}){RST}")

    try:
        session = login()
        if args.only in (None, "backtest"):
            leg_backtest(session)
        # trading leg added next
    except E2EError as e:
        print(f"\n{RED}✗ {e}{RST}")
        _checks.append((False, str(e)))

    passed = sum(1 for ok, _ in _checks if ok)
    total = len(_checks)
    failed = total - passed
    print(f"\n{BOLD}Result:{RST} {GREEN}{passed} passed{RST}"
          + (f", {RED}{failed} failed{RST}" if failed else "") + f" / {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
