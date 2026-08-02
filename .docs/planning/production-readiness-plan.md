# Production readiness: implementation plan

| | |
|---|---|
| **Companion** | `production-readiness-gaps.md` (the register; G-numbers below refer to it) |
| **Created** | 2026-07-28 |
| **Structure** | Three gates matching the MVP milestones (beta, external users, real money) plus a continuous hygiene track. Batches within a gate are ordered; batches across gates can overlap where dependencies allow. |

Effort marks: S is under a day, M is one to three days, L is a week-scale piece.

## Gate 1: closed beta

The beta gate has three themes: the evaluator must not misallocate money, the tenancy backstop must actually be on, and the platform must deploy through CI. Ordering within the gate matters and is given below.

**Batch 1.1: evaluator correctness (G1, G3). L.**
Rework `_evaluate_weight` to allocate per child block: each `group` or nested `weight` child receives its block-level weight (or an equal share under non-specified methods) and subdivides internally, so the documented hierarchical composition holds. Add a validation rule that an `asset` outside a weight context must carry a weight. Land a golden-test suite for nested composition, group weights, and duplicate-symbol semantics before the fix, so the change is provably behavior-correcting. Re-run every shipped template through the evaluator and assert its documented allocation. This batch is first because every backtest and live session run before it produces allocations users did not ask for.

**Batch 1.2: tenancy enforcement (G15, G16, then G14). M.**
Order is load-bearing: first move trading's audit and alert paths onto tenant-scoped sessions (G15) and add a session event hook that re-establishes the transaction-local GUC on every transaction begin (G16); then provision the `llamatrade_app` NOSUPERUSER role, flip every connection string, and call `assert_rls_capable` at startup in all nine services (G14). Flipping the role first would break the trading audit trail. Exit test: the portfolio RLS integration suite runs against the app role in CI, and a cross-tenant read attempt in each service returns zero rows.

**Batch 1.3: money-path fixes (G2, G4, G5). M.**
G2: teach the projection that a reservation arriving for an already-terminal order is a no-op, with a replay test covering both orderings. G4: route the portfolio broker adapter through the same credential resolution trading uses, and add the reconciliation-staleness gauge. G5: emit sleeve-freeze, quarantine, and DLQ-growth events through trading's `AlertService` per-tenant webhook path. These three are independent and can run in parallel with batch 1.2.

**Batch 1.4: build and deploy consolidation (G27, G28, G32, G36). L.**
One parameterized multi-stage Dockerfile (repo-root context, shared-library order, non-root, correct port), applied to all nine services; a CI build matrix so a Dockerfile that does not build cannot merge. Bring the K8s manifests up to the compose topology: add Timescale, the ingestor (single-replica Recreate), the backtest worker and beat; fix the ingress paths, billing ports, and the staging HPA interaction; put `kustomize build` for every overlay in CI. Fix the OTLP endpoint and port so traces export in dev and in cluster, and give the collector a real backend. Add the `buf lint` plus `buf breaking` CI job (one canonical base ref). Exit test: the staging workflow runs end to end from a clean commit and the deployed mesh passes the e2e suite.

Gate 1 exit: an invited tester on staging can run the full loop (connect, build, backtest, deploy paper) on infrastructure deployed by CI, with RLS enforced and correct allocations.

## Gate 2: external users

**Batch 2.1: auth hardening (G18, G19, G20). L.**
Redis token denylist checked in `AuthMiddleware`; logout and password change insert outstanding token ids; refresh rotation invalidates the replaced token. Single-use consumption for OAuth handoffs and signup tickets; shared password validation on the OAuth signup path. Redis-backed rate limiting with lockout on login, register, and credential validation, plus a dummy-hash compare on unknown users.

**Batch 2.2: copilot and billing trust (G21, G51, G52). M.**
Persist tool-call proposals server-side keyed by `confirmation_id` and execute only stored arguments. Require the Stripe webhook secret through `require_secret` in production and return non-200 for retryable handler failures. Collapse the free-tier limits to one source with the fallback stricter than the catalog.

**Batch 2.3: lifecycle convergence (G53, G54). M.**
Extend trading's session rehydrator to adopt RUNNING executions that have no live session, using the existing per-session advisory locks. Complete the paper-QA parity run for `TRADING_USE_RUNTIME_LOOP` (identical order intents over a soak window), flip the flag, delete the hand-rolled loop.

**Batch 2.4: data correctness (G40, G42, G45, G48, G50). M.**
Paginate `get_bars` with `next_page_token` and make range limits most-recent-N. Fix the timestamp conversion at the proto-client source. Add a parser depth limit raising `ParseError`. Make the validator reject metric crossovers and non-momentum `:top`. Land the shared DSL conformance corpus in both CI lanes.

**Batch 2.5: read-path integrity and probes (G6, G7, G8, G35). M.**
Incremental partial-fill tracking in the runner; surface `is_complete` on projection read paths with a metric; resolve the Manual sleeve during recovery emission; register real health checks in the seven services whose readiness is constant.

Gate 2 exit: the platform is safe to expose beyond invited testers; abuse surfaces are throttled, sessions are revocable, and the copilot cannot be made to execute unapproved actions.

## Gate 3: real money

**Batch 3.1: ledger scale (G10, G11). L.**
Persist projection checkpoints keyed by ledger sequence; seed recovery and FIFO enrichment from them; restart cost becomes O(delta). Size the `lt.ledger.fills` partition count from an account-growth estimate while re-partitioning is still cheap; add the OAUTHBEARER token-expiry integration test and auth-failure alert.

**Batch 3.2: identity and secrets (G17, G24-KMS, G26). L.**
Asymmetric JWT signing with a JWKS endpoint on auth; verify-only keys elsewhere; audience and service-name claims checked against an allowlist on money-path services. KMS envelope encryption for broker credentials (per-credential data keys). Reject a wire `user_id` that disagrees with the token; schedule per-user authorization with the self-serve milestone.

**Batch 3.3: platform budgets and posture (G12, G41). M.**
Preflight account-type check admitting margin accounts only, with settled/unsettled modeling deferred to cash-account admission. Shared Redis token budget for the Alpaca rate limit so replicas divide rather than multiply it.

Gate 3 exit: a compromised single service cannot mint tokens or read raw credentials; the ledger restarts in O(delta); the broker budget holds under horizontal scale.

## Continuous hygiene track

Small items to fold into adjacent work rather than schedule as a project: G9 (log bulk-sync failures), G13 (delete the desired-state planner), G22 (fix or delete the gRPC interceptor path), G23 (reject non-HTTP scopes), G24 (derived-key cache and key-prefix column, ahead of the KMS work), G25 (increment the cross-tenant metric), G29 (External Secrets, one Redis), G30 (ingestor manifest), G31 (portable sed), G33 (stream metrics), G34 (wire or delete dead gauges), G37 (auth and agent coverage gates), G38 (workspace dependency declarations), G39 (dead-code decisions), G43 (parse vw/n), G44 (progress publish degrades), G46 (map error positions), G47 (single indicator vocabulary), G49 (dataset janitor), G55 (delete stale docs).

## Round 3 triage

Round 3 of the register (K-items from the Kafka follow-through, T-items from the test-suite sweep, plus status corrections) lands as follows. Beta gate: K1, K2, K3 join batch 1.4 (they are deploy/topology work); T1, T2, T3 form a new batch 1.5 (test the evaluator and templates before fixing them, then wire the lib suites into CI); T4 and T5 form batch 1.6 (make the e2e signal real: fix the two defects it found, kill the dead root suite). External users: K4, K6, K7, K8, K9 (transport hardening), T6 through T12 and T15 (the joint tests and scenario legs, with T15's runner-fill-loop test as the highest-value single addition). Real money: K5, K13 (join batch 3.1). Hygiene: K10, K11, K12, T13, T14. The G-item status corrections (drifted references, G28/G39/G42 partial states) are already folded into the register text.

## Round 2 triage

The register's Round 2 section (R1 to R13) holds findings from the second interrogation pass, marked proposed. Suggested placement on approval: R2 joins batch 1.3 (it shares the reconciliation code path), R1, R3, R5, R6, and R7 join Gate 2, R4, R8, and R10 join Gate 3, and R9, R11, R12, and R13 join the hygiene track. R2 shipped with the 2026-07-28 execution run; the remaining placements are superseded by the Round 4 plan below.

## Dependencies worth naming

- G14 (role flip) strictly after G15 and G16.
- G28 (manifests) depends on G27 (images that build); G32 partially overlaps both.
- Batch 3.1 checkpointing should precede any account whose history makes full folds slow, which in practice means before real-money launch rather than after.
- G50 (conformance corpus) before any further DSL vocabulary work, so G47's consolidation lands against a pinned grammar.
- G55 (doc deletion) after the spec is accepted, so there is one authority to point at.

## Round 4: remaining-work implementation plan (2026-07-29)

Everything above this line was executed in the 2026-07-28 run except where the roll-up's "Open, with reasons" list says otherwise. This section plans what remains: the Round 2 proposals (R1, R3 to R13; R2 shipped), the three follow-ups the run itself surfaced, and the locally buildable half of the environment-gated items. The spec's section 13 questions are reviewer decisions, not work items, and stay out of this plan.

Batches are sized for parallel subagent execution with disjoint file ownership. Waves are ordered; batches within a wave are not. Standing constraints for every batch: work in the main checkout (no worktrees, never run `git checkout`, `stash`, `commit`, or `restore`), no suppression comments, strict typing, minimal one-line comments only where code is not self-explanatory, and finish by running the owning package's test suite plus `ruff check` and pyright on touched files. Each batch appends a one-line closure note to the register's execution roll-up.

### Wave 1: independent, no shared files

**Batch 4.1: credential-deletion guard (R3). M.**
`delete_alpaca_credentials` (`services/auth/src/services/tenant_service.py:150`, servicer at `grpc/servicer.py:855`) currently deletes unconditionally. Before deleting, check the shared database for live trading sessions and funded (non-closed) ledger sleeves that reference the credentials, following the sanctioned `plan_limits` pattern for cross-service reads. If dependents exist, return failed-precondition with the dependent execution ids in the message so the client can offer stop-and-close; no cascading deletion. Tests: deletion refused with a live session, refused with a funded sleeve, allowed after close, plus tenant isolation on the checks.

**Batch 4.2: RLS-bypass audit (R7). S.**
`system_session` and `set_rls_bypass` in `libs/db` gain a structured audit log line (caller, reason argument, tenant scope if any) and a counter metric per use, so bypass frequency is graphable and an unexplained spike is visible. No new table and no migration; the log stream is the audit record at current scale. Tests assert the log and counter fire.

**Batch 4.3: minimum-notional guard (R13). M.**
In the `libs/runtime` sizing routine, skip intended orders whose notional falls below a configurable floor (default one dollar, Alpaca's minimum), count them in a session metric, and log at debug. The skip must not distort the rest of the rebalance: remaining orders keep their sizes, and a skipped sell must not strand the buys it would have funded (if the buy side no longer fits free cash after skips, scale it down the way the existing cash-fit logic does). Tests: sub-notional buy skipped, sub-notional sell skipped without breaking funding, boundary at exactly the floor, metric increments.

**Batch 4.4: hygiene bundle (R9, R11, order-id timestamp normalization). S.**
R11: add a per-environment `concurrency` group to the staging and production deploy workflows so runs queue rather than interleave. R9: document forward-only expand-and-contract as the migration convention (a short section in the contributor docs; downgrades exist for local development only and are not an operational tool), and add the convention to the migration template docstring. Timestamp hardening: normalize the signal timestamp to UTC inside the deterministic order-id derivation so equal instants in different offsets hash identically; keep the existing tests and add the mixed-offset case.

**Batch 4.5: TypeScript drift residue. M.**
Close the four recorded gaps outside the corpus mandate: the builder store omits `:benchmark` from its own metadata round-trip, editor completions still advertise retired keywords, `stoch` serializes to an unparseable form, and the comparator set accepted by the TS parser does not match the Python grammar (`cross-above` handling). Anchors: `apps/core/src/strategy/types.ts`, `apps/core/src/strategy/serializer.ts`, the builder store in `apps/web/src/store/strategy-builder.ts`, and the CodeMirror completions in `apps/web/src/components/strategy-builder/codemirror/completions.ts`. Extend the conformance corpus with a case per fix so regressions fail CI. Verify with the web test suite and `tsc`.

**Batch 4.6: shared health-probe helper. S.**
The database-connectivity readiness check is duplicated across six service mains. Move it into `llamatrade_common.health` as one helper and adopt it in all six, keeping per-service extra checks where they exist. Touches only `main.py` health wiring plus the lib; tests in `libs/common` cover the helper, and each service's existing health test keeps passing.

### Wave 2: money path and trading (after wave 1)

**Batch 4.7: account identity keyed to the broker (R1). L.**
`Account` is unique per `credentials_id` (`libs/db/llamatrade_db/models/ledger.py:119`), so re-linking credentials creates a second book that double-counts on genesis backfill. Fix: store the broker's account id on `Account` at genesis (the account snapshot already carries it), add a unique constraint per `(tenant_id, alpaca_account_id)` in migration 037, and make the get-or-create path in portfolio's onboarding resolve through the broker account id first, so a re-link reuses the existing book and attaches the new credentials to it. Existing data: a startup sweep logs duplicate-broker-id account pairs for operator resolution; no automatic merge, because merging two event logs is exactly the kind of surgery that should not run unattended. Tests: re-link reuses the book, two genuinely different broker accounts stay separate, the duplicate sweep reports and does not mutate.

**Batch 4.8: corporate-actions detection feed (R4). M.**
The planners exist (`services/portfolio/src/ledger/corporate.py`) with no feed. Add a corporate-announcements client to `llamatrade_alpaca` (typed models, same resilience stack as the other REST clients), then a nightly leader-elected poll task in portfolio that fetches announcements for held symbols and routes them to the split, rename, and dividend planners, with `ApplyCorporateAction` remaining the operator-confirmed apply path (the feed proposes, the operator applies, until we trust the feed). This batch owns all `llamatrade_alpaca` edits in the round; no other batch touches the lib. Tests: announcement mapping, planner routing, idempotent re-poll, mock-client driven.

**Batch 4.9: symbol lifecycle, trading side (R6a). M.**
Preflight: refuse session start when any subscribed symbol is not active and tradable at the broker (the assets endpoint already exists in the lib). Operationally: when the all-symbols evaluation gate has not opened past a configurable staleness window, emit a per-tenant alert through the existing alert path and set a gauge; on detecting a delisted symbol, mark the session degraded and surface a forced-close decision to the user through the same path rather than force-closing automatically. Tests: preflight rejection, stall alert fires once per window, delisting marks degraded.

**Batch 4.10: symbol lifecycle, ingest side (R6b). M.**
Derive the market-data ingest universe as the union of the configured baseline (`services/market-data/src/ingest/config.py:56`) and the symbols of running live sessions, refreshed on an interval, so the shared fan-out can serve any deployed strategy. The read follows the sanctioned shared-database pattern. Tests: union and refresh logic, removal after session stop, config-only fallback when the query fails.

**Batch 4.11: rehydration lease on StartSession. M.**
Sessions started through the normal StartSession path never take the rehydration lease, so a peer replica's rehydrate pass could double-claim them (adopted sessions are protected). Take the same per-session advisory lease on the normal start path (`services/trading/src/recovery.py`, `live_session_service.py`) so both entry points hold the same guard. Test: a rehydrate pass running concurrently with a normally started session does not adopt it.

**Batch 4.12: failover chaos test (R8). M.**
A docker-gated integration test that restarts the Postgres container mid-sweep and asserts the single-writer properties hold across re-election: no duplicate drift events, no duplicate equity-curve points, trading's per-session locks re-elect cleanly. Test-only; runs in CI's docker lane next to the existing Kafka rebalance tests.

### Wave 3: larger design work (after wave 2)

**Batch 4.13: forming daily bar in live (R5). L.**
Materialize a forming daily bar from the one-minute stream inside the live bar feed and evaluate daily-resolution indicators at daily resolution, so live indicator semantics match backtest by construction (spec section 5.2). This is the most delicate item in the round: it runs alone, nothing else may touch `libs/runtime` concurrently, and it lands only with parity tests asserting that a live session replayed over a recorded day produces the backtest's indicator series for the same day.

**Batch 4.14: ledger statement renderer (R12). M.**
An operator CLI in portfolio (a script entry point over the existing projections) that renders an account's history into a readable statement: opening balances, postings grouped by day with running per-sleeve balances, and a closing cash and position summary. Output is plain text; golden-file tests pin the format. This is the explain-a-balance-to-a-user tool the spec says the ledger's audit value depends on.

**Batch 4.15: backtest worker autoscaling (R10). M.**
Give the Celery queue-depth signal a stable exported metric name, add the scaler manifest for the worker deployment in the overlays (KEDA ScaledObject if available in the cluster, otherwise an HPA on the external metric), and document the bounds. Manifest correctness is testable locally through the kustomize CI job; behavior under load is environment-gated and goes on the verification list.

### Wave 4: environment-gated preparation

These are buildable locally; their live verification needs infrastructure and stays on the roll-up's open list until performed.

**Batch 4.16: KMS cipher implementation. M.** Implement the GCP KMS cipher behind the existing config-selected seam (typed stub today), with unit tests against a mocked KMS client covering wrap, unwrap, key-rotation shape, and error mapping. Live verification needs cloud credentials.

**Batch 4.17: External Secrets manifests and e2e build gate. S.** Write the External Secrets Operator manifests mapping Secret Manager entries to the cluster secrets the deployments reference, validated by the kustomize CI job; promote the e2e job to a required build gate in CI config.

**Batch 4.18: OAUTHBEARER expiry test. S.** A docker-gated test against a SASL-configured broker asserting the token-refresh path survives expiry mid-consumption. Joins the docker lane.

**Batch 4.19: runtime-loop parity soak harness (G54). M.** Build the comparison harness and runbook for the `TRADING_USE_RUNTIME_LOOP` flip: capture order intents from both loops over a paper soak window, diff them, and define the flip criterion as zero divergence. The soak itself and the flag flip remain a manual gate on the live mesh.

### Final batch: verification sweep

After the last wave: full test suites for every touched package, `ruff check` across services and libs, pyright strict repo-wide, zero suppressions, and the register roll-up updated with closures and any new findings. Anything discovered mid-round lands in the register first and is triaged rather than silently absorbed.

### Round 4 dependencies

- Batch 4.8 owns every `llamatrade_alpaca` edit; 4.9 consumes the existing assets endpoint only.
- Batch 4.13 has exclusive ownership of `libs/runtime` and must follow 4.3.
- Migration 037 belongs to 4.7; no other Round 4 batch adds a migration.
- 4.11 and 4.6 both touch trading's startup surface; 4.6 stays inside health wiring, 4.11 inside session start, and they run in different waves regardless.
- 4.15's manifest work assumes the kustomize CI job from batch 1.4, which is in place.
