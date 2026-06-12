# Trading Service × Portfolio Ledger — Implementation Plan

> **STATUS: IMPLEMENTED (all 6 phases, 2026-06-12).** See CONTRACTS.md for the
> final locked contract including amendments added during implementation
> (GetOrCreateAccount RPC, open-and-fund AllocateCapital, Sleeve.realized_pnl,
> projected reserved). Not yet committed; flag rollout pending QA.

Execution plan for making the trading service the ledger-integrated "execution arm"
described in `portfolio-ledger-integration-brief.md`. Supersedes nothing; it sequences
the brief's Wave 0–2 packages into executable phases and bakes in two approved
contract amendments.

## Approved contract amendments (vs. the brief)

1. **Terminal-fill publishing (decision 2A).** The ledger dedups on
   `event_id = sha256(client_order_id)` (`portfolio/src/ledger/ingestion.py:90`), so
   per-partial-fill publishing would silently drop every partial after the first.
   Trading therefore publishes **exactly one ledger fill per order**, at terminal
   state: on `fill` with cumulative `filled_qty`/`filled_avg_price`; on
   `canceled`/`expired` with `filled_qty > 0`, the filled portion. Partial fills
   update runtime state only.
2. **Portfolio computes FIFO cost basis at ingestion (decision 3A).** `cost_basis`
   becomes optional in the fill payload. The fill consumer (which owns lots and
   serializes through `LedgerWriter`) computes FIFO closed cost + `realized_pnl`
   via `sizing.select_lots_fifo` when absent. Trading reports broker facts only —
   no duplicated accounting, no race on concurrent same-sleeve sells.
3. **Reservation events (addendum).** `reserved_cash` is real: trading publishes a
   cash-reservation event on order submit and a release on cancel/reject; the
   terminal fill consumes it. Free cash = `balance − reserved` everywhere.

## Phases

### Phase 0 — Lock the contract (Wave 0; blocks everything)
- `trading.proto`: `Order` + `Fill` gain `sleeve_id`, `account_id`; `TradingSession`
  gains `account_id`, `sleeve_id`; `SubmitOrderRequest` gains optional `sleeve_id`.
- `ingestion.fill_to_append`: `cost_basis`/`realized_pnl` optional; document terminal
  semantics; reservation event payloads specified.
- NEW `libs/proto/llamatrade_proto/clients/ledger.py` (pattern: `clients/auth.py`).
- `make proto` + `make proto-web`.
- `.docs/planning/CONTRACTS.md` capturing 1a–1d of the brief + amendments above.

### Phase 1 — Portfolio ledger runtime (minimal Wave 1)
- NEW `services/portfolio/src/grpc/ledger_servicer.py` (LedgerService RPCs →
  FundService / SleeveService / LedgerProjector); mount in `main.py`.
- `main.py` lifespan: redis.asyncio client, FillConsumer per active account →
  `LedgerWriter.append`, reconciliation loop; gated on `ledger/settings.py` flags.
- Ingestion computes FIFO cost basis + realized P&L when payload omits it.
- NEW `src/tasks/reconciliation.py`: project vs broker positions
  (`llamatrade_alpaca`, per-tenant creds), shadow-mode logging.
- Backfill on account bootstrap (`plan_backfill`).

### Phase 2 — Strategy funds a sleeve (Wave 1, gate `LEDGER_SLEEVES`)
- `StrategyExecution.allocated_capital` (column/migration + `CreateExecutionRequest`).
- `start_execution`: admission check → `LedgerClient.AllocateCapital` → persist
  `sleeve_id` + `account_id` on the execution row.

### Phase 3 — Trading identity + fill emission (Wave 2a; shadow-safe)
- Migration: `sleeve_id`/`account_id` on `orders` + `trading_sessions`.
- `RunnerConfig` gains `sleeve_id`/`account_id`;
  `live_session_service._start_runner` threads them from the execution.
- `_publish_ledger_fill_event` → `ledger:fills:{account_id}` per amendment 1.
- Manual orders: `SubmitOrder` without `sleeve_id` resolves the account's Manual
  sleeve via LedgerClient (flag-gated), so `Σ sleeve == broker` holds from day one.

### Phase 4 — Sleeve-aware sizing/risk/reservations (Wave 2b, gate `LEDGER_EXECUTION`)
- NEW `src/clients/portfolio_client.py` (LedgerClient + short TTL cache).
- `compiler_adapter`: drift-tolerance rebalance sizing (mirror
  `portfolio/src/ledger/sizing.target_orders`, 5% band; resize on weight change);
  delete dead code at `compiler_adapter.py:213`. Fixes `compiler_adapter.py:223`
  account-equity sizing.
- `runner._sync_equity` (`runner.py:843`): sleeve equity when `sleeve_id` set;
  account equity remains the legacy fallback. Circuit breaker tracks sleeve equity.
- `RiskManager.check_order` + `_check_sleeve_buying_power` (free cash from ledger).
- Reservation publish/release per amendment 3.

### Phase 5 — Reconciliation handoff + alerts
- Under `LEDGER_EXECUTION`, `_position_sync_loop`/`_sync_positions`
  (`runner.py:876–883, 1178+`) become read-only drift alerting (no auto-correct);
  portfolio owns reconciliation. Legacy behavior intact with the flag off.
- `AlertType.RECONCILIATION_DRIFT` + `SLEEVE_FROZEN` + handler methods in
  `alert_service.py`; portfolio reconciliation loop emits them;
  `notification.proto` enum value if webhooks filter by type.

### Phase 6 — Cleanup + hardening
- Runner mode hardcode (~`runner.py:342`) → derive from session `ExecutionMode`.
- Session P&L / position reads from sleeve projection when flag on (local
  `Position` table becomes runtime cache).
- ≥80% coverage on new real code; ruff/pyright/eslint/tsc; `./scripts/ci-local.sh`.

## Explicitly out of scope
- `AlpacaBarStream` consolidation into `llamatrade_alpaca` (brief freezes libs/alpaca).
- Desired-state (`LEDGER_DESIRED_STATE`) and netting (`LEDGER_NETTING`) runtimes.
- Web client ledger UI (separate package in the brief).

## Rollout / QA gates
`LEDGER_SHADOW_MODE` (Phases 1+3 live: fills ingested, reconcile read-only, zero
behavior change — verify `Σ sleeves == broker`) → `LEDGER_SLEEVES` (Phase 2 funding)
→ `LEDGER_EXECUTION` (Phases 4–5; retire legacy sizing after parity). Every phase
is flag-gated: no behavior change with flags off.
