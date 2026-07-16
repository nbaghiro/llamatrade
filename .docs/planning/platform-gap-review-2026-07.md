# Platform Gap Review — 2026-07-13

> **STATUS: Point-in-time review.** Full-repo sweep of every service, shared lib, the
> frontend, and infra/CI, cross-checked against the [MVP release plan](./mvp-release-plan.md)
> (2026-06-16) and the 2026-06-19 hardening plans. Code was treated as the source of
> truth; every claim below was verified in code at the cited location. Where the MVP
> plan is stale, this doc corrects it in **both** directions.

---

## TL;DR

The backend core loop (strategy DSL → backtest → paper execution → double-entry
ledger) is genuinely built, hardened, and well-tested — the 2026-06-22 hardening
commits (`97e8664` trading, `0cbd2ae` strategy, `98560cc` portfolio, `da8fc90`
backtest) landed almost everything planned. What stands between here and the MVP gate
is concentrated in four places:

1. A platform-wide **forged-tenant authorization hole** — only trading binds the wire
   `tenant_id` to the authenticated principal.
2. The entire **live-trading UI surface** — Trading page, Dashboard, and
   broker-credential UI do not exist.
3. A silent, severe **AI-copilot bug** — the system prompt is built and never sent to
   Claude.
4. A **deploy pipeline that cannot ship the stack** — staging rolls only 2 of 9
   services, and no migration step exists anywhere.

MVP-plan staleness: the copilot builder integration and backtest results binding it
lists as gaps are **done**; the broker-setup Phase 0 security fixes it calls a "hard
gate" are **all still unfixed**.

---

## 1. The product, as designed

One loop: **build → backtest → deploy paper → go live → monitor**, iterated. A user
brings their own Alpaca account (LlamaTrade never custodies funds), builds a strategy
visually / in S-expression DSL / via an AI copilot, saves it as an immutable version,
backtests it against a TimescaleDB bar store, then deploys it as a live session whose
fills flow into a double-entry portfolio ledger — the book of record for money, lots,
and per-strategy P&L.

The locked MVP is a **closed invite-only paper-trading beta** (M1 build/backtest →
M2 paper-live UI → M3 copilot → M4 hardening), with self-serve billing (M5) and real
money (M6) as fast-follows. See [mvp-release-plan.md](./mvp-release-plan.md).

---

## 2. Layout and verified current state

| Area | What's there | Verified state |
|---|---|---|
| `libs/dsl` + `libs/compiler` | Parser/validator with source locations; 17 numpy indicators (golden-tested vs TA-Lib); 6 weight methods; shared `StrategySession` | ✅ Solid. Live=backtest parity is **real** — the same session drives `backtest/engine/strategy_adapter.py` and `trading/src/runner/runner.py:619` |
| `services/strategy` | CRUD, immutable versioning, status state machine, 80 seeded templates, execution lifecycle with ledger sleeve funding/release | ✅ Real, 80% coverage gate. Holes: gaps 12, 13, 22 |
| `services/backtest` | Celery engine, metrics/benchmark, streamed bar fetch, Redis-Streams progress, cancel, beat reaper, enqueue compensation, conditional terminal writes, trade pagination | ✅ Real — 2026-06-19 hardening plan fully landed |
| `services/trading` | 4-loop runner, deterministic idempotent `client_order_id`, brackets/OCO, circuit breaker, crash recovery (stranded-order resubmit + ledger re-publish), terminal-fill ledger publishing, per-tenant creds, `resolve_identity` auth | ✅ ~90% of hardening done. Not done: 5A Decimal, 12A fakeredis contract test, 7A partial. Holes: gaps 10, 14, 16 |
| `services/portfolio` | Pure ledger kernel (balanced postings, FIFO, reservations), idempotent ingestion (DLQ, quarantine, advisory-lock single consumer, invariant freeze), drift policy, snapshot-based performance. All reads on the ledger; no `LEDGER_*` flags; no legacy tables | ✅ Strongest code in the repo. Holes: gaps 1, 11, 12, 15, 16 |
| `services/market-data` | Timescale hypertables + 7 continuous aggregates + compression/retention; backfill/gap-repair/corporate-action ingest; store-first serving; bus-mode streaming | ✅ Real. Quotes/trades streaming dead in deployed bus topology; universe is env-only. Docs omit this entire layer |
| `services/auth` | JWT/bcrypt/tenants, Alpaca cred CRUD (encrypted), RBAC check | 🟡 Login/register/refresh real. No email verify / password reset / OAuth / token revocation; API-key validation prefix-only, no CRUD. Gaps 2, 4 |
| `services/agent` | Claude (`claude-sonnet-4`) streaming with real 10-iteration tool loop, 15 tools, DSL validation gate, artifacts, memory/embeddings | 🟡 Architecture right; crippled by gap 7 |
| `services/billing` | Real Stripe subs/payment-methods/webhook handlers with idempotent replay | 🟡 Checkout/portal/usage/invoices are stubs; webhook likely 401'd; fabricated customer emails; zero enforcement. Gaps 8, 21 |
| `services/notification` | In-memory dict stub; channel classes (Twilio/Slack/webhook real, email `return True`) never wired into the servicer | 🔴 Deliberate MVP deferral, but nothing sends and nothing persists |
| `apps/web` | Builder (canvas + CodeMirror DSL + 764-line validator + autosave + optimistic locking); copilot wired via context injection + artifact→builder flow; backtest page fully bound (run/stream/results/trades pager); billing wired | 🟡 Pre-trade half is real; live-trading half doesn't exist. Gaps 5, 6, 9 |
| `libs/events` | Proto-typed Redis Streams: consumer groups, ack, XAUTOCLAIM redelivery, DLQ, lag gauge, NOGROUP recovery | ✅ Real. Only `InMemoryDedupStore` ships (services must supply durable dedup) |
| `libs/telemetry` | OTel + Prometheus bridge, RED middleware, structured logs | 🟡 Local-only by default — nothing exports without env/infra that isn't set. Gap 19 |
| `libs/db` | 30+ models, 21-revision linear Alembic chain | ✅ Healthy migrations. **No RLS anywhere** (gap 3) |
| Infra/CI | Compose (all 9 services + observability dev stack); K8s (8 services, no agent); Terraform (GKE/SQL/Redis/secrets/monitoring); CI lint + 6 services' tests | 🔴 Cannot deploy the stack correctly. Gaps 17–20 |

Notable cross-cutting facts:

- **Python 3.14 floor is real**: PEP 758 bare `except A, B:` appears in production code
  (`libs/common/llamatrade_common/auth.py:157` etc.) — valid on 3.14, `SyntaxError` on ≤3.13.
- **Test volume is high** (portfolio ~5k test lines, backtest ~343 tests, market-data 311,
  compiler ~318) but heavily mock-based at boundaries — several gaps below are green in CI
  precisely because mocks hide them.
- `libs/alpaca` paper **market-data** hosts point at `*.sandbox.alpaca.markets`
  (`libs/alpaca/.../config.py:20,28`) — Alpaca's data API historically has no sandbox
  host. Unverified at runtime; worth one live call to confirm.

---

## 3. High-confidence gaps

Numbered for reference. Everything here was verified in code; medium-confidence items
are marked.

### A. Security / tenant isolation

**GAP 1 — Forged-tenant authorization hole in 6 of 9 services (highest severity).**
Fail-closed `AuthMiddleware` now runs everywhere (anonymous access is closed), but
`resolve_identity()` (`libs/common/llamatrade_common/auth.py:161`) — which binds the
wire `tenant_id` to the verified JWT principal and rejects mismatches — is adopted
**only by trading** (`services/trading/src/grpc/servicer.py:43`). Still trusting
caller-asserted `request.context.tenant_id`:

- portfolio — 18 call sites across `grpc/servicer.py` + `grpc/ledger_servicer.py`
  (includes deposit/withdraw/allocate/close on the money ledger)
- strategy — local `_validate_tenant_context` checks only non-nil UUIDs
  (`services/strategy/src/grpc/servicer.py:43-70`)
- backtest — raw `UUID(request.context.tenant_id)` everywhere
  (`services/backtest/src/grpc/servicer.py:102`)
- agent — same pattern (`services/agent/src/grpc/servicer.py:45-72`)
- notification — trusts wire context (low stakes: in-memory stub)
- market-data — re-parses `X-Tenant-ID` headers itself with stale "auth optional"
  comments (`services/market-data/src/grpc/servicer.py:60-101`)
- auth — `get_user`/`get_tenant` take any UUID with no tenant scoping (IDOR)
  (`services/auth/src/grpc/servicer.py:257,297`)

Any authenticated user can set another tenant's UUID and operate on their data.
Existing isolation tests only cover the honest-intruder case (own tenant asserted →
NOT_FOUND), never a forged mismatch — so this is green in CI. Fix is mechanical:
roll the trading `_identity()` pattern through the remaining servicers + add
forged-tenant tests. This is the M4 gate item.

**GAP 2 — Broker-credential security (broker-setup Phase 0) entirely unfixed.**
All three "hard gate" items from
[broker-setup-individual-traders.md](./broker-setup-individual-traders.md):
- Secrets **not write-only**: `CreateAlpacaCredentials` / `GetAlpacaCredentials`
  return decrypted key+secret (`services/auth/src/grpc/servicer.py:759-769, 810-820`).
- Dev-grade encryption: Fernet with PBKDF2 from a single env var and a **hardcoded
  static salt** `b"llamatrade_salt_v1"`, default key `"default-dev-key-change-me"`
  (`libs/common/llamatrade_common/utils.py:52,70,88`). Not the AES-256-GCM the docs claim.
- No validation against Alpaca on entry (no `get_account()` probe, no paper/live check).

**GAP 3 — No database-level RLS, anywhere.** Repo-wide grep: zero
`CREATE POLICY` / `ENABLE ROW LEVEL SECURITY`. `.docs/architecture.md` documents RLS
that does not exist. Isolation is app-layer `WHERE tenant_id` only — the exact layer
gap 1 bypasses.

**GAP 4 — Auth token/key hygiene.** API-key validation matches the 8-char prefix and
**never compares the secret** (admitted in comment, `services/auth/src/grpc/servicer.py:141`);
no API-key create/list/delete RPCs exist. `logout` is a no-op TODO (`:647-649`);
rotated refresh tokens are never invalidated (leaked token valid the full 7 days).

**GAP 5 — Committed secrets + no TLS.** `infrastructure/k8s/base/secrets.yaml:33-91`
commits six Secret objects (placeholder values) referenced by all overlays; nothing
bridges the Terraform Secret Manager entries into K8s (no External Secrets / CSI).
Ingress annotations reference `llamatrade-cert` / `llamatrade-staging-cert`
(`base/frontend/deployment.yaml:57`, `overlays/staging/ingress-patch.yaml:8`) but no
`ManagedCertificate` object exists, and Terraform provisions neither the cert nor the
static IPs the Ingress names.

### B. Product gaps blocking the MVP loop

**GAP 6 — The live-trading UI surface doesn't exist (M2).** Confirmed current:
`pages/trading/TradingPage.tsx` is 10 lines of static text; `tradingClient`
(`services/grpc-client.ts:120`) is never imported anywhere; no trading store;
`pages/dashboard/DashboardPage.tsx` is 11 lines of gradient divs; **no
broker-credential UI** anywhere (Settings = email display + dead "Change Password"
button). The backend for all of it — sessions, order/position streams, sleeve funding
— is ready. Largest single build item, as the MVP plan predicted.

**GAP 7 — The AI copilot runs with an empty system prompt (M3).**
`_build_llm_messages` builds the full system prompt (persona, DSL grammar, strategy
context, backtest metrics), stores it at
`services/agent/src/services/agent_service.py:358`, and **never uses it**; the
`stream()` call omits it and the LLM client falls back to `""`
(`services/agent/src/llm/client.py:76`). The mock LLM ignores `system_prompt`, so
tests pass. Related copilot defects:
- Every tool swallows downstream failures and returns `success=True` with a
  "service unavailable" note (e.g. `tools/backtest_tools.py:150-158`).
- `run_backtest` tool ignores `dsl_code` — cannot backtest an unsaved/pending
  strategy, the core copilot flow (`tools/backtest_tools.py:339-345`).
- Agent outbound tool calls carry only `X-Tenant-ID`/`X-User-ID` headers, no service
  token (`tools/clients.py:59-64`) — fail-closed downstream services 401 them, which
  the swallow-as-success pattern then hides.

**GAP 8 — Portfolio page lies on failure; half its real path unimplemented (M1).**
Silent demo fallback confirmed: empty `catch {}` → `DEMO_STRATEGIES`
(`apps/web/src/store/portfolio.ts:456-459`). Even the success path hardcodes
`equityCurve: []` / `positions: []` "loaded separately" — and no such call exists
(`:447-448`). Strategies list overlays fully synthetic per-card metrics and a fake
backtest gallery on real strategy names (`StrategiesPage.tsx:134-159`).

**GAP 9 — No frontend token refresh.** `refreshToken` is stored and `setTokens`
exists, but nothing calls `RefreshToken` and there is no 401-retry interceptor
(`store/auth.ts`, `services/grpc-client.ts:49-61`). Every session silently dies at
30-minute access-token expiry.

### C. Money-path correctness

**GAP 10 — `CancelOrder` cancels against the platform's Alpaca account, not the
tenant's.** Servicer builds an executor with no session/tenant
(`services/trading/src/grpc/servicer.py:441`) → env-credential `get_trading_client()`
fallback (`executor/order_executor.py:1351-1352`) → cancels on the wrong account.
Every other order RPC resolves per-tenant creds correctly (2A); this one slipped.

**GAP 11 — Cash is never reconciled against the broker.** The reconcile loop diffs
**positions only** (`services/portfolio/src/ledger/reconciliation.py:50`); broker
cash is fetched (`clients/alpaca.py:110`) but used only at onboarding. Documented
invariant `Σ sleeve_cash == broker_cash` is unenforced after day one — dividends,
fees, interest, external cash moves drift silently. M2's "reconciliation green
against the broker" cannot currently be evaluated for cash.

**GAP 12 — Corporate actions freeze sleeves instead of being applied.**
`ledger/corporate.py` (splits, symbol changes) is implemented and unit-tested but has
**no runtime driver**. A routine split surfaces as `QTY_MISMATCH` → drift policy
freezes every sleeve holding the symbol (`tasks/drift_policy.py:50`). First split in
the beta halts those strategies pending manual intervention. (Similarly dormant:
`ledger/desired_state.py`, `ledger/netting.py` — implemented, no caller.)

**GAP 13 — Stranded-sleeve reconciler is never scheduled.**
`reconcile_stranded_sleeves` (`services/strategy/src/services/strategy_service.py:1052`)
has no Celery/beat/cron caller — the strategy service has no scheduler at all. A
ledger outage during stop strands sleeve capital indefinitely. Durable-by-design,
dead-in-practice.

**GAP 14 — Trading's AlertService and AuditService are dead code.** Both fully
implemented and unit-tested; `LiveSessionService._start_runner` never passes
`alert_service` (`live_session_service.py:414-425`), `create_order_executor` sets it
`None` (`order_executor.py:1358`), and nothing instantiates `AuditService`. No
fill/risk/drift alerts ever fire (compounding the notification stub), and there is
**no audit trail on the money path**.

**GAP 15 — Portfolio performance-metric distortions.** Three verified issues:
- Snapshot loop runs unconditionally on **every replica** (`src/main.py:157-170`,
  outside the advisory-lock gate) with no uniqueness on `SleeveSnapshot` → duplicate
  equity points per interval; strategy reads consume all rows
  (`strategy_performance_read_service.py:287`), deflating volatility / distorting Sharpe.
- Strategy metrics annualize ~hourly snapshot cadence with daily `sqrt(252)` math
  (`ledger/analytics.py:46,148,153`). *(Medium confidence — depends on configured interval.)*
- `GetPerformance` YTD/MTD/WTD are hard-wired `0.0` (`grpc/servicer.py:190-192`,
  never set by the read service).

Also: Decimal-end-to-end in trading (hardening 5A) never started — risk checks and
runner P&L are float, converted only at DB/ledger edges (`risk_manager.py:135`,
`servicer.py:399`).

**GAP 16 — Silent failure modes on attribution and projection.**
- Trading's `_resolve_order_attribution` swallows all exceptions to `(None, None)`
  (`services/trading/src/grpc/servicer.py:150-152`) — a transient portfolio outage
  silently books an order as unattributed with **no ledger events**, indistinguishable
  from a legitimate manual trade (hardening 7A incomplete).
- Portfolio's fold skips poison events and serves silently incomplete balances with
  no read-path signal (`ledger/projection.py:135-162`).
- `_to_proto_order` returns empty `tenant_id`/`session_id` (`servicer.py:774-775`).
- 12A (fakeredis end-to-end trading↔ledger contract test) not started — emission is
  verified only against mocks.

### D. Platform / delivery

**GAP 17 — The deploy pipeline can't ship the stack.**
`deploy-staging.yml` builds+pushes all images to Artifact Registry as `:${sha}`, then
`kubectl set image`s **only auth and frontend** (`:60-63`); the other six services
stay pinned to `gcr.io/llamatrade/<svc>:staging` — a registry and tag the workflow
never produces. No Alembic migration Job/initContainer/await exists anywhere in K8s
or workflows. Both deploys are manual `workflow_dispatch` — **no deploy-on-merge**,
contrary to README/architecture docs. Agent has **no K8s manifests at all**
(absent from `infrastructure/k8s/base/` and both deploy workflows) despite being MVP scope.

**GAP 18 — CI coverage holes.** The cross-service integration suite
(`tests/integration` — full user journeys, ledger pipeline, tenant isolation) is
**never run in CI**; billing, notification, and market-data unit tests are installed
but not executed (`ci.yml` test-backend job); no `buf lint`/`buf breaking` gate
(make targets exist, unwired), so proto wire-contract compatibility is ungated.

**GAP 19 — Observability exports nothing.** Traces require
`OTEL_EXPORTER_OTLP_ENDPOINT` (set nowhere); the otel-collector's only exporter is
`debug` (Tempo/Cloud Trace commented out,
`infrastructure/observability/otel-collector/config.yaml:56-62`); `/metrics` is
scraped only by the dev compose stack. GCP-side container logs do flow (Autopilot →
Cloud Logging + Terraform sink). M4's "tester traffic visible in traces/logs/
dashboards" is unmeetable for traces/metrics today.

**GAP 20 — K8s config landmines.**
- auth Deployment missing `tier: backend` label (`base/auth/deployment.yaml:6-8`) →
  no allow rule under production's default-deny NetworkPolicy (staging applies no
  NetworkPolicy at all); also skipped by staging's tier-scoped patches.
- Production PDBs exist (`overlays/production/pdb.yaml`) but are not referenced in
  the kustomization — never applied.
- K8s market-data has no Timescale DB config/workload (store layer has no DB in K8s).
- No app-container healthchecks in compose (infra only).

**GAP 21 — Stripe webhook likely unreachable + billing stubs.** The webhook is
mounted at `/webhooks/stripe` on the same app as fail-closed `AuthMiddleware` with
default public paths only (`services/billing/src/main.py:70,86`) — Stripe sends no
Bearer token, so its POSTs should 401 (no endpoint-level test exists; verify at
runtime). Checkout/portal sessions return **placeholder URLs**
(`grpc/servicer.py:364-380`); `get_usage` returns zeros, invoices are stubs; customer
emails are fabricated `user-{tenant_id}@llamatrade.example` (`:124,310`); no plan
limit is enforced anywhere in the platform.

### E. Product-vision inconsistencies

**GAP 22 — Docs describe a product ahead of (and behind) the code.**
`.docs/services/*` claim email verification, password reset, OAuth, API-key CRUD,
Postgres-backed notifications, working checkout — none exist. Meanwhile the
market-data doc omits the entire Timescale store/ingest layer that *does* exist, and
portfolio/trading docs describe retired architectures (legacy read services,
event-sourced executor, `RecordTransaction`). For an open-source repo this is a
contributor liability. The MVP plan's maturity table needs refresh in both directions.

**GAP 23 — Small trust-eroding frontend/UX fictions.**
- Post-login navigates to the empty `/dashboard` (`LoginPage.tsx:37`) while the index
  route redirects to `/portfolio`.
- Social-login buttons are decorative (no handlers).
- **Template parameter overrides raise for all 80 seeded templates** — the override
  field names (`symbols`/`timeframe`/`stop_loss_pct`/`take_profit_pct`) match none of
  the templates' actual DSL fields (`strategy_service.py:107-144`); "start from a
  template and tweak" fails today.
- Quotes/trades streaming is dead in the deployed bus topology — `StreamQuotes`/
  `StreamTrades` connect and emit nothing (`services/market-data/src/main.py:92`,
  `streaming/bus_bridge.py:46-50` tails bars only).

---

## 4. Mapping to MVP milestones

| Milestone | Status vs plan | Critical-path gaps |
|---|---|---|
| **M1 Build & Backtest** | Closer than planned — backtest binding + copilot wiring done | 8 (demo fallback), 6 (dashboard), 23 (template overrides) |
| **M2 Paper Trading Live** | Long pole, as predicted; backend ready | 2, 6, 9; ride-alongs 10–14 (beta acceptance = ledger-vs-broker correctness) |
| **M3 AI Copilot** | Mostly done — but silently broken | 7 (days of work, large quality impact) |
| **M4 Beta Hardening** | Nothing started since plan | 1 (highest severity, pattern proven in trading), 3, 5, 17–20 |
| **M5 Self-Serve** | Unchanged | 4, 21 + email verify/reset (absent) |
| **M6 Real Money** | Unchanged | KMS encryption (2), 11, 12, 14 (audit trail), 15 |

## 5. What's verified strong (don't re-litigate)

- Live=backtest parity via the single shared `StrategySession` (old adapters deleted).
- Ledger kernel + ingestion: balanced postings, deterministic event ids +
  `ON CONFLICT DO NOTHING`, FIFO enrichment, poison/quarantine/DLQ triage,
  advisory-lock single consumer with hung-consumer health failover, post-fill
  invariant freeze.
- Trading crash recovery: deterministic `client_order_id` idempotency, stranded-order
  resubmit, startup ledger re-publish safety net.
- Backtest hardening plan: fully landed (reaper, compensation, guarded terminal
  writes, commission reconciliation, numeric guards, streaming fetch, pagination).
- Events lib: consumer groups, ack, XAUTOCLAIM redelivery, DLQ, lag gauge.
- 80 real seeded templates; 17 golden-tested indicators; healthy 21-revision linear
  Alembic chain.
