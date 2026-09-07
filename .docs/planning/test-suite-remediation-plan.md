# Test Suite Remediation Plan

Derived from the 2026-08-02 four-agent test-suite audit (libs, light services, money-path services, e2e/CI topology). Every audit finding maps to a numbered action below. Phases are ordered by leverage: enforcement first (cheap, stops rot), money-path correctness second (the real engineering), feature coverage third, e2e journeys fourth, hygiene last. Actions marked (code) change production code, not only tests.

## Phase 0: Enforcement (Tier A)

The suites that exist must actually run, and their gates must bind.

- 0.1 Add a billing step to CI Test Backend (install `[dev]`, run with coverage) and to ci-local. Gate per D3.
- 0.2 Add CI steps for libs/telemetry, libs/alpaca, libs/common, libs/db. Telemetry and common already declare 80 gates; run them with coverage so the gates bind. Correct the ci-local comment once true.
- 0.3 Give trading an `[integration]` extra containing testcontainers; CI installs `[dev,integration]` explicitly instead of inheriting the earlier step's install. Add trading to `make test-integration`.
- 0.4 Skip-guards: a `CI_REQUIRE_DOCKER=1` env convention. Every Docker-gated conftest turns its skip into a hard failure when the var is set; CI sets it in Test Backend. A runner-side Docker regression then fails loudly instead of passing green.
- 0.5 e2e on PRs: per D1.
- 0.6 Coverage gates for market-data and the ungated libs (alpaca, db, proto): per D3.
- 0.7 Marker and config hygiene: mark libs/db Postgres suites and portfolio `test_account_identity.py` with `integration` (module-level, not conftest `pytestmark`); delete the five dead root markers (slow, security, workflow, gateway, billing); extend root `testpaths` to include `libs/*/tests`.

## Phase 1: Money-path correctness (Tier B)

### 1.1 Backtest gets an integration tier (the only money service without one)

New `tests/integration` on testcontainers Postgres plus a real Redis container:

- `fail_backtest` enqueue compensation executed against a real database.
- The finalize `UPDATE ... WHERE status = RUNNING` cancel race driven by two concurrent coroutines; assert exactly one winner.
- Reaper cutoffs (running-past-limit, stale-pending requeue, pending-fail) on real rows, including the one-result-per-backtest unique constraint the reaper's safety argument cites, and `_reset_to_pending`'s `WHERE status = FAILED`.
- `CancellationFlag` request/should-abort against real Redis, including the fail-open branch; remove the real-Redis touch from unit tests (inject the fake at the seam).
- Real-Celery depth per D2. Independent of that decision: a cheap unit test asserting every beat-schedule task path resolves in `celery_app.tasks` (catches the typo class), and tests for `evict_stale_datasets_task`, the `.parquet.tmp` cleanup, `get_task_status`, `queue_backtest` guards, `_sizing_overrides` non-default branches, `align_daily_returns` numeric pinning, `stream_backtest_progress`'s loop, `InMemoryDatasetStore`, corrupt-Parquet read handling (code: add error handling), and the truncated-snapshot poisoning scenario (mid-fetch failure must not write a partial dataset).

### 1.2 Trading

- Bracket rollback: spec'd broker double whose SL/TP legs raise; assert legs marked rejected, `_rollback_bracket_orders`, and the CRITICAL unprotected-position alert.
- Trade-stream supervisor: first fix fake fidelity (code, libs/alpaca): give `MockTradeStream.stream()` an exhaustion/give-up mode matching the real generator; then test `_trade_stream_loop` and `_rebuild_trade_stream` backoff and mid-fill disconnect.
- Risk: drive layers 3, 4, 5 through `check_order` (not only private helpers), assert multi-violation accumulation, cover `reference_price` seeding.
- Runner lifecycle: `start()` end to end with stream-connect-failure alert branches and `finally` teardown, `stop()`, `RunnerManager.start_runner`, the FastAPI lifespan (RLS verify, rehydration loop, lease release), averaging-up arithmetic, sub-notional skips, breaker signal rejection, `portfolio_client.invalidate` after terminal fill.
- Executor: broker-read failure in the stranded sweep and bulk sync; the sync-path ledger-publish swallow; `create_order_executor` factory.
- Servicer: a table-driven test mapping each `except` block to its Connect status code (12 uncovered blocks).
- Circuit breaker cooldown OPEN to HALF_OPEN and callback-exception swallowing; short-side unrealized P&L formula.
- Real-Kafka signal: extend the portfolio fill e2e or add one trading integration test publishing through a real broker; assert the producer span and `record_ledger_publish("failure")`.

### 1.3 Portfolio

- Cash-drift freeze pipeline end to end: `update_cash_drift_streaks`, `_freeze_sustained_cash_drift` (remove the pragma), `freeze_account_for_cash_drift`, `_dispatch_cash_drift_alert`, `make_drift_handler`.
- `transfer_capital` servicer tests plus an integration case; `lock_account_for_write` invoked for real, plus a two-concurrent-allocate race test on real Postgres proving free cash cannot double-spend.
- Election loss mid-pass tests for the reconciliation and corporate-action loops (top-of-loop loss at minimum; fencing hardening tracked separately in the production-readiness register).
- `classify_fill_error` direct tests; the 3 unexercised incident-kind mappings; bad-tenant alert drop; advisory-acquire exception path; un-pragma and test `monitor_stream_lag`.
- Read surface: `list_portfolios`, `get_performance`, `get_positions`, `list_strategy_performance`, `get_holding_history`, `_backfill_account`; `clients/market_data.py` fallback chain; `read_context` memoization; analytics sharpe/sortino/benchmark.
- `checkpoint_store.save`'s forward-only `ON CONFLICT` predicate against real Postgres; `load_statement` integration test; DLQ replay's `purge(up_to_cursor)` against a real broker.
- Golden-parity scope: route the parity handler through the real `persist_append` core so the closed-sleeve re-home, invariant-freeze guard, and incremental-lots paths sit inside the golden contract, or correct the file's claim.

### 1.4 Market-data

- (code) Fix the `BarIngestor._flush_locked` data-loss bug: restore the buffer when the store write fails; test it.
- (code) Per-symbol isolation in `GapRepairer.repair` so one raising symbol cannot abort the pass; surface the error; test.
- (code) Honor the stream `subscribe()` return value in ingest (False on unauthenticated is currently ignored); align the supervisor fake's signature with the real client; test.
- Alpaca-failure tier: give `FakeMarketDataClient` raise modes; test backfill partial-failure (no false success), the store-fallback snapshot path, and `get_multi_snapshots` degradation.
- Bus-mode selection and lifespan fork, `_check_kafka`, BusBridge backoff doubling/cap/reset and per-bar route-failure swallow.
- `BroadcastCircuitBreaker` driven through the bridge including reset/half-open recovery; delete or test `circuit_breaker_status`.
- `cache.py` lifecycle with a real Redis container in the integration tier (fixes the marker-text mismatch too); `error_handlers.py`; `IngestConfig.from_env` completeness (read all nine tunables or delete the dead five); supervisor branch coverage (admin-server failure, shutdown timeout, re-init None, loop crash, empty universe); migration idempotency and hypertable/policy assertions.
- Move `test_alpaca_errors.py` to libs/alpaca where its subject lives.

### 1.5 Libs

- `llamatrade_common.supervise()`: crash-loop restart, backoff, cancellation.
- `llamatrade_proto` interceptors/auth.py: `_ServiceTokenCache` TTL and refresh-margin behavior, `_with_authorization`.
- Real Alpaca stream loops: `TradingStreamClient.stream()`, `BarStreamClient.stream()`, and `MarketDataStreamClient.run()`'s pump path over `FakeWebSocket`, so the tests exercise the clients rather than the mocks.
- libs/db: `test_models_agent.py`; plan_limits through the real-SQL-on-SQLite tier; dead `sample_*` fixtures removed; the DATABASE_URL-gated `init_db` test given a real home in the Postgres tier.

## Phase 2: Feature coverage (Tier C)

- 2.1 Auth: servicer tests for the four email-token RPCs including uniform no-account-leak responses, `_enforce_credential_rate_limits`, and revoke-all-sessions on reset.
- 2.2 Emission assertions: copy strategy's `test_notifications_emitted.py` pattern into auth (`_notify_security`, `_notify_lockout`), billing (`_notify_billing` for all five categories plus dedup parts), and agent (`confirmation_pending`).
- 2.3 Tenant isolation: billing cross-tenant denial suite; replace agent's tautological isolation test with the real-SQL-on-SQLite predicate pattern; add one representative token-vs-wire mismatch test per service exercising the middleware-populated branch of `resolve_identity`.
- 2.4 Notification: market-loop body tests (bar tailing over FakeTransport, re-election cadence, engine dispatch), main.py wiring, `list_channels`/`update_channel`, stale docstring.
- 2.5 Billing: `trial_will_end` handler; `resume_subscription`, `add_payment_method`, `remove_payment_method` RPC tests.
- 2.6 Strategy: `validate_strategy` RPC test; delete the dead `resume_execution` method.
- 2.7 Agent: `delete_session` servicer test.

## Phase 3: e2e journeys (Tier D)

New journeys (each follows the existing harness conventions, throwaway tenants, bounded polls):

- 3.1 Corporate action propose then apply over the wire, asserting the split fans across sleeves and both notifications land.
- 3.2 Billing webhook-driven transitions: POST signed synthetic Stripe events to the real webhook endpoint (stripe-mock cannot emit); assert subscription state and the emitted notification.
- 3.3 Webhook delivery and auto-disable: register a webhook against an in-test HTTP listener (host-reachable from the mesh), assert signed delivery, then a failing endpoint disables after threshold with the self-notification.
- 3.4 Broker credential lifecycle: Create, Get, Delete over the wire, proving the encrypt-store-decrypt loop and the deletion guard's failed-precondition with dependents.
- 3.5 Auth flows: verify-email round trip through mailpit, welcome email assertion, ChangePassword, RefreshToken rotation, Logout revocation.
- 3.6 Sleeve close with open positions: stop without flattening, assert re-home to Unmanaged at cost and capital release.
- 3.7 Agent: `CommitArtifact` accept path and `SendMessage` unary.
- 3.8 OAuth signup over plain HTTP (start, callback with a stubbed provider ticket where feasible, complete-signup).
- 3.9 Alert surface: ListAlerts/ToggleAlert/DeleteAlert, cooldown suppression, one more condition type.
- 3.10 One true-producer notification e2e (a real service emits, not topic injection), e.g. execution start producing the in-app row.
- 3.11 Strengthen weak assertions: cancel must observe CANCELLED (use a long run), split the billing fallback test, seed-backed asserts for assets and pending artifact, replace fixed sleeps with bounded polls, use the real CloneStrategy RPC.
- 3.12 Document the permanent externals honestly: live_alpaca and live_llm journeys listed as gated in the e2e README, with the substitution seams named.

## Phase 4: Hygiene (Tier E)

- 4.1 One `MockStripeClient`, spec-checked against the real client, in billing conftest; delete the two drifted copies and the six dead fixtures.
- 4.2 `spec=` the trading broker double and shared fixtures; fix the backtest fixture's nonexistent `check_health`; share a single `FakeRedis` test helper.
- 4.3 Delete padding: backtest's duplicated extended file, the zero-src proto-constant file, dead-schema tests, portfolio's tautological servicer block, agent and proto dead fixtures. Re-measure the affected gates afterward; if honest coverage lands under 80, fill with real tests rather than lowering gates.
- 4.4 Frontend: add an explicit vitest config (environment, include) and drop `--passWithNoTests` so zero collected tests fails.
- 4.5 Pin `asyncio_default_fixture_loop_scope` in the packages missing it; clean stale `__pycache__` from deleted test layers; keep the root filterwarnings only if root runs remain a supported entry point.

## Decision points (locked 2026-08-02)

- D1: full e2e job runs on PRs (drop the main-only gate; remove the unused `e2e_smoke` marker).
- D2: broker-backed Celery worker smoke tier in backtest integration, joining trace propagation and exercising acks-late/routing/serialization.
- D3: measure current coverage for billing, market-data, alpaca, db, proto; set each gate at that floor immediately, ratchet to 80 as phases 1 and 2 land.
- D4: agent tenant isolation via the real-SQL-on-SQLite predicate pattern; no new testcontainers tier.

## Sequencing and verification

Phase 0 lands first and alone (small diffs, immediate CI effect). Phases 1 and 2 parallelize by service ownership; Phase 3 follows so new journeys run against corrected services; Phase 4 rides along per-service where files overlap. Every phase ends with full ci-local plus a green remote run. Production code changes carry their own tests in the same change (flush-buffer restore, gap-repair isolation, subscribe return, corrupt-Parquet handling, mock exhaustion mode).
