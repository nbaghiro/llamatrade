# Changeset review, 2026-07-29: remaining items in the Waves 5+6 remediation

Six read-only reviewers (money path, shared libs, runtime/dsl eval, cross-service adoption, resilience/infra, security) went over the remediation changeset against the project rubric (DRY, engineered-enough, explicit over clever, async-first, strict typing, minimal comments, matching existing patterns) plus organization, correctness, and performance. Items are deduplicated across reviewers and ranked. The three HIGH regressions were re-verified against the working tree by execution.

## The theme of what remains

The fixes are individually sound; what remains splits into two shapes. First, two self-inflicted regressions from our own fixes (a crash and a spoofable guard) that must be corrected. Second, a set of adoptions that reached only some call sites because the fix and the file that needed it were owned by different agents, so the same principle is applied in 3 to 8 of the places it belongs. Nothing here is a redesign; all are localized.

## HIGH

1. F8 fix crashes on valid partial-param indicators. `libs/dsl/llamatrade_dsl/analysis.py:84-100`. `_calculate_required_bars` substitutes defaults only when the param tuple is empty, so `(macd SPY 12)` or `(stoch SPY 14 3)` (both accepted by the parser and validator) raise `IndexError` out of `StrategySession.__init__`, crashing compile and backtest-enqueue. Confirmed by execution. The old code guarded `if len(params) >= 3`. Fix: pad from `INDICATOR_DEFAULT_PERIODS[len(params):]` (the default tuples align positionally with `compute_indicator`), and add a partial-param case to `test_warmup_coverage.py`.

2. F31 rate-limit key is spoofable. `services/auth/src/grpc/servicer.py:92-96,433,480`, `services/auth/src/routers/oauth.py:64-68,83`. `_client_ip` takes the leftmost `X-Forwarded-For` hop, which the client controls behind a GCP L7 load balancer, so an attacker rotates the limiter key per request and the brute-force guard never engages (the fail-closed posture is correct but unreached). Fix: derive the client IP from a trusted position (the LB-appended rightmost entry), and make the per-email bucket first-class rather than a fallback.

3. F7 safety-window guarantee is not enforced. `services/portfolio/src/ledger/projector.py:73-88`. The checkpoint advances only past events older than 60s, and the docstring says a bounded `idle_in_transaction_session_timeout` makes that safe, but that GUC is set in no production config (only two code comments reference it, confirmed). Without it a transaction open longer than 60s reproduces the original skip-a-committed-event bug. Also `created_at` is transaction-start time (`func.now()`), so the "created_at rises with sequence" comment is inaccurate. Fix: set `idle_in_transaction_session_timeout` (and `transaction_timeout`) via `server_settings` in `libs/db`, correct the comment; or adopt the per-account append lock so sequence order equals commit order unconditionally.

4. F40 is half-done: the sell FIFO path still folds full history. `services/portfolio/src/tasks/fill_ingestion.py:208-210`. Only the invariant check moved to `project_account_incremental`; `read_account_events` (all events) + `open_lots` still run for every basis-less sell, so fill throughput still degrades with account age (F40's stated symptom). The checkpoint stores blended `PositionState`, not the FIFO lot book, so it cannot seed `open_lots` as intended. Fix: carry the per-(sleeve,symbol) lot book in the checkpoint (delta-fold), or an in-process per-account lot cache in the consumer; otherwise document F40 as unresolved on the FIFO path.

5. Internal exception text leaked to clients in four servicers. `services/portfolio/src/grpc/servicer.py` (10 handlers), `services/notification/src/grpc/servicer.py` (9), `services/backtest/src/grpc/servicer.py` (6), `services/market-data/src/grpc/servicer.py` (6). All raise `ConnectError(Code.INTERNAL, f"...: {e}")`, putting SQLAlchemy messages and table/column names in the client-facing string. `handle_service_errors` (the fix for exactly this) reached only strategy, billing, and agent. Fix: decorate these RPCs (portfolio passes an `on_integrity_error` hook), or at minimum drop `{e}`.

6. Client-triggerable divide-by-zero in three list RPCs. `services/trading/src/grpc/servicer.py:324,503`, `services/agent/src/grpc/servicer.py:298`. `page_size` is read from the request with no floor and used as a divisor, so `page_size=0` raises `ZeroDivisionError`. The shared `resolve_pagination` (which floors at 1) was not adopted in these three because their servicers were owned by a different agent. Fix: `resolve_pagination` + `pagination_response`.

## MEDIUM

7. Systemic: the one-shot tenant GUC is cleared by any mid-transaction commit. Root is `libs/db/llamatrade_db/session.py` `tenant_session` (uses `set_config(is_local=>true)`). Every multi-commit RPC that runs on that session loses tenant scope after its first commit; under the RLS role the follow-on queries fail closed (empty or error), and the RLS backstop drops. Confirmed instances: the agent `confirm_tool_call` (commits to release the F30 row lock, then reads), the portfolio `project_account_incremental(persist=True)` path, and previously the backtest worker (already fixed with `bind_tenant_guc` as the reference pattern). Fix: switch these paths to `bind_tenant_guc` (the after-begin hook re-applies the GUC per transaction), and prefer it in `tenant_session` itself or assert against a mid-session commit.

8. `check_kafka` `is_alive` seam adopted only in market-data. `services/portfolio/src/main.py:254`, `services/trading/src/main.py:115`. Both register the bare fallback probe, which cannot authenticate against the SASL_SSL cluster (no token provider), so the Kafka health check is permanently red on both money-path services and burns ~2s per probe. Fix: register with `is_alive=transport.is_connected` (both hold a live group transport), matching market-data.

9. `LedgerPublishFailures` alert queries a metric that does not exist. `infrastructure/k8s/base/observability/prometheusrule.yaml`. The expr uses `llamatrade_trading_ledger_publish_failures_total`; the emitted series is `llamatrade_trading_ledger_events_published_total{status="failure"}`, so the F15 page can never fire. Fix: `sum(increase(llamatrade_trading_ledger_events_published_total{status="failure"}[10m])) > 0`.

10. `ReservationState.terminal` grows unbounded and is now persisted in every checkpoint. `services/portfolio/src/ledger/projection.py:228`, `checkpoint_store.py:102`. The set only ever grows (one `.add()` per terminal order), is deep-copied into every projection, and serialized into every checkpoint row, so it is O(all orders ever) in both fold cost and row size for a book meant to run for years. The guard it powers only needs recent order ids. Fix: bound it to a recent sequence window or LRU, or drop entries once their release is folded.

11. Market-data silently truncates over-large bar requests. `services/market-data/src/grpc/servicer.py:57-63`. `_clamp_limit` returns `min(requested, 10000)` with no signal, so a backtest asking for up to 100k bars/symbol silently runs on 10k (about 25 minute-bar sessions) and mis-reports, inconsistent with the symbol-count bound in the same file which rejects. Fix: reject over-large windows with `RESOURCE_EXHAUSTED` (or paginate), do not clamp.

12. F17 DLQ purge is a heuristic delete-to-end, not cursor-bounded. `services/portfolio/src/tasks/dlq_replay.py`. `bus.purge` deletes to the current end-offset (the transport has no cursor-bounded purge), called when the queue "did not grow" between a `length()` read and the purge, so a fill re-parked in that window is deleted, and when the queue did grow the whole backlog is left and re-replayed. Fix: add a cursor-bounded purge to `EventTransport.purge` and delete only up to the highest cursor drained this run.

13. F5 Unmanaged sell-routing is inert on the public path. `services/trading/src/grpc/servicer.py:112-135`. `_resolve_order_attribution` does not thread `symbol`/`side` into the resolver, so an RPC-submitted manual order always falls back to Manual; the routing half of F5 runs only on the executor backfill path. The risk-check rejection still fires (fail-closed, acceptable), but a legitimate manual sell of an Unmanaged-only holding will not book. Fix: pass `symbol` and `order_side_to_str(side)` through the resolver.

14. Timestamps still open-coded (tz-naive risk) in several servicers. auth (~15 sites), notification (7), agent `_timestamp_to_proto:97`, trading `_to_proto_session:726,732`, and the market-data Connect client `clients/market_data.py:178-239`. Each uses `Timestamp(seconds=int(x.timestamp()))`; a naive column value books the container's local time. `to_proto_timestamp` (naive-rejecting) was the fix. Fix: route through the helper (coerce naive to UTC where columns are naive).

15. DRY: deterministic-event-id derivation duplicated four ways. `fund_service.py:27`, `drift_policy.py` (`_drift_event_id`, `_cash_freeze_event_id`), `corporate.py:27` each re-implement `UUID(bytes=sha256(key)[:16])`, plus two advisory-lock-key variants. Fix: one `deterministic_event_id(key)` helper (shared ledger-id module) and one lock-key helper.

## LOW

16. `handle_service_errors` returns `ValueError` text to the client, contradicting its "never leak internal text" docstring. `libs/common/llamatrade_common/connect.py:129,153-155`. Tighten the docstring, or map generic `ValueError` to a fixed message and reserve pass-through for an explicit validation-error type.

17. `free_cash = equity - held_value` overstates cash when a holding is absent from the tick's bars. `libs/runtime/llamatrade_runtime/session.py:143-159`. Backtest re-trims in `Portfolio.open`; live has only broker rejection. Fix: assert/log an unpriced held symbol, or derive free cash from the same marks used for equity.

18. Budget-constrained buy fit is greedy (alphabetical), not pro-rata. `libs/runtime/llamatrade_runtime/sizing.py:208-227`. Under a shortfall a 50/50 intent can become 75/25. Fix: scale buys by `budget/sum(buys)` before the floor drop.

19. `close_sleeve` and `apply_corporate_action` parse ids with raw `UUID(...)` outside the try, so a malformed id is an uncaught `ValueError` rather than `INVALID_ARGUMENT`. `services/portfolio/src/grpc/ledger_servicer.py:339`. Fix: `parse_uuid`.

20. Money-path `publish` inherits the shared producer's `linger_ms=10`, raising fill-publish latency floor from ~0 to ~10ms. `libs/events/.../transport/kafka.py`. Modest, but the design meant to keep the money path unbatched. Fix: a conscious decision on the default, or a per-call flush / second producer.

21. F9 live/backtest quantization parity not restored. `services/trading/src/runner/runner.py`. `quantize_quantity` runs only live; the shared sizer still fills unrounded, and `fractional_shares` is a global flag. Fix: move `quantize_quantity` into the shared sizer, add a per-asset fractionable cache.

22. F22 manual `ApplyCorporateAction` still collides on an empty `external_id`. `services/portfolio/src/ledger/corporate.py`. The automated path is fixed; a manual apply that omits `external_id` lets two identical splits derive the same key and no-op the second. Fix: reject an empty `external_id` on the manual RPC or derive a fallback.

23. DRY / dead code: `_ts` pure pass-through wrappers in portfolio and trading proto_mappers; the fold-once local-cache branch duplicated in both read services; billing re-exports the now-dead `init_db`; the `shortfall` accumulator is unused on the `free_cash` sizing branch. Collapse or delete each.

24. Vestigial `ValidateToken` reports `valid=True` for refresh tokens with no type gate. `services/auth/src/grpc/servicer.py:175-206`. Remove if unused, or apply the alg/type matrix.

25. Performance note (accepted tradeoff): marking `obv`/`vwap` unbounded forces the ~2000-bar retention and O(N·window) recompute for otherwise-short strategies; a future incremental cumulative update would remove it. `libs/dsl/llamatrade_dsl/window.py:46-49`.

## Verified clean (so the reader knows what held up)

F6 fund idempotency + advisory lock (hand-traced, both interleavings hold); F12 trade-stream supervisor; F13 rehydration liveness guard; F19 cash-drift freeze streak gate; F20 write-boundary invariants; F21 quantized date-keyed drift id + deduped reporting; F23 revocation default + boot guard + jti on both token types; alg-confusion pinning; F24 deny-all sentinel + portfolio allowlist matches minted names; F25 caller sleeve_id fully ignored on the public path; F26 identity + length bound before the off-thread parse; F30 real FOR UPDATE single-use guard; F43 all bcrypt off the loop; F46 startup uniform across all 9 mains (verified); the trading/notification servicer rewrite is complete; CancelledError containment; the bounded-start silent-hang fix; publish_many ordering; the worker GUC bind surviving multiple commits; snapshot last-wins; the enum-bridge fail-loud + cache_ok (verified by execution); the timestamp helper's naive rejection; F8's warm-up formulas and F35/F32/Sortino/beta numerics (all probe-verified correct); migration 039 + the RLS parity closure; no committed Secrets. Comments are terse with no historical phrasing or register/finding identifiers.

---

## Execution status (2026-07-29): all 25 items addressed

Fixed in two waves (3 foundation-lib agents, then 5 service agents) plus coordinator consolidation. Verified green: all 17 Python packages (~5,000 tests, incl. real-Postgres and real-Kafka integration), apps/web 189 + tsc; ruff clean; pyright 1.1.408 strict at zero errors repo-wide; no suppression comments; no register/finding/section identifiers in code; kustomize renders green on base and both overlays.

Notable resolutions and decisions:
- HIGH regressions both fixed: the F8 partial-param crash (default-padding) and the F31 spoofable rate-limit key (trusted-hop XFF + first-class email bucket).
- The systemic tenant-GUC finding was closed surgically: `tenant_session` stays one-shot (reverted a durable-by-default attempt that broke 32 test doubles across two services), and the three multi-commit callers (backtest, agent confirm, portfolio projector) each adopt `bind_tenant_guc`. The engine now also enforces `idle_in_transaction_session_timeout` (120s), aligned with the projector safety-window raised to 120s.
- F40 fixed with a checkpoint lot-book (FIFO enrichment is now O(delta), not O(history)); the fill-only cache alternative was rejected because splits/renames/closes appended by other processes would silently diverge it.
- The internal-text leak was closed in all four servicers via `handle_service_errors`; the ledger money RPCs were left on their existing correlation-id helper (already leak-free, and it maps domain exceptions the generic decorator cannot).
- Market-data no longer silently truncates bar requests; the ceiling was raised to match `BACKTEST_MAX_BARS_PER_SYMBOL` (backtests were silently capped at 10k before) and genuinely-oversized requests now reject.
- The `LedgerPublishFailures` alert now queries the metric that is actually emitted.

Flagged deferred (as recommended, not regressions): full backtest↔live quantization parity (needs threading `quantization` through `StrategySession`, which changes backtest determinism); a per-asset fractionable cache; the append-lock alternative for the ledger safety-window's residual sequence-vs-commit assumption; `transaction_timeout` enforcement (needs a PG17 upgrade). Two new env knobs (`DB_IDLE_IN_TRANSACTION_TIMEOUT_MS`, `TRADING_INTENT_CAPTURE_DIR` and others) should be recorded in ops config.
