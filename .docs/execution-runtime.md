# Strategy Execution — Runtime & Walkthrough

How a compiled strategy actually runs: the shared evaluation core that powers **both** historical
backtests and live trading, the loop and adapters around it, and the exact parity guarantees (and
known differences) between the two. The final section walks one real strategy end to end —
backtest, funding, and live — with concrete dollars, bars, orders, and ledger events.

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
  calendar-based on the strategy's `:rebalance` cadence (daily / weekly / monthly / quarterly /
  annually) and never twice on the same calendar day.
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

The four adapter seams (three Protocols; `Portfolio` is a concrete base the live adapter
subclasses) are what each path swaps:

| Seam | `libs/runtime` file | Backtest implementation | Live implementation |
| --- | --- | --- | --- |
| `BarFeed` | `feed.py` | `HistoricalBarFeed` (replays a materialized dataset) | `StreamBarFeed` (live bar stream) |
| `ExecutionAdapter` | `execution.py` | `SimulatedExecution` (fill at close ± slippage, flat fee) | `RunnerExecution` (broker-backed submit) |
| `Portfolio` | `portfolio.py` | in-memory book (cash, positions, mark-to-market) | `LedgerPortfolio` (ledger-backed view) |
| `RuntimeObserver` | `observer.py` | progress publisher | telemetry |

The live adapter implementations live in `services/trading/src/runner/runtime_adapters.py`.

---

## Backtest flow (end-to-end)

Backtests run **only** as Celery tasks — the `RunBacktest` RPC enqueues and returns; nothing
executes in the API process. The worker replays a materialized historical dataset through the shared
`StrategyRuntime.run`.

**A. Enqueue (RPC → Celery, in the API process).**

1. `RunBacktest` (`services/backtest/src/grpc/servicer.py`) resolves identity, rejects config the
   engine can't honor (`allow_shorting`, `max_position_size`), enforces the monthly plan quota, and
   commits a `PENDING` `Backtest` row — capturing the **run granularity** (`timeframe`, an
   independent run parameter) and `:benchmark` (SPY by default).
2. It calls `queue_backtest` → `run_backtest_task.delay(backtest_id, tenant_id)`
   (`services/backtest/src/services/backtest_service.py`). A failed enqueue is compensated with
   `fail_backtest`, so a committed PENDING row never strands.

**B. Worker execution (task → service).**

3. A worker runs `run_backtest_task` (`workers/celery_tasks.py`), bridges sync→async, and calls
   `BacktestService.run_backtest` under a fresh DB session. `MarketDataError` retries (row reset to
   PENDING); other errors are terminal.

**C. Compile + materialize the dataset (`_run_backtest_inner`).**

4. Flip the row to `RUNNING`; open a Kafka progress reporter (`lt.backtest.progress`, keyed by backtest id); resolve
   `actual_timeframe = timeframe or "1D"` (the run's bar granularity — not a strategy property).
5. **Compile:** `build_session(config_sexpr)` → `StrategySession` (`SizingMode.DRIFT` by default;
   the run's config can select `BINARY` and set the drift band / notional floor per run), yielding
   `min_bars`, the required symbols (traded ∪ indicator-only ∪ benchmark), and the indicator plan.
6. **Fetch history from the market-data service** (never Alpaca directly): `warmup_padding_days`
   extends the window back so indicators are warm on day one; `DatasetSpec.create` content-addresses
   the request; `prepare_dataset` single-flight-locks on Redis and materializes once — one batched
   `stream_historical_bars` for all symbols, interior gaps re-fetched, persisted as a Parquet
   snapshot (`dataset/prepare.py`).
7. **Validate** OHLCV (`engine/validation.py::validate_bars`) — errors abort, warnings log.

**D. Replay through the shared runtime (`StrategyRuntime.run`).**

8. Wire the engine: `Portfolio(initial_capital)` + `SimulatedExecution(commission, slippage)` + a
   progress `observer`, driven by `runtime.run(HistoricalBarFeed(bars, start, end), should_abort)`.
9. Per tick: `portfolio.update_prices`; warm-up dates prime indicators without trading; trading
   dates run the shared `_evaluate_and_execute` core — `session.evaluate` → `size_orders` →
   `SimulatedExecution.execute` (fill at bar close ± slippage, flat fee) → append `(date, equity())`.
   Cooperative cancel is a Redis flag polled between ticks.
10. **End:** liquidate open positions at last prices.

**E. Metrics, benchmark, terminal write.**

11. `assemble_result` computes return / Sharpe / Sortino / max-drawdown / win-rate on the
    **daily-resampled** curve (every value through a `_finite()` guard); `BenchmarkCalculator` adds
    alpha / beta / information-ratio vs the benchmark.
12. **Guarded terminal write:** `UPDATE … WHERE status = RUNNING → COMPLETED` (row-count 0 ⇒ lost a
    cancel race ⇒ discard), then persist `BacktestResult`. Reads: `GetBacktest` inlines results,
    `GetBacktestTrades` pages the log, `StreamBacktestProgress` tails the Kafka progress topic; a Celery-beat
    reaper recovers stale rows.

**Celery posture.** `worker_concurrency=2` (env-tunable via `BACKTEST_WORKER_CONCURRENCY`), `prefetch_multiplier=1`, `acks_late` +
`reject_on_worker_lost` (a killed worker's task re-queues), soft/hard limits 1800/3600 s, and a
dedicated `backtest_maintenance` queue + beat so the reaper is never starved by long runs.

→ Deep dive: [services/backtesting.md](services/backtesting.md).

---

## Live & paper flow (end-to-end)

Paper and live are the **same** trading path; they diverge only at preflight gates and the
credential `is_paper` flag (see the table below). Going live is, mechanically, funding a sleeve and
starting a runner over it — two services cooperating.

**A. Fund the execution (strategy service).**

1. `StartExecution` → `StrategyService.start_execution` calls `_fund_sleeve` **before** flipping the
   execution to RUNNING (so a funding failure aborts go-live). `_fund_sleeve` emits
   `CAPITAL_ALLOCATED` from the account's **Unallocated** sleeve into a new strategy sleeve (purely
   virtual bookkeeping — the cash already sits in the one Alpaca account) and persists
   `(sleeve_id, account_id, allocated_capital)` on the execution. See
   [portfolio-ledger.md](portfolio-ledger.md).

**B. Preflight + identity (trading service — `LiveSessionService.start_session`).**

2. **Preflight** (`_preflight_checks`), in order: `_check_subscription` (LIVE requires a paid,
   non-free plan); credentials exist and belong to the tenant; **credential-mode match** (a LIVE
   session refuses paper credentials); `_check_alpaca_account` (LIVE requires buying-power ≥ $500);
   `_check_symbols_with_credentials` (every strategy symbol must be active and tradable).
   Returns the decrypted per-tenant credentials.
3. **Resolve ledger identity** (`_resolve_ledger_identity`): read `(sleeve_id, account_id)` from the
   funded execution — exact via `execution_id`, else the strategy's *single* open funded execution,
   **refusing if ambiguous** rather than guessing which sleeve to trade.
4. `_ensure_sleeve_not_in_use` — one active session per sleeve (two runners would race its free cash
   and double-trade its targets) — then create the `trading_session` row and call `_start_runner`.

**C. Build the runner (`_start_runner`).**

5. Load the strategy version, get its DSL sexpr and symbols, and **compile the shared session**:
   `StrategySession(sexpr, sizing_mode=DRIFT if funded else BINARY)` — the same core as backtest.
6. **Provider seam** (`providers.py`): build the bar stream, the `trade_updates` stream, and a REST
   client from the tenant's credentials, all carrying `paper=creds.is_paper` — the one place paper
   vs live routes to Alpaca. (Symbol tradability was already gated in preflight.)
7. **Warm-up preload** (`runner/warmup.py::preload_session_history`): fetch `min_bars` (+ buffer)
   daily bars per required symbol from the **market-data service** and feed them as warm-up, so the
   session trades from its first live bar instead of accumulating `min_bars` in real time.
   Best-effort: on failure the session starts cold and warms from the stream.
8. Build `RunnerConfig`; `RunnerManager.start_runner` launches `StrategyRunner`.

**D. Runner startup + loops.**

9. One-shot crash recovery: sync equity (sleeve-aware), `recover_stranded_orders` (ask the broker
   whether orders left PENDING before a crash actually landed, then adopt or reject), re-publish
   recently-terminal ledger events.
10. Spawn the loops: the **main bar loop**; equity-sync (~60 s, re-reads sleeve equity + free cash
    from the ledger); position-reconcile (~300 s, read-only for sleeve sessions — the ledger owns
    correction); the trade-update fill loop; and a ledger-republish drain (~120 s).

**E. The hot loop: bar → evaluate → submit.**

11. `_process_bar` appends to per-symbol history and calls `_evaluate_session`, which evaluates
    **only when every subscribed symbol has that period's bar** (a complete cross-symbol snapshot),
    once per period, gated by market-open + circuit-breaker, **offloading** `session.evaluate` to a
    worker thread. On the strategy's rebalance cadence this returns sized orders; otherwise the bars
    just keep indicators warm. Degraded (NaN/missing-data) evaluations surface as a metric.
12. `_process_signal`: reject shorts (the sleeve is long-only), **fit buys to sleeve free cash**,
    risk-check, then `OrderExecutor.submit_order(..., signal_timestamp=…)`. Positions are **not**
    updated here — fills are the source of truth.
13. `submit_order`: derive a **deterministic** `client_order_id = lt-{sha256(session:symbol:side:
    signal_ts)[:16]}` (a post-crash retry collapses onto the same broker order); replay if the row
    already exists; persist PENDING; submit via `llamatrade_alpaca`; map the broker status; publish a
    cash **reservation**. A stranded PENDING first asks the broker `get_order_by_client_id` whether
    it landed before resubmitting.

**F. Fills → positions → ledger (the money path).**

14. The trade-update loop applies broker fills to positions (avg-cost on adds, realized P&L +
    circuit-breaker on closes, slippage vs the originating signal). Fills — not local intent — are
    the source of truth for position state.
15. On terminal events, exactly one `LedgerFill` per order (plus reservation releases) is published
    to the global `ledger:fills` stream, idempotently (`event_id = sha256(client_order_id)`). The
    portfolio service's durable consumer group (every pod a member; per-account ordering via the
    partition key) folds it into a balanced double-entry event with FIFO cost basis — see
    [portfolio-ledger.md](portfolio-ledger.md#integration-contract-trading--portfolio--strategy).

### Paper vs. live: the exact differences

| Aspect | Paper | Live |
| --- | --- | --- |
| Subscription | any active subscription | **paid (non-free) plan required** |
| Credentials | paper keys (`is_paper = true`) | **live keys required** (a LIVE session refuses paper creds) |
| Buying-power gate | — | **≥ $500** |
| Alpaca environment | `paper = true` → paper endpoint | `paper = false` → real endpoint |
| Everything else | identical runner, loops, executor, and ledger path | identical |

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
| Sizing mode | `DRIFT` by default; `BINARY` + band/notional floor selectable per run | `DRIFT` when the session is funded (has a sleeve), else `BINARY` |
| Fill model | full/partial fill at bar close ± slippage, synchronous | real broker orders — partial fills, async settlement |
| Daily price basis | split-adjusted daily bars | raw real-time bars (the live *stream* is 1-minute; the configured session/warm-up timeframe is `1D`) |
| Indicator resolution | bars at the backtest timeframe | bars at the live stream timeframe; a lookback is *N bars at that resolution*, so a daily-lookback indicator on a 1-minute live feed warms over minutes, not days |
| Order quantization | fractional quantities pass through unrounded | quantities round to a tradable share increment and re-check the notional floor before submit (`fractional_shares` / `share_decimals` / `min_order_notional` on `RunnerConfig`) |

---

## Current state vs target

- **Unification is at `StrategySession` today.** Both paths share evaluation and sizing; a backtest
  faithfully predicts live *decisions*.
- **The shared `StrategyRuntime.stream` loop is the target live driver.** It is wired and tested
  (`runtime_adapters.py`) and enabled with `TRADING_USE_RUNTIME_LOOP`; the hand-rolled loop remains
  the default until paper-trading QA validates the swap. Until then, the two live loops
  (`_evaluate_session` and `_run_via_runtime`) must be kept behaviorally aligned.
- **Live warms up from history** (`runner/warmup.py`), so a fresh session trades from its first live
  bar rather than accumulating `min_bars` in real time. The preload fetches **daily** bars;
  reconciling that with the raw 1-minute live stream is the open item under *Indicator resolution*.

---

## Worked example: one strategy end to end

This walks **one real strategy** end-to-end through every execution flow — backtest, funding, and
live/paper — with concrete dollars, bars, orders, and ledger events, so you can see *exactly* what
the system does at each step. The sections above are the reference-level model (adapter seams,
parity guarantees); for the money contract, see [portfolio-ledger.md](portfolio-ledger.md).

> Prices and dates below are **illustrative** (chosen for clean arithmetic). The mechanics, code
> paths, ledger postings, and formulas are real.

---

### 0. The strategy

```lisp
(strategy "Momentum Rotation + Trend Filter"
  :rebalance monthly
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))              ; risk-on regime?
    (filter :by momentum :select (top 3) :lookback 90
      (weight :method equal                       ; hold the 3 strongest, equal-weighted
        (asset AAPL) (asset MSFT) (asset NVDA) (asset GOOGL) (asset AMZN)))
    (else
      (asset BIL :weight 100))))                  ; risk-off → 100% T-bills
```

**In plain English:** once a month, if SPY is above its 200-day average, rank a 5-name tech universe
by 90-day momentum, keep the **top 3**, and split equally (≈33.3% each); otherwise hold 100% `BIL`
(cash).

**What compilation produces** (`StrategySession(config_sexpr)`, real values from the lib):

| Compiled artifact | Value |
| --- | --- |
| required `symbols` | `SPY, AAPL, MSFT, NVDA, GOOGL, AMZN, BIL` (7) |
| `indicators` | `sma_SPY_close_200` (one) |
| `min_bars` | **200** (the SMA-200 warm-up) |
| `history_window` | 210 (retained bars/symbol) |
| `rebalance` | `monthly` |

`min_bars = 200` is the load-bearing number: **the strategy cannot produce a single order until every
one of its 7 symbols has 200 bars of history.** Everything below is downstream of that.

---

### 1. Backtest — replaying 2020→2024 on $100,000

The user opens the strategy, picks **$100,000**, **2020-01-02 → 2024-12-31**, run granularity **1D**,
benchmark **SPY**, and clicks *Run Backtest*.

#### 1.1 Enqueue (returns instantly)
`RunBacktest` writes a `PENDING` `Backtest` row and calls `run_backtest_task.delay(...)`. **Nothing
runs in the API** — a Celery worker owns execution. The UI starts tailing the Kafka progress topic.

#### 1.2 The worker fetches the dataset (from market-data, never Alpaca)
The worker compiles the session, then asks the **market-data service** for daily bars of all 7
symbols. Crucially it **pads the window back by `min_bars`**: to trade from 2020-01-02 it needs 200
prior bars, so it actually fetches from ≈ **2019-03**. Market-data serves store-first from
TimescaleDB, back-filling any gaps from Alpaca, and returns a content-addressed, gap-checked snapshot
(~1,450 bars × 7 symbols).

#### 1.3 The replay loop (`StrategyRuntime.run` over `HistoricalBarFeed`)
Bars are fed one **date** at a time. Two phases:

- **Warm-up (2019-03 → 2019-12):** each date is flagged `is_warmup`. The engine appends the bar and
  recomputes `sma_SPY_close_200`, but `evaluate(warm_up=True)` returns **no orders**. By 2020-01-02
  the SMA is fully warm.
- **Trading (2020-01-02 → 2024-12-31):** each date runs `session.evaluate`. But the **monthly
  rebalance gate** means it only *acts* on the **first trading day of each month** — every other day
  just keeps the SMA warm and returns `[]`.

#### 1.4 A concrete rebalance day (first trading day of Jan 2020)
On 2020-01-02, `should_rebalance(monthly)` is `True`. The engine:

1. Reads `SPY.close` ($324) and `sma_SPY_close_200` ($305). **324 > 305 → risk-on.**
2. Scores the 5 names by 90-day trailing return, keeps the **top 3** — say `{AAPL, MSFT, NVDA}` — and
   equal-weights → after normalization, **33.33% each**.
3. `size_orders` turns weights into orders against equity = **$100,000** (all cash on day one):

   | Symbol | Target % | Target $ | Held | Order |
   | --- | --- | --- | --- | --- |
   | AAPL | 33.33% | $33,333 | $0 | **buy $33,333** |
   | MSFT | 33.33% | $33,333 | $0 | **buy $33,333** |
   | NVDA | 33.33% | $33,333 | $0 | **buy $33,333** |

4. `SimulatedExecution` fills each at that day's **close ± slippage**, subtracts a flat fee, and books
   it into the in-memory `Portfolio`. Cash → ≈ $0; the sleeve is fully invested.

#### 1.5 A rebalance that *changes* holdings (DRIFT sizing)
A month later prices have drifted and the ranking shifts. Suppose on 2020-02-03 the book is
`AAPL $36k, MSFT $33k, NVDA $30k` (equity **$99k**, no cash), still risk-on, but the new top-3 is
`{AAPL, MSFT, GOOGL}` (NVDA fell out, GOOGL rose in). Target = 33.33% × $99k = **$33,000 each**.
**DRIFT mode** trades only the delta beyond a 5% band, and `size_orders` emits **sells before buys**:

| Symbol | Target $ | Held $ | Δ | Band check | Action |
| --- | --- | --- | --- | --- | --- |
| NVDA | $0 | $30,000 | −$30,000 | — | **sell all $30,000** |
| AAPL | $33,000 | $36,000 | −$3,000 | 9% > 5% | **trim $3,000** |
| MSFT | $33,000 | $33,000 | $0 | 0% | **hold** (no order) |
| GOOGL | $33,000 | $0 | +$33,000 | new | **buy $33,000** |

The NVDA + AAPL sells free ~$33k of cash *first*, which funds the GOOGL buy in the same rebalance.
MSFT is left alone because it's inside the drift band. **This is the whole point of the sleeve/weight
model: the strategy expresses a *target allocation*, and sizing computes the minimal trades to reach
it.**

#### 1.6 If the regime flips (risk-off)
On any rebalance day where `SPY.close < sma_SPY_close_200` (e.g. the March-2020 crash), the `else`
branch wins: target = **100% BIL**. `size_orders` sells every tech position and buys BIL — the whole
sleeve goes to cash-equivalent until a later month puts SPY back above its average.

#### 1.7 Result
Each trading day appends `(date, equity)` to the curve; at the end open positions liquidate at last
prices. `assemble_result` computes return / Sharpe / Sortino / max-drawdown / win-rate on the
**daily-resampled** curve, plus alpha/beta vs SPY. A guarded `UPDATE … WHERE status = RUNNING`
persists `BacktestResult`, and the UI shows the equity curve. **No broker, no ledger, no real money.**

---

### 2. Funding — how money actually gets allocated

Going live is *not* a special "buy the strategy" operation. It's an entry in the **double-entry
sleeve ledger**. One Alpaca brokerage account is partitioned into **sleeves**; a strategy is just a
sleeve the runner manages.

#### 2.1 Money enters the account → Unallocated
The user connects Alpaca and the account holds $100,000. Connecting runs the broker **backfill**
(existing cash and holdings are adopted at genesis with deterministic `backfill:*` event ids); an
explicit deposit through the funding RPC records `FUNDS_DEPOSITED` — value crossing the account
boundary into the **Unallocated** sleeve:

```
FUNDS_DEPOSITED  $100,000
  EXTERNAL              −100,000     (account boundary — money from outside)
  Unallocated.CASH      +100,000
                      ───────────
  sum                          0     ✓ balanced
```

Account state: `Unallocated: cash $100,000`. No strategy is funded yet.

#### 2.2 Allocate $50,000 to the strategy → a strategy sleeve
When the user sets *Momentum Rotation* live with $50,000, `start_execution` calls the ledger's
`allocate_capital`, which checks `Unallocated.free ≥ $50,000` and emits `CAPITAL_ALLOCATED` — a pure
sleeve-to-sleeve **cash** move (no broker order; the cash is already in the account):

```
CAPITAL_ALLOCATED  $50,000
  Unallocated.CASH     −50,000
  Momentum.CASH        +50,000
                     ──────────
  sum                        0     ✓ balanced
```

Now:

| Sleeve | cash | positions | allocated_capital |
| --- | --- | --- | --- |
| Unallocated | $50,000 | — | — |
| Momentum Rotation | **$50,000** | none | $50,000 |

The execution row stores `(sleeve_id, account_id, allocated_capital=$50k)`. **Every balance you see
for the strategy is a fold of these events — never a mutated column.** Adding capital later is just
another `CAPITAL_ALLOCATED` appended to the same sleeve (the runner picks it up on its next 60-second
equity sync — no restart), and stopping the strategy emits `SLEEVE_CLOSED`, which re-homes positions
to *Unmanaged* and cash back to *Unallocated*.

---

### 3. Live & paper — what happens minute by minute

Paper and live are the **same code**; they differ only by preflight gates and the `is_paper`
credential flag (table at the end). The sleeve now has $50,000 cash and the runner starts.

#### 3.1 Session start (once)
1. **Preflight:** subscription (LIVE needs a paid plan), credentials belong to the tenant,
   credential-mode matches (LIVE refuses paper keys), buying-power ≥ $500 for LIVE.
2. **Resolve the sleeve** from the funded execution; refuse if two open funded executions make it
   ambiguous; ensure no other runner already trades this sleeve.
3. **Compile the same `StrategySession`** (DRIFT sizing, because it's funded).
4. **Warm-up preload:** fetch ~210 **daily** bars per symbol from the market-data service and feed
   them `warm_up=True`, so `sma_SPY_close_200` is warm immediately — the strategy can act on its
   first live bar instead of waiting 200 real bars.
5. **Spawn loops:** the main 1-minute **bar loop**, the **fill loop** (`trade_updates`), a 60-second
   **equity-sync** (re-reads sleeve cash/equity from the ledger), a position-reconcile, and a
   ledger-republish drain.

#### 3.2 A normal (non-rebalance) trading day — thousands of no-op bars
The Alpaca stream delivers **1-minute** bars. Here's a mid-month Tuesday:

| Time (ET) | What arrives | What the runner does |
| --- | --- | --- |
| 9:31:00 | SPY, AAPL, … 1-min bars | buffer each; once **all 7 symbols** have the 09:31 bar → evaluate |
| 9:31:00 | evaluate | append bars, recompute SMA; `should_rebalance(monthly)`? **no** (not 1st of month) → **0 orders** |
| 9:32 … 15:59 | ~390 more bars | same: keep the SMA warm, **0 orders** |

So on an ordinary day the strategy consumes ~390 bars and **trades nothing** — it's only staying
warm. (Caveat: because the live stream is 1-minute, the SMA-200 warms over recent *minutes*, not
days — the backtest↔live resolution gap noted in [execution-runtime.md](execution-runtime.md#parity-guarantees-and-known-differences).)

#### 3.3 The rebalance day — the one minute that trades
On the **first trading day of the month**, the first bar where **all 7 symbols are present** flips the
gate. Suppose the sleeve holds `AAPL $18k, MSFT $17k, NVDA $15k` (equity **$50k**, cash ≈$0) and the
new top-3 is `{AAPL, MSFT, GOOGL}`:

| Time (ET) | Step | Detail |
| --- | --- | --- |
| 9:31:00 | **evaluate** (offloaded to a thread) | risk-on; top-3 = AAPL/MSFT/GOOGL; targets 33.3% × $50k ≈ **$16,667 each** |
| 9:31:00 | **size_orders** (DRIFT, sells first) | sell NVDA $15,000; trim AAPL $1,333; MSFT within band → hold; buy GOOGL $16,667 |
| 9:31:01 | **submit sells** | each via `OrderExecutor.submit_order` |
| 9:31:03 | **fills arrive** (`trade_updates`) | positions updated from broker reality; cash rises to ≈$16,300 |
| 9:31:03 | **buy fires** | GOOGL buy fits to the now-available free cash |
| 9:31:06 | **buy fills** | GOOGL position opened |
| 9:32 … close | more bars | `last_rebalance` is now this date → **0 further orders** all month |

#### 3.4 One order, in full — the GOOGL buy
`_process_signal` → `OrderExecutor.submit_order`:

1. **Deterministic id:** `client_order_id = lt-{sha256("<session>:GOOGL:buy:2020-…T09:31")[:16]}`. If
   the runner crashes and retries, the broker (which enforces per-account id uniqueness) collapses
   the retry onto the same order — no double buy.
2. Persist a `PENDING` order row; submit to Alpaca (**paper or live per `is_paper`**) via
   `llamatrade_alpaca`; publish a **cash reservation** (earmarks $16,667 of free cash so a
   concurrent signal can't double-spend it).
3. The buy fills (possibly in parts). The **fill loop** updates the in-memory position (avg cost),
   and at the terminal fill publishes **one `LedgerFill`** to the global `ledger:fills` Kafka topic
   (keyed by account) with `event_id = sha256(client_order_id)`.

#### 3.5 The fill hits the book — double-entry
The portfolio service's ledger consumer group folds that fill (per-account ordering via the partition key). For the GOOGL buy of 100 sh @
$166.67, fee $1:

```
ORDER_FILLED (buy GOOGL)
  Momentum.CASH        −16,668      (notional + fee)
  Momentum.POSITION    +16,667      (+100 sh at cost)
  Momentum.PNL         +1           (fee)
                     ──────────
  sum                        0      ✓ balanced
```

For the NVDA **sell** (30 sh, cost basis $16,666, sold for $15,000, fee $1 → realized **−$1,667**),
FIFO cost basis is resolved at ingestion and the postings are:

```
ORDER_FILLED (sell NVDA)
  Momentum.POSITION    −16,666      (−30 sh at cost, FIFO)
  Momentum.CASH        +14,999      (notional − fee)
  Momentum.PNL         +1,667       (−realized; a loss lowers sleeve P&L)
                     ──────────
  sum                        0      ✓ balanced
```

After both fold, the sleeve projection reflects the new positions, the new cash, and realized P&L —
and **that projection is what the UI shows and what the next rebalance sizes against.** A fill that
would drive the sleeve negative freezes it (`SLEEVE_FROZEN`) rather than corrupt the book.

---

### 4. The whole picture

```
                         ┌──────────────────────────────────────────────┐
                         │  StrategySession.evaluate                     │
   bars ───────────────▶ │  bars → SMA/regime → top-3 → weights →        │ ──▶ [IntendedOrder]
   (feed adapter)        │  size_orders(vs holdings, vs equity)          │
                         └──────────────────────────────────────────────┘
                                   ▲ same code in every flow ▲
        ┌──────────────────────────┼───────────────────────────┐
        │                          │                            │
   BACKTEST                    PAPER / LIVE                  (funding is
   HistoricalBarFeed           StreamBarFeed (1-min)          out-of-band:
   SimulatedExecution          OrderExecutor → Alpaca         CAPITAL_ALLOCATED
   in-memory Portfolio         fills → ledger:fills →         sets the equity
   → metrics                   portfolio double-entry         the sizer uses)
```

The single invariant: **the same `evaluate` turns bars into target weights and the same `size_orders`
turns weights into trades in every flow.** Backtest wraps it in a historical feed + simulated fills;
live wraps it in a 1-minute stream + a broker + the ledger; funding is a separate ledger event that
sets the equity the sizer targets. A backtest is therefore a faithful preview of the live *decisions*,
and paper is a faithful rehearsal of the live *mechanics*.

---

## Related documentation

- [Strategy DSL Reference](strategy-dsl.md) — the language and its compilation pipeline.
- [Portfolio Ledger](portfolio-ledger.md) — how live target weights become attributed, reconciled trades.
- [Backtesting Service](services/backtesting.md) — the backtest wiring, dataset materialization, metrics.
- [Trading Service](services/trading.md) — the live runner, order execution, risk, fill emission.
- [Signals & Weights](signals-and-weights.md) — indicator and allocation-method behavior.
