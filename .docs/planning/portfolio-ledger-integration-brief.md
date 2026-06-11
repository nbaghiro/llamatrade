# Portfolio Ledger — Parallel Integration Brief

Hand-off for integrating the already-built portfolio ledger into the running
services + web client. Contains a **shared contract** (lock first) and **6
self-contained work packages** that can run largely in parallel.

- Ledger code (built, unit-validated, committed `aa325c4`): `services/portfolio/src/ledger/*`, `libs/db/.../models/ledger.py`, `libs/proto/.../protos/ledger.proto`, migration `015`.
- Design: `.docs/portfolio-ledger.md` · `.docs/strategy-dsl.md`. (Full phase plan + implementation hand-off available internally on request.)

---

## 0. Shared context (read first, everyone)

**What the ledger is.** One append-only, double-entry event log (`ledger_events`) per **Account** (one per broker credential set), partitioned into **Sleeves** (`strategy`/`manual`/`unmanaged`/`unallocated`) holding cash + provenance-bearing **Lots**. Sleeve cash/positions/P&L/holdings are *pure projections* of the log. Portfolio service = book of record; trading service = execution arm that emits fills.

**Invariants** (never violate): conservation (event postings sum to 0); `Σ sleeve_qty == broker_qty`; `Σ sleeve_cash == broker_cash`; idempotency (ledger `event_id = sha256(client_order_id)`); attribution fixed at order origination.

**Feature flags** (`services/portfolio/src/ledger/settings.py`), rolled out in order — keep legacy paths until each is proven:
`LEDGER_SHADOW_MODE → LEDGER_SLEEVES → LEDGER_EXECUTION → LEDGER_DESIRED_STATE → LEDGER_NETTING`.

**Services that DON'T change:** auth, billing, market-data, agent, backtest, libs/alpaca (read-only use), libs/db (done). (Accounts bootstrap lazily in portfolio, so auth needs no change.)

---

## 1. THE CONTRACT (Wave 0 — one owner, blocks Trading/Strategy/Web)

Everything below is the agreed interface the other packages code against. Lock and `make proto` before Wave 1 starts.

### 1a. Redis fill event (Trading → Portfolio)
- **Channel:** `ledger:fills:{account_id}` (see `portfolio/src/ledger/ingestion.py:FILL_CHANNEL_PREFIX`).
- **Payload (JSON)** — must match `ingestion.fill_to_append`:
  ```json
  {
    "tenant_id": "<uuid>", "account_id": "<uuid>", "sleeve_id": "<uuid>",
    "client_order_id": "lt-<hash>", "order_id": "<uuid>",
    "symbol": "SPY", "side": "buy|sell", "qty": "50", "price": "480.00",
    "fees": "0.00",                // optional
    "cost_basis": "4800.00",       // REQUIRED on sells (FIFO closed cost)
    "realized_pnl": "200.00",      // optional on sells
    "filled_at": "2026-06-11T14:30:00Z"
  }
  ```

### 1b. Proto changes (`libs/proto/.../protos/trading.proto`)
- `Order` (≈L68-108): add `string sleeve_id` and `string account_id`.
- `Fill` (≈L111-120): add `string sleeve_id`, `string account_id`.
- `TradingSession` (≈L151-169): add `string account_id`.
- `ledger.proto` already defines `LedgerService` (AllocateCapital/TransferCapital/Deposit/Withdraw/ListSleeves/GetSleeve/GetHoldingHistory) — **served by the portfolio service process** (port 8860), not a new service.
- Run `make proto` (python) **and** `make proto-web` (TS). Generated dirs are gitignored.

### 1c. LedgerClient (`libs/proto/.../clients/ledger.py`, NEW)
- Wrapper over generated `ledger` stubs, pattern from `clients/auth.py` + `clients/base.py`; export in `clients/__init__.py`. Consumed by strategy (AllocateCapital) and trading (GetSleeve → free cash = `balance - reserved`).

### 1d. Identity threading (the tricky bit — document it)
- **account_id**: portfolio derives/creates one `Account` per `credentials_id` (lazy bootstrap). Returned by AllocateCapital / lookup.
- **sleeve_id**: created when a strategy execution is funded (portfolio `AllocateCapital` opens a `strategy` sleeve linked to `strategy_execution_id`, returns `sleeve_id`). Strategy stores `sleeve_id` + `account_id` on the execution; trading reads them when starting the runner and threads them into orders/fills/sizing/risk.

**Deliverable:** edited `trading.proto`, regenerated stubs, `LedgerClient`, and a 1-page `CONTRACTS.md` capturing 1a–1d.

---

## 2. WORK PACKAGES (copy-paste prompts)

> Each package assumes Wave 0 is merged. Flag-gate everything; no behavior change when flags are off.

### 📦 PORTFOLIO (Wave 1) — owns the ledger runtime
```
Integrate the portfolio ledger runtime into services/portfolio. The pure kernel +
phase cores already exist under services/portfolio/src/ledger/. Wire them up:

1. src/main.py (lifespan, L34-59): add a Redis client (redis.asyncio, REDIS_URL);
   start a FillConsumer (src/ledger/ingestion.py) per active account whose handler
   calls LedgerWriter.append(); start the reconciliation loop; clean up on shutdown.
   Gate on src/ledger/settings.shadow_mode_enabled().
2. NEW src/grpc/ledger_servicer.py: implement LedgerService RPCs (allocate/transfer/
   deposit/withdraw → src/ledger/funds.plan_* + LedgerWriter; list/get sleeve + holding
   history → LedgerProjector). Mount its generated ASGI app in main.py alongside
   PortfolioService (TenantContext extracted as in src/grpc/servicer.py:56).
3. NEW src/services/fund_service.py: transactional wrapper (plan → append events →
   reproject → return Sleeve). Orchestrate transfer raise-cash (submit sells, then move).
4. NEW src/services/sleeve_service.py: bootstrap an Account per credentials_id +
   singleton Manual/Unmanaged/Unallocated sleeves; create a strategy sleeve on
   AllocateCapital (link strategy_execution_id, seed allocated_capital cash).
5. NEW src/tasks/reconciliation.py: periodically project_account + fetch broker
   positions (llamatrade_alpaca TradingClient, per-tenant creds) → reconcile_account;
   shadow mode logs; emit drift/freeze alerts (see NOTIFICATION pkg).
6. Backfill: on account onboarding call src/ledger/backfill.plan_backfill and append.
Files: main.py, grpc/ledger_servicer.py (new), services/fund_service.py (new),
services/sleeve_service.py (new), tasks/reconciliation.py (new), clients/alpaca.py (new),
.env.example (REDIS_URL, LEDGER_SHADOW_MODE). Tests: fund ops persist + reproject;
reconciliation classifies drift; consumer idempotency. Keep existing PortfolioService/
TransactionService untouched in shadow mode.
```

### 📦 TRADING (Wave 2 — after portfolio LedgerService + sleeve identity) — execution arm
```
Make services/trading sleeve-aware and emit ledger fills. Gate on LEDGER_EXECUTION.

1. RunnerConfig (src/runner/runner.py:84-99): add sleeve_id: UUID|None, account_id:
   str|None. live_session_service._start_runner (src/services/live_session_service.py:
   189-282) fetches sleeve_id+account_id from the execution/session and passes them in.
2. Fill publish: in runner._handle_fill_event (runner.py:939-1050) add
   _publish_ledger_fill_event() that publishes the §1a payload to ledger:fills:{account_id}
   via the Redis publisher (src/streaming/publisher.py). Compute cost_basis for sells via
   FIFO (reuse services/portfolio/src/ledger/sizing.select_lots_fifo logic) + realized_pnl.
3. Sleeve-aware sizing (FIX runner.py:838): compiler_adapter.__call__ (src/compiler_adapter.py
   :149-249, sizing at 223-224) + runner._sync_equity (runner.py:843-851) must size against
   SLEEVE equity, not account equity. Fetch sleeve equity via LedgerClient.GetSleeve
   (project) or thread it from the session. Replace the binary signal with drift-tolerance
   sizing (mirror sizing.target_orders).
4. Sleeve-aware risk: RiskManager.check_order (src/risk/risk_manager.py:76-170) gains a
   sleeve_id param + _check_sleeve_buying_power() that reads free cash (balance-reserved)
   from LedgerClient.GetSleeve.
5. Remove per-symbol reconciliation (FIX runner.py:1193): disable _position_sync_loop /
   _sync_positions (runner.py:876-883, 1178-1380) — portfolio owns reconciliation now.
6. NEW src/clients/portfolio_client.py wrapping LedgerClient.
client_order_id is already deterministic (event_sourced_executor.py:70-87) — reuse as the
attribution/idempotency key. Tests: fills publish with sleeve+cost_basis; sizing uses sleeve
equity; risk reads sleeve cash; reconciliation loop removed.
```

### 📦 STRATEGY (Wave 1) — fund a sleeve on execution start
```
When a StrategyExecution is funded, open + fund a ledger sleeve via the portfolio
LedgerService. Gate on LEDGER_SLEEVES.

1. Ensure StrategyExecution has allocated_capital (add column + migration if missing);
   accept it in CreateExecutionRequest (strategy.proto) and set it in
   strategy_service.create_execution (src/services/strategy_service.py:645-680).
2. In start_execution (strategy_service.py ~707; handler src/grpc/servicer.py:693-720):
   inject a LedgerClient; run admission (free-cash + feasibility — see
   portfolio/src/ledger/funds.check_admission); call LedgerClient.AllocateCapital(
   account_id, amount=allocated_capital) → store returned sleeve_id + account_id on the
   execution row so trading can read them.
3. Inject LedgerClient into StrategyService (servicer.py:575-618 wiring).
Tests: execution create stores allocated_capital; start_execution opens+funds a sleeve and
persists sleeve_id; admission rejects underfunded/infeasible.
```

### 📦 NOTIFICATION/ALERTS (Wave 1, small) — drift + freeze alerts
```
Surface ledger reconciliation alerts through the existing alert pathway.

1. services/trading/src/services/alert_service.py (AlertType ~L32-61; on_position_drift
   ~L269-330): add AlertType.RECONCILIATION_DRIFT + SLEEVE_FROZEN and methods
   on_reconciliation_drift() / on_sleeve_frozen() mirroring on_position_drift (webhook
   delivery already exists at ~L590-629).
2. The portfolio reconciliation loop (PORTFOLIO pkg #5) calls these on material drift /
   sleeve freeze. If alerting must live in notification svc instead, expose an RPC there;
   otherwise reuse trading's AlertService.
3. notification.proto: add an ALERT_CONDITION_TYPE_RECONCILIATION_DRIFT enum value if
   webhooks filter by type.
Tests: drift above threshold emits a CRITICAL alert; sleeve freeze emits an alert.
```

### 📦 WEB CLIENT (parallel from Wave 1, against proto-web) — provenance + funds + P&L
```
Surface the ledger in apps/web. LedgerService is hosted by the PORTFOLIO service
(use the portfolio URL/port 8860, not a new port).

1. make proto-web → apps/web/src/generated/proto/ledger_pb.ts.
2. src/services/grpc-client.ts (L30-121): add ledgerClient = createClient(LedgerService,
   transport(SERVICE_URLS.portfolio)) with the auth interceptor.
3. NEW src/store/ledger.ts (Zustand, pattern from store/portfolio.ts): sleeves, holdings/
   provenance, fund ops, per-strategy P&L + actions (fetch*, allocate/transfer/withdraw).
4. NEW src/types/ledger.ts: Sleeve, Lot (source: 'strategy'|'manual', sourceId), Holding,
   FundOperation, PerStrategyMetrics.
5. NEW components/pages: a LedgerPage (route /ledger in App.tsx) OR a panel on
   PortfolioPage with: HoldingProvenanceView (per-symbol lot timeline w/ source labels),
   FundAllocationUI (allocate/transfer/withdraw modals), PerStrategyPnlTable.
Conventions: functional components, Tailwind (dark: variants), Zustand, strict TS,
getTenantContext() for calls. Can develop against the proto types with mocked data until
the portfolio LedgerService is live.
```

---

## 3. Dependency graph & waves

```
WAVE 0  Contracts/Proto (1 owner) ── blocks ──► Trading, Strategy, Web
   │  trading.proto fields + make proto/proto-web + LedgerClient + CONTRACTS.md
   ▼
WAVE 1 (parallel):  PORTFOLIO ·  STRATEGY ·  NOTIFICATION ·  WEB(scaffold)
   │  portfolio LedgerService + sleeve identity must exist for Wave 2
   ▼
WAVE 2 (parallel):  TRADING (consume sleeve_id, publish fills, sizing, risk, dereconcile)
                    WEB(wire to live LedgerService)
```

**Critical path:** Wave 0 → Portfolio (LedgerService + sleeve creation) → Trading. Strategy/Notification/Web parallelize off Wave 0/1.

**Flag rollout for QA:** bring up `LEDGER_SHADOW_MODE` (portfolio ingests fills + reconciles read-only, confirm `Σ sleeves == broker`, zero behavior change) → `LEDGER_SLEEVES` (funding works) → `LEDGER_EXECUTION` (trading sizes/risks per sleeve; legacy path retired after parity) → desired-state → netting.

## 4. Definition of done (whole effort)
- Two strategies + manual share one account with exact per-lot provenance and no cross-interference.
- Each strategy sizes/trades against its own sleeve; allocate/transfer/withdraw hold invariants.
- Ledger aggregate reconciles with broker; external trades → Unmanaged; material drift alerts/freezes.
- `runner.py:838` and `:1193` resolved.
- Provenance + per-strategy P&L + fund UI live in the web app.
- ≥80% coverage on new real code; tenant-isolation + conservation suites green.
```
