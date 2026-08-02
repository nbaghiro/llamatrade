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
│ fill_ingestion ─► Kafka consumer group (portfolio-ledger) on lt.ledger.fills           │
│ reconciliation ─► periodic ledger⟷broker drift → correction events                     │
│ equity_snapshot ► materialize read-side equity curve                                   │
│ corporate_actions ► nightly announcement scan → propose-only (operator applies)        │
│ writer_election ─► advisory-lock leadership gates the ledger-writer sweep loops        │
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

           trading fills (lt.ledger.fills)        strategy/web fund ops (LedgerService)
                        │                                        │
                        ▼                                        ▼
        ╭───────────────────────────────╮        ╭───────────────────────────────╮
        │ FILL INGESTION (consumer group│        │ FUND DISBURSEMENT             │
        │ per-account FIFO)             │        │ allocate / transfer / dep/wd  │
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
│   ├── alerts.py                            # LedgerAlertDispatcher: incidents → notification stream
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
│   │   ├── checkpoint_store.py             # persisted incremental-projection checkpoints
│   │   ├── ids.py                          # deterministic ledger event ids (idempotency keys)
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
│   │   ├── analytics.py / performance.py   # NumPy risk metrics + per-sleeve P&L
│   │   └── backfill.py                     # seed the ledger from broker state at bootstrap
│   ├── tasks/
│   │   ├── fill_ingestion.py               # Kafka consumer group (per-account FIFO)
│   │   ├── reconciliation.py               # periodic ledger⟷broker reconcile loop
│   │   ├── equity_snapshot.py              # read-side equity-curve materialization
│   │   ├── corporate_actions.py            # corporate-action detection feed (propose-only)
│   │   ├── drift_policy.py                 # how each drift kind is resolved
│   │   ├── dlq_replay.py                   # operator tool: replay DLQ'd fills
│   │   ├── writer_election.py              # advisory-lock election for the writer sweeps
│   │   └── supervisor.py                   # re-export shim: llamatrade_common.supervise + LeadershipProbe
│   ├── services/
│   │   ├── portfolio_read_service.py       # summary / positions / transactions / metrics
│   │   ├── read_context.py                 # per-request read caches (one fold / one price per request)
│   │   ├── strategy_performance_service.py # per-strategy P&L (write side)
│   │   ├── strategy_performance_read_service.py # per-strategy reads + equity curve
│   │   ├── sleeve_service.py               # sleeve reads / equity / free cash
│   │   ├── sleeve_lifecycle_service.py     # close-sleeve orchestration
│   │   ├── fund_service.py                 # fund disbursement orchestration
│   │   ├── corporate_action_service.py     # corporate-action application
│   │   └── onboarding_service.py           # account + base-sleeve bootstrap
│   ├── clients/
│   │   ├── market_data.py                  # HTTP client for price enrichment
│   │   └── alpaca.py                       # broker positions/cash + corporate announcements
│   └── tools/
│       └── statement.py                    # operator tool: render an account's ledger statement
└── tests/
    ├── conftest.py · golden/
    ├── test_ledger_kernel.py · test_ledger_phases.py · test_fill_ingestion.py
    ├── test_fill_stream_contract.py · test_invariant_freeze_e2e.py · test_invariants.py
    ├── test_reconciliation_task.py · test_drift_policy.py · test_alpaca_broker.py
    ├── test_corporate.py · test_corporate_action_service.py · test_corporate_actions_task.py
    ├── test_alerts.py · test_ledger_incident_alerts.py
    ├── test_sleeve_service.py · test_sleeve_lifecycle_service.py · test_fund_service.py
    ├── test_onboarding_service.py · test_account_identity_sweep.py
    ├── test_portfolio_read_service.py · test_strategy_performance_read_service.py
    ├── test_read_model.py · test_analytics.py · test_projector_checkpoint.py
    ├── test_equity_snapshot.py · test_supervisor.py · test_statement.py
    ├── test_grpc_servicer.py · test_ledger_servicer.py · test_servicer_auth.py
    ├── test_proto_mappers.py · test_metrics.py · test_health.py
    └── integration/  (writer, servicer, rls, fill_e2e, account_identity, writer_lock_failover)
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
| **Fill ingestion**               | `tasks/fill_ingestion.py`                      | Consumer-group ingestion (per-account FIFO) + lag monitor  |
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

- **Fill consumer** — a durable Kafka consumer group (`portfolio-ledger`) on the
  `lt.ledger.fills` topic, keyed by `account_id`. Trading publishes proto
  `LedgerFill` / `LedgerReservation` messages there ([the ledger integration contract](../portfolio-ledger.md#integration-contract-trading--portfolio--strategy)).
  Every pod is a group member: Kafka assigns each account's partition to one
  member, so per-account FIFO (buy-before-sell for FIFO cost basis) holds while
  ingestion runs in parallel across accounts; the group coordinator handles
  failover. Offsets are committed only after the append persists
  (commit-after-write), so a crash redelivers rather than drops.
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
- **Corporate-action detection** (`tasks/corporate_actions.py`): a nightly,
  leader-only pass that proposes splits, ticker renames and dividends detected
  on held symbols; it never appends to the ledger (see
  [Corporate-Action Detection](#corporate-action-detection)).
- **Supervisor + lag monitor** — restart crashed loops; a sustained ingestion
  backlog (consumer-group lag) fails the liveness probe so a hung pod is recycled
  and its partitions rebalance to healthy members. The lag monitor also samples
  the DLQ-depth gauge `llamatrade_ledger_fill_dlq_depth` and warns when new fills
  land on the DLQ topic. The ledger-writer loops (reconciliation, snapshots,
  corporate-action detection) run **only** on the pod holding a Postgres advisory
  lock, to avoid double-writes; fill ingestion itself needs no election. The
  election lives in `tasks/writer_election.py`; `tasks/supervisor.py` is a
  re-export shim exposing the shared `llamatrade_common.supervise` restart loop
  plus the ledger-local `LeadershipProbe` type alias.

---

## Corporate-Action Detection

`tasks/corporate_actions.py` closes the gap between the corporate-action
planners and the broker: without detection, a split or dividend surfaces only as
unattributed drift at reconciliation. A periodic pass runs on
`LEDGER_CORPORATE_ACTIONS_INTERVAL_SECONDS` (default 86400; nightly, because
announcements land the trading day after declaration), only on the pod holding
the writer advisory lock. Each pass:

- reads Alpaca's corporate-announcement feed
  (`clients/alpaca.py::AlpacaCorporateAnnouncements`) for the symbols each
  account actually holds, over a 7-day lookback window;
- maps each announcement onto a `ledger/corporate.py` planner: splits, symbol
  changes, and cash dividends. Mergers, spinoffs, and stock dividends have no
  planner; they are counted
  (`llamatrade_ledger_corporate_actions_unsupported_total`) and logged rather
  than silently dropped;
- records the result as a **proposal only** and never appends to the ledger:
  `record_proposal` emits a structured warning carrying every argument the
  operator needs, and a `corporate_action_proposed` notification is dispatched.
  Booking happens when an operator calls the `ApplyCorporateAction` RPC, which
  publishes `corporate_action_applied` once the events commit.

Re-polling is idempotent: the proposal id derives from the announcement identity
plus the account, a per-process `seen` set surfaces each proposal once, and a
proposal whose planned event ids already exist in the event log (the operator
applied it) is dropped rather than re-proposed. A failure or timeout on one
account never aborts the pass.

---

## Ledger Incident Alerts

`src/alerts.py` (`LedgerAlertDispatcher`) publishes alert-worthy ledger
incidents onto the `lt.notifications` Kafka topic via the shared
`NotificationEvents` producer (`llamatrade_events`); the notification service
owns delivery (in-app row, email, webhooks). Dispatch uses `publish_safe`:
best-effort, failures are logged and swallowed, so an alerting outage never
breaks a ledger operation. Deterministic dedup ids (derived from the incident
kind plus its identifying context: sleeve, order, proposal, account, symbol)
collapse re-reports of the same incident, such as a sleeve freeze re-detected on
every reconciliation pass or a quarantined fill redelivered.

Categories and severities are the proto `NotificationCategory` /
`NotificationSeverity` values (prefixes elided):

| Kind                        | Category                    | Severity   | Raised from                                                                                                           |
| --------------------------- | --------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| `sleeve_frozen`             | `SLEEVE_FROZEN`             | CRITICAL   | invariant-violation freeze after a fill (`tasks/fill_ingestion.py`); position-drift and cash-drift freezes (`tasks/drift_policy.py`) |
| `fill_quarantined`          | `FILL_QUARANTINED`          | CRITICAL   | a fill parked on the DLQ for review (`tasks/fill_ingestion.py`)                                                        |
| `dlq_backlog`               | `FILL_QUARANTINED`          | CRITICAL   | reserved, no call site; aggregate backlog is operator-scoped via Prometheus                                            |
| `external_trade_adopted`    | `EXTERNAL_TRADE_ADOPTED`    | ACTIONABLE | reconciliation adopts an unknown broker holding into Unmanaged (`tasks/drift_policy.py`)                               |
| `corporate_action_proposed` | `CORPORATE_ACTION_PROPOSED` | ACTIONABLE | the detection pass proposes an action (`tasks/corporate_actions.py`)                                                   |
| `corporate_action_applied`  | `CORPORATE_ACTION_APPLIED`  | INFO       | `ApplyCorporateAction` after its events commit (`grpc/ledger_servicer.py`)                                             |

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

# Kafka (ledger fill stream transport)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Market-Data service for price enrichment
MARKET_DATA_URL=http://localhost:8840

# Ledger runtime tuning
LEDGER_RECONCILE_INTERVAL_SECONDS=...            # default 300
LEDGER_SNAPSHOT_INTERVAL_SECONDS=...             # default 3600
LEDGER_CORPORATE_ACTIONS_INTERVAL_SECONDS=...    # default 86400

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

**Endpoints:** `GET /health` (full check), `GET /health/live` (always 200),
`GET /health/ready` (503 only on a critical-check failure). Served by the
shared `HealthChecker` from `llamatrade_common`.

```json
{
  "status": "healthy",
  "timestamp": "2026-01-01T00:00:00Z",
  "service": "portfolio",
  "version": "0.1.0",
  "checks": {
    "database": { "healthy": true, "latency_ms": 1.2, "critical": false },
    "kafka": { "healthy": true, "latency_ms": 0.1, "critical": false },
    "ledger_runtime": { "healthy": true, "latency_ms": 0.0, "critical": false }
  }
}
```

All three checks are registered non-critical, so a failure degrades `status` to
`degraded` (HTTP 200) rather than 503: reads stay available. `database` probes
Postgres. `kafka` is answered from the fill consumer's shared
`KafkaTransport.is_connected` (no second broker connection), falling back to a
short authenticated probe before the runtime starts. `ledger_runtime` surfaces
the background runtime's tri-state as the check message: `down` when the
runtime never started, `degraded` when a supervised task crashed or the fill
consumer is backlogged (the lag tracker), else `ok`.

---

## Startup / Shutdown

**Startup:** init DB → create `PortfolioServicer` + `LedgerServicer` → mount both
Connect ASGI apps → start the ledger runtime (fill consumer joins the Kafka
consumer group on every pod; reconciliation + equity snapshots start only on the
pod holding the writer advisory lock; supervisor + lag monitor run everywhere).

**Shutdown:** signal the runtime `stop_event`, cancel and await the ledger tasks,
release the writer advisory lock if held, close the DB pool.

---

## Testing

```bash
cd services/portfolio && pytest
pytest --cov=src --cov-report=term-missing
```

Key scenarios: writer idempotency + balance enforcement (`test_ledger_kernel`,
`test_ledger_phases`, `integration/test_writer_integration`), fill ingestion
FIFO / quarantine / stray re-home (`test_fill_ingestion`,
`test_fill_stream_contract`, `test_invariant_freeze_e2e`,
`integration/test_fill_e2e`), reconciliation drift classification
(`test_reconciliation_task`, `test_drift_policy`, `test_alpaca_broker`), sleeve
lifecycle + close re-home (`test_sleeve_service`,
`test_sleeve_lifecycle_service`), corporate actions (`test_corporate`,
`test_corporate_action_service`, `test_corporate_actions_task`), incident alerts
(`test_alerts`, `test_ledger_incident_alerts`), fund ops (`test_fund_service`),
onboarding + account identity (`test_onboarding_service`,
`test_account_identity_sweep`, `integration/test_account_identity`), read model +
strategy performance (`test_portfolio_read_service`,
`test_strategy_performance_read_service`, `test_read_model`, `test_analytics`,
`test_projector_checkpoint`), runtime plumbing (`test_equity_snapshot`,
`test_supervisor`, `test_metrics`, `test_health`, `test_statement`,
`integration/test_writer_lock_failover`), invariants (`test_invariants`),
servicer surface + auth/isolation (`test_grpc_servicer`, `test_ledger_servicer`,
`test_proto_mappers`, `test_servicer_auth`, `integration/test_servicer_integration`,
`integration/test_rls`).

---

## Related Documentation

- [Portfolio Ledger](../portfolio-ledger.md) — the full sleeve/lot/ledger design
  and the trading⟷portfolio integration contract (payloads, stream, idempotency,
  identity threading).
- [Trading Service](trading.md) — the execution arm that emits fills.
