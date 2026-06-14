# Portfolio Ledger — Completion & Legacy Retirement Plan

> **⚠️ SUPERSEDED (2026-06-14): flags removed, legacy deleted, ledger always-on.**
> The phased, flag-gated, parity-soak approach described below was the original
> plan. The team then decided the ledger is the **only** source of truth with no
> secondary/legacy path, so all `LEDGER_*` rollout flags were removed and the
> legacy read modules (`portfolio_service`/`performance_service`/
> `transaction_service`/`domain`) + the parity tooling were deleted outright
> across portfolio, trading, and strategy. Sleeve-aware behavior is now keyed off
> `sleeve_id` presence, not a flag. Remaining ledger env vars are tuning intervals
> only. The stage descriptions below are retained for historical context (what was
> built); ignore their flag/soak/removal sequencing.
>
> **Goal:** make the event-sourced ledger the **sole** source of truth for every
> portfolio read (summary, positions, performance, allocation, transactions,
> strategy performance), then delete the legacy float/JSONB read path once it is
> provably unused. Sequenced, flag-gated, parity-verified before removal.
>
> **Status:** READ CUTOVER IMPLEMENTED — READY FOR MANUAL QA (2026-06-13).
> Builds on `portfolio-ledger.md` (design), `CONTRACTS.md` (locked contract), and
> `trading-ledger-implementation-plan.md` (execution integration — all 6 phases
> implemented, rollout pending QA).
>
> **Implemented this pass (behind `LEDGER_READS`, legacy untouched):**
> - **E** reserved-cash fix (`FundService._free_cash` = cash − reserved) + regression tests.
> - **F (kernel)** corporate-action postings `SPLIT_APPLIED`/`SYMBOL_CHANGED` +
>   pure planners (`ledger/corporate.py`: `plan_split`/`plan_symbol_change`/`split_dividend`).
> - **B** equity-curve snapshot task (`tasks/equity_snapshot.py`) writing `SleeveSnapshot`
>   rows (table already existed via migration 015 — **no schema change needed**); wired
>   into `main.py` lifespan under shadow/reads.
> - **C** ledger read model (`ledger/analytics.py`, `ledger/read_model.py`) +
>   `services/portfolio_read_service.py`; `PortfolioServicer` read RPCs routed
>   ledger-vs-legacy by `LEDGER_READS` (same `PortfolioService` proto — frontend unchanged).
> - **D** strategy performance from the strategy-sleeve projection + snapshots
>   (`services/strategy_performance_read_service.py`); three strategy RPCs flag-routed.
> - **H tooling** `portfolio_ledger_read_parity_abs_diff` metric + `read_model.summary_parity`.
> - 38 new tests (252 total green); ruff + pyright clean on all changed files.
>
> **Deferred (not on the read-parity QA path):** A checkpoint/incremental-fold perf
> optimization (current full-replay is already accepted for existing ledger reads);
> F's external Alpaca corporate-actions ingestion feed; G desired-state/netting
> runtimes; settlement (settled/unsettled); H production soak; I legacy removal
> (must follow the soak — deleting now defeats the cutover safety).

---

## Why this plan exists

The trading×ledger plan made the ledger the book of record for **execution**
(fills ingested, sleeves funded, reconciliation). It explicitly left out the
**read side**. Today the frontend and any API consumers still hit the legacy
`PortfolioService` RPCs, backed by:

| Legacy module | Backs | Replacement source |
|---|---|---|
| `services/portfolio_service.py` | summary, positions, allocation | aggregate sleeve projection (mark-to-market) |
| `services/performance_service.py` + `domain.py` | sharpe/sortino/drawdown/alpha/beta | ledger-derived **equity-curve snapshots** + pure metrics kernel |
| `services/transaction_service.py` | transaction history, record txn | ledger events (`ORDER_FILLED`, `FUNDS_*`, `DIVIDEND`, `FEE`) as a txn view |
| `services/strategy_performance_service.py` | per-strategy perf (frontend uses) | **strategy-sleeve** projection + its snapshots |
| `models.py` | legacy Pydantic schemas | new read-model schemas |
| `clients/market_data.py` | live prices for marking | **kept** — graduates into the ledger read layer (price source, not legacy) |

Legacy cannot be removed until each row's replacement exists, is wired to the
proto the frontend already calls, and is shown to produce identical numbers.

### Known gaps blocking "full completion"

1. **No read parity** — ledger has sleeve/fund/holding RPCs only; no
   summary/positions/performance/transactions equivalents.
2. **No equity-curve / snapshot materialization** — performance math needs a
   time series; projector also replays full history on every read (see
   analysis finding #4) — unbounded as event volume grows.
3. **Strategy performance unbacked** — `StrategyPerformance{Snapshot,Metrics}`
   have no populating job.
4. **Reserved-cash bug** — `FundService._free_cash` returns `cash`, not
   `cash − reserved` (analysis finding #1). Must fix before `LEDGER_EXECUTION`.
5. **Corporate actions declared-but-unimplemented** — `SPLIT_APPLIED`,
   `SYMBOL_CHANGED` have enum values but no postings; dividends aren't split
   per-lot across sleeves. Required for long-run cost-basis correctness.
6. **Settlement (settled/unsettled cash) not folded** — column exists,
   projection ignores it.
7. **Desired-state & netting runtimes** — pure kernels exist (`desired_state.py`,
   `netting.py`) but no runtime wiring (`LEDGER_DESIRED_STATE`/`LEDGER_NETTING`).
8. **No historical backfill** — switching reads to the ledger with only
   onboarding-genesis data starts charts/history empty.

---

## Stages

Each stage is independently shippable and flag-gated. Stages A–D deliver read
parity (the critical path to removal); E–F complete accounting correctness;
G completes execution; H–I verify and retire.

### Stage A — Snapshot & read-performance foundation
*Prereq for everything; no behavior change.*

- New tables (`libs/db`, alembic migration): `SleeveSnapshot` (sleeve_id, seq,
  cash, reserved, realized_pnl, positions JSONB, equity, ts) and a projection
  **checkpoint** (account_id, last_sequence, snapshot blob). Per `portfolio-ledger.md`
  §Snapshots: recovery = latest snapshot + replay events after N.
- `LedgerProjector`: fold from latest checkpoint forward instead of genesis;
  write checkpoints every K events / on read when stale. Fixes finding #4.
- Pure helper in kernel: incremental fold `(snapshot, new_events) → projection`.
- Tests: replay-from-checkpoint equals replay-from-genesis (property test).

### Stage B — Equity-curve materialization
*Powers performance + strategy equity curves.*

- New task `src/tasks/equity_snapshot.py`: on a timer (and at market open/close),
  mark each account + sleeve to market via `MarketDataClient`, append/store a
  daily `equity` point (account-level → replaces `PortfolioHistory`; sleeve-level
  → replaces `StrategyPerformanceSnapshot`). Gated `LEDGER_SHADOW_MODE`.
- Reuse `ledger/performance.py` (`account_pnl`/`sleeve_pnl`) for the mark.
- Tests: snapshot count/spacing, downsampling, idempotent same-day write.

### Stage C — Read-model parity (the core deliverable)
*Reimplement the legacy reads on the ledger, behind the **same** `PortfolioService`
proto so the frontend needs no change.*

- New `src/ledger/read_model.py` (pure) deriving from `AccountProjection` + prices:
  - `portfolio_summary()` — total equity, cash, market value, unrealized
    (mark-to-market) + realized (from fold) P&L, day P&L (vs prior snapshot),
    positions count.
  - `aggregate_positions()` — sum lots per symbol across sleeves → `PositionResponse`
    parity (cost basis, avg entry, current price, unrealized).
  - `asset_allocation()` — group aggregate positions.
  - `transactions_view(events, filters, page)` — map economic events to the
    transaction list shape; pagination over the log (or a txn projection table).
- Move the numpy metrics (`_calc_sharpe/_sortino/_max_drawdown`, `benchmark_metrics`)
  into the pure kernel; compute over Stage-B equity curve.
- New `PortfolioReadService` (DB-backed) composing projector + snapshots + prices.
- Reimplement `grpc/servicer.py` `PortfolioServicer` read RPCs on
  `PortfolioReadService`, **flag-gated** (`LEDGER_READS`): flag off → legacy path,
  flag on → ledger path. `RecordTransaction` (manual) appends a ledger event.
- Tests: per-RPC, legacy vs ledger produce equal output on shared fixtures.

> **New flag:** `LEDGER_READS` (read-side cutover), independent of execution flags.

### Stage D — Strategy performance from the ledger

- Derive `list/get/equity_curve` strategy performance from the **strategy sleeve**
  projection + Stage-B sleeve snapshots + the metrics kernel.
- Reimplement `strategy_performance_service` reads behind `LEDGER_READS`; the
  `StrategyPerformance{Metrics,Snapshot}` tables become either populated by the
  Stage-B job or dropped in favor of `SleeveSnapshot` (see Decision 3).
- Tests: returns/sharpe/drawdown over a synthetic sleeve event stream.

### Stage E — Reserved cash + sufficient-allocation correctness

- Fix `FundService._free_cash` → `cash − reserved`; audit every "free cash"
  call site (`funds.py`, `fund_service.py`). Add regression test: withdraw/
  allocate cannot spend reserved funds.
- Wire admission checks (`funds.check_admission`) into `allocate`/strategy-fund.

### Stage F — Corporate actions & settlement (long-run correctness)

- Implement postings for `SPLIT_APPLIED` (qty×ratio, cost basis preserved) and
  `SYMBOL_CHANGED`; split `DIVIDEND_RECEIVED` pro-rata by lot qty across sleeves.
- Ingestion source: Alpaca corporate-actions/activities feed (via `llamatrade_alpaca`,
  per-tenant creds) → reconciliation classifies & appends. Extend
  `reconciliation.py` drift causes accordingly.
- Settlement: fold `settled`/`unsettled` cash; reconciler respects it for cash
  accounts (Decision 4). Tests for each corporate-action posting.

### Stage G — Desired-state & netting runtimes (execution completion)

- `LEDGER_DESIRED_STATE`: runtime loop calling `desired_state.plan_rebalance`
  from strategy sleeve targets → intended orders → trading.
- `LEDGER_NETTING`: block-and-allocate via `netting.net_orders` in the executor;
  fill allocation at avg price. (Both kernels already exist + tested.)
- Note: these depend on trading-side wiring already built in the trading plan.

### Stage H — Parity soak & cutover

- Extend shadow reconciliation to **cash & equity** (not just positions): assert
  `Σ sleeve cash == broker cash` and ledger summary == legacy summary within
  tolerance; emit a `portfolio_ledger_read_parity` metric.
- Historical backfill (Decision 5): one-time job deriving ledger events from
  `Transaction`/`PortfolioHistory`, OR genesis-from-onboarding + keep legacy for
  pre-cutover history reads during the soak.
- Flip `LEDGER_READS` in staging → soak → production. Frontend unchanged
  (same proto). Watch parity metric + legacy-path traffic counter (Stage I gate).

### Stage I — Legacy removal (only after H proves zero legacy traffic)

- Delete: `portfolio_service.py`, `performance_service.py`, `transaction_service.py`,
  `domain.py`, legacy `models.py` schemas; collapse the `LEDGER_READS` branch in
  `grpc/servicer.py` (ledger path becomes unconditional).
- Delete tests: `test_portfolio_service.py`, `test_performance_service.py`,
  `test_transaction_service.py`, `test_domain.py`, `test_position_enrichment.py`,
  and the legacy slice of `test_grpc_servicer.py`.
- Drop now-dead tables/migrations (`PortfolioSummary`, `PortfolioHistory`,
  `Transaction`, `StrategyPerformance*`) per Decision 3/5.
- Keep `clients/market_data.py` (price source for the read layer).
- `clients/market_data.py` retained; remove the legacy `MarketDataClient` only if
  fully superseded. Run `./scripts/ci-local.sh`; ≥80% coverage on new real code.

---

## Decisions

**Locked (2026-06-13):**
1. **Read cutover surface — Reuse `PortfolioService` proto.** Keep the existing
   RPCs; swap the implementation to the ledger underneath, flag-gated by
   `LEDGER_READS`. Frontend untouched; legacy deleted invisibly at Stage I.
3. **Strategy-perf tables — Drop `StrategyPerformance{Metrics,Snapshot}`,** derive
   strategy perf from the strategy-sleeve projection + `SleeveSnapshot`. One
   snapshot model.
5. **Historical data — Genesis + soak, no backfill.** Ledger starts from
   onboarding; legacy serves pre-cutover history during the soak window only.
   Charts show history from cutover forward.

**Still open (safe defaults assumed; revisit if needed):**
2. **Transactions representation** — derive on-the-fly from the event log vs. a
   dedicated transaction **projection table** for paged queries. (Default:
   projection table — pagination over raw events is costly.)
4. **Settlement model scope** — implement settled/unsettled now (cash accounts)
   vs. defer (assume margin/buying-power). (Default: defer unless cash accounts
   are near-term.)
6. **Corporate actions priority** — Stage F lands before `LEDGER_EXECUTION` goes
   authoritative; reads (A–E) cut over first. (Default as sequenced.)

## Critical path to legacy removal

A → B → C → D → (E) → H → I. Stages F and G complete the ledger but do **not**
block read parity / removal; sequence them around `LEDGER_EXECUTION`.

## Flags introduced/used
`LEDGER_READS` (new, read cutover) · existing `LEDGER_SHADOW_MODE`,
`LEDGER_SLEEVES`, `LEDGER_EXECUTION`, `LEDGER_DESIRED_STATE`, `LEDGER_NETTING`.
New env: `LEDGER_SNAPSHOT_INTERVAL_SECONDS` (default 3600).

## Manual QA runbook (read cutover)

Prereq: an onboarded ledger account with some fills (run trading under
`LEDGER_SHADOW_MODE` so `Σ sleeves == broker`, or seed via onboarding backfill).

1. **Generate equity history.** Start the portfolio service with
   `LEDGER_SHADOW_MODE=1` (snapshot loop runs; lower `LEDGER_SNAPSHOT_INTERVAL_SECONDS`
   e.g. `60` to accrue points quickly). Confirm `ledger_sleeve_snapshots` rows appear.
2. **Flip reads on a canary.** Set `LEDGER_READS=1` and restart. The
   `PortfolioService` proto is unchanged, so the frontend needs no rebuild.
3. **Verify each RPC** (e.g. via the web app or grpcurl): `GetPortfolio`,
   `GetPositions`, `GetAssetAllocation`, `GetPerformance`, `ListTransactions`,
   `ListStrategyPerformance`, `GetStrategyPerformance`, `GetStrategyEquityCurve`.
   Summary/positions should match broker/ledger truth; performance is sparse until
   enough daily snapshots accrue (expected — genesis+soak, no backfill).
4. **Parity check.** With both paths available, compare legacy (`LEDGER_READS=0`)
   vs ledger (`=1`) `GetPortfolio` for the same tenant; differences should be ~0
   on equity/cash/positions. (`read_model.summary_parity` +
   `portfolio_ledger_read_parity_abs_diff` formalize this for the prod soak.)
5. **Flag-off regression.** With `LEDGER_READS` unset, behavior is byte-for-byte
   the legacy path (default; covered by the existing suite).

Run `cd services/portfolio && pytest tests -q` (252 passing) and
`ruff check src tests` before sign-off.
