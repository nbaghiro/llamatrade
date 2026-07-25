# Portfolio Service Architecture

The portfolio service is the **book of record** for LlamaTrade. It owns the
event-sourced, double-entry **[Portfolio Ledger](../portfolio-ledger.md)** — the
single source of truth that lets multiple strategies and manual trading share one
brokerage account while preserving exact, per-holding provenance. The trading
service executes orders and emits fills; the portfolio service consumes those
fills and owns sleeves, lots, cash sub-ledgers, fund allocation, corporate
actions, and reconciliation against broker truth.

The service exposes two Connect servicers from a single process (`:8860`):

- **`PortfolioService`** — the read model: portfolio summary, positions,
  performance analytics, transactions, and per-strategy performance. Every read
  derives from the ledger projection.
- **`LedgerService`** — the write/administration surface: account bootstrap, fund
  disbursement (allocate / transfer / deposit / withdraw), sleeve lifecycle
  (close), corporate actions, and sleeve/holding queries.

---

## Overview

The portfolio service is responsible for:

- **The Ledger**: An append-only, double-entry event log (`ledger_events`) —
  every value-moving fact recorded exactly once as a balanced, sleeve-tagged event.
- **Projections**: Per-sleeve positions/lots, cash (`free = balance − reserved`),
  and realized/unrealized P&L, all derived as deterministic folds of the log.
- **Fund Disbursement**: Allocate capital to strategy sleeves, transfer between
  sleeves, deposit/withdraw — virtual moves over per-sleeve cash sub-ledgers.
- **Fill Ingestion**: Consume trading's `LedgerFill` / `LedgerReservation` events
  and append balanced ledger events (FIFO cost basis resolved at ingestion).
- **Reconciliation**: Assert `Σ sleeve_qty(symbol) == broker_qty(symbol)`,
  classify drift, and resolve it (adopt externals into Unmanaged, freeze on
  material drift).
- **Corporate Actions**: Splits, symbol changes, and dividends applied lot-by-lot
  with provenance preserved.
- **Read-Side Analytics**: Portfolio summary, valuation, and risk metrics
  (Sharpe, Sortino, max drawdown) over the ledger-derived equity series.

---

## Architecture Overview

### System Architecture

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║                       PORTFOLIO SERVICE  ·  :8860  —  book of record                       ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                 FastAPI + Connect ASGI                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ /health                  PortfolioServiceASGIApplication + LedgerServiceASGIApplication │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭─────────────────────────────────────────┬──────────────────────────────────────────────╮
│           PortfolioServicer (reads)      │            LedgerServicer (writes)           │
├─────────────────────────────────────────┼──────────────────────────────────────────────┤
│ GetPortfolio · GetPositions             │ GetOrCreateAccount                           │
│ GetPerformance · GetAssetAllocation     │ AllocateCapital · TransferCapital            │
│ ListTransactions · SyncPortfolio        │ DepositFunds · WithdrawFunds                 │
│ ListStrategyPerformance                 │ CloseSleeve · ApplyCorporateAction           │
│ GetStrategyPerformance · EquityCurve    │ ListSleeves · GetSleeve · GetHoldingHistory  │
╰─────────────────────────────────────────┴──────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                  Ledger Core (src/ledger/)                             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ writer ─────► append-only, balance-checked, idempotent (ON CONFLICT event_id)          │
│ projector/projection ─► fold events → AccountProjection (sleeve cash / lots / P&L)     │
│ ingestion ──► LedgerFill/LedgerReservation → balanced append (+ FIFO sizing)           │
│ reconciliation · corporate · funds · lifecycle · invariants · postings · netting       │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                            Background Ledger Runtime (src/tasks/)                       │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ fill_ingestion ─► single active consumer (advisory lock) on lt:ledger:fills            │
│ reconciliation ─► periodic ledger⟷broker drift → correction events                     │
│ equity_snapshot ► materialize read-side equity curve                                   │
│ supervisor ─────► restart crashed loops; lag monitor fails liveness on stall           │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
                  ┌───────────────────────┬──┴─────────────────────────┐
                  ▼                       ▼                            ▼
           ┌────────────┐          ╭─────────────╮          ╭────────────────────╮
           │ PostgreSQL │          │ market-data │          │ producers/consumers│
           │ ledger_*   │          │ :8840       │          │ trading (fills) ·  │
           │ tables     │          │ valuation   │          │ strategy · web     │
           └────────────┘          ╰─────────────╯          ╰────────────────────╯
```

### Data Flow

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║        PORTFOLIO DATA FLOW  ·  fills/fund-ops → append → projection → reads/analytics       ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝

           trading fills (lt:ledger:fills)        strategy/web fund ops (LedgerService)
                        │                                        │
                        ▼                                        ▼
        ╭───────────────────────────────╮        ╭───────────────────────────────╮
        │ FILL INGESTION (single FIFO   │        │ FUND DISBURSEMENT             │
        │ consumer)                     │        │ allocate / transfer / dep/wd  │
        │ • re-home stray CLOSED-sleeve │        │ • solvency check on free cash │
        │ • FIFO cost basis on sells    │        │ • virtual, balanced moves     │
        │ • freeze on invariant breach  │        │                               │
        ╰───────────────────────────────╯        ╰───────────────────────────────╯
                        └───────────────────┬────────────────────┘
                                            ▼
                        ╔════════════════════════════════════════════╗
                        ║ LedgerWriter.append  (SINGLE SOURCE)       ║
                        ║ balanced double-entry · idempotent on       ║
                        ║ event_id · conservation asserted at write   ║
                        ╚════════════════════════════════════════════╝
                                            │  fold
                                            ▼
                        ╭────────────────────────────────────────────╮
                        │ AccountProjection  (per sleeve)            │
                        │ cash(free/reserved) · lots · realized/     │
                        │ unrealized P&L · account aggregate         │
                        ╰────────────────────────────────────────────╯
                                            │
                        ┌───────────────────┴────────────────────┐
                        ▼                                         ▼
                reads (PortfolioService)                reconciliation (ledger⟷broker)
                enriched via market-data                append correction events
```

---

## Directory Structure

```
services/portfolio/
├── src/
│   ├── main.py                              # FastAPI app, lifespan, ledger runtime, health
│   ├── repositories.py                      # SQLAlchemy repositories (accounts, sleeves, events)
│   ├── ports.py                             # Protocols the services depend on
│   ├── proto_mappers.py                     # projection views ↔ proto messages
│   ├── metrics.py                           # Prometheus metrics
│   ├── grpc/
│   │   ├── servicer.py                     # PortfolioServicer (read model)
│   │   └── ledger_servicer.py              # LedgerServicer (fund ops, sleeve lifecycle)
│   ├── ledger/
│   │   ├── writer.py                       # Append-only, balance-checked, idempotent writer
│   │   ├── postings.py                     # event → balanced double-entry legs
│   │   ├── projector.py / projection.py    # fold events → AccountProjection
│   │   ├── read_model.py                   # summary / position / transaction views
│   │   ├── ingestion.py                    # LedgerFill/LedgerReservation → append (+ FIFO)
│   │   ├── sizing.py                       # FIFO lot selection
│   │   ├── reconciliation.py               # drift classification (pure)
│   │   ├── corporate.py                    # splits / symbol changes / dividends (pure)
│   │   ├── funds.py                        # allocate / transfer / deposit / withdraw planners
│   │   ├── lifecycle.py                    # sleeve close / re-home planning (pure)
│   │   ├── desired_state.py                # target vs actual → intended orders
│   │   ├── netting.py                      # block-and-allocate netting (Planned / Not implemented)
│   │   ├── invariants.py                   # sleeve invariant checks
│   │   ├── analytics.py / performance.py   # NumPy risk metrics over equity series
│   │   └── backfill.py                     # seed the ledger from broker state at bootstrap
│   ├── tasks/
│   │   ├── fill_ingestion.py               # durable consumer group + advisory-lock election
│   │   ├── reconciliation.py               # periodic ledger⟷broker reconcile loop
│   │   ├── equity_snapshot.py              # read-side equity-curve materialization
│   │   ├── drift_policy.py                 # how each drift kind is resolved
│   │   └── supervisor.py                   # supervise/restart the runtime loops
│   ├── services/
│   │   ├── portfolio_read_service.py       # summary / positions / transactions / metrics
│   │   ├── strategy_performance_service.py # per-strategy P&L (write side)
│   │   ├── strategy_performance_read_service.py # per-strategy reads + equity curve
│   │   ├── sleeve_service.py               # sleeve reads / equity / free cash
│   │   ├── sleeve_lifecycle_service.py     # close-sleeve orchestration
│   │   ├── fund_service.py                 # fund disbursement orchestration
│   │   ├── corporate_action_service.py     # corporate-action application
│   │   └── onboarding_service.py           # account + base-sleeve bootstrap
│   └── clients/
│       ├── market_data.py                  # HTTP client for price enrichment
│       └── alpaca.py                       # broker positions/cash for reconciliation
└── tests/
    ├── conftest.py
    ├── test_ledger_*.py / test_fill_ingestion.py / test_reconciliation_task.py
    ├── test_sleeve_*.py / test_fund_service.py / test_corporate*.py
    ├── test_portfolio_read_service.py / test_strategy_performance_read_service.py
    ├── test_grpc_servicer.py / test_ledger_servicer.py / test_servicer_auth.py
    └── integration/  (test_writer_integration, test_servicer_integration, test_rls)
```

---

## Core Components

| Component                        | File                                          | Responsibility                                             |
| -------------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| **PortfolioServicer**            | `grpc/servicer.py`                            | Read-model RPCs; `resolve_identity_connect` on every call  |
| **LedgerServicer**               | `grpc/ledger_servicer.py`                     | Fund ops, sleeve lifecycle, corporate actions, sleeve reads|
| **LedgerWriter**                 | `ledger/writer.py`                            | The single mutating entry point — balanced + idempotent    |
| **LedgerProjector**              | `ledger/projector.py`                         | Fold events → `AccountProjection`                          |
| **PortfolioReadService**         | `services/portfolio_read_service.py`          | Summary, positions, transactions, performance metrics      |
| **StrategyPerformanceReadService** | `services/strategy_performance_read_service.py` | Per-strategy performance + equity curve               |
| **FundService**                  | `services/fund_service.py`                     | Allocate / transfer / deposit / withdraw                   |
| **SleeveLifecycleService**       | `services/sleeve_lifecycle_service.py`         | Close a sleeve, re-home holdings to Unmanaged/Unallocated  |
| **CorporateActionService**       | `services/corporate_action_service.py`         | Apply splits / symbol changes / dividends                  |
| **Fill ingestion**               | `tasks/fill_ingestion.py`                      | Single-active-consumer FIFO ingestion + lag monitor        |
| **MarketDataClient**             | `clients/market_data.py`                       | HTTP client for current prices (valuation)                 |

---

## RPC Endpoints

### PortfolioService (read model)

| RPC                      | Description                                                     |
| ------------------------ | -------------------------------------------------------------- |
| `GetPortfolio`           | Portfolio summary + positions (projected from the ledger)      |
| `ListPortfolios`         | Accounts for the tenant                                        |
| `GetPerformance`         | Risk metrics + time series over the ledger equity curve        |
| `GetAssetAllocation`     | Composition breakdown by holding                               |
| `GetPositions`           | All current positions (aggregated across sleeves)              |
| `ListTransactions`       | Paginated transaction history derived from ledger events       |
| `SyncPortfolio`          | Reconcile-on-demand against broker truth                       |
| `ListStrategyPerformance`| Per-strategy P&L rows                                          |
| `GetStrategyPerformance` | One strategy's performance detail                              |
| `GetStrategyEquityCurve` | One strategy's equity time series                             |

### LedgerService (writes + administration)

Served by the same portfolio process (`:8860`). See
[the ledger integration contract](../portfolio-ledger.md#integration-contract-trading--portfolio--strategy) for the locked surface.

| RPC                    | Description                                                             |
| ---------------------- | ---------------------------------------------------------------------- |
| `GetOrCreateAccount`   | Lazy, idempotent `credentials_id → account` bootstrap + base sleeves   |
| `DepositFunds`         | Cash in → Unallocated                                                  |
| `WithdrawFunds`        | Cash out (from free cash; raises cash if needed)                       |
| `AllocateCapital`      | Unallocated → strategy sleeve (open-and-fund by `strategy_execution_id`)|
| `TransferCapital`      | Sleeve → sleeve virtual transfer                                       |
| `CloseSleeve`          | Retire a sleeve; re-home holdings → Unmanaged, cash → Unallocated       |
| `ApplyCorporateAction` | Split / symbol change / dividend applied lot-by-lot                    |
| `ListSleeves`          | Sleeves for an account                                                 |
| `GetSleeve`            | Sleeve + open lots + projected cash (`free = balance − reserved`)      |
| `GetHoldingHistory`    | Ordered lot open/close timeline for a symbol (provenance view)         |

---

## The Ledger Model

The single source of truth is the append-only `ledger_events` table. Everything
else is a projection. Live sleeve balances, positions, and reserved cash are
**never** stored as mutable columns — they are folds of the log.

| Table                     | Model           | Notes                                                            |
| ------------------------- | --------------- | ---------------------------------------------------------------- |
| `ledger_accounts`         | `Account`       | One per `credentials_id` (unique); reconciliation anchor         |
| `ledger_sleeves`          | `Sleeve`        | `type`, `status`, `strategy_execution_id`, `allocated_capital`   |
| `ledger_events`           | `LedgerEvent`   | Immutable; `sequence` (order), `event_id` (idempotency), `data`  |
| `ledger_sleeve_snapshots` | `SleeveSnapshot`| Materialized `cash_balance`/`reserved_cash`/`equity`/`lots` at a sequence — a replay optimization |
| `ledger_lots`             | `Lot`           | Reserved read-optimization: holdings are projected into snapshot `lots`; this table is not on the hot path |

**Enums** (`SleeveType`: strategy/manual/unmanaged/unallocated; `SleeveStatus`:
active/frozen/closed; `LedgerEventType`: capital, trading, position, cash,
corporate, reconciliation, and sleeve-lifecycle families).

**Append semantics** (`LedgerWriter.append`):

- **Idempotent** — `INSERT … ON CONFLICT (event_id) DO NOTHING`; a re-delivered
  fill or a replay is a no-op (effective-once).
- **Balance-checked** — `assert_balanced(build_postings(event_type, data))`;
  economic events must expand to double-entry legs that net to zero, or the append
  is rejected. Conservation is enforced at write time, not hoped for.

---

## Fill Ingestion & Background Runtime

Started in `main.py`'s lifespan and supervised:

- **Fill consumer** — a durable Redis Streams consumer group (`portfolio-ledger`)
  on the global `lt:ledger:fills` stream. Trading publishes proto `LedgerFill` /
  `LedgerReservation` messages there ([the ledger integration contract](../portfolio-ledger.md#integration-contract-trading--portfolio--strategy)).
  Exactly **one active consumer** is elected via a Postgres advisory lock, because
  per-account FIFO (buy-before-sell for FIFO cost basis) requires serialized
  processing; a dead pod's pending entries are reclaimed via XAUTOCLAIM.
- **FIFO cost basis** — a sell without a publisher-supplied `cost_basis` is
  enriched at ingestion (`enrich_sell_fill` → `sizing.select_lots_fifo`) against
  the account projection. A sell whose open lots can't cover it is **quarantined**
  (dropped to `ledger:fills:dlq` for review), never recorded with a fabricated
  basis. An operator replay tool (`python -m src.tasks.dlq_replay`,
  `tasks/dlq_replay.py::replay_dlq`) re-drives DLQ'd fills back onto `ledger:fills`
  idempotently once the root cause is fixed, clearing the DLQ on a full drain.
- **Stray fills** — a fill for a CLOSED sleeve is re-homed to Unmanaged so it can't
  resurrect a retired sleeve; a fill that drives a sleeve into an impossible state
  freezes it (`SLEEVE_FROZEN` + alert).
- **Reconciliation loop** — periodically pulls broker positions/cash and asserts
  `Σ sleeve_qty == broker_qty`. Drift is classified (`OK` / `DUST` /
  `MISSING_AT_BROKER` / `MISSING_IN_LEDGER` / `QTY_MISMATCH`) and resolved by the
  drift policy: unknown broker holdings → Unmanaged (`EXTERNAL_TRADE_DETECTED`);
  material mismatch → freeze the affected sleeves.
- **Equity snapshots** — materialize the read-side equity curve for analytics.
- **Supervisor + lag monitor** — restart crashed loops; a sustained ingestion
  backlog fails the liveness probe so a hung active consumer is recycled (releasing
  the lock to a standby). The lag monitor also samples the DLQ-depth gauge
  `llamatrade_ledger_fill_dlq_depth` and warns when new fills land on
  `ledger:fills:dlq`. The ledger-writer loops (reconciliation, snapshots) run
  **only** on the lock-holding pod to avoid double-writes.

---

## Performance Metrics

`PortfolioReadService.get_metrics` computes risk-adjusted metrics with NumPy over
the ledger-derived daily equity series (`ledger/analytics.py`):

| Metric                | Formula                                       | Description                              |
| --------------------- | --------------------------------------------- | ---------------------------------------- |
| **Annualized Return** | `((1 + total)^(252/days) - 1) * 100`          | Return projected to annual rate          |
| **Volatility**        | `std(daily_returns) * sqrt(252) * 100`        | Annualized standard deviation            |
| **Sharpe Ratio**      | `sqrt(252) * mean(excess) / std`              | Risk-adjusted return (vs 2% risk-free)   |
| **Sortino Ratio**     | `sqrt(252) * mean(excess) / downside_std`     | Like Sharpe but only downside volatility |
| **Max Drawdown**      | `max((peak - current) / peak) * 100`          | Maximum peak-to-trough decline           |

Benchmark alpha/beta vs SPY is available via `analytics.benchmark_metrics`. With
fewer than two equity points the metrics degrade to zeros.

---

## Multi-Tenancy

- **Identity** — every RPC in both servicers resolves the caller via
  `resolve_identity_connect`; the wire `TenantContext` is never trusted directly.
- **Scoped sessions** — reads and writes run inside a `tenant_session`, and the
  integration suite (`tests/integration/test_rls.py`) asserts row-level isolation
  so one tenant can never read another's ledger.
- **Per-account partitioning** — each account owns an independent event stream
  (one `credentials_id`), so accounts scale horizontally with no cross-account
  contention.

---

## External Integrations

| Service         | Use Case                                   | Method                             |
| --------------- | ------------------------------------------ | ---------------------------------- |
| **Market-Data** | Current prices for valuation/analytics     | HTTP `GET /quotes/{symbol}/latest` |
| **Alpaca**      | Broker positions/cash for reconciliation   | `llamatrade_alpaca` (via `clients/alpaca.py`) |

Consumed by: **web** (dashboard/portfolio views), **strategy** (funds a strategy
execution via `AllocateCapital`, closes its sleeve via `CloseSleeve`), **trading**
(reads sleeve equity / free cash via `GetSleeve` for sleeve-aware sizing and risk).

---

## Configuration

```bash
# Database (required)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/llamatrade

# Redis (ledger fill stream transport)
REDIS_URL=redis://localhost:6379

# Market-Data service for price enrichment
MARKET_DATA_URL=http://localhost:8840

# Ledger runtime tuning
LEDGER_RECONCILE_INTERVAL_SECONDS=...
LEDGER_SNAPSHOT_INTERVAL_SECONDS=...

# CORS / Logging
CORS_ORIGINS=http://localhost:8800,http://localhost:3000
LOG_LEVEL=INFO
```

### Service Port

- **Port**: 8860
- **Health Check**: `GET http://localhost:8860/health` — also reports the ledger
  runtime's liveness (fill consumer / reconciliation / snapshots).

---

## Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "service": "portfolio",
  "version": "0.1.0"
}
```

---

## Startup / Shutdown

**Startup:** init DB → create `PortfolioServicer` + `LedgerServicer` → mount both
Connect ASGI apps → start the ledger runtime (elect the single fill consumer via
advisory lock; on the lock holder also start reconciliation + equity snapshots;
start the supervisor + lag monitor).

**Shutdown:** signal the runtime `stop_event`, cancel and await the ledger tasks,
release the fill-consumer advisory lock, close the DB pool.

---

## Testing

```bash
cd services/portfolio && pytest
pytest --cov=src --cov-report=term-missing
```

Key scenarios: writer idempotency + balance enforcement (`test_ledger_writer`,
`test_ledger_kernel`), fill ingestion FIFO / quarantine / stray re-home
(`test_fill_ingestion`, `test_fill_stream_contract`), reconciliation drift
classification (`test_reconciliation_task`, `test_drift_policy`), sleeve lifecycle
+ close re-home (`test_sleeve_lifecycle_service`), corporate actions
(`test_corporate*`), fund ops (`test_fund_service`), read model + strategy
performance (`test_portfolio_read_service`, `test_strategy_performance_read_service`),
invariants (`test_invariants`), servicer auth/isolation (`test_servicer_auth`,
`integration/test_rls`).

---

## Related Documentation

- [Portfolio Ledger](../portfolio-ledger.md) — the full sleeve/lot/ledger design
  and the trading⟷portfolio integration contract (payloads, stream, idempotency,
  identity threading).
- [Trading Service](trading.md) — the execution arm that emits fills.
