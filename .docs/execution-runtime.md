# Strategy Execution Runtime — Backtest & Live

How a compiled strategy actually runs: the shared evaluation core that powers **both** historical
backtests and live trading, the loop and adapters around it, and the exact parity guarantees (and
known differences) between the two.

> **Scope.** This document is the single reference for the *execution runtime*. The strategy
> *language* is [strategy-dsl.md](strategy-dsl.md); how target weights become attributed trades
> across a shared account is [portfolio-ledger.md](portfolio-ledger.md); the per-service
> mechanics are [services/backtesting.md](services/backtesting.md) and
> [services/trading.md](services/trading.md).

---

## The two-layer model

Unification happens at two distinct layers. Keeping them separate is essential to reasoning about
the system, because they are shared to different degrees:

| Layer | Where | What it is | Shared by |
| --- | --- | --- | --- |
| **`StrategySession`** | `libs/runtime/llamatrade_runtime/session.py` | The evaluation + sizing core: merged multi-symbol history → target weights → intended orders | **Both** backtest and live, in production |
| **`StrategyRuntime`** | `libs/runtime/llamatrade_runtime/runtime.py` | The async per-tick loop + pluggable adapters (feed, execution, portfolio, observer) | Backtest always; live via the shared loop behind an opt-in flag |

The evaluation core (`StrategySession`) is the true unification point: the same object, fed the
same way, produces the same intended orders in both paths — so a backtest predicts the live
*decisions* by construction. The loop layer (`StrategyRuntime`) unifies the *driving* of that core;
backtest runs on it today, and live can run on it (`stream()`) behind `TRADING_USE_RUNTIME_LOOP`,
with a hand-rolled loop as the live default.

```
                     ╭───────────────────────────────────────────────╮
                     │   StrategySession  (libs/runtime)             │  ◄── shared by both
                     │   bars → weights → size_orders → orders       │
                     ╰───────────────────────────────────────────────╯
                        ▲                                   ▲
        StrategyRuntime.run()                   StrategySession.evaluate()  (direct)
        + adapters (libs/runtime)               inside the live runner loop
                        │                                   │
              ╭─────────────────╮                 ╭───────────────────────╮
              │ Backtest engine │                 │ Live trading runner   │
              │ (services/…)    │                 │ (services/trading)    │
              ╰─────────────────╯                 ╰───────────────────────╯
                                                   (StrategyRuntime.stream is
                                                    opt-in; see Current state)
```

---

## The shared evaluation core: `StrategySession`

> **Lib boundary.** `libs/dsl` owns the strategy language and the **static AST analysis** that
> compiles a strategy into an execution plan (indicator extraction, required symbols, lookback/window
> — `analysis.py`, `window.py`). `libs/runtime` owns everything that runs that plan over bars — the
> engine, indicators, conditions, sizing, session, and the loop below.

A session is one strategy running over one account/sleeve. It is **stateful across calls** and owns
everything about turning bars into orders:

- **One `CompiledStrategy`** fed the latest bars for **all** symbols together (merged history), so
  cross-symbol conditions (`hold TLT when RSI(SPY) > 70`) evaluate correctly.
- **One portfolio-level rebalance gate** — `should_rebalance` (`libs/runtime/llamatrade_runtime/rebalance.py`),
  date-based and at most once per day.
- **Target-weight computation** — the DSL tree evaluated into `{symbol: weight%}`.
- **Sizing** — `size_orders` (`libs/runtime/llamatrade_runtime/sizing.py`) diffs target weights against current
  holdings and equity into `IntendedOrder`s.

`evaluate(bars, holdings, equity, *, warm_up=False)` is the single entry both paths call:

- `warm_up=True` (or a non-rebalance day) feeds the bars to indicators and returns no orders — it
  keeps history warm and holds the rebalance clock.
- On a rebalance day with enough history, it computes weights and returns the sized orders.

### Sizing rules (identical in both paths)

- **Sells before buys.** `size_orders` returns closes/trims ahead of opens, so cash freed within a
  rebalance funds that rebalance's buys.
- **Sizing mode.** `DRIFT` trades the value delta against a drift band (expresses resizes);
  `BINARY` is all-or-nothing (open when target > 0 and flat, close when target == 0).
- Sizing is against **sleeve equity** in a funded session, not the whole account (see
  [portfolio-ledger.md](portfolio-ledger.md)).

---

## The runtime loop and adapter seams

`StrategyRuntime` drives one `StrategySession` over a `BarFeed`, applies its orders through an
`ExecutionAdapter` against a `Portfolio`, and emits every lifecycle event to a `RuntimeObserver`.
`run()` and `stream()` share the per-tick core `_evaluate_and_execute` and differ only at the ends:

- **`run(feed)`** — bounded feed; `execute` fills synchronously and returns the fill inline;
  liquidates open positions at the end; returns a `RunResult`. (Backtest.)
- **`stream(feed)`** — unbounded feed; `execute` submits and returns "accepted", the fill lands
  out-of-band; never liquidates; no `RunResult`. (Live.)

The four adapter seams (all Protocols) are what each path swaps:

| Seam | `libs/runtime` file | Backtest implementation | Live implementation |
| --- | --- | --- | --- |
| `BarFeed` | `feed.py` | `HistoricalBarFeed` (replays a materialized dataset) | `StreamBarFeed` (live bar stream) |
| `ExecutionAdapter` | `execution.py` | `SimulatedExecution` (fill at close ± slippage, flat fee) | broker-backed submit |
| `Portfolio` | `portfolio.py` | in-memory book (cash, positions, mark-to-market) | ledger-backed view |
| `RuntimeObserver` | `observer.py` | progress publisher | telemetry |

The live adapter implementations live in `services/trading/src/runner/runtime_adapters.py`.

---

## Backtest flow (end-to-end)

1. **Request → quota → config check.** `BacktestServicer.run_backtest` resolves identity, rejects
   config the engine can't honor (`allow_shorting`, `max_position_size`, strategy `parameters`),
   and enforces the monthly plan quota.
2. **Create PENDING + enqueue.** A `PENDING` `Backtest` row is committed, then
   `run_backtest_task.delay(...)` queues it. **Celery is the only execution path**; a failed
   enqueue is compensated (`fail_backtest`).
3. **Worker runs it.** `run_backtest` flips the row to `RUNNING`, opens a progress reporter
   (Redis Stream), and builds the session via `build_session(config_sexpr)` → `StrategySession`
   (`SizingMode.DRIFT`).
4. **Materialize the dataset.** Fetch the required symbols (traded ∪ indicator-only ∪ benchmark),
   extended back by warm-up padding, from the **market-data service** into a content-addressed,
   gap-filled snapshot (`dataset/prepare.py`). No Alpaca in the loop.
5. **Wire the runtime.** `Portfolio(initial_capital)` + `SimulatedExecution(commission, slippage)`
   + a progress observer, driven by `StrategyRuntime.run(HistoricalBarFeed(...), should_abort)`.
6. **Run the loop.** Per date: mark to market; warm-up dates prime indicators without trading;
   trading dates evaluate → size → fill at bar close ± slippage; record equity. Cooperative cancel
   is a Redis flag polled between dates. Open positions liquidate at last prices at the end.
7. **Metrics + benchmark.** `assemble_result` computes return/Sharpe/Sortino/drawdown/win-rate on
   the daily-resampled curve; a benchmark (SPY by default) yields alpha/beta/information-ratio.
8. **Guarded terminal write.** A conditional `UPDATE … WHERE status = RUNNING → COMPLETED`
   (row-count 0 ⇒ lost a cancel race ⇒ discard), then persist `BacktestResult`.
9. **Reads.** `GetBacktest` attaches results inline; `GetBacktestTrades` pages the log;
   `StreamBacktestProgress` tails the Redis Stream. A Celery-beat reaper recovers stale rows.

→ Deep dive: [services/backtesting.md](services/backtesting.md).

---

## Live flow (end-to-end)

1. **Start + preflight.** `LiveSessionService.start_session` checks subscription, resolves per-tenant
   credentials, validates account status/buying-power, and resolves the funded execution's
   `(sleeve_id, account_id)`.
2. **Build the session.** `StrategySession(strategy_sexpr, sizing_mode=DRIFT if funded else BINARY)`
   — the same compiler core as backtest.
3. **Warm-up preload.** `runner/warmup.py::preload_session_history` fetches `min_bars` (+ buffer)
   historical bars per required symbol from the **market-data service** and feeds them as warm-up,
   so the session can rebalance on the first live bar instead of sitting cold until `min_bars`
   real-time bars accumulate. Best-effort: on failure the session starts cold and warms from the
   stream.
4. **Provider seam + runner start.** BYO-credential bar stream, `trade_updates` stream, and a
   per-session trading client are built; `RunnerManager.start_runner` launches `StrategyRunner`.
5. **Runner startup.** Sync equity (sleeve-aware), recover stranded orders, re-publish
   recently-terminal ledger events, connect + subscribe both streams, then spawn four loops:
   equity-sync (~60s), position-reconcile (~300s), trade-stream fill loop, ledger-republish drain.
6. **Main loop (production).** For each live bar, `_evaluate_session` buffers the latest bar per
   symbol and — only when every subscribed symbol has that period's bar, on a new period, market
   open, breaker OK — offloads `session.evaluate(latest_bars, holdings, equity)` to a worker thread
   and submits each resulting order. Degraded (NaN/missing-data) evaluations are surfaced as a
   metric.
7. **Signal → order.** Re-check breaker, reject shorts for sleeve sessions, **fit buys to sleeve
   free cash**, risk-check, then `OrderExecutor.submit_order(..., signal_timestamp=…)`.
8. **Idempotent submit + recovery.** A deterministic `client_order_id = lt-{sha256(session:symbol:
   side:signal_ts)[:16]}` makes a retry after a crash collapse onto the same broker order. A cash
   reservation is published on submit.
9. **Fills are truth.** The trade-stream loop applies broker fills to positions and records
   slippage; position reconciliation vs the broker is read-only for sleeve sessions (the ledger
   owns correction).
10. **Ledger emission.** On terminal events, exactly one `LedgerFill` per order (plus reservation
    releases) is published to the global `ledger:fills` stream, idempotently (see
    [portfolio-ledger.md](portfolio-ledger.md#integration-contract-trading--portfolio--strategy)).

→ Deep dive: [services/trading.md](services/trading.md).

---

## Parity: guarantees and known differences

**Guaranteed identical** (both paths run the same `StrategySession`):

- The evaluation tree, indicators, and their numeric results.
- The portfolio-level rebalance clock (`should_rebalance`).
- Sizing: sells-before-buys ordering, the DRIFT drift band, and fitting buys to available cash.

**Known differences** — the ways the same strategy can behave differently between a backtest and a
live run, and why:

| Aspect | Backtest | Live (production default) |
| --- | --- | --- |
| Loop driver | `StrategyRuntime.run` | hand-rolled `_evaluate_session` (shared `StrategyRuntime.stream` is opt-in via `TRADING_USE_RUNTIME_LOOP`) |
| Evaluation trigger | evaluates on whatever symbols are present for a date | evaluates only when **every** subscribed symbol has the current period's bar (a halted/gappy symbol stalls the rebalance) |
| Sizing mode | always `DRIFT` | `DRIFT` when the session is funded (has a sleeve), else `BINARY` |
| Fill model | full/partial fill at bar close ± slippage, synchronous | real broker orders — partial fills, async settlement |
| Daily price basis | split-adjusted daily bars | raw real-time bars (only diverges for **daily**-timeframe strategies; the live default timeframe is `1Min`) |
| Indicator resolution | bars at the backtest timeframe | bars at the live stream timeframe; a lookback is *N bars at that resolution*, so a daily-lookback indicator on a 1-minute live feed warms over minutes, not days |

---

## Current state vs target

- **Unification is at `StrategySession` today.** Both paths share evaluation and sizing; a backtest
  faithfully predicts live *decisions*.
- **The shared `StrategyRuntime.stream` loop is the target live driver.** It is wired and tested
  (`runtime_adapters.py`) and enabled with `TRADING_USE_RUNTIME_LOOP`; the hand-rolled loop remains
  the default until paper-trading QA validates the swap. Until then, the two live loops
  (`_evaluate_session` and `_run_via_runtime`) must be kept behaviorally aligned.
- **Live warms up from history** (`runner/warmup.py`), so a fresh session trades from its first live
  bar rather than accumulating `min_bars` in real time. The preload fetches at the session timeframe;
  reconciling that with the raw 1-minute live stream is the open item under *Indicator resolution*.

---

## Related documentation

- [Strategy DSL Reference](strategy-dsl.md) — the language and its compilation pipeline.
- [Portfolio Ledger](portfolio-ledger.md) — how live target weights become attributed, reconciled trades.
- [Backtesting Service](services/backtesting.md) — the backtest wiring, dataset materialization, metrics.
- [Trading Service](services/trading.md) — the live runner, order execution, risk, fill emission.
- [Signals & Weights](signals-and-weights.md) — indicator and allocation-method behavior.
