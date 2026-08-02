# Notification service: implementation and integration plan

Status: approved direction, 2026-07-31. Decisions locked interactively; codebase facts verified against the tree as of this date (alembic head `039_backtest_result_tenant_id`, RLS parity at 34 tables).

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Event transport | 1A: new `lt.notifications` Kafka topic; producers publish typed proto events fire-and-forget; the notification service is the sole durable consumer |
| 2 | Existing dispatchers | 2A: trading `AlertService` and portfolio `LedgerAlertDispatcher` become thin publishers; all delivery consolidates into the notification service; delivery halves deleted |
| 3 | Persistence and price alerts | 3B: durable in-app rows for every notification, and the user-defined price-alert evaluation engine ships in this plan |
| 4 | Channels v1 | 4A: in-app, webhook, email (SMTP via aiosmtplib). SMS and Slack adapters stay unwired; push waits for mobile |
| 5 | Recipients | 5A: tenant-scoped; `user_id` threaded only where it already exists (auth, backtest `created_by`, agent). No new `created_by` columns |
| 6 | Auth email flows | 6A: email verification and password reset built as the final phase, descopable independently |
| 7 | Frontend | 7A: bell + notification center, per-category channel preferences, webhook management UI (new CRUD RPCs), price-alert management UI |

## Current state (what this plan builds on)

- `services/notification` is a stub: 9 RPCs backed by in-process dicts (`src/grpc/servicer.py:33-35`), never called by anything. Channel adapters exist: webhook/SMS/Slack make real HTTP calls, email is a no-op returning True (`channels/email.py:23-30`).
- The DB layer already exists and is RLS-registered: `alerts`, `notifications`, `notification_channels`, `webhooks` (`libs/db/llamatrade_db/models/notification.py`, `rls.py:97-101`). No service writes the first three; `webhooks` is read by two parallel dispatchers and written by nothing (no CRUD RPC exists anywhere).
- Trading `AlertService` (`services/trading/src/services/alert_service.py`): 21 alert types, 33 call sites, webhook-only, inline and sequential on money-path tasks. Signs `json.dumps(payload, sort_keys=True)` but transmits httpx's own serialization (`:774` vs `:868`), so signatures never verify. Retries 4xx. `failure_count` is written and never read. The HTTP client is never closed.
- Portfolio `LedgerAlertDispatcher` (`services/portfolio/src/alerts.py`): signs the exact posted bytes (correct), no retries, no delivery tracking. Wires 2 of its 3 incident kinds; `dlq_backlog` has no production dispatch site.
- The events lib has everything a new durable channel needs: `Channel` declaration (`channels.py:46-59`), `StreamConsumer` with dedupe/retry/DLQ/lag (`consumer.py:68-206`), `derive_event_id` (`idempotency.py:16-23`), `FakeTransport` for tests. `events.proto:60-61` reserves EventType 50+ for notification.
- Emission-point sweep (full table in the review record): the highest-value silent events are billing `invoice.payment_failed` (account goes PAST_DUE, live trading then refuses preflight with no warning), `customer.subscription.trial_will_end` (not even in the handled set), backtest terminal states (only an ephemeral progress stream), corporate-action proposals (log line only), strategy funding failure and deferred sleeve release (silent trapped capital), and every auth event (the service sends no email of any kind).
- Frontend: generated clients wired (`apps/core/src/net/clients.ts:117`) and unused; Settings has a placeholder notifications tab.

## Target architecture

Producers publish a `NotificationEvent` onto `lt.notifications`, keyed by `tenant_id` so each tenant's notifications are ordered. The notification service runs one durable consumer group (`notification-delivery`): decode, match against user-defined event-driven alerts, resolve preferences, persist the in-app row (the durable floor, commit before ack), then deliver to external channels with per-delivery tracking. A second, leader-elected loop evaluates market-driven price alerts against the existing bars topic. The servicer serves the persisted rows over the existing proto RPCs plus new webhook CRUD and preference RPCs.

Rendering lives in the service, not in producers: producers send a category plus machine-readable fields; templates per (category, channel) produce the title, body, email subject, and webhook payload. This keeps nine services free of copy and lets template changes ship without touching producers.

Cross-tenant infrastructure events (poison entries, DLQ depth, consumer lag, writer lease loss, reconciliation staleness) are not user notifications. They stay on Prometheus alerts, which already exist for the events metrics. This corrects the spec claim that DLQ growth reaches tenants: per-fill quarantine does (it is tenant-attributed), aggregate backlog is operator-only. The spec gets a follow-up edit.

### Contracts

`libs/proto/llamatrade_proto/protos/events.proto`:

- `EVENT_TYPE_NOTIFICATION = 50` in the reserved block.
- `message NotificationEvent`: `category` (new enum), `severity` (INFO / ACTIONABLE / CRITICAL), `dedup_key`, machine fields (`execution_id`, `strategy_id`, `session_id`, `account_id`, `sleeve_id`, `backtest_id`, `symbol`, `amount` as string decimal, `reason`, `map<string,string> extra`). Tenant and user ride the envelope.
- `enum NotificationCategory`: one value per flow in the catalog below (about 30). This becomes the single vocabulary; today's `AlertType` strings (trading) and `IncidentKind` strings (portfolio) both map onto it, ending the two-enum drift in the `webhooks.events` filter column. The column is effectively empty in every environment (no CRUD RPC ever existed), so no data migration is needed.

`notification.proto` additions: `ListWebhooks` / `CreateWebhook` / `UpdateWebhook` / `DeleteWebhook` / `TestWebhook` (secret returned only on create), `GetPreferences` / `UpdatePreferences` (per-category channel matrix). Existing 9 RPCs keep their shapes.

Envelope `event_id` is `derive_event_id(category, <entity id>, <occurrence discriminator>)`, producer-side deterministic, deduplicated by a unique index in Postgres on the notifications table, same commit-after-write discipline as the ledger writer.

### Data model (migrations 040+)

- `notifications` (exists, reshaped): becomes the logical in-app row. Add `event_id` (unique), `category`, `severity`; drop the per-channel `channel`/`status`/`sent_at` columns in favor of the deliveries table. `user_id` nullable (tenant-scoped rows leave it null).
- `notification_deliveries` (new, tenant-scoped, RLS): `notification_id`, `channel`, `destination`, `status` (PENDING / SENT / FAILED / DISABLED), `attempts`, `last_error`, `delivered_at`. One row per external delivery attempt target.
- `notification_channels` (exists): preferences JSONB carries the per-category matrix; defaults applied in code, criticals and security categories pinned on.
- `alerts` (exists): used as-is by the price-alert engine (`cooldown_minutes`, `last_triggered_at`, `trigger_count`, `expires_at`, `status` already present).
- `webhooks` (exists): gains nothing structurally; `failure_count` finally gets a reader (auto-disable), `secret` stays per-row.
- Migration mechanics: revision ids at 32 chars or fewer, new tables added to `RLS_TABLES` and to `_CREATED_BY_LATER_REVISIONS` in migration 025, parity test count moves from 34.

### Delivery semantics

- Webhook (one implementation, replacing three): sign the exact transmitted bytes, header `X-Webhook-Signature: sha256=<hmac>`, POST with `content=`, 10s timeout, retry only on 5xx / connect / timeout (3 attempts, exponential backoff), never on 4xx. Consecutive-failure threshold (default 25) flips `is_active` false and emits a `webhook_disabled` notification to the tenant so the disable is itself visible. Receiver-perspective tests verify the HMAC against the captured raw body.
- Email: aiosmtplib against `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`FROM_EMAIL` (all already plumbed through compose, k8s, and `.env.example` except `SMTP_PORT`/`FROM_EMAIL` in k8s, which get added). Dev and CI use a mailpit container. Destination defaults to the user's login email; `notification_channels` can override.
- In-app: the persisted row itself; unread count on `ListNotifications` as today's proto already specifies.
- Ordering and failure: persist-then-deliver inside the consumer; a delivery failure never blocks the ack (the row exists, deliveries retry on their own table state); a persist failure is not acked and redelivers, deduplicated by `event_id`.

## Flow catalog

Categories, emission sites, severity, and default channels. Sites reference the detection points found in the sweep; every producer change is "publish at this site", nothing more.

Money (portfolio):

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `sleeve_frozen` | `fill_ingestion.py:258` (invariant), `drift_policy.py:269` (position drift), `drift_policy.py:347` (cash drift) | CRITICAL | in-app, email, webhook |
| `fill_quarantined` | `fill_ingestion.py:417` | CRITICAL | in-app, email, webhook |
| `external_trade_adopted` | `drift_policy.py:219` (currently silent) | ACTIONABLE | in-app, webhook |
| `corporate_action_proposed` | `corporate_actions.py:361` (currently a log line) | ACTIONABLE | in-app, email |
| `corporate_action_applied` | `ledger_servicer.py:377-424` (currently nothing; `user_id` available here) | INFO | in-app |

Trading (all existing `AlertService` call sites keep their `on_*` API; the facade publishes):

| Category | Severity | Default channels |
|---|---|---|
| `order_filled`, `position_opened`, `position_closed` | INFO | in-app, webhook |
| `order_rejected`, `risk_breach` | ACTIONABLE | in-app, webhook |
| `position_drift`, `evaluation_stalled`, `symbol_not_tradable`, `connection_lost`, `strategy_error` | ACTIONABLE | in-app, email, webhook |
| `session_started`, `session_stopped` | INFO | in-app |
| `session_error`, `circuit_breaker_triggered` | CRITICAL | in-app, email, webhook |
| `circuit_breaker_reset`, `stop_loss_hit`, `take_profit_hit` | INFO | in-app, webhook |

Strategy (new emissions at existing sites):

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `execution_started` | `strategy_service.py:902` | INFO | in-app |
| `execution_stopped` | `strategy_service.py:1008-1054` | INFO | in-app |
| `funding_failed` | `strategy_service.py:948` | ACTIONABLE | in-app, email |
| `sleeve_release_deferred` | `strategy_service.py:1093` (trapped capital, currently a warning log) | CRITICAL | in-app, email |
| `execution_cancelled_by_archive` | `strategy_service.py:628` | INFO | in-app |
| `plan_limit_reached` | `servicer.py:693` (also finally wires the existing `plan_limit_exceeded` metric) | INFO | in-app |

Backtest:

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `backtest_completed` | `backtest_service.py:1029-1056` (`created_by` on the row gives `user_id`) | INFO | in-app |
| `backtest_failed` | `backtest_service.py:725-748`, reaper `:1221-1245` | ACTIONABLE | in-app |

Billing (webhook handlers, plus one new handled event type):

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `payment_succeeded` | `webhooks.py:328-387` (receipt fields all present) | INFO | email |
| `payment_failed` | `webhooks.py:390-417` | CRITICAL | in-app, email |
| `trial_ending` | new `customer.subscription.trial_will_end` handler (added to `_HANDLED_EVENT_TYPES`) | ACTIONABLE | in-app, email |
| `subscription_updated`, `subscription_canceled` | `webhooks.py:282-325` | INFO | in-app, email |

Auth and security (non-suppressible):

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `welcome` | registration `servicer.py:457-471` | INFO | email |
| `password_changed` | `servicer.py:546-599` (sessions are revoked with zero warning today) | SECURITY | email |
| `account_locked` | rate-limit lockout `servicer.py:97-117` (once per episode) | SECURITY | email |

Agent:

| Category | Site | Severity | Default channels |
|---|---|---|---|
| `confirmation_pending` | stranded tool proposal, emitted when the stream drops with an unconsumed proposal | ACTIONABLE | in-app |

Backtest completion also covers the agent's fire-and-forget `run_backtest` gap: the completion notification lands regardless of which surface submitted the run.

Price alerts (the 3B engine) generate `price_alert_triggered` notifications with the alert's configured channels.

## Phases

Each phase lands green on its own and is independently shippable. Effort is relative (S/M/L).

### Phase 0: contracts and plumbing (S)

Proto (`events.proto` additions, `notification.proto` RPC additions), `make proto`. Events lib: `NOTIFICATIONS` channel in `_CHANNELS`, `catalog/notifications.py` modeled on `catalog/fills.py` (publish + `StreamConsumer` factory + payload decode), exports. Terraform: `lt.notifications` (6 partitions, 30d) and `lt.notifications.dlq` (3, 30d) in `kafka_topics`; `"notification"` in `kafka_services`. K8s: ServiceAccount + Workload Identity annotation + `kafka-config` env on the notification deployment. Compose: `KAFKA_BOOTSTRAP_SERVERS` + redpanda dependency + mailpit service. `services/notification/pyproject.toml`: add `llamatrade-events`, `llamatrade-proto`, `llamatrade-telemetry` (currently transitive).

Tests: catalog unit tests on `FakeTransport` (topic naming, key = tenant_id, EventType registry round-trip), buf breaking check in CI (already wired).

### Phase 1: service core (L)

Persistence migrations (above). Real servicer: `ListNotifications` / `MarkAsRead` over the table, webhook CRUD, preference RPCs; `TestChannel` actually sends through the channel layer. The durable consumer: decode, alert matching hook (Phase 3 fills it), preference resolution, template rendering, persist, deliver, ack. The unified delivery layer: fixed webhook contract, SMTP email, auto-disable, `notification_deliveries` tracking. Health checks gain DB and Kafka probes (the readiness test asserting empty checks changes deliberately). Telemetry: the seven already-defined notification metrics get their producers.

Tests: pipeline stages as pure functions; receiver-perspective webhook signature (raw-body HMAC via `httpx.MockTransport`, portfolio's pattern); auto-disable threshold and the `webhook_disabled` self-notification; template rendering per category and channel; preference matrix including pinned criticals; servicer tests against real Postgres (testcontainers, RLS role pattern from `portfolio/tests/integration/test_rls.py`); consumer integration against real Kafka (testcontainers): commit-after-persist, redelivery dedup on `event_id`, poison to DLQ. Coverage gate 80% added to the CI step.

### Phase 2: producer integration (M)

Trading: `AlertService.on_*` surface unchanged at all 33 call sites; `_deliver` and the webhook internals replaced by a publish. Delete `_send_webhook`, `_send_webhook_with_retry`, `_update_webhook_delivery`, the leaked client. Portfolio: `LedgerAlertDispatcher.dispatch` becomes a publish; delete its HTTP path. New emissions per the catalog: strategy (6 sites), backtest (terminal writes and reaper), billing (4 handlers plus the new `trial_will_end` handler), auth (3 events), agent (stranded proposal). The webhook-contract change is not compatibility-gated: no webhook CRUD ever existed, so no external receiver depends on the broken signature.

Tests: each producer asserts its publish via an injected `FakeTransport` bus; the existing 38 trading alert tests and 11 portfolio alert tests are rewritten to assert publishes instead of HTTP; billing handler tests extend for `trial_ending`; the strategy/backtest/auth suites gain emission assertions at their 80% gates.

### Phase 3: price-alert engine (M)

Event-driven conditions (`ORDER_FILLED`, `STRATEGY_SIGNAL`, `RECONCILIATION_DRIFT`, `SLEEVE_FROZEN`): matched inside the Phase 1 consumer against active alerts (tenant, condition type, symbol or strategy filter), respecting cooldown and expiry, incrementing `trigger_count`. Market-driven conditions (`PRICE_ABOVE`/`BELOW`, `PRICE_CHANGE_PERCENT`, `VOLUME_ABOVE`, `RSI_ABOVE`/`BELOW`): a leader-elected loop (advisory lock, the portfolio sweep pattern with its documented fencing caveat) tails `lt.market.bars.1m` filtered to the symbols of active alerts (set refreshed periodically), computes RSI from `llamatrade_runtime` indicator code over rolling windows, and triggers with deterministic ids (`alert_id`, bar timestamp bucket) so a torn leader cannot double-notify. `CreateAlert` and friends go real over the existing `alerts` table.

Tests: deterministic bar sequences per condition type (trigger, no-trigger, cooldown skip, expiry); RSI against known vectors; leader-election single-writer test; dedup under deliberate double-evaluation; servicer CRUD against real Postgres.

### Phase 4: frontend (M)

Bell with unread badge polling `ListNotifications(unread_only)` on the existing lazy client; notification center (list, mark read, mark all); Settings notifications tab replaces the placeholder: per-category channel matrix, webhook management (create shows the secret once, test button, disabled-state surfacing), price-alert management. Zustand store in `apps/core/src/stores/notifications.ts` following the existing store conventions.

Tests: store and component tests in the existing vitest suite; msw-style RPC stubbing per current conventions.

### Phase 5: auth email flows (M, descopable)

New RPCs: `RequestPasswordReset` (uniform response regardless of account existence, rate-limited by the existing limiter), `ResetPassword` (single-use hashed token, revokes all sessions, sends `password_changed`), `VerifyEmail`, `ResendVerification`. New tenant-scoped `auth_tokens` table (hashed token, purpose, expiry, used_at), RLS-registered. Registration sends `welcome` plus a verification link; `is_verified` finally gets written. Unverified accounts are not restricted in v1 (beta invites must not bounce off a verification wall); restriction is a later product decision. Web pages: request-reset, reset form, verify landing.

Tests: token single-use and expiry; enumeration resistance (identical responses and timing shape); rate-limit interaction; full e2e round-trip through mailpit (register, extract link from captured email, verify; request reset, reset, old sessions dead).

### E2E and CI (lands with each phase, listed once)

CI edits: install `services/notification` in the e2e job, add it to the honcho mesh boot, add 8870 to the health gate, add mailpit to the service containers, coverage gate on the notification step. E2E flows in `tests/e2e/` (the mesh client already maps the service): quarantined fill via the Kafka inject seam produces an in-app row, a signed webhook captured by a local receiver, and a mailpit-captured email; stripe-mock `invoice.payment_failed` produces the payment-failed notification; backtest completion produces its row; a price alert triggers off an injected bar; the Phase 5 round-trips. The whole-life test gains a notification assertion pass.

## Rollout order and risks

Phases 0 to 2 are the dependency chain; 3, 4, 5 can proceed in parallel after 1 (4 needs 1's RPCs; 3 needs 1's consumer; 5 needs 1's email channel). Producers cut over per service within Phase 2, lowest-stakes first (strategy, backtest, billing, auth, agent, then trading, then portfolio), each behind its own PR with its suite green.

Risks worth naming: the consumer is a new stateful workload in a service that has never had one (mitigated by copying the supervised-task shape from portfolio's main.py); the notifications topic becomes a soft dependency of nine services' UX (mitigated by fire-and-forget publishes that never raise into callers, same asymmetry as ledger publishes); template sprawl (mitigated by one templates module with per-category golden tests); the price-alert bars tail adds market-data-shaped load to the notification service (bounded by the active-alert symbol set, and the loop is leader-elected so replicas do not multiply it).

The architecture spec has already been updated to present this subsystem in its implemented state, per its final-state convention (notification stance, six-topic eventing counts, the second `consume` user, limitation and finding renumbering, and a Notifications block under Platform plumbing). The reality baseline lives in this plan; items close here, not in the spec.
