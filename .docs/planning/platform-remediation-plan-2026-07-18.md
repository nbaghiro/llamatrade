# Platform Remediation Plan — 2026-07-18

> **STATUS: Refreshed full-repo backend deep-dive + remediation plan.** Supersedes the
> point-in-time [platform-gap-review-2026-07.md](./platform-gap-review-2026-07.md)
> (2026-07-13) where code has since moved. Every gap below was re-verified against
> current working-tree code (HEAD `d21f09a`, Python 3.14.3) by a per-service trace.
> This doc corrects the review in both directions and sequences the fixes against the
> [MVP milestones](./mvp-release-plan.md) (M1–M6).

---

## 0. What changed since the 2026-07-13 review (the headline corrections)

Three of the four "TL;DR" blockers in the prior review have had major work land after it
was written (commits `52afd69`, `97e8664`, `0cbd2ae`, `98560cc`, migrations 025–027, agent rework):

| Prior "top blocker" | 2026-07-13 verdict | **Verified 2026-07-18** |
|---|---|---|
| **GAP 1 — forged-tenant hole (6 of 9 services)** | Highest severity; only trading adopted `resolve_identity` | **RESOLVED across the board.** All 8 gRPC servicers now bind wire tenant to the verified JWT principal (`resolve_identity`/`current_context`) and reject a mismatch. Billing is the lone off-pattern holdout — *not* vulnerable (reads the signed token) but bypasses the shared path and rejects service tokens. |
| **GAP 3 — no RLS anywhere** | Zero policies; docs describe RLS that doesn't exist | **STAGED-BUT-INERT.** Migration 025 now `ENABLE`+`FORCE`s fail-closed RLS on 33 tenant tables, GUC set per-request from verified identity. But **every environment connects as superuser `postgres`, which bypasses RLS** — so it's schema-real yet ineffective anywhere runnable. Remaining work is operational (a NOSUPERUSER app role), not schema. |
| **GAP 7 — copilot runs with empty system prompt** | Silent, severe | **FIXED.** Prompt is built, passed (`agent_service.py:185,410`) and consumed by the provider (now **Gemini 2.5 Flash**, not Claude). Outbound tool calls now mint a service token. Residual: 4 *read* tools still swallow failures as success. |
| **GAP 17 — deploy can't ship the stack** | Rolls 2 of 9, no migrations | **Confirmed and worse** — the staging build would *fail outright* (wrong build context) and target the wrong namespace/names. Unchanged as the M4 long pole. |

Net: the **security posture is dramatically better than the doc reads**, the **copilot works**, and the remaining backend risk has concentrated into (a) a handful of genuine money-path / durability bugs in trading & portfolio, (b) finishing RLS operationally, (c) the M2 broker-credential security gate, and (d) the delivery pipeline.

---

## 0.5 Implementation status — 2026-07-18 remediation session

**Landed this session (implemented + tested; 1,823 tests green across the 8 touched
services/libs, ruff + pyright clean). Nothing committed.**

| Area | Item | What shipped |
|---|---|---|
| trading | **T1** runner rehydration | `src/recovery.py`: leased (per-session advisory lock) boot+periodic rehydration; wired in `main.py`. 8 tests. |
| trading | **T2** bracket attribution | Child orders inherit parent `sleeve_id`/`account_id`. Test in `test_bracket_orders.py`. |
| trading | **GAP 10** CancelOrder | Resolves order's session → cancels via per-tenant creds (`get_order_session_id` helper). Test. |
| trading | **T3** runner isolation | `stop/pause/resume` verify tenant ownership before touching the registry. 4 tests. |
| alpaca | **paper data host** | `DATA_PAPER`/`STREAM_PAPER` → env-agnostic host (data.alpaca.markets). Tests updated. |
| portfolio | **P3** snapshot outage guard | Skip persisting a sleeve when a held symbol has no price; guard price-fetch errors. Test. |
| portfolio | **GAP 15a / P1** replica dup writes | Reconciliation + snapshot writers now run only on the lock-holding pod (`main.py`). |
| portfolio | **P2** cache leak | `_INCREMENTAL_CACHE` bounded to an LRU (2048). |
| portfolio | **GAP 15e** YTD/MTD/WTD | Account period returns computed in `get_metrics` (was hard-0.0). Test. |
| strategy | **GAP 13** stranded-sleeve scheduler | `src/tasks.py`: advisory-lock-gated periodic sweep; wired in `main.py`. 2 tests. |
| strategy | **GAP 23** template overrides | Retired-DSL override fields skipped (logged), not fatal. Test. |
| agent | **GAP 7 residual** | backtest read tools + `validate_dsl` fail honestly (`success=False`); tool-loop exhaustion now emits a closing turn. |
| market-data | **bus-mode footgun** | Bus mode requires explicit `MARKET_DATA_BARS_FROM_BUS` (no `REDIS_URL` inference); `/health` reports the active mode; compose sets the flag. |
| billing | **GAP 21** webhook 401 | `/webhooks/stripe` allowlisted; wrong "exempt" comment fixed. Reachability test. |
| auth | **GAP 2a** write-only creds | Create/Get never return the secret; key masked to a prefix (`_mask_key`). Test. |
| infra | **GAP 20** | auth `tier: backend` label; production PDB referenced in kustomization. |
| infra | **GAP 17** | deploy build context fixed (root, not `services/<svc>`); staging namespace/names corrected; rolls all 9. |

**Also landed (money-path refactors, follow-up pass):**
- **GAP 11** cash reconciliation — `cash_drift`/`ledger_cash` kernel helpers, a `vs_broker_cash_mismatch_dollars` gauge, broker `cash()` port+adapter, threaded through the reconciliation pass (surfaced, not auto-frozen). Tests added.
- **GAP 16** `_to_proto_order` — `OrderResponse` now carries `tenant_id`/`session_id`; the proto order no longer emits empty strings. Test updated.
- **GAP 16 / 5A** risk-manager money math — order value, sleeve buying-power, and position-size checks are now computed in `Decimal` (float inputs converted at the boundary), so order gating never turns on float rounding at a limit/buying-power boundary. 52 risk tests green.
- **GAP 16 Decimal — MONOREPO-WIDE (dev-mode, no data-risk).** Every convertible money value across the platform is now `Decimal`; `float` survives only where an external engine is float **by type** (not by risk): numpy (compiler indicators, backtest Sharpe/Sortino/σ analytics, strategy indicators, and the OHLC bar/quote/trade series that feed `np.array`) and Prometheus. Landed: (a) **trading** — whole service + storage; (b) the **2 remaining SQL-`Float` trading tables** `risk_configs` + `daily_pnl` migrated to `Numeric(18,8)` (**migration 028**; risk_manager boundary casts removed → clean pass-through); (c) **libs/alpaca** REST models `Order`/`Position`/`Account` → Decimal (parsers `Decimal(str(...))` — exact vs. Alpaca's string wire; `FillData`/`TradeEvent` were already Decimal), `submit_order`/`close_position` → Decimal; trading's Alpaca-boundary `Decimal(str(...))`/`float(...)` round-trips simplified away; (d) **billing** `PlanResponse` prices → Decimal (DB `Plan`/invoices were already `Numeric`; removed a lossy `float(plan.price_monthly)`); (e) **portfolio** was already Decimal and consumes the new Decimal broker models cleanly. Verified green: trading 590 / portfolio 258 / market-data 344 / alpaca 159 / billing 175, all pyright + ruff clean.
- **GAP 16 Decimal — WHOLE TRADING SERVICE** — extended from the runner to the entire service. All owned DTOs are now `Decimal` (`OrderCreate`/`OrderResponse`/`PositionResponse`/`RiskLimits`/`SessionResponse.pnl`), the risk-manager public API + internals are Decimal, and the **proto boundary is now exact**: the servicer previously did `float(request.quantity.value)` on a string-backed `common_pb2.Decimal` and re-emitted `str(float)` — a lossy round-trip through an exact-decimal wire — now `Decimal(request.quantity.value)` in / `str(decimal)` out. Executor, position/session services, and the streaming publisher all carry Decimal (publisher emits exact `common_pb2.Decimal`). The `orders`/`positions` DB tables were already `Numeric`; a stray `float(order.filled_avg_price)` lossy conversion was removed. **`float()` survives only at the physically-float edges:** (1) numpy compiler (`evaluate`/`Holding`), (2) Prometheus, (3) the Alpaca vendor lib (broker JSON wire) — `submit_order(qty: float)` out, `Decimal(str(...))` on market-data in, (4) JSON (alert webhooks, audit JSONB), (5) two SQL-`Float` money tables — `risk_config` + `daily_pnl` (the ledger/orders/positions tables are `Numeric`; migrating these two to `Numeric` is a separate libs/db + alembic unit). Trading src pyright 0 / ruff clean / 590 tests green (81% cov).
- **GAP 16 Decimal runner-P&L → circuit breaker + whole-runner Decimal** — the circuit breaker is now **fully `Decimal`** (`_daily_pnl`/`_current_equity`/`_peak_equity`/`starting_equity`, the `max_daily_loss_percent`/`max_drawdown_percent` thresholds, and all percentage math), so P&L accumulates and compares to dollar/percentage halts without float drift. Trigger `details` money values are stringified (JSON-safe). Per the "everything Decimal" directive this was then extended through the **entire runner**: `Signal`, `Position` (cost basis), `self._equity`, `self._free_cash`, the weighted-average fill math, realized-P&L (shared `_realized_pnl` helper), and the broker-drift reconciliation are all `Decimal`. The governing rule is now explicit and uniform: **every quantity/price/money value inside the runner is `Decimal`; `float()` (or `Decimal(str(x))` on the way in) appears only at the four genuinely float-native external edges** — (1) the compiler/strategy engine (`evaluate(equity: float)`, `Holding(quantity: float)`, `IntendedOrder`), (2) the broker-order model + Alpaca (`OrderCreate.qty`, `fill_qty`/`fill_price`, `broker_pos.qty`/`cost_basis`), (3) Prometheus metrics (`record_slippage`, drift %), (4) the alert/webhook layer (float-typed + JSON). Note those four are float **because their downstream systems are** (numpy indicators, Alpaca, Prometheus, JSON) — converting them to Decimal would mean rewriting those subsystems, not the runner. 590 trading tests green (81% cov); pyright + ruff clean.

**Money-path correctness cluster (follow-up pass — implemented + tested):**
- **GAP 16 attribution** — `_resolve_order_attribution` no longer swallows ledger failures into an unattributed `(None, None)`; a resolution failure now fails the order (fail-loud). Test added.
- **P4 transfer_out** — a sleeve→sleeve transfer now renders both legs (transfer_out source + transfer_in destination). Test added.
- **GAP 14 Alert + Audit** — both services refactored to own short DB sessions (session-maker) and wired into the executor + runner: fill/rejection/circuit-breaker alerts → tenant webhooks, and a money-path **audit trail** (order submit/fill/cancel → `AuditLog`). Import cycle broken; tests added.
- **Portfolio poison-read** — `AccountProjection.poison_events`/`is_complete` make an incomplete (poison-skipped) projection inspectable; folds increment it. Test added.
- **GAP 15d annualization** — the strategy read path now collapses the ~hourly snapshot series to a daily grid before `sqrt(252)` annualization (matches the account path). Test added.

**Also landed (money-path, final pass):**
- **GAP 12 corporate-action driver** — new operator/feed-triggered `ApplyCorporateAction` RPC on `LedgerService` (proto regenerated) + a `CorporateActionService` that fans a split / ticker-rename / dividend across **every sleeve holding the symbol** via the pure planners, **idempotently** (deterministic event ids). Splits no longer freeze sleeves once applied. Tests added.
- **GAP 16 fakeredis contract test (12A)** — a proto `LedgerFill` now round-trips through the **real** Redis Streams transport (fakeredis-backed) — publish → XADD → consumer-group XREADGROUP → decode → translate — into the portfolio ingestion, exercising the transport + codec + translation together (not mocks). `fakeredis` added to portfolio dev deps.

**Portfolio surfaces (final pass — implemented + tested):**
- **`get_asset_allocation`** — per-symbol weights are now over the WHOLE portfolio (positions + cash) and a **Cash** slice is emitted, so the symbol weights + cash weight sum to 100% (was: single "Stocks" bucket, cash ignored). Test added.
- **`sync_portfolio`** — now triggers an on-demand **reconciliation pass** over the tenant's accounts (adopt external trades into Unmanaged, flag material drift — the real "sync" for an event-sourced ledger) via a new `reconcile_accounts_once` helper, and reports the drift count as `transactions_recorded` (was: no-op returning 0). Test added.

**Deferred — with reasons:**
- **GAP 16 Decimal runner-P&L** — DONE (see "Also landed": circuit breaker + P&L accumulation now fully Decimal; runner adapter stays float by design).
- Remaining stubs: `get_asset_allocation` sector labels still need an asset-classification source; the transfer raise-cash path is intentionally-disabled dead code (removal is a product call).
- **Portfolio stubs** — `get_asset_allocation` sector labels need an asset-classification source; `sync_portfolio` is a no-op re-read (reconciliation is the real sync); the transfer raise-cash path is intentionally-disabled dead code (removal is a product call).
- **GAP 15d** annualization — DONE (see above).
- **GAP 16** Decimal end-to-end (5A) — a large float→Decimal sweep across `models`/`risk_manager`/`runner`/`servicer`; high regression surface, warrants its own focused PR, not a rushed pass. fakeredis contract test (12A) — needs a new dev dep + an end-to-end harness.
- **GAP 12** corporate-action driver — needs a split/symbol-change detection source wired to the (already-built) `plan_split`/`plan_symbol_change` planners. **P4** transfer_out row — needs event-shape work.
- **GAP 2c** validate-on-create — the `ValidateAlpacaCredentials` RPC already exists (UI can call it); inline probe deferred. **GAP 2b** KMS — M6 per plan. **GAP 4** token/key hygiene — M5.
- **GAP 3** RLS role — create a `NOSUPERUSER`/`NOBYPASSRLS` app role + repoint app `DATABASE_URL` + audit mid-block-commit GUC callers; touches deploy, needs validation.
- **GAP 5** TLS/secrets, **GAP 18** CI suites+buf, **GAP 19** OTLP export, **GAP 17** migration Job + agent K8s manifests, billing checkout/portal/enforcement (**GAP 21**), libs cleanup, **GAP 22** docs — infra/M5 items best validated against a stack.
- **NEW deploy blocker found:** the K8s overlays fail `kustomize build` (a `configMapGenerator` merge error, present in staging too) — needs its own fix.
- **NEW (pre-existing):** the auth test suite has an order-dependent isolation leak (a new early-sorting test file exposes it) — worth fixing.

---

## 1. How the platform works (verified architecture map)

**The loop:** build (DSL / visual / copilot) → immutable strategy version → backtest (Celery, TimescaleDB bars) → deploy as a funded live session → fills flow to a double-entry ledger (book of record) → portfolio/perf reads. A user brings their own Alpaca keys; LlamaTrade never custodies funds.

| Service | Role & shape | Verified state |
|---|---|---|
| **auth** (`:8810`) | Connect servicer; JWT(HS256)+bcrypt, tenant/user, refresh; Alpaca cred CRUD (Fernet-encrypted); RBAC; `ValidateAlpacaCredentials` live probe. Runs **RLS-bypass on every query**. | Login/register/refresh real. Cred security & token hygiene are the open items (GAP 2, 4). |
| **strategy** (`:8820`) | CRUD + immutable versioning + status state-machine; deploy → ledger sleeve fund/release (single-authority lifecycle, archive guard, durable release marker); 80 allocation templates; compiles/validates via shared `libs/dsl`+`libs/compiler`. Does **not** run the engine itself. | Real, 80% gate. Open: no scheduler (GAP 13), template/exec overrides use a dead DSL vocabulary (GAP 23). |
| **backtest** (`:8830`) | Celery engine + beat reaper; shared `StrategySession` adapter (live=backtest parity); streamed bar fetch; Redis-Streams progress; cooperative cancel; commission reconciliation; guarded terminal writes. | **Cleanest service.** All 2026-06-19 hardening present + tested, 80% gate, 327 tests. GAP 1 fixed. |
| **market-data** (`:8840`) | TimescaleDB store (2 hypertables + 7 continuous aggregates + compression/retention); backfill/gap-repair/corp-action ingest; store-first serving; bus-mode streaming. | Store/serve real. Open: quotes/trades streaming dead in deployed bus topology (GAP 23); universe env-only; **paper data host `data.sandbox.alpaca.markets` may not exist — needs a live probe.** |
| **trading** (`:8850`) | 4-loop runner (bar/equity/position/trade-stream); deterministic idempotent `client_order_id`; brackets/OCO; circuit breaker; crash-recovery sweeps; per-tenant creds; publishes terminal fills to the **global `ledger:fills`** stream. | ~90% hardened. Open: GAP 10/14/16 + **three new money-path/isolation bugs** (see §3). |
| **portfolio** (`:8860`) | Pure double-entry ledger kernel (balanced postings, FIFO lots, reservations); idempotent single-consumer ingestion (advisory lock, DLQ, quarantine, invariant freeze); drift policy; snapshot performance; reconciliation loop; all reads projection-backed. | **Strongest code in the repo.** GAP 1 fixed. Open: GAP 11/12/15/16 + new replica/leak/outage issues (§3). |
| **agent** (`:8890`) | Gemini streaming, 10-iteration tool loop, 14 tools, DSL-validation gate → draft artifacts, DB-backed memory (ILIKE) + regex extraction. | Architecture right, **GAP 7 fixed.** Residual: read-tool swallow; loop-exhaustion drops final answer. |
| **billing** (`:8880`) | Real Stripe subs/payment-methods/webhook handlers (idempotent). `get_usage`/invoices now real+tenant-scoped. | Open: checkout/portal are placeholder URLs; webhook 401'd by middleware; fabricated emails; no plan enforcement (GAP 21); off-pattern auth (GAP 1). |
| **notification** (`:8870`) | In-memory dict stub; real Twilio/Slack/webhook channel classes **orphaned**; email `return True`. | **No Send/Dispatch RPC exists** — alerts created can never fire. Deferred per MVP, compounds GAP 14. |

**Shared libs:** `libs/common` (`resolve_identity`, fail-closed `AuthMiddleware`, Fernet creds), `libs/db` (30+ models, linear 001→027 Alembic, RLS DDL + GUC session helpers), `libs/events` (proto Redis Streams: groups/ack/XAUTOCLAIM/DLQ/lag; only `InMemoryDedupStore` ships), `libs/alpaca` (single Alpaca entry point), `libs/compiler`+`libs/dsl` (shared `StrategySession`, golden-tested indicators), `libs/telemetry` (OTel+Prometheus; **exports nothing by default**), `libs/proto`.

---

## 2. Consolidated gap ledger (verified)

Status legend: ✅ FIXED · 🟡 PARTIAL/CHANGED · 🔴 OPEN. Milestone = MVP-plan mapping.

| # | Gap | Area | Status | Milestone | Notes |
|---|---|---|---|---|---|
| 1 | Forged-tenant authorization | all services | ✅ | M4 | Closed everywhere; billing off-pattern only. |
| 2 | Broker-cred security (write-only, KMS/salt, validate-on-create) | auth/common | 🔴 | **M2 gate** | `ValidateAlpacaCredentials` exists but not called on create. |
| 3 | Database RLS | libs/db + infra | 🟡 | M4 | Schema+app done; **needs NOSUPERUSER app role** to be effective. |
| 4 | Token/key hygiene (API-key CRUD+hash, logout, refresh rotation) | auth | 🔴 | M5 | Prefix-only key check; refresh valid 7d on leak. |
| 5 | Committed secrets + no TLS cert/IP | infra | 🔴 | M4 | Placeholder Secrets; no ManagedCertificate; no SM→K8s bridge. |
| 6 | Live-trading UI (Trading page, Dashboard, broker UI) | frontend | 🔴 | M2 | Backend ready; largest single build item (out of this backend scope). |
| 7 | Copilot system prompt | agent | ✅ | M3 | Fixed; residual read-tool swallow (see #16-adjacent). |
| 8 | Portfolio page demo fallback / half-unimpl | frontend | 🔴 | M1 | Backend `GetPerformance` YTD/MTD/WTD still 0.0 (see #15e). |
| 9 | No frontend token refresh | frontend | 🔴 | M2 | Sessions die at 30-min expiry. |
| 10 | `CancelOrder` cancels the **platform** Alpaca account | trading | 🔴 | **M2** | Env-cred fallback; every other order RPC resolves per-tenant. Money-path. |
| 11 | Cash never reconciled vs broker | portfolio | 🔴 | **M2** | Reconcile diffs positions only; `Σ sleeve_cash == broker_cash` unenforced. |
| 12 | Corporate actions freeze sleeves instead of applying | portfolio | 🔴 | M6 (beta risk) | `corporate.py`/`desired_state.py`/`netting.py` dormant, no driver. |
| 13 | Stranded-sleeve reconciler never scheduled | strategy | 🔴 | **M2** | No scheduler at all in the service. |
| 14 | AlertService/AuditService dead code | trading | 🔴 | M2/M6 | No alerts fire; **no audit trail on money path.** |
| 15 | Portfolio performance distortions | portfolio | 🟡 | **M2** | Replica dup snapshots; ~5× mis-annualized strategy Sharpe; YTD/MTD/WTD 0.0. |
| 16 | Silent failure modes (attribution, poison, Decimal, contract test) | trading/portfolio | 🟡 | M6 | Telemetry added; behavior unchanged; 5A/12A not started. |
| 17 | Deploy pipeline can't ship stack | infra | 🔴 | **M4** | Build fails (context); wrong ns/names; no migration job; agent no manifests. |
| 18 | CI coverage holes | infra | 🔴 | M4 | integration suite unrun; billing/notif/market-data tests unrun; no buf gate. |
| 19 | Observability exports nothing | infra/telemetry | 🔴 | M4 | No OTLP endpoint; collector only `debug`; metrics pull-only. |
| 20 | K8s config landmines | infra | 🔴 | M4 | auth missing `tier:backend`; PDBs unreferenced; no timescale; staging no NetworkPolicy. |
| 21 | Stripe webhook 401 + billing stubs | billing | 🔴 | M5 | Webhook not allowlisted; checkout/portal placeholders; no enforcement. (`get_usage`/invoices now real.) |
| 22 | Docs describe a different product | .docs | 🔴 | M4 | strategy doc = retired service; auth crypto mislabeled AES-256-GCM. |
| 23 | Template overrides raise for all 80 + quotes/trades streaming dead | strategy/market-data | 🔴 | M1/M3 | Override vocabulary matches neither templates nor the shipped DSL. |

---

## 3. New gaps found in this pass (not in the 2026-07-13 review)

**Trading (money-path / isolation — high priority):**
- **T1 — No runner rehydration after crash/restart.** Recovery sweeps run only *inside* `StartSession`; `main.py` does no boot-time scan of `RUNNING` sessions. After a crash, DB rows stay `RUNNING` with **no runner alive** — the session looks active but is dead. Undercuts the entire "crash-safe" claim.
- **T2 — Bracket child orders carry no `sleeve_id`/`account_id`.** REST-sync/recovery emitters skip them, so a stop-loss/take-profit that fills during a trade-stream outage is **never re-emitted → permanent ledger gap on the exit leg** of a funded position.
- **T3 — Cross-tenant runner control.** `stop/pause/resume` hit the `session_id`-keyed runner registry *before* the tenant-scoped DB check; knowing another tenant's session UUID halts their live runner.

**Portfolio (correctness / resource):**
- **P1 — Reconciliation & snapshot loops run on every replica**, un-lock-gated (only fills are single-consumer) → redundant broker reads + racy status writes (saved only by deterministic event-id dedupe).
- **P2 — `_INCREMENTAL_CACHE` is an unbounded module-global** (deep-copied twice/call) → memory grows with account count.
- **P3 — Snapshots persist cost-basis equity during a price outage** with no "prices incomplete → skip" guard → permanently distorts the immutable equity curve.
- **P4 — `transactions_view` maps allocate+transfer both to `transfer_in`** → sleeve→sleeve outflow (`transfer_out`) invisible in history.

**Agent:** read tools (`get_backtest_results`, `list_backtests`, `get_asset_info`, `validate_dsl`) still return `success=True` on downstream failure; tool-loop exhaustion at iteration 10 can drop the final summarizing answer.

**Market-data:** `stream_historical_bars` fully buffers all symbols despite its "streaming" docstring (server memory risk on big backtests); bus mode auto-enables whenever `REDIS_URL` is set (couples live streaming to the cache var); `/health` always reports the stream unavailable in bus mode.

**Libs:** legacy fail-**open** `TenantMiddleware` still exported (footgun); `libs/proto` grpc `AuthInterceptor` never calls `set_context`, so `resolve_identity` behind it would silently fall to the trust-the-wire branch; `StreamConsumer` retry counter is in-memory (poison entries can exceed `max_attempts`).

**Billing:** `main.py:67-69` comment falsely claims webhooks are exempt from middleware (masks the 401 bug); rejects internal service tokens; webhook handlers swallow all exceptions and return 200, plus a dev signature-verification bypass when `STRIPE_WEBHOOK_SECRET` is unset.

**Infra:** staging `docker build` uses `services/<svc>` context but Dockerfiles copy from repo root → **build fails**; deploy `kubectl` targets `llamatrade/auth` while the overlay creates `llamatrade-staging/staging-auth` → **set-image fails**; Terraform Workload-Identity binding is dangling (no K8s ServiceAccount); backtest worker/beat absent from K8s (backtests would enqueue with no consumer).

**Auth:** no rate-limit/lockout on login or change-password; `ValidateAlpacaCredentials` is an unthrottled, tenant-unscoped outbound-probe primitive.

**Cross-cutting verification item:** the Alpaca paper **market-data** host (`data.sandbox.alpaca.markets`, `libs/alpaca/.../config.py:20,28`) historically does not exist — one live call must confirm paper market data actually flows, or M2 can't paper-trade.

---

## 4. Remediation plan (prioritized)

Effort: **S** ≈ days · **M** ≈ 1–2 wk · **L** ≈ 2–4 wk (single engineer).

### Tier P0 — Correctness & durability that silently corrupts the money-path or isolation
*Small, high-leverage; do before opening the live loop to any tester.*
1. **T1 runner rehydration** — boot-time scan of `RUNNING` sessions → relaunch runners (fires the existing recovery sweeps). *(M, trading)*
2. **T2 bracket-order attribution** — stamp `sleeve_id`/`account_id` on child orders so recovery re-emits exit fills. *(S, trading)*
3. **GAP 10 CancelOrder** — resolve per-tenant creds like every other order RPC. *(S, trading)*
4. **T3 cross-tenant runner control** — verify tenant ownership before touching the runner registry. *(S, trading/isolation)*
5. **P3 snapshot price-outage guard** — skip (don't persist) equity points when prices are incomplete. *(S, portfolio)*
6. **Verify Alpaca paper data host** — one live probe; fix `config.py` if the sandbox host is dead. *(S, libs/alpaca)*

### Tier P1 — MVP-gate blockers (M2 core + M4 hardening)
**M2 money-path & durability:**
7. **GAP 11 cash reconciliation** — add a broker-cash term to the reconcile loop + `Σ sleeve_cash == broker_cash` invariant. *(M, portfolio)*
8. **GAP 13 scheduler** — add a beat/cron to run `reconcile_stranded_sleeves` (+ decide tenant-scoping). *(S–M, strategy)*
9. **GAP 14 wire Alert/Audit services** — pass them into runner+executor; **money-path audit trail** is a real-money prerequisite. *(M, trading)*
10. **GAP 15 performance integrity** — unique constraint on `SleeveSnapshot`, dedupe strategy reads, fix hourly-vs-`sqrt(252)` annualization, lock-gate the snapshot/reconciliation loops (**P1**), set YTD/MTD/WTD. *(M, portfolio)*
11. **P2 cache bound** — evict/size `_INCREMENTAL_CACHE`. *(S, portfolio)*

**M2 broker-credential security gate:**
12. **GAP 2** — make Create/Get responses write-only; call `ValidateAlpacaCredentials` inline on create; per-value random salt + rotation path (KMS deferred to M6). *(M, auth/common)*

**M4 make-RLS-real + delivery:**
13. **GAP 3 operationalize RLS** — create a `NOSUPERUSER NOBYPASSRLS` app role, split migration-role vs app-role, connect app traffic as the limited role; audit `get_db()`/mid-block-commit callers before flipping. *(M, infra+libs/db)*
14. **GAP 17 fix deploy** — correct build context, namespace/names, roll all 9, add an Alembic migration Job/initContainer, add agent K8s manifests + backtest worker/beat. *(M, infra)*
15. **GAP 20 K8s landmines** — `tier:backend` on auth, reference PDBs, staging NetworkPolicy, market-data Timescale wiring, ServiceAccount for Workload Identity. *(S–M, infra)*
16. **GAP 5 secrets+TLS** — ManagedCertificate + static IP (Terraform), External Secrets/CSI bridge from Secret Manager. *(M, infra)*
17. **GAP 18/19 CI + observability** — run integration + billing/notif/market-data suites, add buf gate; ship traces to Cloud Trace, wire an OTLP endpoint, scrape `/metrics`. *(S–M, infra)*

**M1 builder truthfulness:**
18. **GAP 23 template/exec overrides** — rebuild the override layer against the shipped allocation DSL (or remove the dead `symbols/timeframe/stop_loss_pct` vocabulary from templates, exec `config_override`, and the request-schema example). *(S, strategy)*

### Tier P2 — Copilot & streaming polish (M3)
19. **GAP 7 residual** — read tools return honest `success=False`; add a closing LLM turn when the tool loop exhausts. *(S, agent)*
20. **GAP 23 quotes/trades streaming** — publish quotes/trades onto the bus (or document bars-only for beta). *(M, market-data)* — only if the live UI needs sub-bar ticks.
21. **Market-data hardening** — true streaming in `stream_historical_bars`, decouple bus-mode from `REDIS_URL`, fix `/health`. *(S, market-data)*

### Tier P3 — Post-MVP / M5–M6 / cleanup
22. **GAP 4 token/key hygiene** (M5); **GAP 21 checkout/portal/emails/enforcement** (M5); **billing adopts `resolve_identity`** + fix webhook allowlist + dangerous comment.
23. **GAP 12 corporate-action driver** — at minimum a manual `plan_split`/`plan_symbol_change` driver so the first beta split doesn't freeze sleeves (promote to P1 if a split is likely during beta).
24. **GAP 16** Decimal end-to-end (5A) + fakeredis contract test (12A) (M6); **P4** transaction `transfer_out` row.
25. **GAP 22 docs refresh** (strategy/auth/market-data/portfolio); **libs cleanup** (delete fail-open `TenantMiddleware`, reconcile/delete proto `AuthInterceptor`, durable `StreamConsumer` retry); **auth login rate-limit**.

### Recommended sequencing
- **Now (P0):** items 1–6 — a ~1–2 week sprint of small, high-leverage correctness fixes that make the live loop safe to exercise. These are mostly S with two Ms.
- **Then, in parallel:** P1-M2 money-path (7–11) + P1-M2 security gate (12) on one track; P1-M4 delivery/RLS (13–17) on an independent track (can start immediately, per the MVP plan).
- **M1 quick win (18)** slots in anywhere — small and unblocks "start from a template and tweak."
- **P2/P3** follow once the beta gate is in view.

Frontend gaps (6, 8, 9, 23-UX) are a separate track owned by the web app; the backend for all of them is verified ready.
