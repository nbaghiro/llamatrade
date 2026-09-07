# Test Suite Round 2: honesty, depth, and real-flow coverage

Derived from the 2026-08-03 five-agent analysis of the post-remediation suite (libs hunt with three sub-audits, services hunt, integration expansion map, e2e real-flow map). Round 1 (`test-suite-remediation-plan.md`) fixed enforcement and the worst gaps; this round removes the remaining meaningless tests, closes the residual gaps, and extends integration and e2e coverage toward real flows. Every finding from the analysis maps to an action below.

## Phase R0: source defects found by the analysis (fix before the tests that pin them)

- R0.1 **BoundedRetry does not retry on Kafka; the notification consumer silently drops entries on transient failure.** `FakeTransport.consume` redelivers unacked entries per call (Redis-Streams reclaim semantics); `KafkaTransport.ack` commits `offset+1`, so a failed record followed by any later ack in the same partition is committed past and never redelivered. The `_attempts` counter increments only on same-process redelivery, which Kafka gives only after a rebalance. Fix in `llamatrade_events` (in-place retry loop for BoundedRetry mirroring RetryForever's mechanics, or explicit park-on-first-failure), update the notification consumer docstring, and add the real-broker fail-then-later-ack test that demonstrates the loss (integration build item I3).
- R0.2 **Validated trailing-stop orders dispatch as unprotected market orders.** `models.py` accepts trailing-stop with `trail_percent`; `order_type_to_str` falls back to "market", `_submit_to_alpaca` drops `trail_percent`, and `llamatrade_alpaca.submit_order` has no trail parameter. Decide: reject trailing-stop at the executor until the lib supports it (recommended, smallest), or implement trail support end to end. Pin with a test either way.
- R0.3 **DSL escape round-trip is lossy.** `parse(serialize(s))` corrupts a name containing backslash-n into a newline (unescape order in `parser.py:687`). Fix with a single-pass unescaper; add the failing round-trip test and a conformance corpus case covering the collision.
- R0.4 **Proto auth client decodes timestamps as naive local time.** `clients/auth.py` uses `datetime.fromtimestamp` without tz in six places; token `expires_at` compared against UTC is wrong by the host offset. Migrate to `from_proto_timestamp`; add real-pb2 decode tests.
- R0.5 **Closed-sleeve fill replay drives cash negative** (carried from the round-1 e2e finding): fills replayed into an already-closed sleeve are applied at ingestion; the negative-cash invariant trips only on the next CloseSleeve, deferring capital release. Fix in portfolio `fill_ingestion` (engage the reroute for post-close replays) with a regression test at the integration tier.
- R0.6 **Delete the server LoggingInterceptor** (`libs/proto` logging.py:39-104): its continuation model is wrong (logs before the handler runs), no production consumer exists. Delete with its tests; keep the client side, rebuilt on a real `AioRpcError` (hunt item H2).
- R0.7 Product gap to file, not fix here: `UpdateStrategyRequest` has no version field, so the builder's `conflictDetected` handling can never trigger (server is last-write-wins). File for the strategy-service owner.
- R0.8 Design decision to route to the owner, not silently pin: market-data ingest flush drops bars from the bus when the Kafka publish fails after a successful store write (rows durable, bus consumers never see them). Decide re-publish semantics before writing the pinning test.

## Phase R1: delete or replace meaningless tests (the hunt lists)

Work per suite from the agents' file:line registers (in the session transcripts; the top tier is repeated here). Rule: delete only where stronger coverage exists or the test is tautological; where the deletion exposes a gap, the replacement lands in the same change. Re-measure every touched gate after; floors must hold with honest tests.

- R1.1 Tier-1 misleading (claim security/correctness, cannot fail): auth `test_tenant_service.py:80,423` fake isolation tests; strategy `test_strategy_service.py:332`; agent `test_artifact_service.py:202` (replace with a real-SQL case: the predicate has no honest coverage anywhere); trading `test_live_session_service.py:253-289` self-mocked pause/resume; no-assert tests (agent `test_agent_service.py:880`, trading `test_runner.py:831`, backtest `test_validation.py:421-437`, trading `test_live_session_service.py:661`).
- R1.2 Whole-file double-testing: delete backtest `test_market_data.py`; delete trading `test_market_data_client.py` and rewrite against trading's own untested `src/clients/market_data.py`; replace alpaca `test_market_data_client_errors.py` wholesale with respx-seam tests asserting the real typed errors.
- R1.3 Legacy-branch tests: port trading market-hours tests (`test_runner.py:392,428,987-1214`) to the session-backed runner so the production gates `_live_gate`/`_evaluate_session` are covered, then delete the tests-only `strategy_fn` branch and its tests.
- R1.4 The Tier-2/3/4 lists: billing/agent/strategy/auth mock-only remnants, cross-file duplicates, constant-mirror and dataclass tautologies (proto `test_clients_auth.py:20-226`, dsl extractor tautologies, runtime `test_types.py` subset, db not-None model tests replaced with named-constraint/default.arg assertions per the db report), the fused Kafka test split (`test_kafka.py:530`), proto redaction tests rebuilt with caplog, singleton `__init__`-patch tests folded into their honest siblings.
- R1.5 Hygiene from the hunts: dead conftest fixture blocks (portfolio, market-data, backtest, trading, agent, billing, libs/db, libs/proto); consolidate the five Prometheus exposition parsers onto shared helpers; consolidate the triplicated SQLite JSONB hook and duplicated session adapters onto `_sqlite_tier`; replace hand-rolled `_FakeRedis` copies with `llamatrade_common.testing.FakeRedis` (including libs/alpaca's, acceptable dependency in tests only if alpaca's Protocol seam allows; otherwise leave alpaca's); fix misdescribing docstrings; delete dead src surface with its tests (trading `utils/cache.py`, strategy `get_template_config`) or mark intentional; make webhook retry backoff injectable so its tests stop paying real seconds.

## Phase R2: close the residual unit gaps (ranked, from the hunts)

- R2.1 Auth servicer identity branches: the analog of strategy's `test_servicer_auth.py` (set_context around servicer calls; cross-tenant NOT_FOUND guards, role-source authorization, service-token rejection).
- R2.2 Runtime money-path semantics: rejection propagation through `run()` (`rejected_signals`, observer on_reject), missing-bar-at-tick order skip, metric conditions end to end (drawdown crossing flips allocation), `:select bottom` and `:by volatility` filters, `_evaluate_if` paths, wiped-out-portfolio metrics clamp, covariance fallbacks, non-default indicator output fields.
- R2.3 Ledger read-path: `_partition_at_window`, tail-refold split, `_mismatch_dollars` (book-of-record correctness).
- R2.4 Trading recovery internals: `_load_live_specs`, `_load_orphaned_executions` (join predicate), `_rehydrate_one`, `_adopt_one`, `rehydration_loop`, `release_all_leases`, `LiveSessionService.rehydrate_runner`; risk-limit boundary equalities; ClosePosition partial/short branches.
- R2.5 Notification: pipeline poison classification and delivery failure branches; decide Slack/SMS (wire into the dispatcher or move the ~1,000 lines of tests out with the channels); backtest notification emissions asserted (categories/dedup/tenant).
- R2.6 Alpaca/proto/events/db/common residuals per the lib reports: `get_order_by_client_id` HTTP tests, unsubscribe paths, `parse_alpaca_error` edges, LedgerClient `close_sleeve` + allocate idempotency key, Kafka `ack`-no-consumer path, `close()`, corrupt-envelope raise, DSL tokenizer error tokens + parser error branches + input-size cap + `get_required_sources` parity for high/low indicators, db `get_db` rollback path, pool-exhaustion counter, query-timing helpers, `_json_serializer` Decimal precision, `check_postgres`/`check_redis`, migration-vs-model metadata diff (supersedes column-presence lists), `AuthMiddleware._bearer_token` non-Bearer acceptance pin, revocation non-numeric-iat fail-open.
- R2.7 Fake-fidelity: parametrized transport contract suite run on FakeTransport unconditionally and on KafkaTransport under the integration marker; FakeWebSocket signature pins; MockBarStream given union typing + give-up contract like MockTradeStream; proto client tests migrated from MagicMock-pb2 to real generated messages (model: `test_clients_ledger.py`); FakeRedis contract test against `redis.asyncio.Redis` (bytes-returning get, NX return shape) or the real-Redis tier below; portfolio fakes aligned to the `append() -> (event, inserted)` port; spec-check strategy/trading ledger mocks against `LedgerClient` (the ~40-line contract test replacing the skipped two-service tier).

## Phase R3: integration build list (from the expansion map; skip list per that report stands)

- I1 RLS leverage pair: table-driven policy-parity loop over all 34 `RLS_TABLES` on the migrated container (extend `test_backtest_results_rls.py`); add the `rls_maker` enforcing-role fixture to trading, auth, and notification integration conftests.
- I2 Strategy concurrent `start_execution` on real PG (double capital allocation is the failure), plus archive-guard, `reconcile_stranded_sleeves` predicate, and the tasks advisory lock.
- I3 libs/events real-broker retry semantics: BoundedRetry fail-then-later-ack (demonstrates R0.1; lands with its fix) and RetryForever transient failure through real pause/backoff/resume to a single fold.
- I4 Agent confirm-lock on real PG: `@>` match plus two concurrent `_consume_proposal` calls serialize (the double-executed-trade guard); a minimal agent integration conftest copied from notification.
- I5 Trading: `submit_order` driven into the real unique constraint; `publish_reservation` + dual-path collapse on the real broker; real-PG `rehydrate_pass`/`adopt_orphaned_executions`.
- I6 Backtest: worker SIGKILL redelivery proving `reject_on_worker_lost`/`visibility_timeout`; un-monkeypatch the reaper requeue; an RLS tier pinning `_get_strategy_version`'s RLS reliance; maintenance-queue/beat coverage in the smoke module.
- I7 Portfolio: `test_read_services_pg.py` (6 RPCs, retires the last compiled-SQL assertion); `apply_corporate_action` idempotency; `SqlOrderActivityLookup.has_recent_activity` on rows; PG-tear mid-fill drill.
- I8 Market-data: compressed-chunk upsert; `run_job` policy-firing tests (retention/compression, surfacing the retention-90d boundary); cagg unmaterialized-tail read; one serving-read with a real cache.
- I9 libs/common real-Redis tier (TTL expiry for ratelimit/revocation/consume_once, bytes-returning client) and health-probe tests; libs/db migration upgrade/downgrade round-trip + PG enum execution + CHECK-constraint rejection.
- I10 Auth `test_identity_pg.py` (duplicate-email IntegrityError, concurrent token redemption); billing webhook-dedup idempotency on SQLite (no container).
- I11 Selective infra drills: Kafka broker restart mid-consume for the portfolio fill loop (own opt-in marker); market-data `pg_terminate_backend` between flushes; trading DB-tear mid-submit.
- I12 Zero-cost hygiene: markers on trading's two older integration modules; trading + notification in `make test-integration` and ci-local `--integration`; `[integration]` extras on auth/notification CI installs; market-data integration `__init__.py`; delete trading's dead redis dependency.

## Phase R4: e2e build list (from the real-flow map; skip list per that report stands)

- E1 `StreamBars` over the live fan-out (the platform's pub-sub streaming surface; nearly free).
- E2 Dashboard-after-activity journey (performance/equity RPCs re-read after real fills; the biggest read-model gap).
- E3 Failure-path pack: insufficient-funds StartExecution, plan-limit rejection shape, invalid-DSL CreateStrategy, RunBacktest on DRAFT and bad window.
- E4 Templates journey (list, get, both create paths).
- E5 Billing plan-change/cancel/resume (lift the duplicated subscribe scaffold into `_scaffold.py` first); AddPaymentMethod as far as stripe-mock supports.
- E6 Bell flow completion (mark-all-read, unreadCount) plus `TestWebhook` against the shared listener fixture (move it to conftest).
- E7 Two-tenant concurrency (parallel journeys, no cross-talk in streams or notifications).
- E8 Builder modified-DSL round trip + version history (`ListStrategyVersions`, `change_summary`).
- E9 Trading blotter ungated reads.
- E10 Cooldown expiry (slow marker, ~2-3 min budget).
- E11 One restart-resilience test (portfolio down during fill, restart, durable consumer catches up), opt-in env gate.
- E12 The alpaca-sim realism upgrade (1-2 days, separate change): env-overridable `AlpacaUrls`, a compose alpaca-sim service (account/clock/assets/orders + fill-emitting WS), one journey exercising the real runner loop and retiring the fill-injection seam for it. Schedule after E1-E11.

## Source defects found while building the R4 journeys

These were not in the original analysis; each was found by a test written from the
build list above and is fixed in the same change.

- R0.9 **`ListPositions` and `GetPosition` returned INTERNAL for a bad session id.** Both parsed `session_id` unconditionally and had no `ValueError` arm, so an unset or malformed field surfaced as an opaque 500 while the sibling handlers (`ListOrders`, `ClosePosition`) already mapped it to `invalid_argument`. Fixed in the trading servicer; pinned by E9. These reads only ran under the permanently-skipped `live_alpaca` gate, which is why nothing caught it.
- R0.10 **Every billing subscription mutation returned a 500.** `CreateSubscription`, `UpdateSubscription`, `CancelSubscription` and `ResumeSubscription` committed and then refreshed only the `plan` relationship. The write expires the rest of the row, so `subscription_to_proto`'s first read of `created_at` attempted IO outside the greenlet and raised `MissingGreenlet`; on the create path `plan` itself was also unloaded. Both loads are now done in one `_commit_and_reload` helper. The existing e2e test had a `try/except MeshError` that fell back to the checkout path, which is what hid this: the fallback is removed and the test now requires the subscribe to succeed.

## Round 3: gaps found by a third pass (2026-08-04)

The first two rounds audited the backend only, which left one whole tier unexamined.

- G1 **Nine of fourteen `@llamatrade/core` stores had no tests** (~2,022 lines: portfolio, dashboard, billing, activity, funding, deploy, auth, broker, trading). Both web and mobile depend on this package, and the frontend deposit regression fixed earlier this session (a missing `requestId` after the server added `_require_request_id`) shipped precisely because nothing covered it. Closed: 94 new tests across the nine stores, frontend suite 202 to 328.
- G2 **The ledger writer's re-election loop had no executed coverage.** `ledger_writer_loop` carried `# pragma: no cover` deferring to the failover suite, but that suite covers `acquire_ledger_writer_lease`, not the election around it, and the only tests parsed the module's own source with `ast`. Closed: `test_writer_election.py` drives acquire, lead, lose-lease, stop-sweeps, re-elect and shutdown with fake sweeps; the pragma is gone and the module is at 100%. The one genuinely source-level assertion (that `main.py` starts the election and never a sweep directly) is kept.
- G3 **The copilot's tool layer was the weakest backend surface.** `backtest_tools` 51%, `portfolio_tools` 66%, `validation_tools` reaching only its import-error fallback. Closed: read-tool suites for both, plus `validate_dsl` driven through the real `llamatrade_dsl`. backtest_tools 96%, portfolio_tools 100%, agent 81 to 85%.
- G4 **Model/migration drift on `strategy_executions`.** The migration creates `started_at`/`stopped_at` as `timestamptz`; the model declared a bare `Mapped[datetime]`, which maps to a naive `DateTime`. Production is unaffected because the migration wins, but any schema built from `Base.metadata` (the integration tier) got naive columns, and `to_proto_timestamp` then rejects the value it reads back. Fixed in the model. This is the drift the R2.6 migration-vs-model diff item is meant to catch systematically.
- G5 Compiled-SQL assertions replaced with executed ones: the agent confirm-lock test (superseded by `test_confirm_lock_pg.py`) is deleted, and the `_sleeve_series` window assertion is replaced by a real-PG test with snapshots straddling the window. Three remain and are lower value: `trading/test_bracket_orders.py`, `portfolio/test_projector_checkpoint.py`, `backtest/test_queue_metrics.py`.
- G6 Weak assertions strengthened, including three of our own in `test_read_services_pg.py` that asserted only `resp is not None`.
- G7 The `integration` marker was unregistered in agent and strategy, so `-m "not integration"` filtering was unreliable in exactly the two packages that gained Docker-dependent tests. Registered.
- G8 **The orphan-adoption sweep never gave up.** Trading re-attempted every funded RUNNING execution on each tick, so an execution that can never be adopted (a lapsed subscription, revoked credentials) was retried forever, at the cost of a full preflight each time. Locally 92 such executions accumulated across e2e runs and produced 156 failed adoptions every three minutes. Fixed: `ADOPT_MAX_ATTEMPTS` (default 5, env-overridable) abandons an execution after repeated failures, logs it as needing attention, and counts it on `llamatrade_trading_adoptions_abandoned_total`; a successful adoption clears the counter so a transient outage does not accumulate toward the threshold. Give-up is per execution, not a breaker over the sweep. The e2e fixtures also stop their executions now. Note the sweep is what keeps a genuinely orphaned execution recoverable, so abandoning one leaves it funded and RUNNING with no session: the metric and the error log are the operator's signal, and there is no automatic re-arm yet.

Still open from this pass: trading `recovery.py` (77%) needs the real-Postgres tier tracked as I5 rather than more mocks; auth `oauth.py` (71%) is largely the provider-callback path documented as out of e2e reach; `apps/mobile` has no tests at all.

## Status

Done: R0 (plus R0.9/R0.10 above), R1, R2, I1-I4, I7, E1, E3, E4, E5, E6, E7, E8, E9, E10, E11, and E2 (`test_dashboard_after_activity.py`).

Outstanding: I5, I6, I8-I12 (integration depth), R2 residuals, and E12 (the alpaca-sim realism upgrade), which the build list already schedules as its own 1-2 day change.

New opt-in gates: `E2E_SLOW=1` for the cooldown-expiry leg (~70s) and `E2E_RESTART=1` for the restart-resilience leg, which stops and starts the portfolio container.

## Sequencing

R0 first (source fixes unblock their pinning tests; R0.1 pairs with I3, R0.5 with its portfolio regression test). R1 and R2 parallelize by suite ownership, same-change rule: a deletion that exposes a gap lands with its replacement. R3 and R4 follow, R4 last since journeys run against corrected services. Every phase ends with full ci-local plus a green remote run; gates re-measured wherever padding was deleted.
