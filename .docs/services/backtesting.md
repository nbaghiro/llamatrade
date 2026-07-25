# LlamaTrade Backtesting System

This document describes the backtesting subsystem—how users interact with it, how a run executes, what it calculates, and how it integrates with the broader LlamaTrade platform.

---

## Overview

Backtesting lets users evaluate trading strategies against historical market data before risking real capital. A run replays a strategy over a date range one trading date at a time, simulating fills, tracking a portfolio, and producing industry-standard performance metrics.

**Key capabilities:**

- Simulate any DSL strategy over a historical period and timeframe
- Run asynchronously on Celery workers with real-time progress streaming and cooperative cancel
- Compute performance metrics (Sharpe, Sortino, drawdown, win rate, profit factor, etc.)
- Produce an equity curve and a trade-by-trade breakdown
- Compare against an SPY buy-and-hold benchmark (alpha / beta / information ratio)
- Reuse warm, shared, content-addressed datasets so overlapping runs pay for data once

The backtest engine is the **shared strategy runtime** (`llamatrade_runtime`) — the *same* evaluate → size → execute loop that drives live trading. A backtest is that runtime wired to a historical bar feed and a simulated fill adapter.

---

## Architecture Overview

### System Architecture

```
┌───────────────┐   Connect   ┌──────────────────────────────┐  Celery   ┌──────────────────────┐
│    Frontend   │  ────────►  │        Backtest :8830        │  ──────►  │   Celery worker(s)   │
│ progress bar  │             │  BacktestServicer (7 RPCs)   │  (Redis   │ run StrategyRuntime  │
│ cancel button │  ◄────────  │  BacktestService: validate · │  broker)  │ metrics · benchmarks │
└───────────────┘  progress   │  create row · enqueue        │           │ persist result       │
                   (stream)    └──────────────────────────────┘           └──────────────────────┘
                                       │                                          │
                                       ▼ beat schedule                            ▼
                               reap_stale_backtests_task                  prepare_dataset (Parquet
                               (backtest_maintenance queue)               snapshot, Redis single-flight)
                                                                                  │
┌─────────────────────────────────────────────────────────────────────────────┐ │
│                              DATA DEPENDENCIES                                │ ▼
├──────────────────────────────────────────────────────────────────────────────┤
│ Strategy DB   ───────►  strategy version (S-expression config) via shared DB │
│ Market Data   ──gRPC──►  historical OHLCV bars (StreamHistoricalBars)         │
│ PostgreSQL    ────────►  backtest + result rows (tenant-scoped, RLS)          │
│ Redis         ────────►  Celery broker · progress pub/sub · dataset lock      │
│ Object store  ────────►  content-addressed Parquet bar snapshots (dataset/)   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Execution substrate

The **Celery worker is the only execution path**. `RunBacktest` validates the request, creates a `PENDING` backtest row, and enqueues `run_backtest_task`; nothing runs in the API process. The worker loads the strategy version, materializes the dataset, drives the runtime, computes metrics/benchmarks, and persists the result.

A Celery **beat schedule** runs a periodic reaper (`reap_stale_backtests_task`) on a dedicated `backtest_maintenance` queue so it is never starved behind long runs. The reaper recovers orphaned rows:

- **Stale `RUNNING`** (worker lost after the hard time limit + grace) → `FAILED`.
- **Stale `PENDING`** in the requeue window (lost enqueue) → re-driven.
- **Stale `PENDING`** past the fail threshold (never picked up) → `FAILED`.

### The simulation loop

A run is `StrategyRuntime.run(feed)` (`libs/runtime/llamatrade_runtime/runtime.py`) — an **async, per-trading-date** loop over the shared `StrategySession`:

```
for (date, bars, warm_up) in feed:            # bars = one bar per symbol for the date
    portfolio.update_prices(bars)             # mark to market
    if warm_up: session.evaluate(warm_up=True); continue   # prime indicators, no trading
    if should_abort(): raise RuntimeCancelled              # cooperative cancel (Redis flag)
    orders = session.evaluate(bars, holdings, equity)      # evaluate → size
    for order in orders:
        outcome = execution.execute(order, bar, portfolio, date)   # fill at close ± slippage
        observer.on_fill / on_trade / on_reject
    equity_curve.append((date, portfolio.equity()))
# liquidate open positions at last known prices, then assemble RunResult
```

The loop is neither vectorized nor parallelized — it is a straight per-date replay through the **same `StrategySession` the live runner uses**, so a backtest reproduces live's evaluation and sizing *decisions* by construction. For the exact parity guarantees and the known backtest-vs-live differences (loop driver, symbol alignment, sizing mode, fill model, price basis), see [execution-runtime.md](../execution-runtime.md). Warm-up ticks (fetched via start-date padding) prime indicators without trading or advancing the rebalance clock.

### Dataset materialization

Before the loop runs, `prepare_dataset` (`services/backtest/src/dataset/`) guarantees complete, gap-free bar coverage and writes an **immutable, content-addressed Parquet snapshot**:

- `DatasetSpec.create(symbols, timeframe, start, end)` → a stable `dataset_hash` (order/case/dupe-invariant SHA-256).
- Warm hit → read the snapshot; otherwise fetch from the market-data service (`StreamHistoricalBars`), fill interior gaps the read path misses, and write the snapshot.
- A **Redis single-flight lock** keyed by `dataset_hash` coalesces concurrent identical prepares: one fetch, others await (with a dead-producer fallback). Redis is optional — absent, it degrades to no coalescing.
- `LocalDatasetStore` writes on-disk Parquet under `BACKTEST_DATASET_DIR`; the default is an in-memory store.

The sim then reads pure warm data — **the backtest never calls Alpaca directly**; all historical data comes through the market-data service.

---

## Directory Structure

```
services/backtest/
├── src/
│   ├── main.py                     # FastAPI app, Connect mount, AuthMiddleware, /health
│   ├── models.py                   # request schemas + VALID_TIMEFRAMES
│   ├── convert.py                  # numeric coercion helpers (safe_float)
│   ├── progress.py                 # BacktestProgressReporter / ProgressSubscriber (Redis pub/sub)
│   ├── proto_mappers.py            # DB rows ↔ proto messages
│   ├── celery_app.py               # Celery config, task routes, beat schedule
│   ├── grpc/
│   │   └── servicer.py             # BacktestServicer — 7 RPCs
│   ├── services/
│   │   └── backtest_service.py     # business logic: create · run · cancel · retry · reap
│   ├── engine/
│   │   ├── bars.py                 # BarData typed dict
│   │   ├── benchmarks.py           # SPY buy & hold, alpha/beta/information ratio
│   │   └── validation.py           # OHLCV validation before simulating
│   ├── dataset/
│   │   ├── spec.py                 # DatasetSpec + dataset_hash
│   │   ├── store.py                # DatasetStore / Local / InMemory
│   │   └── prepare.py              # prepare_dataset (fetch · gap-fill · snapshot · single-flight)
│   └── workers/
│       └── celery_tasks.py         # run_backtest_task, reap_stale_backtests_task
└── tests/
```

The strategy execution core (runtime loop, portfolio, simulated execution, bar feed, metrics) lives in the shared **`llamatrade_runtime`** library, not in this service.

---

## Core Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **BacktestServicer** | `grpc/servicer.py` | Connect RPC handlers for all 7 RPCs |
| **BacktestService** | `services/backtest_service.py` | create, run, cancel, retry, reap; dataset + benchmark orchestration |
| **StrategyRuntime** | `llamatrade_runtime/runtime.py` | per-trading-date evaluate → execute loop |
| **Portfolio / SimulatedExecution** | `llamatrade_runtime/{portfolio,execution}.py` | book of holdings/equity; fill at close ± slippage + flat commission |
| **HistoricalBarFeed** | `llamatrade_runtime/feed.py` | replays materialized bars per date, with warm-up |
| **metrics** | `llamatrade_runtime/metrics.py` | Sharpe, Sortino, drawdown, returns, trade stats |
| **BenchmarkCalculator** | `engine/benchmarks.py` | SPY buy & hold, alpha, beta, information ratio |
| **prepare_dataset** | `dataset/prepare.py` | warm/materialize content-addressed bar snapshot |
| **BacktestProgressReporter / ProgressSubscriber** | `progress.py` | publish/tail progress over Redis pub/sub |
| **Celery tasks** | `workers/celery_tasks.py` | `run_backtest_task`, `reap_stale_backtests_task` |

---

## Historical Data

All historical bars come from the **market-data service** over gRPC (Alpaca-backed, TimescaleDB store-first). The backtest service does not talk to Alpaca or any other data vendor directly.

Supported timeframes (`VALID_TIMEFRAMES`): `1Min`, `5Min`, `15Min`, `30Min`, `1H`, `4H`, `1D`, `1W`.

The fetch window is extended before the requested start (`warmup_padding_days`) so indicators are warm on the first trading date. Strategy-referenced symbols (e.g. an indicator on `SPY` while trading `TLT`) and the benchmark symbol are fetched in the same batch. OHLCV data is validated before simulating (`engine/validation.py`): structural errors abort the run; gaps and suspected splits are logged as warnings.

---

## User Experience

### Initiating a backtest

From the Strategy Builder or Strategy Detail page, users configure: strategy + version, date range, initial capital, timeframe, and optional commission / slippage / symbol overrides.

### Progress tracking

The run executes asynchronously; the UI subscribes to `StreamBacktestProgress` and sees a percentage, a phase message (e.g. "Running simulation"), and a cancel button. Phases: 10% loading strategy, 20% compiled, 30% fetching data, 40–85% simulating, 85–95% metrics/benchmark, 100% completed.

### Results dashboard

On completion the UI shows the equity curve, a performance-metrics panel, trade statistics, a monthly-returns view, the trade list (paged via `GetBacktestTrades`), and the SPY benchmark comparison.

---

## Performance Metrics

Metric math lives in `llamatrade_runtime/metrics.py` and is computed on a **daily-resampled** equity curve (`resample_daily`) so annualized figures are not inflated by intraday bar counts.

### Return metrics

| Metric | Formula | Notes |
| --- | --- | --- |
| **Total Return** | `(final_equity - initial) / initial` | overall gain/loss |
| **Annual Return** | `((1 + total_return) ^ (252 / trading_days)) - 1` | clamped to −100% if the book is wiped out |
| **Monthly Returns** | month-over-month equity change | keyed `YYYY-MM` |

### Risk-adjusted metrics

| Metric | Formula |
| --- | --- |
| **Sharpe Ratio** | `sqrt(252) × mean(returns − daily_rf) / std(returns)` |
| **Sortino Ratio** | `sqrt(252) × mean(returns) / std(downside_returns)` |

Risk-free rate defaults to 2% annual. Both return `0.0` when standard deviation is zero or there are no returns.

### Drawdown metrics

| Metric | Formula |
| --- | --- |
| **Max Drawdown** | `max((peak − equity) / peak)`, guarded against non-positive peaks |
| **Max Drawdown Duration** | longest run of consecutive underwater bars |

### Trade statistics

| Metric | Formula |
| --- | --- |
| **Win Rate** | `winning_trades / total_trades` |
| **Profit Factor** | `sum(wins) / abs(sum(losses))` — `None` when there are no losing trades |
| **Avg Trade Return** | mean `pnl_percent` across trades |
| **Exposure Time** | percentage of trading days with an open position |

---

## Execution Model

For each trading date the runtime marks the portfolio to market, evaluates the session against current holdings and equity, and executes the resulting orders.

**Fills** (`SimulatedExecution`): orders fill at the bar **close**, adjusted for slippage —

- BUY: `price = close × (1 + slippage_rate)` (pay more)
- SELL: `price = close × (1 − slippage_rate)` (receive less)

A flat `commission_rate` is charged per fill. The engine is **long-only**: buy opens/adds, sell closes; any other side is recorded as a rejected signal. Open positions are liquidated at the last known price at the end of the run (no slippage on liquidation).

### Rejected configuration

To avoid silently misleading results, `RunBacktest` rejects config the engine does not honor (`_reject_unsupported_config`): `allow_shorting`, `max_position_size`, and strategy `parameters`. These are surfaced as `INVALID_ARGUMENT` rather than accepted and ignored. `use_adjusted_prices` is honored — the daily bar series is split-adjusted at the source (market-data ingests Alpaca split-adjusted daily bars), so daily backtests are adjusted.

### Plan quota

`RunBacktest` enforces a per-tenant monthly quota (`backtests_per_month` from the tenant's plan; free-tier default 10) via `llamatrade_db.plan_limits.enforce_plan_limit`, returning `RESOURCE_EXHAUSTED` when the quota is exceeded.

---

## API Reference

The service is **Connect/gRPC only** — there is no REST/JSON API and no WebSocket endpoint. Progress is delivered by the `StreamBacktestProgress` server-stream (backed by Redis pub/sub), not a WebSocket.

| RPC | Description |
| --- | --- |
| `RunBacktest` | validate config, create a `PENDING` row, enqueue the Celery task, return the run |
| `GetBacktest` | fetch a run; when `COMPLETED`, attaches results + a bounded trades preview |
| `ListBacktests` | list a tenant's runs (filter by strategy / status, paginated) |
| `CancelBacktest` | set status `CANCELLED` and raise the cooperative cancel flag |
| `StreamBacktestProgress` | server-stream progress updates; replays buffered updates on connect |
| `CompareBacktests` | return several runs' metrics side by side |
| `GetBacktestTrades` | paged trade log for a completed run |

Identity is resolved from the JWT via `resolve_identity_connect`; every handler opens a `tenant_session` (Postgres row-level security), so runs, results, progress, and cancel are all tenant-scoped.

### Result storage

A completed run writes one `BacktestResult` row: scalar metrics (returns, Sharpe/Sortino, drawdown + duration, win rate, profit factor, exposure time, final equity), benchmark fields (return, alpha, beta, information ratio, benchmark equity curve), and inline JSONB detail (`equity_curve`, `trades`, `daily_returns`, `monthly_returns`). The stored equity curve is daily-resampled and capped at 5000 points; the trade list is paged on read via `GetBacktestTrades`.

---

## Benchmark Comparison

Every run compares the strategy against **SPY buy & hold** (`engine/benchmarks.py`): the benchmark's total return and equity curve, plus, on date-joined daily returns, **alpha**, **beta**, and **information ratio**.

- **Beta** = `cov(strategy, spy) / var(spy)`
- **Alpha** = `strategy_return − (rf + beta × (market_return − rf))`

Benchmark bars are taken from the combined fetch (no extra data call) and restricted to the backtest window so warm-up padding does not distort the comparison. If benchmark data is unavailable the run completes without it (benchmark fields are `NULL`).

---

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/backend, progress pub/sub, dataset lock |
| `MARKET_DATA_GRPC_TARGET` | `market-data:8840` | market-data service address |
| `BACKTEST_DATASET_DIR` | — | on-disk Parquet snapshot dir (in-memory store when unset) |
| `BACKTEST_MAX_BARS_PER_SYMBOL` | `100000` | per-symbol bar cap for the fetch |
| `BACKTEST_TASK_SOFT_TIME_LIMIT` | `1800` | Celery soft time limit (s) |
| `BACKTEST_TASK_TIME_LIMIT` | `3600` | Celery hard time limit (s) |
| `BACKTEST_REAPER_INTERVAL` | `300` | reaper beat interval (s) |
| `BACKTEST_TRADES_PREVIEW` | `500` | max trades inlined by `GetBacktest` |
| `BACKTEST_MAX_TRADES_PAGE_SIZE` | `200` | max page size for `GetBacktestTrades` |
| `CORS_ORIGINS` | localhost set | allowed CORS origins |

### Celery configuration

```python
celery_app.conf.update(
    task_soft_time_limit=1800,       # BACKTEST_TASK_SOFT_TIME_LIMIT
    task_time_limit=3600,            # BACKTEST_TASK_TIME_LIMIT
    task_acks_late=True,             # ack after completion
    task_reject_on_worker_lost=True, # reject if the worker dies
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=86400,
    worker_prefetch_multiplier=1,    # fair scheduling
    worker_concurrency=4,
)
# routes: run_backtest_task → "backtest"; reap_stale_backtests_task → "backtest_maintenance"
# beat:   reap-stale-backtests every BACKTEST_REAPER_INTERVAL seconds
```

Transient market-data errors are retried (up to 3×, resetting the row to `PENDING` between attempts); other failures are terminal and leave the row `FAILED` with its error message.

### Port & health

| Service | Port | Health |
|---------|------|--------|
| Backtest | 8830 | `GET /health` → `{"status":"healthy","service":"backtest","version":"0.1.0"}` |

---

## Planned / Not Implemented

The following are documented for direction but are **not** in the current engine:

- **Vectorized / parallel engine** — the runtime is a straight per-date replay; there is no whole-series NumPy engine and no symbol/time-chunk parallelism.
- **Multi-tier / cold storage cache** — no in-process LRU tier and no GCS + DuckDB Parquet cold store. Warm data is the market-data store plus the per-run Parquet dataset snapshot.
- **Multi-source deep history** — history is Alpaca-only via market-data; there is no Polygon.io / Tiingo / EOD Historical ingestion and no pre-2016 coverage.
- **Dividend-adjusted & adjusted intraday prices** — daily bars are split-adjusted at the source, so `use_adjusted_prices` is honored for daily backtests; dividend adjustment and adjusted intraday bars are not implemented.
- **Position sizing caps & parameter overrides** — `max_position_size` and strategy `parameters` are rejected rather than enforced.
- **Additional benchmarks** — only SPY buy & hold (+ alpha/beta/information ratio); no 60/40 portfolio, risk-free-rate, or user-defined custom benchmarks.
- **Walk-forward optimization** and **Monte Carlo simulation** — not implemented.
- **Scale-to-zero worker autoscaling & externalized results** — the Celery worker/beat and broker are deployed (`infrastructure/k8s/base/backtest/`), but KEDA queue-depth autoscaling and moving large result payloads (trades/curves) out of inline Postgres JSONB into object storage remain future work.

---

## Glossary

| Term | Definition |
| --- | --- |
| **Backtest** | simulation of a strategy over historical data |
| **Equity Curve** | time series of portfolio value |
| **Drawdown** | decline from peak equity to current value |
| **Sharpe Ratio** | risk-adjusted return measure |
| **Sortino Ratio** | like Sharpe but only penalizes downside |
| **Win Rate** | percentage of trades that were profitable |
| **Profit Factor** | gross profits divided by gross losses |
| **Slippage** | difference between the close and the simulated fill price |
| **Dataset snapshot** | content-addressed Parquet bar set shared across identical runs |
| **Sleeve** | ledger capital envelope for a live execution (see the strategy service) |
| **Bar** | OHLCV data for a single time period |
