# Production readiness: gap register

| | |
|---|---|
| **Baseline** | 2026-07-28, verified against the working tree during the architecture review |
| **Companion** | `production-readiness-plan.md` (sequencing, batches, exit criteria) |
| **Relation to the spec** | `.docs/architecture.md` presents the post-plan final state as the design of record. This register records the baseline and is the tracking document; close items here, not there. |

Priorities: **beta** blocks the closed beta, **ext** blocks external users, **rm** blocks real money, **hyg** is debt to schedule opportunistically. Evidence references were verified during the review session and re-verified on 2026-07-28 (see Status corrections below). The Kafka cutover executed on 2026-07-28: the transport was swapped, the Redis Streams transport deleted, and the suites are green including real-broker integration tests. The plan's dual-run parity soak was **not** performed (no harness or artifact exists; the Redis fold was deleted rather than run in parallel), so the migration's validation basis is the test suites plus the fill end-to-end test, not a production soak. Round 3 below tracks the gaps the migration introduced and the test-suite gaps found in the full sweep.

## Execution roll-up (2026-07-28 implementation run)

The full list was executed in one run (all work uncommitted, per repo convention). Verification at completion: 3,952 tests green across all 17 packages, zero suppression comments, ruff clean, pyright strict (pinned 1.1.408) at zero errors repo-wide.

**Closed.** G1-G5 (evaluator composition, late-reservation no-op, bare-asset semantics, OAuth broker adapter + staleness gauge, ledger incident alerts incl. freeze/quarantine dispatch), G6-G10 (fill-delta tracking, degraded-projection surfacing, Manual-sleeve backfill on recovery emission, bulk-sync logging, persisted projection checkpoints w/ migration 034), G12 (margin-only preflight), G14-G16 (RLS startup asserts + per-transaction GUC binding + scoped audit/alert sessions), G17-G26 (RS256 with anti-confusion matrix, revocation + rotation, single-use OAuth flows + password parity, rate limiting + dummy hash, server-persisted copilot proposals, gRPC server path deleted, websocket scopes rejected, key cache + prefix column w/ migration 035 + cipher seam, cross-tenant metric wired, wire-user rejection), G27-G28 (all nine Dockerfiles rebuilt, manifests aligned incl. Timescale + ingestor, kustomize green), G30-G36 (ingestor manifest, portable sed, OTLP fixed everywhere, stream metrics, dead gauges deleted, real readiness probes, buf gates in CI w/ WIRE_JSON policy), G38-G39 (dependency declarations, dead-code deletions incl. normalize_weights and the unused IndicatorType enum), G40-G49 (bar pagination + most-recent-N, shared Redis rate budget, UTC timestamp fix, stream vwap/trade_count, progress degrade, parser depth guard, error positions to the wire, vocabulary parity tests, validator rejections for metric crossovers and non-momentum :top, dataset janitor), G50-G53 (conformance corpus w/ 7 TS bugs fixed, webhook hardening + dedup + non-200, free-tier single source, orphaned-execution adoption), G55 (docs sweep executed; RLS claims kept because now true). K1-K12 closed (compose wiring, bootstrap substitution, keyed DLQ, cursor resume, auto-create gate, transport reconnect + bridge supervision, partition pause + max_poll_interval, check_kafka, lock hygiene, dead config, docstring sweep) plus staging WI bindings from K13. T1-T15 closed as specified, including the whole-life e2e leg and the money-path joint tests. R2 closed (drift adoption defers on in-flight orders).

**New findings from the run.** The `orders.client_order_id` column had no database unique constraint despite being the platform's idempotency key; fixed with migration 036 and real-Postgres tests. Sessions started through the normal StartSession path never take a rehydration lease, so a peer replica's rehydrate pass could double-claim them (adopted sessions are protected); open follow-up. The deterministic order id hashes `isoformat()`, so equal instants in different UTC offsets derive different ids; documented in tests, all current callers pass UTC. Residual TS drift outside the corpus mandate: the builder store omits benchmark from its own metadata, completions advertise retired keywords, `stoch` emits unparseably, and only `cross-above` is accepted; follow-ups. Health-probe DB check is duplicated across six mains pending a shared helper in llamatrade_common.

**Open, with reasons (updated at Round 4 close, 2026-07-29).** G54 (flip TRADING_USE_RUNTIME_LOOP) remains gated on the paper parity soak, but the harness, diff tool, and runbook now exist (`.docs/runbooks/runtime-loop-parity-soak.md`); what remains is running the soak on a live mesh and flipping. The KMS cipher is implemented with mocked-client coverage; cloud verification (key creation, IAM, image extras, cutover, rotation check) follows the six-step procedure in the Wave 4 roll-up. External Secrets manifests and terraform are shipped opt-in; enabling requires installing ESO, populating the six versionless Secret Manager entries, and dropping the committed placeholder Secrets in the same change. The OAUTHBEARER suite exists and passed against a real SASL broker; its first containerized run happens in CI's docker lane. Docker-gated integration tests remain CI-only. R1 through R13 are closed across Waves 1 to 3 except two named partial halves: close-aligned evaluation timing (the R5 remainder, a product decision) and live cluster enablement of the worker scaler (the R10 remainder).

### Round 4 execution, Wave 1 (2026-07-29)

**Closed.** R3: deleting Alpaca credentials is refused with failed-precondition while RUNNING/PAUSED sessions or funded sleeves depend on them, via a shared tenant-scoped query helper (`libs/db/llamatrade_db/credential_dependents.py`, plan_limits pattern; base singleton sleeves exempt through `allocated_capital > 0`). R7: every `system_session`/`set_rls_bypass` use emits a structured audit line (caller, optional reason, bound tenant scope) and increments `llamatrade_db_rls_bypass_total{operation}`. R9: forward-only expand-and-contract documented in `architecture.md` and the Alembic template; the contradictory `alembic downgrade -1` operational snippet removed. R11: per-environment concurrency groups on both deploy workflows (queue, never cancel mid-deploy). R13: sizing skips orders under a configurable notional floor (default one dollar), counted as `sub_notional_skip_count` beside `degraded_eval_count`, with a skipped sell's shortfall re-fitting the buy side through the shared `affordable_quantity`. Follow-ups from the 07-28 run also closed: order-id UTC normalization (aware timestamps normalized inside the derivation; UTC-input ids proven byte-identical via pinned goldens plus a 2,000-input old-versus-new sweep), the shared health probe (`cached_engine_check` in `llamatrade_common.health`, adopted by the six duplicated mains, exported from the package root), and the TS drift residue (benchmark threaded through the builder store; completions purged of roughly twenty retired keywords; TS parse cases added for stoch/cci/mfi/obv/vwap/williams-r, whose emitted forms previously degraded silently to a default condition on re-parse; comparator set aligned to crosses-above/crosses-below/=/!=; new `apps/core/src/strategy/vocabulary.ts` pinned by generated `conformance/vocabulary.json` and corpus cases 16 and 17).

Verification at wave close: libs/db 332, libs/common 159, libs/runtime 352, services/auth 134, services/trading 668, apps/web 189, libs/dsl 280, all passing; ruff and pyright (1.1.408 strict) clean on all touched files; no suppressions.

**New findings from Wave 1 (triage pending).**
- TS `parseOperand` maps `momentum` and `donchian` onto an `sma` placeholder, so a valid strategy using them round-trips into a different strategy; `IndicatorRef` also lacks stoch smoothing slots, so `(stoch SPY 14 5 5 :k)` re-emits as `14 3 3`. This is the worst remaining drift class.
- `codemirror/linting.ts` keeps private vocabulary copies and lints retired keywords; it should move onto `@llamatrade/core/strategy/vocabulary`.
- `_ProtoEnumType._convert_to_db_value` silently coerces unmapped proto ints to the first enum member (wrong query or write instead of an error), and the inner Enum impl lacks `cache_ok`, disabling SQLAlchemy statement caching on every query touching these columns.
- Cash deposited into base sleeves does not block credential deletion (live cash is a projection, not a column); a strict non-zero-book-balance rule needs a portfolio-side check.
- Runtime counters `degraded_eval_count` and `sub_notional_skip_count` are read by no service; wiring them into live and backtest telemetry is a small follow-up. `build_session()` threads neither `min_order_notional` nor `drift_tolerance`, so backtest runs on defaults. BINARY-mode orders remain not provably affordable (the sizer sees equity, never free cash).
- `llamatrade_db_rls_bypass_total` needs a `telemetry.md` catalog entry and a Prometheus alert rule; bypass call sites pass no `reason` yet; `tenant_scope` logs null for sessions scoped by one-shot `set_tenant_guc`.
- market-data's main has no database readiness check; portfolio's probe builds a new engine per kubelet probe, uncached, and is `critical=False` so a dead database still reports ready; `check_postgres` is engine-per-call generally; `libs/db/tests/conftest.py` engine fixtures are dead and broken (JSONB on SQLite).
- Smaller: Python `WEIGHT_METHODS` still carries `market-cap` (parse-accept, validate-reject); the benchmark field has no builder UI; no direct Python test reads `vocabulary.json` (the guard is the CI regenerate-and-diff); nothing enforces timezone-aware signal timestamps at the Signal boundary; `ci.yml` has no concurrency group; staging and production deploys can still run simultaneously (per-environment grouping is the intended semantics).

### Round 4 execution, Wave 2 (2026-07-29)

**Closed.** R1: `Account.alpaca_account_id` (nullable, unique per tenant, migration 037), learned at genesis and lazily backfilled; resolution goes credentials-first then broker-id, so a re-link re-points the existing book to the new credentials instead of creating a duplicate; genesis seeding is gated on actual row creation (re-onboarding an existing account would double-import positions through per-symbol backfill keys); a startup sweep reports duplicate broker ids and never merges; the snapshot adapter now carries `broker_account_id` (wired inline post-batch). R4: `TradingClient.get_corporate_announcements` in the Alpaca lib (full resilience stack, 90-day window guard) plus a nightly leader-elected detection pass in portfolio routing announcements to the split, rename, and dividend planners; proposals surface as structured logs plus metrics with durable deterministic-id idempotency, and the operator applies through the existing RPC. R6a: session start refuses inactive or non-tradable symbols; a gate stalled past a configurable window alerts once per episode (resets on pause and market close); a delisting marks the session degraded (marker on `TradingSession.config`, surfaced on session reads) and sends a critical close-or-continue alert without auto-closing. R6b: the ingest universe is the union of the configured baseline and running live-session symbols (`live_session_symbols.py` helper under an audited `system_session`), refreshed on an interval, baseline never dropped, subscription changes committed only after the stream accepts them. Rehydration-lease follow-up: `start_session` now takes the same per-session advisory lease the rehydrator uses, fail-closed, released on start failure. R8: a docker-gated chaos suite (12 tests across portfolio, trading, and libs/db) exercises Postgres death and restart against the real lock helpers; all 12 were additionally executed against a live throwaway Postgres 15 cluster.

Verification at wave close: libs/alpaca 224, libs/db 358, services/portfolio 413, services/trading 702, services/market-data 352 (26 pre-existing Docker-fixture errors), all green; ruff clean, pyright 1.1.408 strict zero errors on touched files, no suppressions (one agent-introduced `# pyright:` directive was removed and the gate re-verified). The register-identifier strip now covers the whole changeset; the no-refs rule held in all Wave 2 output.

**New findings from Wave 2 (triage pending; the first three are serious).**
- The R8 chaos suite falsified the clean-re-election assumption. Sweep election is one-shot with no fencing: a torn leader reconnects through the pre-ping pool and keeps sweeping alongside the newly elected peer indefinitely. Duplicate equity-curve points are real (`SleeveSnapshot` has no idempotency key; the account-level read dedupes but `strategy_performance_read_service._sleeve_series` does not, so duplicates feed period returns, volatility, and Sharpe). Drift events are safe (deterministic ids plus `ON CONFLICT`).
- A trading pod whose lease connection died still believes it owns its sessions: `_try_claim` short-circuits on the in-memory `_leases` registry, nothing pings the lease connection, and `rehydrate_pass` sees the local runner and continues, so a torn holder keeps trading while a peer adopts the same session. Fencing the sweeps and heartbeating the leases are new work items.
- Each session lease pins one `idle in transaction` connection from the shared pool (about 30 live sessions exhaust pool plus overflow), and a managed-Postgres `idle_in_transaction_session_timeout` silently revokes leases with no failover involved; PgBouncer transaction pooling would break session-level advisory locks outright.
- The proto-enum bridge fallback is now a demonstrated bug: writing `EXECUTION_STATUS_PENDING` to `trading_sessions.status` stores `'active'` (first-member fallback), observed while building the symbol-source helper. Fail-loud conversion in `models/_enum_types.py` is the fix; the inner Enum impl also lacks `cache_ok`, disabling statement caching on every query touching these columns.
- Corporate-actions proposals have no durable queue: the operator applies from a log line today. A proposals table plus a list RPC and a webhook/UI surface is a decision to make; dividend amounts are estimates until the account-activities feed (`/v2/account/activities/DIV`) is wrapped; mergers, spinoffs, and stock dividends are counted as unsupported rather than planned.
- `trading.proto` has no field for session degradation, so `SessionResponse.degraded` stops at the service boundary and clients cannot see it. A residual millisecond race exists in the start path (row committed before the lease is taken; a peer winning the window sends the start to ERROR, fail-closed); closing it means pre-generating the session id and locking before the insert.
- A delisted symbol still participates in evaluation and holds the all-symbols gate shut until the user decides; excluding halted symbols from the gate and from targets is a product decision, deliberately not automated. The degraded marker's single `reason` field is lossy when several symbols halt for different reasons.
- Portfolio's `snapshot()` returns an empty snapshot when credentials cannot be resolved instead of raising like its siblings, which now also masks "broker unreadable" as "no broker identity"; reconciliation never sees the broker id (it calls `positions()`/`cash()`, so no lazy backfill there); an account created while the broker was unreachable is never re-seeded (pre-existing); `LedgerAccount` proto lacks the broker-id field.
- Newly derived ingest symbols stream immediately but have no minute history until the next backfill pass (hourly gap repair narrows it); a junk symbol on a session row can make a subscribe batch retry-stick; the ingest process now reads the platform Postgres with unreviewed pool sizing.
- Portfolio's shutdown calls `release_ledger_writer_lock` unguarded, so a torn-connection unlock can skip `fills.close()` and `close_db()`; a session-level advisory lock taken inside a pooled session that commits would leak onto the pooled connection (latent, current call sites safe).

### Round 4 execution, Wave 3 (2026-07-29)

**Closed.** R12: an operator statement CLI in portfolio (`python -m src.tools.statement`, account, broker-id, or credentials selectors, date ranges, `--json`) renders opening balances, day-grouped activity with running per-sleeve cash, closing lots with realized P&L, and the conservation identity, all computed through the real fold (per-line amounts are fold deltas, not payload re-reads); the text format is pinned by a committed golden. R10, locally buildable half: the declared-but-unwired `llamatrade_celery_queue_depth` gauge is now sampled in the scraped backtest API process over every routed queue (queue set derived from the routing table, with a parity test), and a KEDA ScaledObject ships disabled behind a one-line overlay opt-in, kustomize-green in both states; the worker's termination grace was raised from the 30-second default to 3660 seconds with Celery warm shutdown, since every scale-down or rolling update previously SIGKILLed mid-flight backtests. R5, mechanism half: a pure `FormingBarAggregator` in the runtime folds the one-minute stream into a forming daily bar stamped at the exchange-local period start; `FormingBarFeed` owns the live gate once (trading's `StreamBarFeed` is now a thin translation subclass, deleting a duplicated gate implementation); same-timestamp bars revise history in place; mid-day and crash-restart starts seed the forming bar from the preload; parity tests assert bar-for-bar, indicator-series, order, and equity equality between the live path and a backtest over the folded days. Backtest results are bit-identical (suite unchanged), and a latent bug fell out and was fixed: minute bars used to evict the daily warm-up from the history window within hours.

Verification at wave close: libs/runtime 390, services/trading 707, services/backtest 260, services/portfolio 449, all green together; ruff clean; pyright 1.1.408 strict zero errors repo-wide; no suppressions; no register identifiers in new code.

**New findings from Wave 3 (triage pending; the first is serious).**
- Split lots are not re-based: `SPLIT_APPLIED` opens a new zero-cost lot for the added shares instead of rescaling existing lots, so FIFO enrichment realizes the first post-split sell against a basis twice too high and later sells against zero. Per-sell realized P&L after a split is wrong even though the lifetime total nets out, and with the corporate-actions feed now detecting splits automatically this is beta-gate material. `SYMBOL_CHANGED` similarly collapses per-lot granularity into one merged lot, losing true acquisition order for FIFO.
- Close-aligned evaluation is the remaining half of the live-parity item: live decides at the first complete snapshot of the day (a close-so-far reading the parity tests pin), and gating the daily evaluation to the last minutes of the session is a trade-timing product decision. Blocker if taken: `TradingHoursChecker.get_next_close` uses a fixed 16:00 close and ignores early-close days, so a naive close window would silently skip roughly four sessions a year.
- Forming-bar edges: pre-market minutes enter the fold while after-hours minutes never reach history, so open, extremes, and volume can differ slightly from Alpaca's regular-session daily bar; a replayed minute after a stream reconnect double-counts volume (OHLC is idempotent); `vwap` and `trade_count` are not modeled in the runtime bar; the market-data weekly and monthly continuous aggregates bucket on UTC days, which will not match exchange-local period keying if coarser data is ever fed to the runtime.
- Statement and lots: the statement read is O(full account history) with no `(account_id, occurred_at)` index, and `open_lots` re-walks history once per sleeve-symbol pair; `occurred_at` is not guaranteed monotonic with sequence (backfill and corporate planners set business time in the past) and nothing detects it; the reserved `ledger_lots` table remains unwritten, so lots have no persisted identity to cite in a support ticket.
- Autoscaling context: there is no in-cluster Prometheus or scrape wiring at all, so the new gauge is scraped only in the compose dev stack and the scaler's server address points at nothing until observability lands; Celery's default queue is uncovered if a task ever loses its route; the sampler holds its last value when Redis is unreachable, so a scaler would act on stale data; nothing sets pod-deletion-cost, so scale-down can pick a busy worker (the grace period mitigates); staging's namePrefix would break the scaler's target reference if enabled as-is.

### Round 4 execution, Wave 4 (2026-07-29) and round close

**Closed (locally buildable halves; live verification remains operator work).** KMS cipher: `GcpKmsCipher` is real behind the config seam, with a versioned `kms1.` envelope carrying the wrapping key version so rotation needs no migration, a lazy import behind a `gcp-kms` extra, error mapping preserved to the seam's existing contract, `reencrypt_value` and `key_version_name` for rotation sweeps, and deliberately no data-key cache, because the per-call KMS permission check is the point of the design. External Secrets: the workload secret inventory (eight Secrets, fourteen keys) is covered by a namespaced GCPSM SecretStore plus eight ExternalSecrets shipped as a commented opt-in kustomization (ESO CRDs are not installed); terraform gained the ESO service account, accessor role, Workload Identity bindings, and six missing Secret Manager entries in the existing naming style; enabling is documented as a two-line change because the committed placeholder Secrets must be dropped in the same commit. The e2e job now gates image builds on main, and CI renders both opt-in directories so they cannot rot. OAUTHBEARER: the token-refresh path is tested at two tiers, unit tests over an injectable token-provider seam (the one transport change) and docker-gated real-broker tests for expiry-boundary rotation, additionally executed against a real Kafka 4.1.2 SASL/OAUTHBEARER broker run from the Apache tarball (16 passed live). G54 harness: flag-independent intent capture at the pre-risk sizer output in both loops, a `parity_diff` operator tool with a scriptable zero-divergence exit code (empty captures fail, so a soak cannot pass on missing evidence), and the soak runbook at `.docs/runbooks/runtime-loop-parity-soak.md`; the soak and the flip remain manual.

**Round-close verification (fresh, full sweep).** All 17 Python packages green: libs alpaca 224, common 199, db 358, dsl 280, events 110, proto 95, runtime 390, telemetry 79; services agent 284, auth 134, backtest 260, billing 187, market-data 352 (26 docker-gated fixture errors expected without Docker), notification 57, portfolio 449, strategy 157, trading 723. That is 4,338 Python tests, plus apps/web 189 and clean tsc in web and core. Ruff clean across services, libs, and scripts; the suppression gate is clean; pyright 1.1.408 strict reports zero errors repo-wide; the register-identifier grep over the full changeset is clean.

**New findings from Wave 4 (triage pending; the first three are serious).**
- Every deploy overwrites live secrets: `base/secrets.yaml` commits eight `CHANGE_ME` Secret objects and both deploy workflows `kubectl apply -k` them, clobbering operator-set values. This is live today and independent of ESO. Related: `JWT_SECRET` is mounted only into auth while every service requires it fail-closed, and `ENCRYPTION_KEY` is mounted only into auth while trading needs it to decrypt broker credentials, so the manifested mesh cannot have been running the full platform as deployed.
- aiokafka accepts a rejected OAUTHBEARER token as a successful authentication (the KIP-255 in-band error is ignored by its authenticator), after which `publish()` and `consume()` hang forever with no exception, no reconnect, and no metric. In GCP this is the wrong-audience or clock-skewed Workload Identity failure mode: the ledger writer stalls silently. Mitigation has to be ours (a bounded start, a post-auth liveness probe, or an upstream patch).
- `KafkaTransport.length()` and `purge()` raise spurious `asyncio.CancelledError` against a real broker, reproducibly, on aiokafka 0.14 with Python 3.14. Inside the ingestion loop a spurious cancellation reads as cooperative shutdown and can kill a supervised task without an error log. Production callers: DLQ replay and fill ingestion.
- KMS operational follow-ups: the cipher seam is synchronous, so under KMS every credential decrypt becomes a blocking network call inside async request paths and order placement decrypts twice (an async seam or `asyncio.to_thread` at call sites belongs before the cutover); the seam carries no AAD, so a database-write attacker can swap two tenants' envelopes between rows (binding requires the row identity in the seam signature); CRC32C request and response fields are unverified against vendor guidance; consuming images do not yet declare the `gcp-kms` extra; a local-to-KMS migration needs an explicit two-cipher pass, which `reencrypt_value` (single-cipher) does not cover.
- Smaller: a permanent token-provider failure typed as a Kafka error retries forever with no distinct broken-credentials signal; each aiokafka client builds its own token provider, so a reconnect storm repeats ADC discovery; two-pod parity soaks have an attribution hole (independent books shift sizing; capturing the equity and holdings snapshot per evaluation would close it); the two loops' signal-timestamp agreement is load-bearing for order-id equality and nothing pins the invariant; `TRADING_INTENT_CAPTURE_DIR` is not documented in `.env.example`; the six new Secret Manager entries are versionless until populated out of band; four Workload Identity annotations hardcode the `llamatrade` project name; the migrate Job is applied via sed outside any kustomization, invisible to the kustomize CI; e2e still does not run on pull requests, so the new gate protects main only.

## Status corrections (2026-07-28 re-verification)

Every G-item was re-checked against the working tree. 44 confirmed as written. Corrections:

- **Drifted references:** G12 → `ledger_servicer.py:84`; G14 → `.env.example:23`, and the fix is cheaper than stated (assert is centralized in `init_db()`, `libs/db/llamatrade_db/session.py:203`; five services simply never call it); G30 → compose comment now at `docker-compose.yml:244-246`; G31 → `Makefile:225,238`; G36 → `Makefile:248,251` vs `libs/proto/Makefile:12,24`; G44 → `progress.py:125-130`; G52 → the module moved to `libs/db/llamatrade_db/plan_limits.py` (line 24 still holds).
- **G17 wording:** `mint_service_token` does emit an `svc` claim; `verify_credential:142` discards it. The gap is that verification throws the principal away, not that none is minted.
- **G28 partially fixed:** the backtest worker and beat manifests now exist (`base/backtest/worker.yaml`). Still open: no Timescale, no ingestor manifest, `.v1.` ingress paths, staging-replicas-vs-HPA. The configMapGenerator clause was wrong (none exists) and the billing 8881 port was never bound by any code, not retired.
- **G39 partially superseded:** the events-lib runtime pieces changed roles in the migration; production usage of `StreamConsumer`/`StreamFanout` is disputed between verification passes and needs a direct check before the delete-or-wire decision. `ledger_lots`, `normalize_weights`, pgvector, and the `openai` dependency remain dead as written.
- **G42 widened:** the same naive-timestamp bug also exists for quotes (`clients/market_data.py:352`) and trades (`:363`); the backtest side now conditionally relabels, which masks rather than fixes.
- **G37 addition:** the events lib now gates coverage in CI; auth and agent remain ungated.
- **G55 widened:** `architecture.md:526` still requires `REDIS_URL` and never mentions Kafka; `CLAUDE.md` also points TS proto output at a path that moved to `apps/core/src/proto`.

## A. Money-path correctness

**G1 (beta). Group weights are ignored by the evaluator.** `_evaluate_weight` flattens children and reads only `asset.weight` (`libs/runtime/llamatrade_runtime/evaluation/compiled.py:278-319`) while the validator requires group weights under `specified` (`libs/dsl/llamatrade_dsl/validator.py:285-292`); the "Classic 60/40" template evaluates 50/50, and nested weight blocks flatten instead of composing.
Fix: allocate per child block (a group or weight child receives its block weight, then subdivides by its own method); add nested-composition golden tests.
**FIXED 2026-07-28.** Evaluation is now hierarchical: every block returns a normalized internal allocation, `specified`/`equal` scale children by share, computed methods flatten to the symbol union by design, sibling contributions to the same symbol sum, and the serializer emits group `:weight`. Two extensions the shipped templates required: an `if` directly under `specified` takes its share from the taken branch's declared weight (validator accepts it only when all branches declare the same weight), and a group of bare assets splits its share equally. Golden tests in `libs/runtime/tests/test_composition.py`, round-trip fidelity in `libs/dsl/tests/test_roundtrip_fidelity.py`.

**G2 (beta). Reservation-versus-fill race leaks reserved cash.** The reservation publishes after the broker call returns (`services/trading/src/executor/order_executor.py:251-253`) while the fill publishes from the trade-stream task (`runner.py:984`); a fill that lands first leaves a reservation with no releaser (`services/portfolio/src/ledger/projection.py:198-208`), understating free cash forever and blocking sleeve close.
Fix: the projection treats a reservation for an already-terminal order as a no-op; pure-function, replay-safe.

**G3 (beta). Bare-asset strategies evaluate to liquidation.** `(strategy "X" (asset VTI))` passes validation, evaluates to zero weights (`compiled.py:319`), and sizing closes everything.
Fix: validation rule requiring a weight context for assets.
**FIXED 2026-07-28, differently than planned.** The G1 composition rewrite gives bare assets well-defined semantics instead of a validation error: an asset is its whole subtree (internal allocation 100), and weightless siblings split equally, so `(strategy "X" (asset VTI))` holds VTI at 100 and a group of bare assets splits its share. The validator rule became unnecessary; templates rely on the equal-split behavior.

**G4 (beta). OAuth accounts break the portfolio side silently.** The broker adapter builds only key-and-secret clients (`services/portfolio/src/clients/alpaca.py:144-148`) while trading resolves OAuth (`services/trading/src/credentials.py:50-56`); reconciliation skips those accounts and genesis backfill no-ops.
Fix: mirror trading's credential resolution in the portfolio adapter; add a per-account reconciliation-staleness gauge so skipped accounts alert.

**G5 (beta). Ledger incidents are invisible to users.** Sleeve freezes, quarantined fills, and DLQ growth surface only as logs and metrics; the notification service is an in-memory stub (`services/notification/src/`).
Fix: wire the three incident types to trading's existing per-tenant `AlertService` webhook path; defer the full notification service.

**G6 (ext). Partial fills double-apply in the runner's local state.** The partial handler delegates to the full-fill handler (`runner.py:1270-1283`); the ledger is unaffected and the 5-minute reconciliation repairs it.
Fix: track incremental filled quantity per order.

**G7 (ext). Degraded projections are served as whole.** `AccountProjection.is_complete` has zero readers (`projection.py:74-80`); poison events are counted and the incomplete projection still feeds every read path.
Fix: surface the flag on read paths, plus a metric and an alert.

**G8 (ext). Recovery emission skips unattributed orders.** `_emit_ledger_for_terminal` returns early when `sleeve_id` is None (`order_executor.py:487`), so the order becomes drift adopted into Unmanaged, which is mis-attribution.
Fix: resolve the Manual sleeve during recovery emission.

**G9 (hyg). Bulk sync swallows per-order broker failures.** `sync_all_pending_orders` continues past exceptions silently (`order_executor.py:736-741`).
Fix: log and count.

## B. Money-path scale and design forks

**G10 (rm). Projection replay from genesis.** Full folds are O(account history), the incremental checkpoint is an in-process LRU (`services/portfolio/src/ledger/projector.py:57-58,124-160`), and FIFO enrichment reads the full history per basis-less sell (`tasks/fill_ingestion.py:126-129`).
Fix: persist projection checkpoints keyed by ledger sequence; seed both recovery and FIFO enrichment from them.

**G11 (rm). Kafka operational edges.** Partition count on `lt.ledger.fills` is decide-once and 24 is a placeholder; the OAUTHBEARER token provider needs an expiry integration test and auth-failure alerting (`kafka-event-backbone-migration-plan.md` sections 9-10). Cutover itself executed 2026-07-28.
Fix: size partitions against the account-growth trajectory; add the token-expiry test and alert.

**G12 (rm). Settlement is not modeled.** `unsettled` is hardcoded zero (`services/portfolio/src/grpc/ledger_servicer.py:85`); cash-account users can hit good-faith violations.
Fix (decided): admit margin accounts only at launch through a preflight account-type check; model settled and unsettled balances when cash accounts are admitted.

**G13 (hyg). The desired-state reconciler is built but unwired.** `portfolio/src/ledger/desired_state.py` exists while the runner sizes and submits directly.
Fix (decided): retire the portfolio-side planner; the sizing-ownership question reopens only if block-and-allocate netting is built.

## C. Security and tenancy

**G14 (beta). RLS is inert everywhere.** All environments connect as superuser (`infrastructure/docker/docker-compose.yml`, `.env.example:26`); `create_app_role.sql` is unused and `assert_rls_capable` runs in only four services.
Fix: provision the NOSUPERUSER role, flip connection strings, assert capability at startup in every service. Must land with G15 and G16.

**G15 (beta). Trading writes RLS tables without a tenant GUC.** `AuditService` and `AlertService` use bare sessions (`services/trading/src/services/audit_service.py:444-452`, `alert_service.py:98-101`) against RLS-covered tables.
Fix: route through `tenant_session` or set the GUC.

**G16 (beta). Long-lived sessions lose the GUC on first commit.** The GUC is transaction-local (`libs/db/llamatrade_db/session.py:220-226`); live-session factories set it once (`live_session_service.py:647-668`, `order_executor.py:1293-1301`).
Fix: re-establish the GUC per transaction through a session event hook.

**G17 (rm). Shared HS256 secret; unconstrained service tokens.** Any service can mint any token; service tokens carry no principal or audience (`libs/common/llamatrade_common/auth.py:103-120,142`).
Fix: asymmetric signing with a JWKS endpoint on auth; audience and service-name claims checked against an allowlist on money-path services.

**G18 (ext). No token revocation.** Logout is a no-op (`services/auth/src/grpc/servicer.py:633-634`); refresh tokens stay valid seven days; password change invalidates nothing.
Fix: Redis denylist checked in `AuthMiddleware`; refresh rotation invalidates the replaced token.

**G19 (ext). OAuth flow weaknesses.** Handoff tokens and signup tickets are replayable within TTL and travel in URLs (`services/auth/src/session.py:143-152`, `routers/oauth.py:227-279`); the OAuth signup path skips password validation (`session.py:89-125`); `is_paper=True` is hardcoded.
Fix: single-use consumption store; shared password validation; a decision on live-account OAuth.

**G20 (ext). No rate limiting or lockout on auth surfaces.** Login, register, and credential validation are unthrottled; a missing user skips the bcrypt compare (timing enumeration).
Fix: Redis-backed limiter in the shared middleware; dummy-hash compare on miss.

**G21 (ext). Copilot confirmation trusts client-echoed arguments.** The proposal is never persisted server-side (`services/agent/src/services/agent_service.py:403-412`).
Fix: persist the proposal keyed by `confirmation_id`; execute only stored arguments.

**G22 (hyg). The gRPC auth interceptor never sets identity context.** `libs/proto/llamatrade_proto/interceptors/auth.py` validates but never calls `set_context`, landing `resolve_identity` in the trust-the-wire branch.
Fix: set the ContextVar there, or delete the unused gRPC server path.

**G23 (hyg). Non-HTTP ASGI scopes bypass auth.** `AuthMiddleware` passes WebSocket scopes through (`auth.py:232-234`); latent until an inbound WebSocket exists.
Fix: reject non-HTTP scopes explicitly.

**G24 (hyg, rm for KMS). Hot-path PBKDF2 and platform-wide key.** 100k iterations per decrypt, twice per order (`libs/common/llamatrade_common/utils.py:84-106`, `tenant_service.py:129`).
Fix: derived-key cache (or HKDF) and a stored key-prefix column now; KMS envelope encryption for real money.

**G25 (hyg). The cross-tenant-attempt metric is dead.** Defined (`libs/telemetry/llamatrade_telemetry/domain.py:446`), never incremented.
Fix: increment on the `resolve_identity` deny path; alert on it.

**G26 (rm, gates self-serve). Multi-user tenant assumptions.** `resolve_identity` ignores the wire `user_id` for user tokens (`auth.py:190`); `CheckPermission` is dead code.
Fix: reject a mismatched wire user id; build per-user authorization with the self-serve milestone.

## D. Build, deploy, and infrastructure

**G27 (beta). Six of nine prod Dockerfiles cannot build.** Context-escaping `COPY ../libs`, python3.12 site-packages on a 3.14 base, wrong ports (`services/billing/Dockerfile:4,9,14-16` is representative; backtest, market-data, notification, portfolio, trading share it; auth and strategy expose wrong ports). `deploy-staging.yml` fails at its first build; `deploy-prod.yml` only re-tags.
Fix: one parameterized multi-stage Dockerfile modeled on the agent service's; CI build matrix over all nine.

**G28 (beta). K8s manifests do not describe the real topology.** No Timescale, market-data ingestor, or backtest worker and beat (`infrastructure/k8s/base/`); ingress paths use a nonexistent `.v1.` prefix (`base/frontend/deployment.yaml:72-134`); billing probes and scrape target retired port 8881; staging replica patch defeated by HPA min 2; `kustomize build` reported failing on a configMapGenerator merge.
Fix: align manifests with the compose topology; add the missing workloads; `kustomize build` in CI.

**G29 (ext). Terraform and the cluster disagree.** Memorystore provisioned while the cluster hardcodes in-cluster Redis (`base/configmap.yaml:33`); Secret Manager entries with no bridge; committed `CHANGE_ME` Secrets (`base/secrets.yaml`).
Fix: External Secrets Operator; one Redis; delete placeholders.

**G30 (hyg). The ingestor singleton is a compose comment.** (`docker-compose.yml:218-220`); no K8s manifest at all.
Fix: single-replica Recreate deployment; leader lock only if it ever matters (writes are idempotent).

**G31 (hyg). `make proto` is macOS-only.** BSD `sed -i ''` (`Makefile:224,237`).
Fix: portable invocation.

## E. Observability

**G32 (beta). Traces export nowhere.** Endpoint unset in dev (`docker-compose.dev.yml:202-205`); K8s points at gRPC port 4317 while the exporter is OTLP/HTTP 4318 (`base/configmap.yaml:22` vs `libs/telemetry/llamatrade_telemetry/tracing.py:50-52`); collector exports to debug only.
Fix: set endpoints everywhere, correct the port, real collector backend.

**G33 (hyg). Streaming RPCs uninstrumented.** Telemetry interceptor is unary-unary only (`libs/proto/llamatrade_proto/interceptors/telemetry.py:65-67`).
Fix: stream-count and active-stream metrics at the Connect layer.

**G34 (hyg). Defined-but-dead metrics.** Rate-limiter, circuit-breaker, market-data stream, and backtest throughput gauges have zero call sites (`domain.py:235-270,348-353`).
Fix: wire or delete.

**G35 (ext). Readiness probes are decorative in seven services.** Only market-data and portfolio register checks; elsewhere `/health/ready` is a constant 200 (`llamatrade_common/health.py:186-187`).
Fix: per-service Postgres, Redis, and broker checks with cheap cached probes.

## F. CI and API hygiene

**G36 (beta). `buf lint` and `buf breaking` are not in CI.** Two make targets disagree on base ref (`Makefile:249-250` vs `libs/proto/Makefile:29-31`); the Kafka schema posture leans on this gate.
Fix: one CI job running both against main.

**G37 (hyg). Coverage gates missing for auth and agent.** (`.github/workflows/ci.yml` gates only strategy, backtest, portfolio, trading.)
Fix: add the gates.

**G38 (hyg). Workspace dependency declarations incomplete.** `libs/db` imports proto and common undeclared (Dockerfile hand-installs, `libs/db/Dockerfile:15-19`); market-data imports events, proto, telemetry undeclared.
Fix: declare; remove workarounds.

**G39 (hyg). Dead code needing decisions.** `StreamConsumer`/`StreamFanout` usage (owned by Kafka cleanup), the unused `ledger_lots` table, `conditions.normalize_weights`, idle pgvector, the agent's unused `openai` dependency.
Fix: delete or wire each; no third states.

## G. Data, backtest, and DSL correctness

**G40 (ext). Alpaca bar fetches silently truncate.** `get_bars` ignores `next_page_token`; `BACKTEST_MAX_BARS_PER_SYMBOL=100000` unreachable; store reads truncate to earliest N (`services/market-data/src/services/market_data_service.py:176`).
Fix: paginate in `llamatrade_alpaca`; most-recent-N limit semantics.

**G41 (rm). Rate limiting is per-process.** Each replica gets a full 200-per-minute budget (`libs/alpaca/llamatrade_alpaca/resilience.py:35`).
Fix: shared Redis token budget.

**G42 (ext). Timestamps relabel local time as UTC.** `datetime.fromtimestamp(seconds)` then `.replace(tzinfo=UTC)` (`libs/proto/llamatrade_proto/clients/market_data.py:338`, `services/backtest/src/services/backtest_service.py:277-279`); masked in UTC containers.
Fix: `fromtimestamp(seconds, tz=UTC)` at the source.

**G43 (hyg). Stream bars lose vwap and trade_count.** `_parse_bar` never reads `vw`/`n` (`libs/alpaca/llamatrade_alpaca/streaming/market_data_stream.py:291-303`); NULL vwap degrades aggregates.
Fix: parse both fields.

**G44 (hyg). Progress-publish failure fails the backtest.** Publish errors re-raise (`services/backtest/src/progress.py:126-131`).
Fix: degrade to logging after repeated consecutive failures.

**G45 (ext). Deep nesting produces a 500.** No parser depth guard; `create_strategy` catches only `ParseError` (`services/strategy/src/services/strategy_service.py:204`).
Fix: depth limit in the parser raising `ParseError`.

**G46 (hyg). Validation errors lose position at the wire.** `validation_to_proto` hardcodes line and column to zero (`services/strategy/src/proto_mappers.py:181-184`).
Fix: map the fields through.

**G47 (hyg). DSL vocabulary duplication.** Four indicator lists (AST, lookbacks, dispatch, proto enum, the last out of sync); duplicated window constants; two normalizers with different fallbacks.
Fix: one vocabulary module with parity tests; delete the unused normalizer.

**G48 (ext). Accepted-but-unhonored semantics.** Metric crossovers can never fire (`conditions.py:153-154`); `:top` ignored except for momentum.
Fix: validator rejects both until implemented.

**G49 (hyg). The dataset store grows without bound.** No TTL or eviction (`services/backtest/src/dataset/store.py`).
Fix: last-access janitor.

**G50 (ext). TypeScript DSL drift.** No conformance suite; drops `:benchmark` on emit; accepts three extra keywords (`apps/core/src/strategy/serializer.ts:1345-1360`).
Fix: shared conformance corpus (S-expression in, canonical JSON out) in both CI lanes.

## H. Billing, lifecycle, and documentation

**G51 (ext). Stripe webhook trust and error handling.** Signature check skipped when the secret is unset (`services/billing/src/routers/webhooks.py:109-119`); handler failures return 200 (`:168-171`).
Fix: `require_secret` in production; non-200 for retryable handler failures.

**G52 (ext). Free-tier limits disagree.** `plan_limits.py:24` says 1 live and 10 backtests; the catalog says 0 and 5 (`billing_service.py:58-62`); the fallback is the generous one.
Fix: one source; fallback stricter than the catalog.

**G53 (ext). No server-side reconciliation for the two-phase deploy.** The client orchestrates create, start, and session start (`apps/core/src/stores/deploy.ts:66-101`); a RUNNING execution with no runner is permanent.
Fix (decided): trading's session rehydrator adopts RUNNING executions without sessions.

**G54 (ext). Two live loops maintained by hand.** `_evaluate_session` is the default while `StrategyRuntime.stream()` sits behind `TRADING_USE_RUNTIME_LOOP` (`services/trading/src/runner/runner.py:229,428`).
Fix: complete paper-QA parity, flip the flag, delete the hand-rolled loop.

**G55 (hyg). Documentation actively misleads.** `services/strategy.md:195-815` documents a retired language; `architecture.md` misstates the crypto and presents aspirational infra as current; CLAUDE.md claims generated protos are gitignored; `X-Tenant-ID` propagation is described but not real.
Fix: delete stale sections; point them at the spec and subsystem contracts.

## Round 2: architecture interrogation findings (2026-07-28, proposed, pending approval)

A second review pass questioned each section of the spec from failure, concurrency, adversarial-user, operational, and product-evolution angles. These are new findings and proposals, not yet approved directions; triage them into the plan's gates before treating any as committed. The spec carries each of these questions inline in its home section as a *what if* with the honest current answer, referencing the R-numbers here; this register remains the tracking location.

**R1 (proposed, ext). Credential re-linking creates a duplicate account book.** `Account` is unique per `credentials_id` (`libs/db/llamatrade_db/models/ledger.py:119`), so deleting and re-adding broker credentials creates a second `Account` whose genesis backfill adopts the same broker positions the old account still holds; tenant-level reads aggregate across accounts and double-count.
Proposal: key or dedupe accounts by `alpaca_account_id`, or run a migrate-and-close of the old account on re-link.

**R2 (proposed, beta-adjacent). Reconciliation can race an in-flight fill.** A fill that has reached the broker but not yet folded looks like `MISSING_IN_LEDGER` to a concurrently running reconcile pass; adoption into Unmanaged followed by the real fill's append double-counts the position, which the invariant check then converts into a freeze.
Proposal: exclude symbols with open or recently terminal orders for the account from drift adoption, or require the drift to persist across two consecutive passes before acting.

**R3 (proposed, ext). Credential deletion is unguarded.** Nothing blocks deleting Alpaca credentials while funded sleeves or live sessions depend on them; trading then hard-fails and reconciliation goes permanently stale on the account.
Proposal: refuse deletion while dependent sessions or funded sleeves exist, offering stop-and-close first.

**R4 (proposed, rm). Corporate actions have planners but no detection feed.** Split, rename, and dividend planners exist (`services/portfolio/src/ledger/corporate.py`) and `ApplyCorporateAction` is operator-only; dividends today surface only as unattributed cash drift.
Proposal: a nightly corporate-announcements poll through `llamatrade_alpaca` driving the planners, with dividends attributed pro-rata by lots.

**R5 (proposed, ext). Candidate resolution for the live indicator parity item.** Live indicators warm from daily bars but update on the 1-minute stream (spec section 5.2's named open item).
Proposal: materialize a forming daily bar from the intraday stream and evaluate indicators at daily resolution in live, making live indicator semantics identical to backtest by construction; the language is daily-or-coarser anyway.

**R6 (proposed, ext). No symbol lifecycle handling.** A halt or delisting silently stalls the all-symbols evaluation gate forever; the ingest universe is env-only (`services/market-data/src/ingest/config.py:56`), which also blocks the shared bar fan-out flag from serving arbitrary strategy symbols.
Proposal: asset-status checks at session preflight and periodically during operation, an explicit tenant alert on halt or delisting, and a universe derived from the union of live-session symbols before `TRADING_BARS_FROM_SERVICE` flips on.

**R7 (proposed, ext). RLS bypass is unaudited.** `system_session` and `set_rls_bypass` are legitimate escape hatches with no audit trail of their use.
Proposal: emit an audit event and a metric per bypass use, so the escape hatch stays observable.

**R8 (proposed, rm). Advisory locks under database failover are untested.** The narrowed portfolio lock (reconcile and snapshot writers) and trading's per-session locks release on connection loss by design, but the behavior under a Cloud SQL failover (half-open connections, split-brain windows) has never been exercised.
Proposal: a failover chaos test asserting single-writer properties hold across a forced failover.

**R9 (proposed, hyg). No migration rollback policy.** The deploy runs Alembic forward; what happens when a migration must be undone under load is undefined.
Proposal: adopt and document forward-only expand-and-contract as the convention, enforced in review.

**R10 (proposed, rm). Backtest workers do not autoscale.** Worker replicas are fixed; a submission burst queues silently. The queue-depth signal exists and is unused.
Proposal: KEDA autoscaling on Celery queue depth; revisit at the external-users gate.

**R11 (proposed, hyg). Deploy workflows have no concurrency guard.** Two staging runs can interleave image pushes and rollouts.
Proposal: a GitHub Actions concurrency group per environment.

**R12 (proposed, hyg). The ledger's audit value lacks support tooling.** Explaining a balance to a user currently means reading raw events; the read model is close but not operator-shaped.
Proposal: a support tool that renders an account's event history into a human-readable statement (every balance explained by its events).

**R13 (proposed, hyg). Sub-notional churn on small sleeves.** Feasibility is checked at admission only; a sleeve whose equity has shrunk can emit orders below the broker minimum, which reject and churn reservations.
Proposal: a runtime minimum-notional guard that skips and counts such orders.

## Round 3: full-repo sweep, 2026-07-28 (Kafka follow-through + test suites)

Findings from a six-way verification sweep after the Kafka cutover: the migration's leftover gaps (K-items) and the test-suite gaps (T-items). K1 to K3 and T1 to T5 are beta-gate.

### K. Kafka migration follow-through

**K1 (beta, blocking). Compose services are not wired to the broker.** The Redpanda service exists (`docker-compose.yml:59-80`) but no service sets `KAFKA_BOOTSTRAP_SERVERS` or `depends_on: redpanda`; every container falls back to `localhost:9092` inside itself (`transport/kafka.py:43,106-108`). Fills, bars, and progress are all broken in local compose.
Fix: add the env and depends_on to backtest, backtest-worker, market-data, market-data-ingestor, trading, and portfolio, pointing at `redpanda:29092`.

**K2 (beta). The K8s bootstrap address is a literal placeholder.** `base/configmap.yaml:43` ships `KAFKA_BOOTSTRAP_ADDRESS_PLACEHOLDER`; neither deploy workflow substitutes it.
Fix: template it from `terraform output kafka_bootstrap_address` in the deploy workflows, or move it to the External Secrets path with G29.

**K3 (beta). DLQ and dead-letter publishes are unkeyed.** `dlq_replay.py:38`, `fill_ingestion.py:69`, and `consumer.py:120,158` publish without `key=account_id`, so a replayed fill round-robins onto an arbitrary partition and can fold out of order against the account's live fills, violating the migration's core invariant.
Fix: recover the account id from the envelope and key every DLQ produce and replay.

**K4 (ext). Cursor resume is silently downgraded.** `KafkaTransport.tail` (`kafka.py:202`) honors only `CURSOR_BEGIN`; a real `partition:offset` cursor falls through to `latest`, so a reconnecting UI client loses the gap it reconnected to recover, while `subscriber.py:71-74` still promises replay. The deleted Redis suite covered this; implementation and coverage were lost together.
Fix: seek to the stored offset per partition; restore the reconnect-replay test.

**K5 (rm). App-side topic auto-creation defeats Terraform sizing.** `_ensure_topic` (`kafka.py:227-236`) creates missing topics with 1 partition and replication factor 1; if it races or outruns Terraform, `lt.ledger.fills` becomes serial and unreplicated permanently (partition count is decide-once).
Fix: fail loudly on a missing topic in non-dev environments instead of creating it.

**K6 (ext). No transport reconnect, and the bars bridge dies permanently.** `tail`/`consume` have no retry (the Redis transport had backoff loops); `BusBridge._run` is an unsupervised task (`bus_bridge.py:41-53`), so one broker error stops live bars until pod restart. The fill consumer is safe only because it is supervised.
Fix: reconnect-with-backoff in the transport generators, and supervise the bridge.

**K7 (ext). In-place retry blocks the pod's whole assignment and risks rebalance storms.** The infinite retry in `fill_ingestion.py:309-346` stalls every partition assigned to the pod (single consume loop), not one account as its docstring claims, and no `max_poll_interval_ms` is configured, so a database outage past five minutes evicts the member and cascades rebalances.
Fix: configure `max_poll_interval_ms` well above the backoff cap, pause/resume the specific partition during retry, and correct the docstring.

**K8 (ext, tenancy). Shared-topic tails scan every tenant's records.** Per-entity UI streams multiplex onto shared topics and filter client-side by key (`kafka.py:211-214`); every subscriber deserializes all tenants' records in process, isolation rests on one string compare, and progress replay-from-start scans the whole 6-hour topic for all tenants (`catalog/progress.py:50`). The plan's recent-offset seek was never implemented.
Fix: implement timestamp/offset seek for tails; consider per-tenant topic sharding only if subscriber volume makes the scan material.

**K9 (ext). Nothing health-checks Kafka.** No `check_kafka` exists in `llamatrade_common.health`; market-data still probes Redis as if it were the backbone; portfolio's consumer can be disconnected from the fills topic and still report ready.
Fix: a broker-connectivity check registered by every producer/consumer service, plus consumer-group membership in portfolio's readiness.

**K10 (hyg). Toolchain drift makes the Kafka tests skippable everywhere but GitHub CI.** `uv.lock` still locks `redis`/`testcontainers[redis]` with no `aiokafka`; `testcontainers[kafka]` is missing from the portfolio and market-data extras and from `ci-local.sh:223`, so the new integration tests silently skip locally.
Fix: regenerate the lock, add the kafka extra everywhere, and make skips loud (see T13).

**K11 (hyg). Dead Redis and dead config left behind.** Portfolio still depends on `redis` and `fakeredis` and its K8s manifest injects `REDIS_URL`; `Channel.maxlen` and `DLQ_MAXLEN` are dead numbers that tests still assert (`test_channels.py:45-47`) while real retention lives only in Terraform; `EVENTS_RECONNECTS_TOTAL` has no callers and the lag gauge's help text still says PEL.
Fix: delete the dead deps/env/config; either drop `maxlen` or generate Terraform retention from the channel registry.

**K12 (hyg). Stale transport prose in shipped code.** `transport/base.py` still frames the seam as "swap Redis Streams for Kafka" and cites a deleted migration doc; `fill_ingestion.py:1`, trading's publisher/subscriber headers, backtest progress docstrings, and `libs/events/README.md` all describe the deleted architecture.
Fix: one docstring sweep alongside G55.

**K13 (rm). OAUTHBEARER and IAM edges.** `GcpTokenProvider` has zero tests and no refresh-ahead; a provider instance is created per client (seven call sites, each hitting the metadata server); staging-namespace Workload Identity bindings are missing (`kafka.tf:84-93` hardcodes `llamatrade`); topic-scoped ACLs are deferred to a provider bump with a cluster-wide client role in the interim.
Fix: token-expiry integration test and auth-failure alert (G11), shared provider, staging bindings, ACLs when the provider allows.

### T. Test-suite gaps

**T1 (beta). The DSL and runtime suites never run in CI.** 540 tests (209 in `libs/dsl`, 331 in `libs/runtime`) are installed but never executed: no pytest step in `ci.yml`, `Makefile` loops `services/*` only, root `testpaths` excludes `libs/*/tests`, and the TA-Lib golden suite's `golden` extra is never installed so all 27 oracle tests would skip anyway. `libs/runtime` also has no coverage gate.
Fix: CI steps for both libs with `--cov-fail-under`, the golden extra installed, and `libs/*/tests` in the root testpaths.
**MOSTLY FIXED 2026-07-28.** Both suites now run as CI steps and `libs/runtime` gates at 80 via package addopts (93 actual). Still open: the `golden` extra needs the TA-Lib C library in the CI image, so the 27 oracle tests still skip there.

**T2 (beta). 35 of 80 shipped templates do not parse.** Verified empirically; only 4 of 80 survive parse, validate, serialize, reparse, validate. The sole guard asserts the string starts with `(strategy` (`test_template_service.py:86`), and one test pins a broken template as working by patching out `create_strategy`. This is a live product defect, not only a test gap.
Fix: a template conformance test that runs every template through the full round-trip, then repair or remove the failing 35.
**FIXED 2026-07-28.** All 80 templates now pass parse, validate, serialize, reparse, revalidate, with AST equality via the JSON IR; the cosmetic `startswith` test was replaced by the full conformance gate. The defects were mechanical: missing trailing closers (32 templates), the `:output <name>` idiom for indicator outputs (6, corrected to `:<name>`), and three mid-structure paren misplacements fixed by hand.

**T3 (beta). The evaluator's composition semantics have no tests, and several tests pin the buggy behavior.** No test in the repo exercises a weight block inside a weight block, a group `:weight`, duplicate symbols across branches, `:top` on non-momentum methods, or a bare asset; `test_roundtrip_all_weather` certifies the weight-destroying round-trip and `TestSerializeGroup` documents the weight-free serializer as the contract.
Fix: land the golden composition suite (60/40 groups, nested equal, duplicate-symbol pin, bare-asset) before the G1/G3 code fixes, so the fixes are provably behavior-correcting; fix the pinning tests in the same change.
**FIXED 2026-07-28.** The golden suite landed first and failed on the old behavior (seven of eight, with the flat case pinned green), then went green under the G1 fix. The pinning tests survived unchanged because they asserted shapes, not weights; the template test that pinned the broken `:output` idiom was corrected.

**T4 (beta). The e2e suite is red on main, surfaces two real defects, and blocks nothing.** `get_plan_limit` crashes on `None` limits (`plan_limits.py:49` versus the seeded Pro plan's unlimited `None`), and the CI e2e env never sets `PORTFOLIO_GRPC_TARGET`/`MARKET_DATA_GRPC_TARGET` so every service-to-service hop fails on compose hostnames; `build` deliberately excludes `test-e2e` from its needs and images shipped on a red run; two harness checks are `check(True, ...)` no-ops.
Fix: treat `None` as unlimited with a test; set the target env vars in the e2e job; make the two no-op checks real; gate `build` on e2e after ten consecutive green main runs.
**PARTIALLY FIXED 2026-07-28.** `get_plan_limit` treats null as `UNLIMITED` with tests, and the e2e job env now carries `*_GRPC_TARGET` for every booted service. Still open: the two `check(True, ...)` no-ops and gating `build` on e2e once it proves stable.

**T5 (beta). The root `tests/integration` suite is 11k lines of dead code.** It imports eight models that do not exist, a deleted backtest engine module, and a moved bar-stream module; collection errors interrupt any root pytest run; `Makefile:130` swallows it with `|| true`; `docker-compose.test.yml` is consumed by nothing (an autouse fixture overrides its URLs; stripe-mock has no consumer).
Fix: port `security/test_tenant_isolation.py` and `services/test_billing_webhooks.py` onto the working per-service testcontainers pattern, delete the rest, drop the path from `testpaths`/`Makefile`/`ci-local.sh`, and remove or repurpose the test compose file.
**FIXED 2026-07-28, with one substitution.** The suite, its root conftest, factories, and mocks are deleted; `testpaths`, `make test-integration`/`test-security`/`test-integration-docker`, and `ci-local.sh --integration` now run the real per-service suites (portfolio, market-data, events Kafka, strategy tenant isolation). Rather than porting the two named files, the security target points at the stronger existing equivalents (portfolio RLS and servicer-auth tests, strategy tenant-isolation tests); billing webhook router tests remain T8 work to write fresh. The test compose file stays, as the Kafka migration now uses it.

**T6 (ext). Money-path joints are untested.** `generate_deterministic_order_id` has zero tests; no test drives one order through both emission paths and asserts one ledger row; reservation release on reject/expiry is unasserted on both paths (a leak permanently blocks sleeve close); the negative-cash freeze and freeze idempotency never run end to end; the public `check_order(sleeve_id=...)` wiring is never called in tests; there is no Kafka rebalance-redelivery test, no real-broker DLQ test, and the per-account ordering test is vacuous on an auto-created single-partition topic; the bracket OCO row-lock assertion is a tautology; trading has no real-database test of the `client_order_id` unique constraint.
Fix: the joint tests above, a multi-partition ordering proof, and a two-member group kill test; remove the `pragma: no cover` on the consume loop once covered.

**T7 (ext). Auth's dangerous paths are the untested ones.** `complete_signup` has zero tests (and skips password strength); the cross-tenant guards on `get_user`/`get_tenant` are dead under test because no test sets the ambient context; handoff replay is untested against a documented one-time claim; the OAuth router's DB half (including the 409 already-linked branch and the ticket race with no row lock) is untested; the login timing oracle has no test; nothing asserts protected paths stay protected.
Fix: a `complete_signup` suite with strength enforcement, context-set guard tests, a replay test backed by single-use consumption (G19), router DB tests, and a dummy-hash timing fix with test.

**T8 (ext). Billing's webhook router and limits parity are untested.** No test calls `handle_stripe_webhook` (missing-signature 400, the missing-secret unverified-dispatch bypass, the signature-failure metric); there is no `event.id` dedup at all and no double-delivery test; the exception-swallow-to-200 path is uncovered; no test imports both plan-limit sources to assert parity, and the `int(None)` crash is untested on both sides.
Fix: router-level tests with real signatures, an event-id dedup store with a replay test, non-200 on retryable failures (G51), and a cross-module limits parity test (G52).

**T9 (ext). Agent test blind spots.** `test_extraction_service.py` and `test_memory_integration.py` are zero-byte files against 317 lines of extraction logic and the RLS-scoped fire-and-forget insert; the confirmation tests codify the client-echoed pass-through instead of flagging it (T-side of G21/R-agent fix); the Anthropic and Gemini adapters (747 lines) and `strategy_tools.py` (433 lines) have no tests.
Fix: fill the empty files, rewrite confirmation tests against server-persisted proposals, and add adapter contract tests with recorded SDK shapes.

**T10 (ext). Market-data's most important guarantees have vacuous or missing tests.** The forming-bar guard test is true by construction and ends in a tautology; the adjustment-discipline fake records adjustments that no test reads (the exact mislabel bug class the code comments warn about); the ingest supervisor (202 lines including the reconnect-exhaustion recovery) has zero tests; about 400 lines of streaming tests are skipped wholesale; a skip cites clock-error coverage in `libs/alpaca` that does not exist.
Fix: a real closed-boundary test, adjustment assertions on the recorded fake, supervisor tests with a scripted dying stream, and delete or resurrect the skipped classes.

**T11 (ext). Alpaca resilience machinery is untested where it matters.** WebSocket `_reconnect` (backoff, jitter, max attempts, the `on_reconnect` hook) has no tests; circuit-breaker HALF_OPEN transitions have none; the rate limiter has no time-based or concurrency test; `RetryConfig.retryable_status_codes` is dead config.
Fix: fake-clock reconnect and HALF_OPEN tests; delete the dead config.

**T12 (ext). The tenancy primitives in `libs/db` are untested at the lib level.** `set_tenant_guc`/`tenant_session`/`system_session` appear nowhere in the lib's tests (including the documented commit-clears-GUC hazard); `assert_rls_capable` is untested; the conftest is SQLite so no Postgres behavior can ever be exercised there; the only real RLS enforcement test lives in one service.
Fix: a Postgres testcontainer harness in `libs/db` with GUC-lifecycle, bypass, and non-superuser policy tests, shared as a fixture for services.

**T13 (hyg). Coverage and skip discipline.** No branch coverage anywhere (line-only 80% gates); the root run has no `fail_under` and unions services; `libs/alpaca`, `libs/db`, market-data, auth, and agent are ungated; Docker or broker unavailability converts entire integration layers into silent green skips.
Fix: `branch = true`, per-package gates, and a CI env flag that turns infra-unavailable skips into failures.

**T14 (hyg). Test-quality debt.** Trading's concurrency file largely tests its own mocks; the notification suite spends about 1,160 lines on an in-memory stub and a `return True` channel; sleeps-based timing tests risk flakes; the telemetry strict-mode setting is tested and the registry is tested but the wiring between them is not; the middleware's websocket-scope, `/health/` prefix, and bare-header behaviors are untested.
Fix: prune with the stub (G5 supersedes the notification mirage), fake clocks for timing tests, and the small middleware/telemetry connection tests.

**T15 (ext). The e2e scenario roadmap.** In order of value: a single-strategy whole-life leg (create through backtest, deploy, fill, stop, close, with real close assertions); a two-tenant isolation leg over real HTTP with a NOSUPERUSER role so RLS is not inert in e2e; a trading-runner fill loop with a responsive `MockTradeStream` publishing to real Kafka and folded by the real consumer (joins the two proven halves of the money path); auth token lifecycle; market-data ingest with a fake feed; billing plan limits in situ; progress streaming; copilot with a scripted LLM. Plus a PR-scoped smoke subset and a seed-invariants test pinning the seed-to-harness contract.
