# Telemetry & Observability

> Source of truth for **what** LlamaTrade reports and **how** the unified
> `llamatrade_telemetry` library emits it. Every service, lib, and the web app
> conform to this document. If you add a metric/span/log, add it here first.

> **Status:** the unified library is live in every service and worker (the
> Celery workers and the market-data ingestor included). Shared domain
> instruments live in the lib's `domain.py`; service-scoped instruments are
> created through the validated registry factories in thin per-service modules
> (`services/*/src/metrics.py`, `services/backtest/src/queue_metrics.py`). The
> scrape and trace infra (Prometheus / Grafana / Tempo / OTel Collector /
> Alertmanager) runs in compose and k8s (§9); the true remainder is in §10.

---

## 1. Goals & principles

1. **One library, one setup call.** Every service gets metrics + structured logs
   + traces + a `/metrics` endpoint from a single `init_telemetry(app, service=…)`.
2. **No duplication.** A concept is instrumented **once**. There is exactly one
   Alpaca call metric, owned by `libs/alpaca` and recorded as the uniform
   outbound-dependency series (`llamatrade_dependency_*` with `target="alpaca"`);
   the trading and market-data services define no Alpaca metrics of their own.
3. **OTel-native, Prometheus-exposed.** Instruments are created through the
   OpenTelemetry API; a `PrometheusMetricReader` exposes them at `/metrics` for
   scraping. Traces export via OTLP. This gives us distributed tracing across the
   9-service `signal → risk → order → fill → ledger` path (the collector is wired
   in compose and k8s) without giving up Prometheus dashboards.
4. **Three signals, three jobs** (see §3). Metrics answer *aggregate* questions,
   logs answer *drill-down*, traces answer *why was this one request slow*.
5. **Cardinality is sacred** (see §4). `tenant_id`/`session_id` never become
   Prometheus labels. They live on logs/traces; `plan` is the per-segment label.
6. **Graceful degradation.** If no OTLP collector is configured, tracing exports
   nothing (spans are still recorded, so `trace_id` reaches the logs); metrics
   have a kill-switch (`TELEMETRY_METRICS_ENABLED`); label mistakes raise in
   dev/test and log-and-drop in prod. Telemetry must never crash a request or a
   worker.
7. **Async-first, strictly typed.** No blocking calls in async paths; no `Any`.

---

## 2. What the library provides

| Area | Approach |
|---|---|
| Setup | one `init_telemetry()` call per service/worker |
| Metrics | `llamatrade_telemetry` core + typed `metrics.<domain>.*` namespaces |
| Alpaca metrics | one set, owned by `libs/alpaca` |
| Logging | JSON everywhere, with `trace_id` / `span_id` |
| Tracing | OTel spans + W3C propagation across services (no-op without a collector) |
| Events | `llamatrade_events_*` counters/gauges via the telemetry registry; W3C trace propagated through the envelope |
| Scraping | each service exposes `/metrics`; Prometheus scrapes all nine services plus the market-data ingestor; Grafana / Tempo / OTel Collector / Alertmanager run in compose and k8s (§9) |
| Frontend | `apps/web/src/telemetry/`: web-vitals, RPC latency, JS errors, trace propagation |
| Workers | queue depth + job states sampled from the backtest API process; per-task CONSUMER spans via Celery signals (§8) |

---

## 3. The three-signal model

| Signal | Backend | Cardinality | Carries tenant/session? | Answers |
|---|---|---|---|---|
| **Metrics** | Prometheus (via OTel) | **low** — each label combo is a stored series | **no** (labels); `plan` yes | "fleet p99 order latency? error rate up?" |
| **Logs** | JSON → Loki / Cloud Logging | high — fine | **yes**: `request_id`, `tenant_id`, `user_id`, `trace_id` | "everything that happened for tenant X" |
| **Traces** | OTLP → Tempo / Cloud Trace | high — fine | **yes** as span attributes | "why was *this* order slow end-to-end" |

### How per-tenant dashboards work without tenant labels on metrics

There are three different "per-tenant numbers" people conflate:

1. **Per-tenant business data** (P&L, positions, MRR) — **not telemetry**. It is
   served from the **ledger / Postgres** via the portfolio/billing APIs. The
   user-facing "your P&L" view reads the double-entry ledger; that is the source
   of truth, never a Prometheus label.
2. **Per-tenant operational drill-down** (this tenant's error rate / slow calls) —
   **logs + traces**. Grafana `tenant_id` template variable → LogQL/Cloud Logging
   query; the log line's `trace_id` opens the tenant's trace in Tempo.
3. **Aggregate operational health** (95% of dashboards) — **metrics**, sliced by
   bounded labels: `service`, `route`, `status`, and `plan`.

The escape hatch when Prometheus genuinely needs a customer dimension is a
**bounded top-N gauge** (app-side, e.g. top-20 tenants by order volume).
Exemplars are not emitted today (§8).

---

## 4. Conventions (enforced by the lib)

### 4.1 Metric naming

`llamatrade_<domain>_<noun>_<unit>` — e.g. `llamatrade_trading_order_submission_latency_seconds`.

- Units are explicit suffixes: `_seconds`, `_bytes`, `_total` (counters),
  `_ratio`, `_dollars`, `_bps`, `_count`/gauge nouns.
- Domains: `http`, `grpc`, `dependency`, `db`, `events`, `alpaca`, `runtime`,
  `celery`, `trading`, `ledger`, `marketdata`, `strategy`, `backtest`,
  `billing`, `auth`, `notification`, `agent`.
- Instruments are created under the full underscored name; the
  `conventions.py` validator (`METRIC_NAME_RE`) rejects anything that does not
  match the pattern, so names never drift.

### 4.2 Allowed label set (bounded)

A central allow-list. Adding a label not on it fails the `conventions` validator
in tests.

| Label | Values (bounded) | Notes |
|---|---|---|
| `service` | the 9 service names + lib names | always present |
| `transport` | `http`, `connect`, `grpc` | inbound/outbound |
| `method` | HTTP verb or RPC method name | RPC method names are bounded by the proto |
| `route` | registered path / RPC prefix | unregistered paths collapse into one `__unmatched__` series |
| `operation` | dependency op (`select`, `publish`, `submit_order`…) | |
| `target` | dependency (`postgres`, `redis`, `alpaca`, `stripe`, peer service) | |
| `status` / `status_code` / `status_class` | `ok`/`error`, code, `2xx`… | |
| `result` | `hit`/`miss`/`error`, `success`/`failure`, `passed`/`failed` | |
| `plan` | `free`/`starter`/`pro` | **the** per-segment business label |
| `kind`/`type`/`side`/`reason`/`event_type`/`channel`/`model`/`data_type`/… | small enums per domain | the full set is `conventions.ALLOWED_LABEL_KEYS` |

**Forbidden as labels:** `tenant_id`, `session_id`, `user_id`, `order_id`,
`client_order_id`, `symbol`* , `backtest_id`, `request_id`, raw URLs, emails,
and the other identifier keys in `conventions.FORBIDDEN_LABEL_KEYS`
(strategy/sleeve/account ids, ip, path, trace ids).

\* `symbol` is allowed **only** on a deliberately bounded top-N gauge, never on
counters/histograms.

### 4.3 Histogram buckets (standardized)

- **RPC/HTTP latency:** `0.005,0.01,0.025,0.05,0.075,0.1,0.25,0.5,0.75,1,2.5,5,7.5,10` (s)
- **Dependency/db:** `0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5` (s)
- **Order/market latency (tight):** `0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1` (s)
- **Job duration (backtest):** `1,5,10,30,60,120,300,600,1800` (s)
- **Slippage:** bps buckets `1,2,5,10,25,50,100,250`

Further domain sets (drift percent, staleness, delivery, bcrypt, LLM latency)
are declared next to these in `conventions.HISTOGRAM_BUCKETS`; creating a
histogram whose name has no entry there raises, which forces a deliberate
bucket choice.

---

## 5. The `llamatrade_telemetry` library

### 5.1 Module layout

```
libs/telemetry/llamatrade_telemetry/
├── __init__.py        # init_telemetry, get_logger, metrics, span, counter/gauge/…, shutdown
├── config.py          # TelemetrySettings (pydantic-settings): exporters, sampling, env, log fmt
├── conventions.py     # name/label allow-lists + histogram buckets + validators
├── registry.py        # MeterProvider + PrometheusMetricReader; counter/gauge/histogram/… + get_metrics
├── setup.py           # init_telemetry(app, service, version): wires everything; /metrics; idempotent
├── domain.py          # typed namespaces: metrics.trading.*, metrics.ledger.*, …
├── runtime.py         # event-loop lag + process collectors
├── logging.py         # JSON formatter + stdlib config + request-context contextvars
├── tracing.py         # TracerProvider + OTLP export (no-op w/o collector); span(); W3C inject/extract
└── instrumentation/
    ├── http.py        # ASGI RED middleware: TelemetryMiddleware
    ├── grpc.py        # llamatrade_grpc_requests_total + record_grpc_request
    ├── db.py          # SQLAlchemy query timing + pool observer (PoolStatsLike)
    ├── celery.py      # queue-depth gauge (set by the backtest API sampler)
    └── dependency.py  # outbound dependency (db/redis/peer/external) timing
```

`/metrics` exposition lives in `setup.py` via `registry.get_metrics()`; there is
no `metrics/`, `logging/`, or `tracing/` subpackage and no `exporters.py`. Event
metrics live in `llamatrade_events/observability.py` (surfaced as
`llamatrade_events_*`), not here.

Companion web package: `apps/web/src/telemetry/` (web-vitals, RPC interceptor,
error sink, trace propagation).

### 5.2 Public API

```python
from llamatrade_telemetry import init_telemetry, get_logger, metrics

# one call per service
init_telemetry(
    app,                       # FastAPI/ASGI app; omit for workers (Celery/ingestor)
    service="trading",
    version=__version__,
    pool_stats_provider=get_pool_stats,   # optional; wires db pool gauges
)
# auto-wired: JSON logging (+trace ids), /metrics, RED middleware, runtime
# collectors, trace context + W3C propagation, graceful OTLP export.

log = get_logger(__name__)                # stdlib logger; context + trace ids injected

# domain metrics — typed, namespaced, naming + label-allowlist enforced
metrics.trading.order_submitted(side="buy", type="market", status="accepted")
with metrics.trading.fill_processing_duration.time():
    ...
metrics.ledger.reconciliation_drift(kind="qty_mismatch")
```

Workers (no FastAPI app):

```python
init_telemetry(service="backtest-worker", version=__version__)  # no app → no middleware
```

### 5.3 Configuration (`TelemetrySettings`, env-driven)

| Env var | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `development` | resource attribute `deployment.environment` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset → tracing no-ops)_ | OTLP collector |
| `OTEL_TRACES_SAMPLER` / `_ARG` | `parentbased_traceidratio` / `0.1` | sampling |
| `LOG_LEVEL` | `INFO` | |
| `LOG_FORMAT` | `json` (`text` for local dev) | |
| `TELEMETRY_METRICS_ENABLED` | `true` | metrics kill-switch |
| `TELEMETRY_TRACING_ENABLED` | `true` | tracing kill-switch (export also needs an OTLP endpoint) |
| `TELEMETRY_STRICT_LABELS` | _(unset → strict in dev/test, lenient in prod/staging)_ | fail fast on a bad label |
| `SERVICE_VERSION` / `GIT_SHA` | from build | `service.version` / `service.git_sha` resource attrs |

### 5.4 Integration seams (where the lib plugs in)

1. `instrumentation/http.py::TelemetryMiddleware` — ASGI RED middleware; extracts
   the inbound `traceparent` and opens the SERVER span. `init_telemetry` adds it
   after every other middleware, so it sits outermost (§8).
2. `libs/db` session/pool — query timing (`instrumentation/db.py`);
   `get_pool_stats` → pool gauges; the RLS-bypass counter rides `session.py`.
3. `libs/events` (`bus.py` + `consumer.py`) — the bus injects `traceparent` into
   the envelope `metadata`; `StreamConsumer` extracts it so a trace follows a fill
   into the ledger. Event metrics live in `llamatrade_events/observability.py`.
4. `libs/alpaca` — the single Alpaca call metric + a CLIENT span per request,
   plus the `llamatrade_alpaca_*` resilience series from `resilience.py`.
5. S2S clients — Connect clients call `inject_headers` at their `_headers()`
   seams (`llamatrade_proto.clients`, portfolio's market-data client, agent tool
   clients); native gRPC calls go through `TelemetryClientInterceptor`
   (`llamatrade_proto.interceptors.telemetry`).
6. Celery (`services/backtest`) — trace context through task message headers
   (`worker_telemetry.py`); queue depth + job states sampled by the API process
   (`queue_metrics.py`).
7. `apps/web` Connect client — interceptor: client RPC latency, errors, trace inject.

### 5.5 No back-compat shims

Services call `init_telemetry` directly. There are no
`llamatrade_common.{metrics,observability,logging}` re-export shims; metrics,
logs, and traces come from `llamatrade_telemetry`, and the event system from
`llamatrade_events`.

---

## 6. Metric catalog

### Tier 0 — Cross-cutting (emitted automatically by the lib for every service)

**Inbound requests (RED)** — HTTP + Connect, one schema
(`instrumentation/http.py`; `/metrics` and `/health` are excluded, and paths
that match no registered route collapse into one `__unmatched__` series):
- `llamatrade_http_requests_total{transport,method,route,status_code,status_class}`
- `llamatrade_http_request_duration_seconds{transport,method,route}` (histogram,
  RPC buckets; unary responses only)
- `llamatrade_http_requests_in_progress{transport,method,route}` (gauge)
- streaming RPCs: `llamatrade_http_streams_total{transport,method,route}` ·
  `llamatrade_http_streams_active{transport,method,route}` (gauge). A
  multi-chunk response is counted once here and excluded from the latency
  histogram, so unbounded stream lifetimes never skew p99.

**Native gRPC peer calls** (client side, recorded by
`TelemetryClientInterceptor` via `instrumentation/grpc.py`; there is no
server-side interceptor, and Connect RPCs are covered by the HTTP middleware):
- `llamatrade_grpc_requests_total{method,status}`

**Outbound dependencies** (uniform across db/redis/peer/external):
- `llamatrade_dependency_requests_total{target,operation,status}`
- `llamatrade_dependency_duration_seconds{target,operation}`

**Alpaca client resilience** (`libs/alpaca`; the calls themselves ride the
dependency series with `target="alpaca"`, `operation=<endpoint>`):
- `llamatrade_alpaca_circuit_transitions_total{state}` (state entered:
  `open`/`half_open`/`closed`)
- `llamatrade_alpaca_rate_limit_throttle_total{mode,outcome}` (mode: `local`
  in-process bucket / `shared` Redis window; outcome: `waited`/`refused`)
- `llamatrade_alpaca_rate_limit_wait_seconds{mode}` (histogram)
- `llamatrade_alpaca_retry_attempts_total{reason}` (bounded retryable-error
  classification)

**Database:**
- `llamatrade_db_query_duration_seconds{operation,table}`
- `llamatrade_db_connections{state}` (`active`/`idle`/`max`; sampled at scrape
  time from the registered pool-stats provider)
- `llamatrade_db_pool_exhausted_total`
- `llamatrade_db_rls_bypass_total{operation}` (`set_rls_bypass`/`system_session` —
  one increment per RLS system-bypass activation, alongside the audit log line
  that carries the caller, reason and tenant scope; identifiers stay off the
  metric)

**Events (`llamatrade_events`, Kafka):** defined in the lib's
`observability.py` through `llamatrade_telemetry` (`counter`/`gauge`), so they
share the naming + label validation. Labelled by the stream's logical prefix only
(`stream_label`, bounded cardinality):
- `llamatrade_events_published_total{stream}`
- `llamatrade_events_publish_failures_total{stream}` (publish attempts that
  raised before the broker confirmed the record(s))
- `llamatrade_events_consumed_total{stream,group,outcome}` (outcome:
  `ok`/`deduped`/`error`/`dlq`/`poison`)
- `llamatrade_events_reconnects_total{stream,mode}` (mode: `tail`/`consume`)
- `llamatrade_events_client_start_failures_total{kind,reason}` (kind:
  `producer`/`consumer`/`probe`/`admin`; reason: `start_timeout`/`liveness_timeout`
  — a client that did not connect or prove its session live within the start
  budget, which is how a rejected OAUTHBEARER token surfaces at all)
- `llamatrade_events_broken_credentials_total{stream,mode}` (a reader past the
  consecutive-start-failure threshold; readers keep retrying, so this is the only
  signal that a credential or broker grant is permanently broken)
- `llamatrade_events_consumer_lag{stream,group}` (gauge — uncommitted
  entries per consumer group, i.e. Kafka consumer lag; the single event-lag metric)
- `llamatrade_events_dlq_depth{stream}` (gauge — entries parked on a
  dead-letter stream, sampled on an interval by `DlqDepthSampler` in the owning
  service)
- `llamatrade_events_fanout_dropped_total{fanout}` ·
  `llamatrade_events_fanout_clients{fanout}` (gauge) — gRPC fan-out backpressure
  drops / connected clients

**Async runtime** (async-first → critical):
- `llamatrade_runtime_event_loop_lag_seconds` · `llamatrade_runtime_asyncio_tasks`
- process CPU/RSS/FDs/GC (default collectors)

**Workers / Celery:**
- `llamatrade_celery_queue_depth{queue}` — pending tasks per broker queue,
  sampled from the backtest API process (Redis `LLEN`; a saturated worker
  cannot report its own backlog). Job states are the `llamatrade_backtest_jobs`
  gauge below; per-worker task metrics are deliberately not built (§10).

**Meta:** service identity (`service.name`, `service.version`, `service.git_sha`,
`deployment.environment`, instance) rides the OTel resource, surfaced by the
Prometheus exporter as `target_info`; there is no separate service-info metric.
`up` and scrape duration come from Prometheus itself.

### Tier 1 — Per-domain business metrics

**Trading** (`metrics.trading.*` + `services/trading/src/metrics.py`,
`recovery.py`) — the crown jewels
- orders: `order_submissions_total{side,type,status}` ·
  `order_submission_latency_seconds` (signal→Alpaca) · `order_slippage_bps{side}` ·
  `fills_total{side,fill_type}` · `fill_processing_duration_seconds`. Rejections
  are the `status="rejected_risk"` / `"rejected_api"` series of
  `order_submissions_total`; fill/partial ratios derive from the above.
- order sync: `orders_synced_total{status_change}` (`filled`/`cancelled`/
  `partial`/`no_change`) · `order_sync_duration_seconds`
- brackets: `bracket_orders_submitted_total{bracket_type}` ·
  `bracket_orders_triggered_total{bracket_type}` (`stop_loss`/`take_profit`) ·
  `bracket_oco_conflicts_total{outcome}` (`both_filled`/`cancelled_already`/
  `lock_contention`)
- risk: `risk_checks_total{result}` · `risk_check_duration_seconds` ·
  `risk_violations_total{violation_type}`
- runner: `active_runners` (gauge) · `signals_generated_total{signal_type}` ·
  `bars_processed_total` · `bar_processing_duration_seconds` ·
  `strategy_errors_total{error_type}` · `strategy_degraded_evals_total`
  (conditions that could not be evaluated, NaN/missing data, treated as False) ·
  `strategy_sub_notional_skips_total` (intended orders under the minimum notional)
- streams: `bar_stream_reconnects_total` · `bar_stream_connected` (gauge) ·
  `bar_stream_latency_seconds` · `trade_stream_reconnects_total` ·
  `trade_stream_connected` (gauge) · `trade_stream_events_total{event_type}`
- reconciliation: `position_reconciliation_total{result}` ·
  `position_reconciliation_duration_seconds` ·
  `position_drift_detected_total{drift_type}` · `position_drift_quantity_pct`
  (histogram, no labels)
- `idempotent_replay_total` (validates crash recovery: ~0 steady-state, >0 after
  deploy) · `session_leases_lost_total` (session ownership leases found dead on
  their own connection)
- session lifecycle: `evaluation_stalls_total` (one per episode where the
  all-symbols evaluation gate stayed shut past the staleness window, so the rate
  reads as sessions that went blind rather than how long they stayed blind) ·
  `symbol_halts_total{reason}` (reason: `unknown`/`inactive`/`not_tradable` —
  subscribed symbols the broker stopped listing as active and tradable)
- circuit breaker: `circuit_breaker_triggered_total{reason}`
- ledger emission: `ledger_events_published_total{kind,status}` — publish failures are the
  `status="failure"` series (no separate counter), and the `LedgerPublishFailures` alert
  matches that expression.
- Per-session financial gauges (daily P&L, drawdown, position value) are not
  emitted: tenant/session are forbidden labels, and those values are served by
  the ledger and structured logs.

**Ledger / portfolio** (`metrics.ledger.*` + `services/portfolio/src/metrics.py`,
`tasks/`) — integrity is everything
- ingestion & fold: `events_ingested_total{result}` ·
  `event_append_latency_seconds` · `projection_fold_duration_seconds` ·
  `poison_events_total` (unapplicable events skipped during a projection fold) ·
  `incomplete_projection_reads_total` (reads served from a projection degraded by
  skipped poison events; the warning log names the account)
- fill consumer: `fill_consumer_active` (gauge, 1 on the pod holding the
  fill-consumer lock; the sum across pods should be 1) · `fill_dlq_depth`
  (gauge, `llamatrade_ledger_fill_dlq_depth` — un-booked fills parked on
  `ledger:fills:dlq`, sampled by the lag monitor; alerted by `LedgerFillDLQBacklog`)
- writer election: `writer_active` (gauge, 1 on the pod holding the
  ledger-writer advisory lock that gates the reconciliation and equity-snapshot
  loops) · `writer_fenced_total` (sweep passes refused because the lock was lost
  mid-leadership)
- reconciliation: `reconciliation_drift_total{kind}` · `drift_actions_total{action}` ·
  `sleeves_frozen_total` (alerted by `LedgerSleeveFrozen` — a freeze is an
  integrity incident) · `reconcile_stale_accounts` (gauge — accounts whose last
  successful reconcile is older than 3x the reconcile interval)
- vs broker: `ledger_vs_broker_mismatch_dollars` (gauge, should be ~0) ·
  `ledger_vs_broker_cash_mismatch_dollars` (gauge, sleeve cash vs broker cash,
  should be ~0; alerted by `LedgerCashVsBrokerMismatch`)
- capital: `capital_allocated_dollars` / `capital_unallocated_dollars` (gauge) ·
  `capital_insufficient_total`
- corporate actions: `corporate_action_proposals_total{kind}` (`split`/
  `symbol_change`/`dividend`) · `corporate_action_proposals_open` (gauge) ·
  `corporate_actions_unsupported_total{type}` (announcements no ledger planner
  models)
- per-strategy realized/unrealized P&L + Sharpe/Sortino/maxDD → **ledger/Postgres**,
  surfaced as bounded top-N gauges only if dashboards need them

**Market data** (`metrics.marketdata.*` + `services/market-data/src/metrics.py`)
- streams: `stream_reconnects_total` (the ingestor's Alpaca stream) ·
  `stream_message_lag_seconds` (Alpaca ts→received) ·
  `bar_publish_lag_seconds` (bar timestamp→internal-bus publish, the ingest
  write-through) · `bar_fanout_lag_seconds` (bar timestamp→StreamManager
  fan-out, end-to-end lag in bus-mode serving) ·
  `broadcast_circuit_breaker_transitions_total{state}` (`open`/`closed`).
  Fan-out backpressure rides the events series
  (`llamatrade_events_fanout_dropped_total` / `_fanout_clients`).
- data quality: `data_staleness_seconds{data_type}` (`bars`/`quotes`/`trades`,
  age of served data) · `data_gaps_detected_total` (interior holes in served
  intraday bar series) · `missing_symbol_errors_total`
- ingest universe (declared in the service, so listed under its full name):
  `llamatrade_marketdata_ingest_universe_symbols{kind}` (gauge, kind:
  `baseline`/`live`/`total` — the derived set the singleton ingestor streams),
  `llamatrade_marketdata_ingest_universe_refresh_failures_total{reason}` (reason:
  `query`/`subscribe` — a refresh that kept the previous set),
  `llamatrade_marketdata_ingest_targeted_backfills_total{outcome}` (outcome:
  `ok`/`error` — catch-up passes for symbols that just entered the universe).
  Symbol counts are aggregate only; per-symbol labels are forbidden and the
  ingest logs name the symbols that entered or left.
- Alpaca REST calls ride `llamatrade_dependency_*{target="alpaca"}` and the
  `llamatrade_alpaca_*` resilience series (Tier 0); the service defines no
  Alpaca request metrics of its own.

**Strategy / DSL / compiler** (`metrics.strategy.*`)
- `dsl_parse_errors_total{kind}` · `compile_duration_seconds`
- `versions_minted_total` · `template_instantiations_total{template}`

**Backtest** (`metrics.backtest.*` + `queue_metrics.py`, `backtest_service.py`)
- lifecycle: `jobs_total{state}` (counter of state transitions: `enqueued`/
  `running`/`completed`/`failed`/`cancelled`) · `llamatrade_backtest_jobs{state}`
  (gauge sampled from the backtests table by the API process under the audited
  RLS bypass: `running`/`pending` are point-in-time counts, `completed`/`failed`
  count the trailing hour)
- `execution_duration_seconds` · `market_data_fetch_failures_total` ·
  `progress_publish_failures_total`
- run health (full names `llamatrade_backtest_strategy_*`):
  `strategy_degraded_evals_total` · `strategy_sub_notional_skips_total` — the
  backtest counterparts of the trading runner's degraded-eval / sub-notional
  series, reported when a run finishes
- broker backlog: `llamatrade_celery_queue_depth{queue}`, sampled by the API
  process (Tier 0); workers and beat expose no listener

**Billing** (`metrics.billing.*`)
- `invoice_paid_total{plan}` · `invoice_payment_failed_total{plan}`
- `webhook_received_total{event_type}` · `webhook_signature_failures_total` (security)
- `webhook_handler_duration_seconds{event_type}` · `webhook_idempotency_duplicates_total`
- `plan_limit_exceeded_total{limit}`
- Stripe calls ride `llamatrade_dependency_*{target="stripe",operation=…}`
- MRR/ARR and subscription-state gauges are wanted-later intents (§10); revenue
  aggregates come from billing data, not scrape-time state

**Auth / security** (`metrics.auth.*`)
- `registrations_total` · `logins_total` · `login_failures_total{reason}` (brute-force)
- `tokens_issued_total{type}` · `token_validation_failures_total{reason}`
- `bcrypt_hash_duration_seconds`
- `credential_decryption_failures_total` · `api_key_validation_failures_total{reason}`
- `cross_tenant_access_attempts_total` (**security alarm**)
- guard backends (Redis; declared in `ratelimit.py` / `revocation.py`, so listed under their full
  names): `llamatrade_auth_ratelimit_backend_errors_total`,
  `llamatrade_auth_revocation_backend_errors_total` (a sustained increase means the guard is
  degraded; alerted by `AuthRateLimitBackendErrors` / `AuthRevocationBackendErrors`)

**Notification** (`metrics.notification.*`)
- `alerts_triggered_total{type}` · `alerts_cooldown_skipped_total`
- `deliveries_total{channel}` · `delivery_failures_total{channel,reason}` · `delivery_latency_seconds{channel}`
- alert-eval latency and an unread-backlog gauge are wanted-later intents (§10)
- The delivery consumer's health rides the generic events series:
  `llamatrade_events_consumed_total{stream="notifications",group="notification-delivery"}` for
  outcomes and `llamatrade_events_consumer_lag{stream="notifications"}` for backlog; webhook
  auto-disables surface as `delivery_failures_total{channel="webhook"}` plus the tenant-facing
  WEBHOOK_DISABLED notification itself

**Agent / LLM** (`metrics.agent.*`)
- `llm_requests_total{model,result}` · `llm_latency_seconds{model}`
- `llm_tokens_total{model,direction}` · `llm_errors_total{type}`
- LLM cost, time-to-first-token, and per-tool-call counters are wanted-later
  intents (§10)

### Tier 2 — SLOs, KPIs & cost

**SLOs (with error budgets + multi-window burn-rate alerts):**

| SLO | Indicator | Target (initial) |
|---|---|---|
| Service availability | `1 - rate(5xx)/rate(all)` per service | 99.9% |
| Order submission latency | `order_submission_latency_seconds` p99 | < 1s |
| Order success | `fills / submissions` | > 99% (ex-market-reject) |
| Market-data freshness | `stream_message_lag_seconds` p95 | < 2s |
| Ledger reconciliation freshness | time since last clean reconcile | < 5 min |
| Backtest completion | `execution_duration_seconds` p95 | < 120s |

**Trace-derived end-to-end:** signal→fill wall-clock; backtest request→result;
fill→ledger-projection lag (span links across services).

**Business KPIs** (from ledger/billing data + log-based metrics, **not** labels):
MRR/ARR, churn, trial conversion, activation funnel (signup→strategy→backtest→live),
DAU/WAU, strategies-live, capital under management.

**Cost:** Alpaca rate-limit utilization, LLM `$`/period, notification (SMS) spend,
cloud spend. Per-tenant unit economics via log-based aggregation / ledger, not metrics.

---

## 7. Structured logs

JSON (`JSONFormatter`) on every service, with fields:
`timestamp, level, logger, message, service, request_id, tenant_id, user_id,
trace_id, span_id, location, exception, extra`.

- `trace_id`/`span_id` injected from the active OTel span → click from a log
  to its trace.
- Context via `contextvars` set by the RED middleware (`set_request_context`).
- Noise suppression for `uvicorn.access`, `httpx`, `httpcore`.
- Log-based metrics/alerts (Loki ruler / Cloud Logging) cover per-tenant slices
  that must not become Prometheus labels.

---

## 8. Traces

Propagation is W3C `traceparent`/`tracestate` end to end. Where each hop is
made:

- **Roots:** the browser mints a fresh, sampled `traceparent` (flags `01`) per
  RPC (`apps/web/src/telemetry/trace.ts`), so every backend span of a
  user-initiated flow parents into the browser's trace.
- **SERVER spans:** `TelemetryMiddleware` extracts the inbound context and opens
  one SERVER span per request. `init_telemetry` adds the middleware after every
  other `add_middleware` call, so it sits outermost: auth/CORS rejections
  (401s included) still get spans and RED series.
- **Service-to-service (Connect):** clients inject via
  `llamatrade_telemetry.inject_headers` at their `_headers()` seams — the proto
  ledger and market-data clients (`llamatrade_proto.clients`), portfolio's
  market-data client, and the agent tool clients.
- **Service-to-service (native gRPC):** `TelemetryClientInterceptor` opens a
  CLIENT span and injects into call metadata; the callee's HTTP middleware is
  not involved for these, and there is no server-side interceptor.
- **Events (Kafka):** `EventBus.publish` injects the context into the envelope
  metadata; `StreamConsumer` extracts it and runs each handler inside a CONSUMER
  span, so a fill's trace continues into the ledger. Exception: the portfolio
  fill loop consumes `ledger:fills` via `consume_raw` directly and does not
  extract; its migration onto `StreamConsumer` is a locked decision, pending
  (§10).
- **Celery (backtest):** the API injects into the task message headers
  (`apply_async(headers=inject_headers())`); worker `task_prerun`/`task_postrun`
  signals open and close a CONSUMER span per task. A message with no trace
  headers (reaper re-enqueue, beat schedule) becomes a new root. Workers, beat,
  and the market-data ingestor all run `init_telemetry`.
- **Outbound dependencies:** `time_dependency` opens a CLIENT span per call
  (Alpaca, Stripe, peer services).
- **Span attributes:** `tenant_id`, `session_id`, `client_order_id`, `symbol`,
  `sleeve_id` (high-cardinality is fine on spans). `X-Request-ID` is bridged to
  the request context for log correlation.
- **Sampling:** `parentbased_traceidratio` at ratio 0.1 by default
  (`OTEL_TRACES_SAMPLER` / `_ARG`). Browser-minted parents carry the sampled
  flag, so user-initiated flows are sampled at 100%; the 10% ratio applies to
  background roots (consumers, schedulers, samplers).
- **Export:** OTLP/HTTP → OTel Collector (§9). With no endpoint configured,
  spans are still recorded (so `trace_id` appears in logs) but nothing exports.
- **Not built** (future work, if wanted): error-biased sampling, exemplars on
  latency histograms, and named money-path spans. Services contain no manual
  `span()` call sites; service-internal steps appear in a trace only as the
  middleware, dependency, and consumer spans above.

---

## 9. Infrastructure

- **docker-compose (dev):** `prometheus`, `alertmanager`, `otel-collector`,
  `tempo`, and `grafana` run beside the app services
  (`infrastructure/docker/docker-compose.dev.yml`, configs under
  `infrastructure/observability/`). Every backend container (backtest worker and
  beat and the market-data ingestor included) sets
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`; the collector
  batches and exports traces to Tempo, keeping the `debug` exporter as a
  secondary sink. Grafana provisions two datasources, Prometheus and Tempo.
- **Scraping (dev):** Prometheus scrapes the nine services' `/metrics` on their
  app ports, the market-data ingestor's admin listener on 8841, and the
  collector's own metrics on 8888. The `job` label carries the service name
  (metrics themselves have no `service` label). Alert rules live in
  `infrastructure/observability/prometheus/alerts.yml`.
- **Backtest worker/beat are intentionally listener-less:** the broker backlog
  (`llamatrade_celery_queue_depth`) and job states (`llamatrade_backtest_jobs`)
  are sampled by the API process (§6), so nothing scrapes the workers.
- **Kubernetes:** every service deployment plus the market-data ingestor carries
  `prometheus.io/scrape|port|path` annotations; a `PrometheusRule` mirrors the
  SLO/burn-rate alerts. The k8s collector exports traces to the `debug`
  exporter until a managed backend is provisioned (§10).
- **GCP:** OTLP → Cloud Trace via the collector's `googlecloud` exporter (kept
  commented in the config until credentials are wired); Prometheus → Managed
  Service for Prometheus, or keep self-hosted Prometheus + Grafana. Existing
  Terraform uptime checks stay.
- **Dashboards-as-code:** Platform/RED ships
  (`grafana/dashboards/platform-red.json`); the remaining domain folders
  (Trading, Ledger, Market Data, Backtest, Billing, Auth-Security, Notification,
  Agent, SLOs) are listed under Remaining work.

---

## 10. Remaining work

- **Portfolio fill loop → `StreamConsumer`** (locked decision, pending): the
  loop drives `consume_raw` directly with its own dedupe/DLQ handling, so
  `ledger:fills` consumption lacks the standard
  `llamatrade_events_consumed_total{outcome}` series and per-event CONSUMER
  spans (§8). Migrating it closes both gaps.
- **Wanted-later instruments**, recorded here as intents (nothing is declared in
  code): billing MRR/ARR and subscription-state gauges; agent LLM cost,
  time-to-first-token, and per-tool-call counters; trading submit→fill latency;
  strategy indicator/signal evaluation durations; notification alert-eval
  latency and an unread-backlog gauge.
- **Per-worker Celery task metrics are deliberately not built.** Workers and
  beat expose no listener; the API-side samplers (`llamatrade_backtest_jobs`
  from the backtests table, `llamatrade_celery_queue_depth` from the broker)
  answer the operator questions without per-worker scrape targets.
- **Managed trace backend for k8s**: the k8s collector exports traces to the
  `debug` exporter until one is provisioned (§9).
- **A hook parameter on the market-data stream singleton factory**: the ingestor
  installs its reconnect hook with a `setattr` on the stream instance today.
- **Error-biased sampling, exemplars, and named money-path spans** if wanted
  (§8).
- Build out the dashboards-as-code beyond Platform/RED (Trading, Ledger,
  Market Data, Backtest, Billing, Auth-Security, Notification, Agent, SLOs).
- Keep `libs/telemetry` at ≥80% coverage as domains are added.

---

## 11. Rules of thumb (for contributors)

- Adding a metric? Pick the domain namespace in `llamatrade_telemetry/domain.py`
  (or, for a service-scoped instrument, the validated `registry` factories in the
  service's `metrics.py`), name it per §4.1, use only §4.2 labels. The
  `conventions` validators reject violations.
- Never put an id/email/url/symbol on a counter or histogram label.
- Need per-tenant numbers on a dashboard? Use logs/traces or a bounded top-N
  gauge — never a `tenant_id` label.
- Telemetry must never raise into the request path. Recorders swallow their own
  errors (the pool observer and the API-side samplers all do), and label
  mistakes log-and-drop in prod (§5.3).
