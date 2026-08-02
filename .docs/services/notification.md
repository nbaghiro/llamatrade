# Notification Service

> **Implementation status: fully implemented.** DB-backed in-app notifications, a durable
> Kafka delivery pipeline, email and webhook channels, tenant preferences, and a price-alert
> engine (event-driven and market-driven). SMS/Slack/push channel enum values exist in the
> proto but are not wired into delivery (see "Not wired").

## Overview

The Notification Service is the single sink for user-facing notifications on the platform.
Every other service publishes machine-shaped `NotificationEvent`s to one Kafka stream;
this service is the only consumer. It persists the in-app row (the durable floor of every
flow), renders all human-readable copy, delivers to external channels (email, webhooks),
and evaluates user-defined price alerts.

**Core Responsibilities:**

- Durable ingestion of the `notifications` stream (one consumer group, keyed by tenant)
- In-app notification persistence, listing, and read-status tracking
- Per-category routing with tenant channel preferences and pinned severities
- Email delivery (SMTP, multipart/alternative with committed React Email HTML shells)
- Webhook delivery with an HMAC signature contract, bounded retry, and auto-disable
- Price alerts: event-driven matching in the consumer plus a leader-elected market loop
- Webhook, alert, channel, and preference CRUD over 16 Connect RPCs

Design posture: producers publish fire-and-forget (`publish_safe` never raises into an
order path or a webhook handler), and this service owns persistence, rendering, routing,
and delivery. Copy changes never touch a producing service.

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                                   FastAPI :8870                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║ Connect / gRPC ASGI  ·  AuthMiddleware (fail-closed)  ·  /health  ·  /metrics        ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
        │ RPCs                    │ supervised task                │ supervised task
        ▼                        ▼                                ▼
╭──────────────────────╮ ╭──────────────────────────╮ ╭───────────────────────────────╮
│ NotificationServicer │ │ notification consumer    │ │ market loop (leader-elected)  │
│  16 RPCs             │ │ StreamConsumer, group    │ │ pg advisory lock 0x6E6F7469   │
│  NotificationService │ │ "notification-delivery"  │ │ tails lt.market.bars.1m       │
╰──────────────────────╯ ╰──────────────────────────╯ ╰───────────────────────────────╯
        │                        │ persist-then-deliver           │ evaluate + trigger
        ▼                        ▼                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                    PostgreSQL (RLS)                                  │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ notifications · notification_deliveries · notification_channels · webhooks · alerts  │
└──────────────────────────────────────────────────────────────────────────────────────┘
                 ▲                                        │ external delivery
                 │ lt.notifications (Kafka,               ▼
                 │ keyed by tenant_id)          ┌──────────────────────┐
┌────────────────┴─────────────────┐            │ SMTP (mailpit in dev)│
│ Producers: auth · billing        │            │ Tenant webhook URLs  │
│ strategy · portfolio · trading   │            └──────────────────────┘
│ agent  (publish_safe)            │
└──────────────────────────────────┘
```

### Event Pipeline

```
producer                     notification service                        channels
   │                                │                                       │
   │ publish_safe(NotificationEvent)│                                       │
   ├────────────────────────────────►  lt.notifications (Kafka)             │
   │   envelope id = deterministic  │                                       │
   │   derive_event_id(category,    │  StreamConsumer (group                │
   │   tenant, *dedup_parts)        │  notification-delivery, 5 attempts,   │
   │                                │  DLQ notifications:dlq, lag gauge)    │
   │                                │                                       │
   │                                │  1 persist in-app row                 │
   │                                │    INSERT ... ON CONFLICT (event_id)  │
   │                                │    DO NOTHING  (dedup floor)          │
   │                                │  2 plan deliveries (category matrix   │
   │                                │    x tenant prefs), one row each      │
   │                                │  3 commit, ack offset                 │
   │                                │  4 event-driven alert matching        │
   │                                │  5 dispatch (best-effort, tracked)    │
   │                                ├───────────────────────────────────────►
   │                                │            email · webhook            │
```

Decode failures and envelopes without a `tenant_id` are poison: they go to the DLQ and are
acked. Transient DB errors raise and redeliver; the unique `event_id` index makes the
redelivered persist a no-op. External delivery runs after the commit and never raises into
the consumer, so a slow webhook or an SMTP outage cannot stall ingestion.

---

## Directory Structure

```
services/notification/
├── src/
│   ├── main.py                 # FastAPI app, Connect mount, consumer + market-loop tasks
│   ├── pipeline.py             # persist_and_plan, consumer handler, recipient resolution
│   ├── delivery.py             # DeliveryDispatcher: send, track, auto-disable webhooks
│   ├── preferences.py          # CATEGORY_SPECS matrix, PINNED_SEVERITIES, channels_for
│   ├── templates.py            # per-category copy: NotificationEvent -> Rendered
│   ├── email_render.py         # HTML assembly from the committed shells
│   ├── email_html/             # 8 committed shells (4 severities x plain/cta)
│   ├── grpc/
│   │   └── servicer.py         # NotificationServicer (16 RPCs) + proto mappers
│   ├── services/
│   │   └── notification_service.py  # in-app reads, webhook/alert/preference CRUD
│   ├── channels/
│   │   ├── email.py            # EmailChannel (aiosmtplib)
│   │   ├── webhook.py          # WebhookChannel (HMAC contract, retry policy)
│   │   ├── sms.py              # Twilio client, NOT wired into delivery
│   │   └── slack.py            # Slack incoming-webhook client, NOT wired into delivery
│   ├── alerts/
│   │   ├── engine.py           # condition evaluation, transactional trigger_alert
│   │   ├── matcher.py          # event-driven matching inside the consumer
│   │   └── market_loop.py      # leader-elected bar tail for market conditions
│   └── tasks/
│       └── consumer.py         # run_notification_consumer wiring
├── emails/                     # @llamatrade/emails: React Email source (standalone package, own node_modules, outside the root npm workspace)
│   └── src/render.tsx          # `make emails` renders the committed shells into ../src/email_html/
├── tools/
│   └── preview_emails.py       # design/QA gallery of every scenario (`make emails-preview`); not shipped
├── tests/
│   ├── conftest.py             # ASGI test client
│   ├── test_*.py               # unit suite (channels, templates, engine, servicer, ...)
│   └── integration/            # real Postgres (testcontainers) + FakeTransport
├── pyproject.toml
├── Dockerfile
└── Dockerfile.dev
```

---

## Core Components

| Component              | File                                | Purpose                                              |
| ---------------------- | ----------------------------------- | ---------------------------------------------------- |
| `NotificationServicer` | `grpc/servicer.py`                  | Connect servicer, 16 RPCs, proto mapping             |
| `NotificationService`  | `services/notification_service.py`  | Tenant-scoped CRUD over the notification tables      |
| Consumer handler       | `pipeline.py` + `tasks/consumer.py` | Persist-then-deliver handler for the StreamConsumer  |
| `DeliveryDispatcher`   | `delivery.py`                       | Email/webhook sends, per-row tracking, auto-disable  |
| Category matrix        | `preferences.py`                    | Severity, default channels, in-app type per category |
| Templates              | `templates.py`                      | All human-readable copy                              |
| Alert engine           | `alerts/`                           | Condition evaluation, matching, market loop          |

---

## RPC Endpoints

`NotificationService` (proto: `libs/proto/llamatrade_proto/protos/notification.proto`), 16 RPCs.

### Notifications

| Method              | Description                                                                     |
| ------------------- | ------------------------------------------------------------------------------- |
| `ListNotifications` | Paginated list (page size clamped to 100, default 20), `unread_only` filter, returns `unread_count` |
| `MarkAsRead`        | Mark one notification (`notification_id`) or all (`mark_all`); returns `marked_count` |

The servicer only reads and flags notification rows; the durable consumer is the sole
writer of `notifications` and `notification_deliveries`.

### Price Alerts

| Method        | Description                                                                        |
| ------------- | ---------------------------------------------------------------------------------- |
| `ListAlerts`  | List the tenant's alerts, optional `active_only`                                   |
| `CreateAlert` | Create an alert: name, condition (type, symbol, threshold, strategy_id), channels, cooldown (default 60 min) |
| `DeleteAlert` | Delete an alert                                                                    |
| `ToggleAlert` | Set `ALERT_STATUS_ACTIVE` / `ALERT_STATUS_DISABLED`                                |

### Channels

| Method          | Description                                                                    |
| --------------- | ------------------------------------------------------------------------------ |
| `ListChannels`  | Channel states derived from preferences; `is_verified` is true only for email  |
| `UpdateChannel` | Enable/disable one channel type                                                |
| `TestChannel`   | Email only: sends a test message to the resolved recipient; other types return `success=false` and point at `TestWebhook` |

### Webhooks

| Method          | Description                                                                    |
| --------------- | ------------------------------------------------------------------------------ |
| `ListWebhooks`  | List the tenant's webhook endpoints                                            |
| `CreateWebhook` | Validates name and http(s) URL; generates a server-side secret (`secrets.token_urlsafe(32)`), returned once in the response |
| `UpdateWebhook` | Update name/url/events/active; re-enabling resets `failure_count`              |
| `DeleteWebhook` | Delete an endpoint                                                             |
| `TestWebhook`   | Sends a signed test payload to the stored URL; returns status code and outcome |

### Preferences

| Method              | Description                                                              |
| ------------------- | ------------------------------------------------------------------------ |
| `GetPreferences`    | Per-channel enabled flag + optional category narrowing (email, webhook)  |
| `UpdatePreferences` | Upsert `notification_channels` rows; unknown channel types are ignored   |

Errors follow the shared `handle_service_errors` decorator: validation failures
(`WebhookValidationError`, malformed UUIDs) map to `INVALID_ARGUMENT`, missing rows to
`NOT_FOUND`.

---

## Event Ingestion

The stream contract lives in `libs/events/llamatrade_events/catalog/notifications.py`:

- One global logical stream `notifications` (Kafka topic `lt.notifications` after transport
  namespacing), `Delivery.CONSUME`, partitioned by `tenant_id`: each tenant's notifications
  stay ordered while delivery parallelizes across tenants.
- `NotificationEvents.publish` builds the envelope with a deterministic id:
  `derive_event_id(category, tenant_id, *dedup_parts)`. `dedup_parts` extends the seed for
  flows that recur per entity (for example `(client_order_id,)`).
- `NotificationEvents.publish_safe` is the producer entry point: a 5 second ceiling, never
  raises into the producing path, logs and drops on failure. `shared_notification_events()`
  is the per-process publisher singleton.
- `NotificationEvents.consumer()` returns a `StreamConsumer` for group
  `notification-delivery` with `group_start=CURSOR_BEGIN`: a fresh group replays the
  retained stream, which is safe because the persist side dedups on `event_id`.

`StreamConsumer` (shared lib) supplies in-place retry (5 attempts), dead-lettering to
`notifications:dlq`, and the consumer-lag gauge. The consumer name is the pod's
`HOSTNAME`. Producers: auth (welcome, verification, password flows, lockout), billing
(payment and subscription events), strategy (execution lifecycle, funding), portfolio
(sleeve/ledger money events), trading (session and risk events), agent (pending
confirmations).

---

## Routing: Category Matrix and Preferences

`preferences.py` is the routing single source. Each of the ~43 `NotificationCategory`
values declares a `CategorySpec`: default severity, default external channels (the in-app
row is always persisted and needs no channel), and the `NotificationType` the in-app row
renders as. Unknown categories fall back to `(INFO, no external channels, SYSTEM)`.

| Group             | Examples                                                | Typical routing        |
| ----------------- | ------------------------------------------------------- | ---------------------- |
| Money (portfolio) | `SLEEVE_FROZEN`, `FILL_QUARANTINED`                     | CRITICAL, email+webhook |
| Trading           | `ORDER_FILLED`, `RISK_BREACH`, `SESSION_ERROR`          | INFO webhook up to CRITICAL email+webhook |
| Strategy          | `EXECUTION_STARTED`, `FUNDING_FAILED`, `SLEEVE_RELEASE_DEFERRED` | in-app only up to CRITICAL email |
| Backtest          | `BACKTEST_COMPLETED`, `BACKTEST_FAILED`                 | in-app only            |
| Billing           | `PAYMENT_FAILED`, `TRIAL_ENDING`                        | email                  |
| Auth/security     | `PASSWORD_CHANGED`, `EMAIL_VERIFICATION`, `PASSWORD_RESET` | SECURITY, email     |
| Service-generated | `PRICE_ALERT_TRIGGERED`, `WEBHOOK_DISABLED`             | alert channels / email |

Resolution (`channels_for`): start from the category's default channel set, then apply the
tenant's `notification_channels` rows. A disabled row drops that channel; an enabled row
with a `categories` list narrows it to those categories; channels without a row keep the
defaults. Finally, `PINNED_SEVERITIES = {CRITICAL, SECURITY}` always add email: a disabled
email channel cannot silence a critical or security notification (recipient resolution
passes `ignore_disabled=True` for pinned severities).

Email recipients are the enabled EMAIL channel row's `destination` override when set,
otherwise all active users of the tenant. Webhook targets are the tenant's active
endpoints whose `events` list is empty (all categories) or contains the category.

The effective severity is the event's severity when set, else the category default.

---

## Delivery Channels

Each planned delivery has a `notification_deliveries` row (channel, destination, status,
attempts, `last_error`, `delivered_at`). Dispatch marks rows `SENT` or `FAILED` and
increments `attempts`; there is no cross-process retry queue beyond the webhook channel's
own in-call retries, and a failed row records why.

### Email

`EmailChannel` sends over SMTP via `aiosmtplib` (10 s timeout). STARTTLS and login run
only when credentials are configured, so the mailpit dev catcher (plain SMTP, no auth) and
a real provider share one code path. An empty `SMTP_HOST` means email is off: `send()`
reports failure rather than pretending delivery happened.

Messages are `multipart/alternative`: the plain-text part comes from the template (and
always carries the CTA link, so text-only clients keep it), the HTML part from
`email_render.build_html`. The HTML shells in `src/email_html/` (8 files: info,
actionable, critical, security, each with and without a CTA button) are authored in React
Email under `emails/` — the standalone `@llamatrade/emails` package with its own
`node_modules`, outside the root npm workspace — and rendered by `make emails` (which runs
`tsx src/render.tsx`, equivalently `npm run build --prefix services/notification/emails`).
The rendered shells are committed, like the generated protos, so the Python service needs
no Node at runtime; the Docker image ships them via `COPY services/notification/src`.
`build_html` substitutes HTML-escaped content into the `__LOGO_URL__`, `__PREHEADER__`,
`__TITLE__`, `__BODY__`, `__CTA_URL__`, and `__CTA_LABEL__` placeholders at send time. The
header logo is a hosted PNG (`apps/web/public/logo-monolith.png`), since Gmail and Outlook
strip inline SVG: `__LOGO_URL__` resolves to `{EMAIL_ASSET_BASE_URL}/logo-monolith.png`
(the base defaults to the app origin), and the email canvas carries the app's
vertical-column-divider background. All copy lives in `templates.py` (subject is
`LlamaTrade: {title}`); `EMAIL_VERIFICATION` and `PASSWORD_RESET` carry their CTA link in
`event.extra["link"]`.

A CI drift guard (`emails-drift` in `.github/workflows/ci.yml`) re-renders the shells from
source and fails if the committed `src/email_html/` differs, so a template edit cannot ship
without a rebuild. For design/QA, `tools/preview_emails.py` (`make emails-preview`) renders
all ~44 scenarios with demo data through the real send path into one gallery.

### Webhooks

`WebhookChannel` is the platform's one webhook delivery contract:

- The payload is encoded once (`json.dumps(payload, sort_keys=True, default=str)`) and
  posted as those exact bytes (`content=`, never `json=`).
- The signature is HMAC-SHA256 over the exact transmitted bytes with the endpoint's
  secret, sent as `X-Webhook-Signature: sha256=<hex>`, so receivers verify byte-for-byte.
- Retry covers only transient classes: up to 3 attempts on 5xx, timeout, or connect
  errors, with exponential backoff (0.5 s base). A 4xx is a permanent verdict and is
  returned immediately, with no retry. Request timeout is 10 s.
- Custom per-endpoint headers from `webhooks.headers` are merged into the request.

Every attempt updates the endpoint's tracking columns (`last_triggered_at`,
`last_status_code`, `failure_count`; success resets the count). When `failure_count`
reaches 25 consecutive failures the endpoint is disabled (`is_active=false`) and a
`WEBHOOK_DISABLED` notification is persisted with a deterministic event id and delivered
by email (the category spec is email-only, so webhook recursion is impossible), giving the
tenant a visible record of why the integration went quiet. Re-enabling via
`UpdateWebhook` resets the count.

### Not wired

`ChannelType` in the proto also defines `SMS`, `PUSH`, `SLACK`, `DISCORD`, and
`TELEGRAM`. `channels/sms.py` (Twilio) and `channels/slack.py` (incoming webhooks) exist
as clients with unit tests, but nothing routes to them: `DeliveryDispatcher` handles only
`EMAIL` and `WEBHOOK`, and the preference surface (`PREFERENCE_CHANNELS`) exposes only
those two. Selecting another channel on an alert stores the value but produces no
delivery.

---

## Price Alerts

Alerts live in the `alerts` table: condition type, optional symbol, JSONB condition
(threshold, optional description and `strategy_id` filter), channel list, cooldown
(default 60 minutes), optional expiry, trigger bookkeeping.

### Condition types

| Kind          | Types                                                                        | Evaluated by |
| ------------- | ---------------------------------------------------------------------------- | ------------ |
| Market-driven | `PRICE_ABOVE`, `PRICE_BELOW`, `PRICE_CHANGE_PERCENT`, `VOLUME_ABOVE`, `RSI_ABOVE`, `RSI_BELOW` | market loop |
| Event-driven  | `ORDER_FILLED`, `RECONCILIATION_DRIFT`, `SLEEVE_FROZEN`                      | consumer matcher |
| Defined, unmatched | `STRATEGY_SIGNAL` (no backbone event exists yet)                        | nothing      |

### Event-driven matching

`EventAlertMatcher` runs inside the consumer after a notification is persisted. It maps
arriving categories onto condition types (`ORDER_FILLED`; `POSITION_DRIFT` and
`RECONCILIATION_DRIFT` both map to `RECONCILIATION_DRIFT`; `SLEEVE_FROZEN`), filters
candidates by symbol and by the condition's optional `strategy_id`, and fires each match.

### Market loop

One pod at a time evaluates market conditions. Leadership is a session-level Postgres
advisory lock (`llamatrade_db.advisory`, key `0x6E6F7469`) held on a dedicated
connection; replicas without the lock retry every 15 s, and a dead backend releases the
lock server-side, which is the crash-failover path. The leader tails the live bars stream
(`lt.market.bars.1m`) via `BarEvents`, keeps a rolling per-symbol window of 120 one-minute
bars, and refreshes the watched symbol set every 30 s from active market alerts
(cross-tenant, via `system_session` with an audit reason).

RSI uses `llamatrade_runtime.indicators` (`compute_indicator`, period 14), so alert
semantics match the strategy engine exactly. `PRICE_CHANGE_PERCENT` compares the latest
close against the oldest retained close (about a 2 hour window).

### Triggering

`trigger_alert` is transactional: it locks the alert row `FOR UPDATE`, re-checks status,
expiry, and cooldown under the lock, then persists the `PRICE_ALERT_TRIGGERED`
notification through the same `persist_and_plan` path with two deviations: the event id is
deterministic, `derive_event_id(alert_id, bucket)` where the bucket is the bar's minute
timestamp (or an event-derived key for event-driven matches), and the alert's own channel
list overrides the category matrix. A torn leader or a concurrent event matcher therefore
collapses to one notification. On success it stamps `last_triggered_at`, increments
`trigger_count`, commits, and dispatches.

---

## Data Model

Models in `libs/db/llamatrade_db/models/notification.py`; all tables are tenant-scoped
and RLS-enabled.

| Table                     | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `notifications`           | The logical in-app row; unique `event_id` is the platform-wide dedup key; proto category/severity ints, rendered title/message, JSONB `data`, `read_at` |
| `notification_deliveries` | One row per (notification, external target): channel, destination, status, attempts, `last_error`, `delivered_at` |
| `notification_channels`   | Per-tenant channel configuration: type, destination override, enabled, JSONB preferences (category narrowing) |
| `webhooks`                | Endpoint: URL, signing secret, category filter (`events`), custom headers, active flag, failure tracking |
| `alerts`                  | Condition type, symbol, JSONB condition, channels, cooldown, expiry, trigger bookkeeping |

Migrations: the base tables come from the initial schema chain; revision
`040_notification_delivery` reshaped `notifications` into the durable in-app row (added
`event_id` with its unique index, proto category/severity, nullable `user_id`; dropped the
per-row `channel`/`status`/`sent_at`/`error_message` columns) and created
`notification_deliveries` with RLS. Revision `041_auth_tokens` created the `auth_tokens`
table (owned by the auth service) backing the email verification and password reset flows
whose emails are delivered through this service.

---

## Configuration

### Environment Variables

| Variable                  | Required | Default                  | Description                                    |
| ------------------------- | -------- | ------------------------ | ---------------------------------------------- |
| `DATABASE_URL`            | Yes      | -                        | PostgreSQL connection string                   |
| `KAFKA_BOOTSTRAP_SERVERS` | Yes      | -                        | Kafka/Redpanda brokers (event transport)       |
| `SMTP_HOST`               | No       | empty (email off)        | SMTP server; mailpit in dev                    |
| `SMTP_PORT`               | No       | `587`                    | SMTP port (mailpit: 1025)                      |
| `SMTP_USER`               | No       | empty                    | SMTP username; empty skips STARTTLS + login    |
| `SMTP_PASSWORD`           | No       | empty                    | SMTP password                                  |
| `FROM_EMAIL`              | No       | `noreply@llamatrade.com` | Sender address                                 |
| `EMAIL_ASSET_BASE_URL`    | No       | app origin               | Base for email image assets; the header logo resolves to `{base}/logo-monolith.png` |
| `AUTH_JWT_PUBLIC_KEY`     | No       | empty                    | RS256 verification key (HS256 fallback), used by `AuthMiddleware` |
| `CORS_ORIGINS`            | No       | localhost origins        | Comma-separated allowed origins                |
| `HOSTNAME`                | No       | `notification-0`         | Consumer member name within the group          |

Dev mail catching: the compose stack runs mailpit (SMTP `:1025`, UI `http://localhost:8025`).

### Port Assignment

| Service      | Port |
| ------------ | ---- |
| Notification | 8870 |

---

## Health Check

```http
GET /health
```

```json
{ "status": "healthy", "service": "notification", "version": "0.1.0" }
```

`HealthChecker` registers two non-critical checks: `database` (Postgres reachability) and
`kafka`. The Kafka check answers from the running consumer's shared transport when live,
so it reflects the actual consumer connection rather than opening a probe connection.
Both are non-critical so notification reads stay available during a broker outage.

Telemetry via `init_telemetry` (OTel + Prometheus `/metrics`, DB pool stats). The
`metrics.notification` group records delivered/failed counters per channel and reason,
delivery latency, alert triggers, and cooldown skips; `tenant_id` is never a metric label.

Lifecycle: the lifespan verifies RLS enforcement, mounts the Connect app, and starts the
consumer and market loop under `supervise` with a shared stop event; shutdown waits 10 s
for both tasks before cancelling, then closes the bus and the DB.

---

## Multi-Tenancy

- The fail-closed `AuthMiddleware` wraps the app; RPCs resolve identity via
  `resolve_identity_connect` and never trust the wire `TenantContext`.
- All RPC queries run inside `tenant_session(tenant_id)` (Postgres RLS); the service
  refuses to boot in prod/staging if the DB role can bypass RLS
  (`verify_rls_enforcement`).
- The consumer takes `tenant_id` from the event envelope (missing tenant is poison) and
  persists inside a tenant session, so RLS also bounds the write path.
- The market loop's symbol sweep and bar evaluation are the two deliberate cross-tenant
  reads, run through `system_session` with an audit reason; triggering re-enters a tenant
  session per alert.

---

## Internal Service Connections

### Who talks to Notification

| Caller                    | Mechanism                        | Purpose                              |
| ------------------------- | -------------------------------- | ------------------------------------ |
| Web frontend              | Connect RPCs                     | Bell UI, alerts, webhooks, settings  |
| auth, billing, strategy, portfolio, trading, agent | `lt.notifications` (Kafka, `publish_safe`) | Emit notification events |

### What Notification calls

| Target              | Purpose                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| PostgreSQL          | All persistence (RLS-scoped)                                             |
| Kafka               | Consume `lt.notifications`, tail `lt.market.bars.1m`, produce to the DLQ |
| SMTP provider       | Email delivery                                                           |
| Tenant webhook URLs | Signed webhook delivery                                                  |

No synchronous RPC to another service is made from this service.

---

## Testing

```
tests/
├── conftest.py                  # httpx ASGI client fixture
├── test_health.py               # health endpoint
├── test_templates.py            # copy rendering, CTA plumbing
├── test_email_render.py         # shell substitution, escaping, variant selection
├── test_email_channel.py        # SMTP config gating, failure reporting
├── test_webhook_channel.py      # signature over transmitted bytes, retry classes
├── test_webhook_tracking.py     # failure count, auto-disable, disabled notice
├── test_preferences.py          # matrix resolution, narrowing, pinned severities
├── test_alert_engine.py         # condition evaluation, cooldown, windows, RSI
├── test_grpc_servicer.py        # servicer behavior with a mocked session maker
├── test_slack.py / test_sms.py  # unwired channel clients
└── integration/                 # marker: integration (requires Docker)
    ├── conftest.py              # testcontainers postgres:16, schema from ORM metadata
    ├── test_pipeline_pg.py      # persist/dedup/delivery against real Postgres
    ├── test_alerts_pg.py        # trigger path, cooldown re-check, determinism
    └── test_servicer_pg.py      # RPCs end-to-end over the real schema
```

- About 115 unit tests and 25 integration tests. The integration suite skips itself when
  Docker is unavailable; enum types are created from the model TypeDecorators so the
  throwaway schema stays in lockstep with the models.
- The event bus is faked with `FakeTransport` from `llamatrade_events.testing` (in-memory
  transport with redelivery semantics), so retry/DLQ paths run without a broker.
- Webhook tests capture the wire request through `httpx.MockTransport` and verify the
  HMAC against the raw transmitted body: the receiver's perspective.
- Coverage: `pytest --cov=src --cov-report=term-missing`; the repo target is 80% for real
  implementations.

---

## Capabilities

- Durable ingestion of `lt.notifications` (one consumer group, tenant-keyed, replay-safe)
- Persist-then-deliver with platform-wide `event_id` dedup (`ON CONFLICT` no-op)
- Category matrix routing with tenant preferences and pinned CRITICAL/SECURITY email
- In-app notifications: pagination, unread counts, read marking
- Email: multipart/alternative, committed React Email shells, CTA-safe text part
- Webhooks: HMAC-SHA256 sign-what-you-send contract, transient-only retry, per-endpoint
  tracking, auto-disable at 25 consecutive failures with a self-notification
- Price alerts: 6 market condition types (leader-elected bar loop, runtime RSI) and 3
  event condition types (consumer matcher), transactional deterministic triggering
- Webhook/alert/channel/preference CRUD over 16 Connect RPCs
- Per-delivery tracking rows (status, attempts, last error)

## Not implemented

- SMS, push, Slack, Discord, and Telegram delivery (enum values and, for SMS/Slack,
  client modules exist; nothing routes to them)
- `STRATEGY_SIGNAL` alert matching (no backbone event to match against)
- Cross-process delivery retry beyond the webhook channel's in-call attempts

---

## Summary

The Notification Service turns machine-shaped events from every other service into
persisted in-app notifications, emails, webhook posts, and triggered price alerts. Its
contract is deliberately narrow: producers publish fire-and-forget with deterministic
event ids, and this service owns dedup, copy, routing, and delivery. The durable floor is
the `notifications` row (persisted before the offset commit), external channels are
best-effort with per-delivery tracking, and the alert engine reuses the runtime indicator
library so alert semantics match strategy evaluation.
