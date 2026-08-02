# Deep review, 2026-07-29: findings and solution options

| | |
|---|---|
| **Scope** | Six-angle read-only review of the backend after the Wave 5 fixes: scalability and performance, resilience and failure modes, data integrity and money correctness, code structure and cleanliness, functional correctness, security and tenancy. |
| **Method** | One reviewer per angle, each deduplicated against `production-readiness-gaps.md` (through Round 4) and the Wave 5 fixes, each required to verify every claim by reading code and to mark inference as suspected. The coordinator independently re-verified every critical and high finding against the working tree before recording it. |
| **Status** | Findings only. Nothing here is executed. Each item carries options and a recommendation for a decision. |

## The one theme

The core is sound and the seams are not. Every angle independently reported the same shape: the hard part is correct (the ledger arithmetic balances and folds purely, the identity matrix pins algorithms correctly, the write path is partitioned and idempotent, live and backtest share one engine), and the defects sit at the boundaries around it, most often as a fix that shipped one half. Revocation is written but checked in one of nine services. The projection checkpoint exists but the fill path still folds from genesis. Deterministic event ids cover every writer except the fund RPCs. The invariant check runs on one of the eight event families that can violate it. Service tokens carry a principal that nothing verifies. The health endpoints for liveness and readiness both exist but every probe points at the wrong one.

Two consequences of that shape matter for how to read the list. First, most items are small and local, because half of each was already built. Second, the test suites are green through all of it, because the seams are exactly what unit tests with mocks and compose-based integration do not exercise; several findings were invisible precisely because a test asserted a contract the production transport does not have.

## Reading order

Findings are grouped by cross-angle severity rather than by review, so the ranking is across the whole system. Within each item: the angle tag, the evidence as a code fact, the failure, lettered options with effort (S under a day, M one to three days, L week-scale), and a recommendation. Angle tags: SCALE, RESIL, DATA, STRUCT, FUNC, SEC.

---

## Tier 0: the deployment has never run the real mesh

Four findings converge on one conclusion that outranks everything else: the Kubernetes deployment path has never run the actual service mesh end to end. Each is independently a blocker, and together they explain why every suite is green while the deployed system could not serve a request. These are the first things to fix and the first things to prove with a real staging boot, not a compose boot.

### 1. The trading and notification Connect services cannot resolve a single endpoint (STRUCT, CRITICAL)

The generated Connect app binds endpoints by snake_case attribute (`trading_connect.py` dispatches to `svc.start_session`), but both servicers define PascalCase methods (`services/trading/src/grpc/servicer.py:161` `async def StartSession`, 15 of them; notification 9) and use `await context.abort(...)` (33 calls in trading, 12 in notification) against a Connect `RequestContext` that has no `abort`. Executed against the real library, `TradingServicer` raises `AttributeError: no attribute 'start_session'`. The seven other servicers use snake_case and `raise ConnectError` and resolve correctly. The 723 green trading tests hide it because five hand-rolled `MockServicerContext` fakes implement the nonexistent `abort` and call the PascalCase methods directly; the only over-the-wire e2e is gated on paper keys and market hours. This is the state at HEAD, not new drift.

- **(A, recommended)** Rename all 24 methods to snake_case, replace every `context.abort` with `raise ConnectError(Code.X, ...)`, delete the abort helpers and the five mock-context copies, and add one conformance test that instantiates every `*ASGIApplication` with its real servicer and asserts the endpoint map resolves. **M.** The test is ~30 lines and is the only thing that prevents recurrence after the next proto regeneration.
- **(B)** Rewrite without the conformance test. **M.** Same effort minus the guard; the drift comes back.
- **(C)** Do nothing. Not defensible; the money path's RPC surface is non-functional.

### 2. Every liveness probe points at the dependency-aware `/health`, so a Postgres blip restarts the whole mesh (RESIL, CRITICAL)

All nine deployments set `livenessProbe.httpGet.path: /health` (`trading/deployment.yaml:93`, and the rest), which returns 503 whenever any critical check fails (`health.py:244`); six services register `database` as critical. The always-200 `/health/live` exists and is referenced by no manifest. No `timeoutSeconds`/`failureThreshold` is set, so kubelet defaults (1s, 3 failures) apply against a 5s check budget. A 40-second Cloud SQL failover returns 503 from six services and the kubelet kills every pod of every service at once; trading restarts crash-loop because `verify_rls_enforcement` re-raises while Postgres is still down.

- **(A, recommended)** Point liveness at `/health/live` and readiness at `/health/ready`, and set `timeoutSeconds: 5`, `failureThreshold: 3`. **S.** The endpoints already exist; this is the intended wiring.
- **(B)** (A) plus a real per-process liveness signal (event-loop responsiveness or a task watchdog) so liveness reflects the process, not its dependencies. **M.**
- **(C)** Do nothing. Only defensible if a dependency outage restarting the mesh is acceptable.

### 3. `check_kafka` cannot succeed in staging or production and burns its full timeout (RESIL, CRITICAL)

`health.py:406` builds `AIOKafkaProducer(bootstrap_servers=...)` with no `security_protocol` and no token provider, while the cluster runs `SASL_SSL` (`configmap.yaml:45`). Registered critical-adjacent by portfolio, trading, and market-data at `timeout=5.0`. In-cluster it attempts a plaintext handshake against a TLS/SASL listener, can never report healthy, and (suspected, not measured) consumes near its 5s budget per probe. With finding 2's wiring, that alone would restart-loop those three services from the first probe.

- **(A, recommended)** Have the check answer from the already-connected shared transport (is the producer/consumer live) rather than opening a new probe connection, and lower the timeout. **S.** Removes a per-probe broker connection per service entirely.
- **(B)** Give `check_kafka` the transport's security kwargs (factor `_security_kwargs` into a shared helper). **S.** Fixes the handshake, keeps the per-probe connection.
- **(C)** Remove the Kafka health check. **S.** A permanently red non-critical check trains operators to ignore the payload, so removal beats leaving it broken.

### 4. Auth cannot start: no RS256 keypair exists in any environment (SEC/STRUCT, CRITICAL; carried from Wave 5)

`services/auth/src/session.py:29` evaluates `user_token_signing_key()` at import, which raises in production/staging without `AUTH_JWT_PRIVATE_KEY`/`AUTH_JWT_PUBLIC_KEY`; the base ConfigMap sets `ENVIRONMENT: production`. The Wave 5 secrets work added the `auth-jwt-keys` mount and the Secret Manager containers, but the key material does not exist and no code path generates it.

- **(A, recommended)** Generate the RS256 keypair, load it into Secret Manager, and document the step in the deploy runbook as a hard precondition; boot auth in staging to confirm. **S.** Operational, not code.
- **(B)** (A) plus a first-boot generator in a controlled admin path. **M.** Convenient, adds a key-management surface.
- **(C)** Do nothing. Auth cannot start; not defensible.

**Tier 0 recommendation.** Fix 1 through 4, then boot the full mesh in staging from the manifests (not compose) and run the e2e suite against it before any beta tester touches it. The convergence of these four is the strongest evidence in the review that green tests are not currently evidence of a working deployment.

---

## Tier 1: money-path correctness (unconditional or high-probability)

These change what the ledger records or what reaches the broker, and they fire on ordinary use rather than only under a race.

### 5. A sell of shares held in another sleeve is always quarantined, then freezes the book (DATA, CRITICAL)

Genesis backfill seeds pre-existing broker holdings into Unmanaged (`backfill.py:64`); an order with no session sleeve attributes to Manual (`attribution.py:79`); FIFO enrichment reads `open_lots` scoped to the target sleeve (`fill_ingestion.py:210`). A user who connects an account holding 100 AAPL and sells it through the platform books to Manual, finds no lots, quarantines the fill and acks it, so the proceeds and the exit are never recorded; the next reconciliation sees ledger 100 versus broker 0 and freezes every sleeve holding AAPL. Risk never blocks it (sells are not cash-checked). Untested.

- **(A)** Position-aware sell attribution: resolve the sell's sleeve from the lot book, splitting across sleeves when needed. **M.** The correct fix; changes the "attribution fixed at origination" rule and needs a multi-sleeve fill payload.
- **(B, recommended now)** Route an unattributed order whose symbol has no Manual lots to Unmanaged, and reject at risk-check time a sell the target sleeve cannot cover. **S.** Turns a certain silent quarantine into a pre-trade rejection, matching the fail-closed posture elsewhere.
- **(C)** Make quarantine non-terminal (hold in a pending table for operator assignment). **S.** Stops the freeze cascade, leaves the mis-attribution.

Recommendation: B now, A before real money.

### 6. Fund RPCs are neither idempotent nor serialized (DATA, HIGH)

The ledger writer defaults `event_id = event_id or uuid4()` (`writer.py:62`) and `FundService` passes none; the proto requests carry no idempotency key; free cash is read and spent in separate statements with no lock (`fund_service.py:146`). A start whose `allocate_capital` response is lost re-allocates on the user's second click (the guard only checks `sleeve_id is not None`), double-funding the sleeve while `allocated_capital` disagrees. Two concurrent allocates each pass the free-cash check under READ COMMITTED and drive Unallocated negative. Untested for duplicates or concurrency.

- **(A+B, recommended)** Add a client `request_id` to the four fund requests and derive `event_id = sha256(account:op:request_id)` (the pattern every other writer already uses), and take a transaction-level advisory lock on `account_id` for the operation. **S each, independent.** A fixes the retry, B fixes the race.
- **(C)** Post-append `check_sleeve_invariants` that aborts on negative cash. **S.** Catches the race only, not the retry.

### 7. The incremental projection can skip a committed event permanently (DATA, CRITICAL; suspected under concurrency, mechanism verified)

`sequence` is an autoincrement identity column assigned at INSERT (`ledger.py:223`), so commit order is not sequence order; the incremental read filters `sequence > after_sequence` (`writer.py:113`) against a forward-only checkpoint. A fill that takes sequence 500 and holds its transaction open across the full-history freeze check can commit after an `allocate` that took 501 and committed first; a reconciliation pass in between checkpoints at 501, and event 500 is never folded again, in-process or after restart. The gap then launders into a double count: reconciliation reports the missing shares as `MISSING_IN_LEDGER` and drift adoption re-books them into Unmanaged. This falsifies the checkpoint's stated replay-equivalence property.

- **(A, recommended now)** Do not checkpoint to the head; advance only past events older than a safety window (`created_at < now() - 60s`) and re-fold the recent tail each pass, with `idle_in_transaction_session_timeout` enforcing the precondition. **S.** Two-line change, keeps the O(delta) win.
- **(B)** Serialize appends per account with a transaction-level advisory lock in `LedgerWriter.append`, making sequence order equal commit order (also fixes 6 and the close race in 13). **M.** Strongest, adds a lock to the hot path.
- **(C)** Record `xmin` per row and advance only past `pg_snapshot_xmin`. **M.** Exactly correct, heavier than the rest of the codebase.

Recommendation: A now, B when per-account append volume justifies it.

### 8. `(adx …)` is permanently NaN, and the history window understates several indicators (FUNC, CRITICAL)

The retained history window is `max_lookback + 10` (`window.py:41,81`), but ADX is only defined at `2*period` bars (28 for the default 14) while its declared lookback is `period + 1`; history is trimmed to 25 before ADX is ever defined. A probe recorded 786 of 786 evaluations degraded: the strategy holds its else-branch for the entire run regardless of what ADX does. Broken for any ADX period ≥ 12. The same table understates macd signal, stochastic, keltner, and momentum warm-ups (a shorter wrong-branch window), and `obv`/`vwap` are cumulative with no lookback so their value changes with unrelated indicators in the same strategy. The TA-Lib golden suite tests the raw functions over 250 bars and cannot see any of it.

- **(A, recommended)** Derive `required_bars` from each indicator's true first-defined index (`2p` adx, `slow+signal-1` macd, `k+smooth+d-2` stoch, `p+1` keltner/momentum) and add a generated test asserting `first_non_nan_index + 1 <= required_bars` for every indicator and parameter set. **M.** Fixes both consequences and pins the class.
- **(B)** Mark `obv`/`vwap` as unbounded reads so they get the max window. **S.** Needed regardless; only half.
- **(C)** Raise the window buffer. **S.** Papers over the table; ADX(50) stays broken.

### 9. Order quantities reach the broker as raw 14-decimal float strings (FUNC, HIGH)

DRIFT sizing computes `delta_value / price` and the quantity is serialized verbatim (`runner.py:825`, `alpaca/clients/trading.py:154`); the one `quantize` in trading is a limit price. Alpaca's fractional API accepts at most 9 decimal places and non-fractionable symbols reject any fraction; the simulator fills these happily, so the backtest predicts fills the broker declines, and the divergence appears only live.

- **(A, recommended)** Quantize at the sizer boundary (9dp fractional, whole shares for non-fractionable), re-check the notional floor after rounding, and use the same rounded quantity in the sim. **S/M.** Keeps live and backtest identical.
- **(B)** Quantize only in `OrderExecutor` before submit. **S.** Fixes live, widens the sim/live gap.
- **(C)** Cache `fractionable` per asset and fall back to whole shares. **M.** Complete, needs an asset-metadata cache.

### 10. DRIFT sizing emits buys it cannot fund (FUNC, HIGH)

The drift band is applied per symbol (`sizing.py:236`) and `size_orders` never sees free cash. A suppressed sell (inside the band) and an emitted buy (outside it) no longer net to zero; the backtest silently trims the buy (mis-reporting the achieved weight) while live sends an unfunded order Alpaca rejects. The recorded gap covered only BINARY mode; this is the DRIFT path.

- **(A, recommended)** Pass free cash into `size_orders` and fit the buy side to cash plus realized sell proceeds after the band. **M.** One signature change, makes sizing provably affordable in both modes, also fixes the notional-floor shortfall heuristic.
- **(B)** Apply the band to the portfolio-level net rather than per symbol. **M.** Keeps the funding identity, changes churn behavior.
- **(C)** Reject unfunded orders in the risk layer only. **S.** Backtest keeps predicting fills live refuses.

### 11. "Allocate to nothing" is inexpressible; an empty branch levers the rest to 100% (FUNC, CRITICAL as a silent semantics trap)

`_evaluate_children` drops empty contributions and renormalizes to 100 (`compiled.py:317`), and a wholly empty allocation returns before sizing (`session.py:138`). A 60% SPY strategy with a conditional 40% hedge becomes 100% SPY the moment the hedge switches off; an else-less `if` that evaluates empty never emits the liquidating close. No shipped template hits it (none is else-less), so it is a user-authored-strategy trap, and it is directional and silent.

- **(A)** Introduce explicit residual cash: an empty sibling keeps its declared share unallocated, and `session.evaluate` distinguishes "no history" from "target is nothing" so a real liquidation sizes. **M/L.** Correct, touches composition, sizing, and the sleeve-equity contract.
- **(B, recommended now)** Validator rejects an `if` with no `else` and any block that can evaluate empty, forcing the explicit cash-proxy idiom the templates already use. **S.** Ships today, narrows the language.
- **(C)** Document only. Not recommended; the failure is silent.

Recommendation: B now, A as the model fix; pairs with finding 20.

---

## Tier 2: resilience and money-path durability

Correct on the happy path, wrong when a dependency misbehaves.

### 12. The Alpaca trade stream gives up permanently after ~5 minutes and the runner trades blind (RESIL, CRITICAL)

`_reconnect` returns False after 10 attempts and sets `_running = False` (`streaming/base.py:173`); `stream()` breaks and the async generator returns normally (`trading_stream.py:135`), so the runner's `async for` ends with no exception and the task is never restarted (created once at `runner.py:485`). A six-minute trade-updates outage permanently loses the fill feed while the bar loop keeps submitting orders; no `LedgerFill` or reservation-release is published for the session's life, so reserved cash grows monotonically and the ledger diverges until reconciliation adopts the positions.

- **(A, recommended)** Supervise `_trade_stream_loop` with restart-and-backoff that reconstructs the client (resetting the attempt counter) and treats generator exhaustion as a crash, paired with an alert. **S.**
- **(B)** Make `stream()` raise `StreamExhaustedError` and have the runner mark the session degraded via the existing marker. **M.** Touches every `stream()` consumer including the ingest supervisor, which already hand-rolls a restart.
- **(C)** Both, plus per-session labels on `trade_stream_connected`. **M.**

### 13. A dead runner is never rehydrated because the guard tests presence, not liveness (RESIL, HIGH)

The market-data stream gives up identically, so the bar loop ends and the runner exits with `_running = False`; the rehydrate guard skips on `get_runner(...) is not None` (`recovery.py:441`) while `active_runners` (which filters on `running`) is used only for the stop branch. The session row stays RUNNING, the lease stays held so no peer claims it, and the pass skips the session forever. The user sees a running strategy that has silently stopped trading.

- **(A, recommended)** Change the guard to liveness (`get_runner(id) is not None and r.running`) and drop a non-running runner from the registry before re-claiming. **S.** Covered by existing rehydration tests.
- **(B)** Add a done-callback in `start_runner` that logs, evicts, and releases the lease so a dead runner is reclaimed within one tick. **M.** Introduces callback/stop reentrancy.
- **(C)** Both, plus set the row to ERROR on an unrequested exit. **M.**

### 14. No deadline on any inter-service Connect RPC (RESIL, HIGH)

No caller sets `timeout_ms`; `channel_ready()` is unbounded and `wait_for_ready`'s argument is ignored (`clients/base.py:105`). A wedged portfolio pod makes trading's `get_sleeve` on the order path never return, so the bar loop stops silently with `_running` still True and no stall detection (the detector only watches bar arrival).

- **(A, recommended)** Default `timeout_ms` per client wrapper (seconds for reads, longer for fund mutations, `None` for `stream_bars`) and fix `wait_for_ready`; deadline the read paths now and leave fund mutations unbounded until they carry idempotency keys (finding 6). **S.**
- **(B)** Per-call deadlines threaded from an inbound request budget. **M.**

### 15. Ledger publishing has no outbox; the compensating drain is windowed on creation time and 15 minutes wide (RESIL/DATA, HIGH)

Every emission path swallows publish failures; the only retry filters `Order.created_at >= now - 900s` (`order_executor.py:596`), and the `Order` row has no "published" marker. A 25-minute Kafka outage loses the fill and release events for anything that reached terminal state in the first ten minutes (the filter is on creation, not the terminal transition), permanently; a long-lived GTC order filling during a blip is missed the same way. The loss surfaces later as drift adoption or a sleeve freeze.

- **(A, recommended now)** Window the drain on terminal time (`filled_at`/`canceled_at`/`updated_at`) and widen it. **M.** Cheapest correctness fix; still best-effort.
- **(B, before real money)** A transactional outbox: persist the ledger payload in the same transaction as the order status write and drain it marking rows published. **L.** Removes the loss window and gives an operator a query for what is unbooked.
- **(C, complementary)** A `ledger_publish_failures_total` alert plus a startup reconciliation of unpublished terminal orders. **S.**

### 16. Portfolio's hung-consumer recovery is documented, implemented, and disarmed (RESIL, MEDIUM-HIGH)

The backlog tripwire is meant to fail the liveness probe (`fill_ingestion.py:527`) but is registered `critical=False`, which maps to DEGRADED and HTTP 200 (`health.py:244`); separately the crashed-loop health branch is unreachable because `supervise` catches and restarts every exception. A wedged partition grows unbooked fills indefinitely with no restart and no page.

- **(A, recommended)** Expose the backlog on a liveness-specific check gated on "connected but not advancing" (not raw lag), fix the probe wiring per finding 2, and add a restart counter in `supervise`. **S.**
- **(B)** Alert on `llamatrade_ledger_stream_pending` and the restart counter without K8s restarting money-path pods. **S.**

### 17. The DLQ replay tool can delete the entries it just re-parked (RESIL, MEDIUM)

`dlq_replay` republishes, then `purge()` reads `end_offsets` at purge time and deletes everything below (`transport/kafka.py:732`); the live consumer re-parks still-unrecordable fills during the run. Running it before the root cause is fixed re-quarantines the broken fills and then purges them, along with any new poison that arrived during the run. A null-valued parked record also hangs the tool forever (tail skips without advancing the count).

- **(A, recommended)** Purge by cursor: record the highest cursor read during the loop and delete only up to it. **S.**
- **(B)** Do not purge; let retention expire drained entries and report the count. **S.**
- **(C)** Replay into a separate retry topic so a re-drop is distinguishable. **M.**

### 18. Celery's Redis visibility timeout equals the backtest time limit, so a long run can execute twice (RESIL, MEDIUM)

`task_time_limit = 3600` with `acks_late` and no `visibility_timeout` set, so kombu's 3600s default matches: a task still running at the hour mark becomes visible again and a second worker starts the same backtest. Autoscaling makes a free worker likelier.

- **(A, recommended)** Set `broker_transport_options = {"visibility_timeout": TASK_TIME_LIMIT * 2}` derived from the limit. **S.**
- **(B)** Per-backtest execution lease. **M.**

---

## Tier 3: reconciliation does less than the design claims

The ledger's continuous-assertability property is not actually continuous.

### 19. Cash drift is observability only: it never freezes, alerts, or corrects (DATA, HIGH)

Cash drift sets a gauge and logs a warning above $1 and nothing else (`projector.py:266`); `_surface_drifts` handles only position drift; `RECONCILIATION_ADJUSTED` exists in the enum and is never written. A user who wires cash out directly leaves every strategy sizing against phantom free cash permanently, since no code path writes a correcting event.

- **(A, recommended now)** After N passes above a threshold, freeze the account's sleeves and dispatch a `LedgerIncident`, reusing the position-drift machinery. **M.** No cause attribution required.
- **(B, real fix)** Attribute cash drift from the Alpaca account-activities feed and emit typed events, freezing only the residue. **L.** Overlaps the Wave 2 corporate-actions work; needs the activities feed wrapped.
- **(C)** Alert on the existing threshold only. **S.** Leaves strategies trading on a known-wrong book.

### 20. The sleeve invariants are checked only after fills, on one of eight event families (DATA, HIGH)

The freeze check runs only for `ORDER_FILLED` (`fill_ingestion.py:221`) and covers only negative cash and negative position per sleeve. No fund, close, corporate-action, drift, or onboarding path checks anything, so the concurrent-allocate negative balance (finding 6) and a drift-written negative position both pass silently.

- **(A)** Move the check into `LedgerWriter.append` so every writer inherits it. **M.** Uniform, but makes every append pay a fold (finding 7's cost).
- **(B+C, recommended)** Call `check_sleeve_invariants` at each writing service's transaction boundary, refusing synchronous operations rather than freezing, and extend the check with "reserved never exceeds cash" and account-level `Σ cash ≥ 0`. **S.** A synchronous fund op should be refused; freezing is right only for the async fill path.

### 21. Drift event ids key on the drift state, so a recurring identical drift is swallowed while reporting success (DATA, HIGH)

The drift id is `sha256(account:kind:symbol:ledger_qty:broker_qty)` (`drift_policy.py:110`) with `ON CONFLICT DO NOTHING` and an unconditional "adopted" log and metric. A drift that recurs with the same quantities derives the same id, no-ops the insert, and still logs and counts as adopted, so the second occurrence is never booked and every later pass repeats the no-op. The id also interpolates `Decimal` via `str()`, so `"20"` and `"20.0"` adopt twice.

- **(B+reporting, recommended)** Quantize the quantities into the key and add the pass date, and report a distinct `deduped` action on a no-op insert instead of `adopted`. **S.** The false telemetry is what makes it silent.

### 22. Corporate-action dedup keys omit the action's date and external id (DATA, MEDIUM)

Split and rename keys are `split:symbol:ratio:sleeve` and `rename:old:new:sleeve` (`corporate.py:79`), while dividends correctly carry `pay_id`. Two 2-for-1 splits on the same symbol derive the same key, so the second is reported applied and no-ops, leaving the sleeve at half the broker quantity and freezing on the mismatch. Inexact `Decimal` ratio division also risks a scale-mismatched double-apply.

- **(A, recommended)** Put the announcement's external id into the key, exactly as dividends already do (it is in hand at `corporate_actions.py:215`). **S.**

---

## Tier 4: security and tenancy

The identity core is correct; these are omissions at specific surfaces.

### 23. Token revocation is enforced only on the auth service (SEC, HIGH)

`AuthMiddleware` skips the revocation check entirely when no Redis client is passed (`auth.py:399`), and only auth passes one; the other eight construct the middleware bare. A logged-out, password-changed, or operator-revoked access token keeps working everywhere except auth for its 30-minute life. G18's write half shipped, the enforcement half did not.

- **(A, recommended)** Build the Redis client inside `AuthMiddleware` from `REDIS_URL` when none is supplied, so the secure default does not depend on nine call sites, and add a startup assertion refusing to boot in production with revocation disabled. **S.**
- **(B)** Pass `redis_client=get_redis()` in all eight mains. **S.** Same effect, nine edits that can drift again.

### 24. Service tokens carry a principal that nothing verifies (SEC, HIGH)

`mint_service_token` sets `svc`, but the service context drops it (`auth.py:248`) and `resolve_identity` trusts the wire tenant unconditionally; six mint sites share one HS256 secret, including the agent process that runs LLM-directed code. Any single service compromise or secret leak yields a token that authenticates to every service and can set an arbitrary `tenant_id` on `LedgerService/WithdrawFunds`. G17's audience check shipped, the allowlist did not.

- **(A, recommended)** Keep `svc` on the context and have each money-path service check the caller against a short allowlist in `resolve_identity`. **S/M.**
- **(B)** Per-service secrets or RS256 keys so one leak is not platform-wide. **L.**

### 25. `SubmitOrder` accepts a caller-supplied `sleeve_id` with no ownership check (SEC, HIGH)

On the normal branch (session has an `account_id`), `attribution.py:63` returns `requested_sleeve_id` verbatim; the tenant-scoped validation runs only on the fallback branch a started session never hits, and the projection materializes unknown sleeves with `setdefault`. A user can book a fill against another tenant's sleeve id, leaving the phantom sleeve cash-negative and freezing the account.

- **(A, recommended)** Always resolve `requested_sleeve_id` through the tenant-scoped ledger lookup and reject a sleeve whose account differs from the session's; make the projection fail loud on an unknown sleeve rather than `setdefault`. **S.**
- **(B)** Reject any non-empty `sleeve_id` on the public `SubmitOrder` RPC and derive it from the session. **S.**

### 26. Unbounded work from one tenant against shared capacity (SEC, MEDIUM; several surfaces)

`CompileStrategy` runs an RLS-bypass session with no identity resolution and no input bound (`servicer.py:338`), parsing multi-megabyte DSL synchronously on the loop while flooding the bypass audit; market-data RPCs bound neither symbol count nor `limit`; a strategy may declare 50,000 symbols with only a warning above 20, which the backtest and the live ingest universe both fan out on.

- **(A, recommended)** Bound each surface: `_MAX_SEXPR_LEN` on the compile RPC plus identity resolution and dropping its DB session; cap symbols and clamp `limit` on market-data; a validator cap on symbols per strategy threaded into the existing warning. **S each.**
- **(B)** Add a per-tenant limiter on the market-data edge and the agent LLM RPCs via the shared `RateLimiter`. **M.**
- **(C)** Accept while the beta is closed; gate on the external-users milestone. **S.**

### 27. Internal exception text is returned to clients from 25 handlers, including every ledger money RPC (SEC, MEDIUM)

`ConnectError(Code.INTERNAL, f"...: {e}")` in the ledger servicer and the backtest and market-data servicers surfaces SQLAlchemy messages carrying SQL text, bound parameters (account ids, amounts, tenant UUIDs), and internal hostnames; trading is the counterexample with a fixed string.

- **(A, recommended)** Return a fixed message and log with a correlation id the client can quote, matching trading; adopt the existing `handle_service_errors` decorator across the three services. **M.**
- **(B)** Fix only portfolio and backtest (tenant-scoped), leave market-data. **S.**

### 28. Outbound webhook dispatch has no URL validation and merges tenant-controlled headers (SEC, MEDIUM; latent until the management surface ships)

Both alert paths POST to `webhook.url` with no scheme or private-range check and `headers.update` from a stored value that can override `Content-Type`; secret and headers are plaintext columns. No RPC creates webhook rows yet, so the sink is wired and the source is not. Once management ships, a tenant can point a webhook at the metadata endpoint and use `last_status_code` as a blind SSRF oracle.

- **(A, recommended before the management surface)** Validate the URL at write and send time (https, public IP after resolution, deny link-local and RFC1918), restrict headers to an allowlist, and encrypt secret and headers through the existing cipher seam. **M.**

### 29. `backtest_results` and `oauth_pending_signups` carry tenant data with no `tenant_id`, so no RLS and the parity test is structurally blind (SEC, MEDIUM-LOW)

Both are keyed only by a parent id, and the RLS parity test derives its expected set from tables that have a `tenant_id` column, so a child-keyed table is invisible to the drift check by construction. `oauth_pending_signups` holds encrypted OAuth tokens. Application filtering is correct today, so this is a missing backstop rather than a live leak.

- **(A, recommended)** Add `tenant_id` with a backfill, which brings both RLS and the parity test along. **M.**
- **(B)** Keep the column off, add a policy joining through the parent, and extend the parity test to enumerate FK-reachable tables. **M.**
- **(C)** Document both as asserted exemptions inside the parity test. **S.**

### 30. The copilot proposal single-use guard is an unlocked read-modify-write (SEC, LOW-MEDIUM)

`_consume_proposal` loads, checks `status == consumed`, mutates, and commits with no lock or conditional update (`agent servicer.py:692`); two concurrent confirmations of the same id both execute. Only backtests are gated today, so the impact is duplicate spend now and material when a money-moving tool is added.

- **(A)** Lock the row before read and commit in the same transaction. **S.**
- **(B, recommended)** Move proposal state to its own table with a unique `confirmation_id` and a conditional `UPDATE ... WHERE status = 'proposed'` that must affect one row. **M.**

### 31. Rate limiting, revocation, and single-use consumption all fail open on a Redis error, together (SEC, LOW)

Three Redis-backed guards each return the permissive answer on error, so a Redis outage disables brute-force protection, revocation, and OAuth handoff single-use simultaneously; the OAuth exchange routes and every non-auth mutating RPC have no limit at all, and the agent LLM RPCs have no quota.

- **(A, recommended)** Fail closed on the auth surfaces specifically, alert on the two defined-but-unalerted backend-error counters, and add a per-tenant limiter to the agent and the strategy and backtest mutations. **S/M.**

---

## Tier 5: functional-math correctness (metrics and clock)

Wrong numbers that are not money movements but that users read and trust.

### 32. `:rebalance weekly` skips every week whose Monday is a holiday (FUNC, HIGH)

Weekly requires `weekday() == 0` (`rebalance.py:48`) while monthly and the rest key on a period change. Over the 2024 NYSE calendar the clock fires 49 times in 53 weeks, missing MLK, Presidents', Memorial Day, and Labor Day weeks, so the strategy carries its allocation for a fortnight four to five times a year.

- **(A, recommended)** Make weekly a period-change test (`isocalendar()[:2]`) like the others so it fires on the first trading day of each ISO week. **S.** Makes all five frequencies consistent.

### 33. The Sortino ratio is not the Sortino ratio (FUNC, MEDIUM)

The denominator is `np.std` of the losing days about their own mean rather than downside deviation about the target, and the declared `risk_free_rate` is never used (`metrics.py:39`). A steady 15-up-5-down series returns 0.00 against a textbook 15.87; a varied-loss series inflates by 17%. The error is not even directionally consistent.

- **(A, recommended)** Replace the denominator with downside deviation about the daily risk-free rate and use excess returns, keeping `sqrt(252)`, with a golden test against a hand-computed series. **S.**

### 34. Beta and therefore alpha are inflated by `n/(n-1)` from a ddof mismatch (FUNC, MEDIUM)

`np.cov` (ddof=1) over `np.var` (ddof=0) inflates beta by `n/(n-1)` (`benchmarks.py:143`): identical-to-benchmark returns report beta 1.05 over 20 days, 1.004 over a year, and alpha inherits it, so a market-neutral short backtest shows spurious negative alpha. Alpha also annualizes arithmetically while the `annual_return` beside it is geometric.

- **(A, recommended)** Use `np.var(..., ddof=1)` or one `np.cov` call, with a test pinning beta at 1.0 for an identical series; decide whether alpha should annualize geometrically to match. **S.**

### 35. `trailing_return` is off by one bar and disagrees with the `momentum` indicator (FUNC, MEDIUM)

`bars[-lookback]` is `lookback - 1` bars back (`statistics.py:10`), so `(return SYM 10)`, momentum weighting, and momentum filtering all measure nine bars while `(momentum SYM 10)` in a condition measures ten. On a 10%-per-bar series the two disagree by 23 percentage points.

- **(A, recommended)** Index `bars[-(lookback + 1)]`, require `len >= lookback + 1`, bump the window defaults, and add a parity test asserting `trailing_return` and `_momentum` agree. **S.**

### 36. Declared weights outside a `specified` block are silently renormalized (FUNC, MEDIUM)

The sum-to-100 validator rule fires only inside `weight :method specified` (`validator.py:302`), while `_scaled_merge` always renormalizes, so a root-level `SPY 60 / BND 30` evaluates to 66.7/33.3 (the intended 10% cash vanishes) and an obvious `60 / 60` typo becomes 50/50.

- **(A, recommended)** Hoist the sum-to-100 check into a shared helper applied wherever siblings carry declared weights. **S.** Pairs with findings 11 and 20's residual-cash direction.

### 37. The dataset content hash does not cover what changes the bars (FUNC, MEDIUM)

The hash covers symbols, timeframe, range, and adjustment (`spec.py:47`), but `adjustment` is always the `"raw"` default while market-data serves split-adjusted daily, the currently-forming partial bar can be snapshotted as a close, and the corporate-action self-heal rewrites stored bars with no vintage in the key. A run ended intraday caches a partial bar forever under a key later requests reuse; a pre-split cached dataset replays pre-split prices with post-split share counts.

- **(A, recommended)** Clamp `end` to the last closed session and add a vintage component (a `data_version` bumped by the self-heal, or a coarse `fetched_on`) to the hash. **M.** Closes both holes, keeps warm-hit reuse for closed history.

---

## Tier 6: scalability and cost

These do not corrupt anything; they set the ceiling and the failure mode under load.

### 38. No connection-pool configuration reaches Kubernetes (SCALE, HIGH)

Every pod defaults to 10+20 connections (`session.py:137`) with zero `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` in the manifests; at HPA maxima that is roughly 1,770 connections against a 2-vCPU Cloud SQL instance with no pooler, before the Celery workers' per-task engines. Exhaustion refuses new connections platform-wide, taking down the money path.

- **(A, recommended)** Add pool sizes to the ConfigMap with per-service overrides budgeted against measured `max_connections` and the HPA maxima, and wire the existing connection alert into the deploy gate. **S.**
- **(B)** PgBouncer in transaction mode, exempting the connections that hold session-level advisory locks. **M.**
- **(C)** Raise the tier and set `max_connections` explicitly. **M.**

### 39. The dashboard re-folds the whole ledger per strategy and issues one market-data RPC per strategy (SCALE, HIGH)

`GetPortfolio` folds every account twice with no memoization, then `book_totals` loops per execution calling `_summary`, each of which folds the full account, RPCs market-data, and scans snapshots; `get_strategy_performance` folds three times; `list_transactions` reads every event and paginates in Python. A tenant with 20 strategies and 20k events pays about 22 full folds, 21 RPCs, and 21 scans per dashboard load on a 500m/512Mi pod.

- **(A, recommended)** Fold once per request and pass the projection into `book_totals`; batch the price fetch into one `get_prices`; filter `_sleeve_series` in SQL. **S.**
- **(B)** Route reads through the incremental projector. **M.**
- **(C)** Materialize sleeve state into rows updated by the fold. **L.**

### 40. The checkpoint has one caller; the fill path still folds full history on every fill (SCALE, HIGH)

`project_account_incremental` is called only from reconciliation; 22 sites fold from genesis, including FIFO enrichment and the invariant check on every `ORDER_FILLED`, so fill throughput per pod falls as accounts age. The G10 checkpoint fix did not reach the hot path.

- **(A, recommended)** Use the incremental projector for the invariant check and seed `open_lots` from the checkpoint. **S.** Interacts with finding 7; do them together.
- **(B)** Keep an in-process per-account fold in the consumer. **M.**

### 41. Historical-bar streaming buffers and sorts the whole dataset on market-data's event loop (SCALE, HIGH)

`StreamHistoricalBars` awaits the full multi-symbol fetch, flattens, and `sorted()`s before yielding (`servicer.py:325`), while the backtest requests up to 100,000 bars per symbol against a 512Mi pod. A large fetch can OOM the pod and its uninterruptible sort stalls the `GetSnapshots` that live order risk checks block on.

- **(A, recommended)** Stream per symbol with a cursor and merge with `heapq.merge`, so nothing larger than a page is resident and the sort disappears. **M.**
- **(B)** Cap `limit` server-side and reject over-large windows. **S.** Pushes the problem to the client.
- **(C)** Separate the batch-read path from live snapshot serving. **M.**

### 42. Kafka publishes are one synchronous round-trip per record with no batching (SCALE, HIGH)

`send_and_wait` per publish with `acks=all` and no `linger_ms`/`batch_size` caps throughput at 1/RTT, roughly 65 to 200 records per second; the minute-boundary burst for a 500-symbol universe needs several seconds against a one-second flush loop.

- **(A, recommended)** Set `linger_ms` and `batch_size`, switch to lz4/snappy, and add a `publish_many` for the paths that already have a batch (bars, DLQ replay), keeping single-record `publish` for the money path where the cursor is used. **S/M.**

### 43. bcrypt runs on the auth event loop (SCALE, HIGH)

All four hash sites call `bcrypt` directly in async handlers at cost 12 (`servicer.py:451`); one hash is 250 to 400ms of uninterruptible CPU on a 500m pod, so a login burst or the dummy-hash burn on unknown emails trips liveness probes.

- **(A, recommended)** Wrap all four in `asyncio.to_thread`, matching what the cipher seam already does, and raise the auth CPU limit to at least one core. **S.**

### 44. Miscellaneous cost items (SCALE, MEDIUM/LOW)

Every order runs two full risk checks each with its own market-data RPC, serially per rebalance (halve by passing the first result into submit and prefilling the price cache from evaluation bars); backtest workers run four CPU-bound sims in a 2-CPU limit with the dataset materialized two to three times (set `--concurrency` and drop the duplicate representation); live sessions still default to one Alpaca socket pair each (flip `TRADING_BARS_FROM_SERVICE` after a parity soak); lag sampling builds a fresh consumer every 30s and the snapshot cache has no single-flight (cache the probe consumer, add a per-symbol lock). All **S/M**.

---

## Tier 7: structure and maintainability

Not defects users see; the reason the defects above were easy to introduce and hard to catch.

### 45. Shared helpers exist but adoption stopped at one or two callers (STRUCT, HIGH; several)

The pagination block is copy-pasted ten times with a client-triggerable `ZeroDivisionError` and no upper bound while a correct `paginate` helper sits unused; credential resolution is implemented twice with the same name and swapped argument order (a swap type-checks clean and does a cross-tenant lookup); error mapping has three idioms with a live `parse_uuid` divergence; there is no shared proto time converter, so 41 open-coded conversions and four new tz-naive sites keep reappearing (backtest start/end dates shift a day in a non-UTC container).

- **(A, recommended)** One `resolve_pagination`/`pagination_response`, one `resolve_credentials` in `llamatrade_db` returning a decrypted result (keyword-only), one `handle_service_errors` plus `parse_uuid` in `llamatrade_common.connect`, and one `to_proto_timestamp`/`from_proto_timestamp` in `llamatrade_proto` rejecting naive input, with a grep or import-linter gate for each. **M total.** The credential dedup is the security-critical one and should land with the KMS cutover.

### 46. Nine `main.py` copies with three RLS postures, four of which swallow the fail-closed assert (STRUCT, HIGH)

The app-assembly block is hand-copied nine times; `agent`, `auth`, `billing`, and `portfolio` call `init_db()` (which runs `create_all` in production) inside a `try/except Exception: logger.warning("non-critical")` that swallows the `RuntimeError` `assert_rls_capable` raises, so the fail-closed RLS guarantee is inert in exactly those four; market-data and notification check neither.

- **(A)** A `create_service_app` factory in `llamatrade_common`; each main becomes a factory call plus its lifespan, the Connect mount is mandatory, and `verify_rls_enforcement()` is standard. **M.**
- **(B, recommended now)** Drop `init_db()` from service startup, let the Connect `ImportError` propagate, and add `verify_rls_enforcement()` everywhere. **S.** Closes the swallowed-assert hazard without the factory churn.

### 47. Two God modules (STRUCT, HIGH)

`StrategyRunner` is 1,716 lines fusing five independently-scheduled concerns with a 313-line `_sync_positions`, and `template_service.py` is 5,050 lines of which 4,944 are a template-content literal that makes editing product copy a code review.

- **(A, recommended for the runner: sequence)** Delete the hand-rolled loop after G54 flips (removes ~200 lines and settles the seams), then extract `FillIngestor` and `PositionReconciler`. **M after G54.**
- **(A, recommended for templates)** Move the catalog to `data/templates.json` validated at import against `TemplateData`, keep the conformance test, drop the pointless `async`. **S/M.**

### 48. Smaller structural items (STRUCT, MEDIUM/LOW)

`libs/proto` imports `llamatrade_common` undeclared (the same layer inversion G38 closed for `libs/db`; add an import-linter gate and declare it); dead public surface (`utils.py` has eight unused helpers, market-data's `error_handlers.py` is 148 lines wired to a path the Connect app never consults, market-data calls `init_telemetry` twice with the second overwriting the first's JSON logging config, two dead `USE_GRPC*` env keys); `__all__` lists that omit the symbols services actually import (`resolve_identity_connect`, the `llamatrade_db` query helpers). All **S**.

---

## Decision items carried from Waves 1 through 5

These were deferred during execution as product or design calls rather than mechanical fixes, and belong on the same docket:

- Corporate-action proposals have no durable queue; the operator applies from a log line. A proposals table plus a list RPC and a UI or webhook surface is the real path.
- Billing maps an unknown Stripe status to a sentinel that used to silently mark a subscription active and now raises in the webhook; the fallback (keep existing status versus a dedicated label) needs a decision.
- Live evaluation decides at the first complete snapshot of the day (close-so-far); aligning it to the session close is a trade-timing product change, blocked on `get_next_close` ignoring early-close days.
- Backtest cannot express sizing config (mode, drift band, notional floor) at any layer; adding it needs a proto field.
- The tail-cursor contract is one partition wide; a resuming reader sees other partitions only from their end, skipping downtime history. A per-partition cursor set is an `EventTransport` signature change.
- `SLEEVE_CLOSED` merges lots into one blended-basis lot in Unmanaged, losing acquisition order; the proper fix needs the lot book keyed by (sleeve, symbol).
- The snapshot idempotency key resolves ties as first-mark-of-day; `ON CONFLICT DO UPDATE` on a freshness predicate would restore last-wins.
- Historical post-split sells carry the wrong frozen basis in their event payloads; replay does not repair them, so they need identification and correcting entries.
- KMS envelopes carry no AAD, so a database-write attacker can swap two tenants' encrypted credentials between rows; binding needs the row identity in the seam signature.
- The `asyncio.to_thread` cipher path shares the default executor; a KMS burst under order load could saturate it. Measure before the KMS cutover.

## Suggested sequencing

1. Tier 0 (1 through 4), then a real staging boot from the manifests. Nothing else is verifiable until the mesh runs.
2. The money-path unconditional bugs (5, 6, 7, 8, 11), since they fire on ordinary use and several gate real money.
3. The durability and reconciliation tiers (12 through 22), which turn the ledger's continuous-assertability from a claim into a property.
4. Security omissions (23 through 25 first; they are the "one half shipped" trio and each is small).
5. The math and clock fixes (32 through 37) as a batch with golden tests, since none is pinned today.
6. Scalability sizing (38, 43 first) before the beta takes real load, the rest as load reveals it.
7. Structure (45, 46 first) folded into whichever change touches those files, so adoption of the shared helpers rides along rather than becoming its own project.

---

## Execution status (2026-07-29): all findings addressed

All 48 findings plus the decision docket were executed in a two-wave, multi-agent run (6 foundation agents, then 9 per-service agents), followed by a full-repo verification sweep. Verified green: all 17 Python packages (~4,900 tests) plus apps/web (189) and tsc; ruff clean; pyright 1.1.408 strict at zero errors repo-wide; no suppression comments; no register/finding/section identifiers in code; kustomize renders green on base and both overlays with zero committed Secrets; `uv lock` and `make proto-ts` regenerated.

Flagged for manual QA (implemented safe default, decision is yours): trading `AUTH_ACCEPTED_SERVICES` deny-all; billing unknown-Stripe-status keep-unchanged/create-path PAST_DUE; terraform `db_max_connections` opt-in flag; dev full-mesh RS256 wiring. Manual ops step: RS256 keypair generation and Secret Manager upload (runbook at `.docs/runbooks/jwt-key-provisioning.md`). Deferred with reason: the StrategyRunner God-class split (gated on the G54 loop flip). New cross-cutting follow-up: the one-shot tenant GUC is cleared by mid-RPC commits, so multi-commit RPCs need `bind_tenant_guc` under the RLS role flip (backtest resolved its instance as the reference pattern; the agent service's remains open). Small follow-ups: drop the shared `quantize_quantity` into the runtime sizer to restore exact backtest/live parity; thread `symbol`/`side` through the trading servicer so unowned-sleeve sell routing (not just rejection) engages on the public path; true page-bounded historical-bar streaming pending the continuous-aggregate refresh decision.
