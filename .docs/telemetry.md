# Telemetry & Observability

> Source of truth for **what** LlamaTrade reports and **how** the unified
> `llamatrade_telemetry` library emits it. Every service, lib, and the web app
> conform to this document. If you add a metric/span/log, add it here first.

Status: **design locked, migration in progress.** See the task list / commit
history for what has shipped.

---

## 1. Goals & principles

1. **One library, one setup call.** Every service gets metrics + structured logs
   + traces + a `/metrics` endpoint from a single `init_telemetry(app, service=…)`.
   No more three divergent setups (`setup_observability` vs hand-rolled `/metrics`
   vs `enable_db_pool_metrics`).
2. **No duplication.** A concept is instrumented **once**. Today
   `alpaca_api_calls_total` is defined in three places (`libs/alpaca`,
   `services/trading`, `services/market-data` as `market_data_alpaca_*`). After
   migration there is exactly one Alpaca call metric, owned by `libs/alpaca` via
   telemetry conventions.
3. **OTel-native, Prometheus-exposed.** Instruments are created through the
   OpenTelemetry API; a `PrometheusMetricReader` exposes them at `/metrics` for
   scraping. Traces export via OTLP. This gives us distributed tracing across the
   9-service `signal → risk → order → fill → ledger` path (we have none today)
   without giving up Prometheus dashboards.
4. **Three signals, three jobs** (see §3). Metrics answer *aggregate* questions,
   logs answer *drill-down*, traces answer *why was this one request slow*.
5. **Cardinality is sacred** (see §4). `tenant_id`/`session_id` never become
   Prometheus labels. They live on logs/traces; `plan` is the per-segment label.
6. **Graceful degradation.** If no OTLP collector is configured, tracing no-ops;
   if `prometheus_client` is missing, metrics no-op (matches the existing
   `libs/alpaca` pattern). Telemetry must never crash a request or a worker.
7. **Async-first, strictly typed.** No blocking calls in async paths; no `Any`.

---

## 2. Current state (what this replaces)

| Area | Today | After |
|---|---|---|
| Setup | 3 patterns; only `market-data` runs full `setup_observability` | one `init_telemetry()` everywhere |
| Metrics defs | `libs/common/metrics.py` (22 std) + `trading/metrics.py` (573 lines) + `market-data/metrics.py` (161) + `portfolio/metrics.py` (49) + `libs/alpaca/metrics.py` | `llamatrade_telemetry` core + typed domain namespaces |
| Alpaca metrics | defined 3× under 3 names | 1 set in `libs/alpaca` |
| Logging | full JSON formatter exists, only `market-data` configures it | configured everywhere, with `trace_id`/`span_id` |
| Tracing | none (only an `X-Request-ID` header) | OTel spans + W3C propagation across services |
| Events (`llamatrade_events`) | n/a (predecessor `eventbus_*` shim removed) | `llamatrade_events_published_total`, `llamatrade_events_consumed_total{outcome}`, `llamatrade_events_reconnects_total`, `llamatrade_events_consumer_lag` (via the telemetry registry; W3C trace propagated through the envelope) |
| Scraping | every service exposes `/metrics`; **nothing scrapes them** | Prometheus + Grafana + OTel Collector + Alertmanager (compose + k8s) |
| Frontend | `console.error` only | `@llamatrade/telemetry`: web-vitals, RPC latency, JS errors, trace propagation |
| Workers | Celery backtests have **zero** task/queue metrics | full Celery instrumentation |

---

## 3. The three-signal model

| Signal | Backend | Cardinality | Carries tenant/session? | Answers |
|---|---|---|---|---|
| **Metrics** | Prometheus (via OTel) | **low** — each label combo is a stored series | **no** (labels); `plan` yes | "fleet p99 order latency? error rate up?" |
| **Logs** | JSON → Loki / Cloud Logging | high — fine | **yes**: `request_id`, `tenant_id`, `user_id`, `trace_id` | "everything that happened for tenant X" |
| **Traces** | OTLP → Tempo / Cloud Trace | high — fine | **yes** as span attributes | "why was *this* order slow end-to-end" |

**Exemplars** link a histogram bucket to a `trace_id`, so a latency spike on a
Grafana panel clicks straight through to the exact slow trace.

### How per-tenant dashboards work without tenant labels on metrics

There are three different "per-tenant numbers" people conflate:

1. **Per-tenant business data** (P&L, positions, MRR) — **not telemetry**. It is
   served from the **ledger / Postgres** via the portfolio/billing APIs. The
   user-facing "your P&L" view reads the double-entry ledger; that is the source
   of truth, never a Prometheus label.
2. **Per-tenant operational drill-down** (this tenant's error rate / slow calls) —
   **logs + traces**. Grafana `tenant_id` template variable → LogQL/Cloud Logging
   query; click an exemplar → the tenant's trace in Tempo.
3. **Aggregate operational health** (95% of dashboards) — **metrics**, sliced by
   bounded labels: `service`, `route`, `status`, and `plan`.

Escape hatches when Prometheus genuinely needs a customer dimension:
**bounded top-N gauges** (app-side, e.g. top-20 tenants by order volume) and
**exemplars**.

---

## 4. Conventions (enforced by the lib)

### 4.1 Metric naming

`llamatrade_<domain>_<noun>_<unit>` — e.g. `llamatrade_trading_order_fill_latency_seconds`.

- Units are explicit suffixes: `_seconds`, `_bytes`, `_total` (counters),
  `_ratio`, `_dollars`, `_bps`, `_count`/gauge nouns.
- Domains: `http`, `grpc`, `db`, `cache`, `eventbus`, `runtime`, `celery`,
  `trading`, `ledger`, `marketdata`, `strategy`, `backtest`, `billing`, `auth`,
  `notification`, `agent`, `slo`.
- OTel instrument names use dots (`trading.order.fill_latency`) and the
  Prometheus exporter mangles them to the underscored form above. The
  `conventions.py` validator asserts the mapping so names never drift.

### 4.2 Allowed label set (bounded)

A central allow-list. Adding a label not on it fails the `conventions` validator
in tests.

| Label | Values (bounded) | Notes |
|---|---|---|
| `service` | the 9 service names + lib names | always present |
| `transport` | `http`, `connect`, `grpc` | inbound/outbound |
| `method` | HTTP verb or RPC method name | RPC method names are bounded by the proto |
| `route` | normalized path / RPC | path params collapsed (existing `_get_endpoint`) |
| `operation` | dependency op (`select`, `xadd`, `submit_order`…) | |
| `target` | dependency (`postgres`, `redis`, `alpaca`, `stripe`, peer service) | |
| `status` / `status_code` / `status_class` | `ok`/`error`, code, `2xx`… | |
| `result` | `hit`/`miss`/`error`, `success`/`failure`, `passed`/`failed` | |
| `plan` | `free`/`starter`/`pro` | **the** per-segment business label |
| `kind`/`type`/`side`/`reason`/`event_type`/`channel`/`model`/`data_type` | small enums per domain | each domain declares its allowed values |

**Forbidden as labels:** `tenant_id`, `session_id`, `user_id`, `order_id`,
`client_order_id`, `symbol`* , `backtest_id`, `request_id`, raw URLs, emails.

\* `symbol` is allowed **only** on a deliberately bounded top-N gauge, never on
counters/histograms.

### 4.3 Histogram buckets (standardized)

- **RPC/HTTP latency:** `0.005,0.01,0.025,0.05,0.075,0.1,0.25,0.5,0.75,1,2.5,5,7.5,10` (s)
- **Dependency/db:** `0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5` (s)
- **Order/market latency (tight):** `0.001,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1` (s)
- **Job duration (backtest):** `1,5,10,30,60,120,300,600,1800` (s)
- **Slippage:** bps buckets `1,2,5,10,25,50,100,250`

---

## 5. The `llamatrade_telemetry` library

### 5.1 Module layout

```
libs/telemetry/llamatrade_telemetry/
├── __init__.py        # init_telemetry, get_logger, get_tracer, metrics, shutdown
├── config.py          # TelemetrySettings (pydantic-settings): exporters, sampling, env, log fmt
├── conventions.py     # name/label constants + validator (rejects ad-hoc names/labels)
├── registry.py        # MeterProvider + PrometheusMetricReader → CollectorRegistry; instrument cache
├── setup.py           # init_telemetry(app, service, version): wires everything; idempotent
├── exporters.py       # /metrics exposition (generate_latest) + OTLP trace exporter wiring
├── metrics/
│   ├── http.py        # ASGI RED middleware (replaces ObservabilityMiddleware)
│   ├── grpc.py        # gRPC/Connect server + client interceptors
│   ├── db.py          # SQLAlchemy query timing + pool observer (keeps PoolStatsLike)
│   ├── cache.py       # redis/cache op timing + hit/miss
│   ├── eventbus.py    # publish/consume/lag/reconnect/ack/dlq recorders
│   ├── runtime.py     # event-loop lag + process collectors
│   ├── celery.py      # task/queue/lag signals
│   └── domain.py      # typed namespaces: metrics.trading.*, metrics.ledger.*, …
├── logging/
│   ├── config.py      # JSON formatter (moved from common) + stdlib config
│   └── context.py     # contextvars: request_id, tenant_id, user_id (+ trace_id/span_id from span)
└── tracing/
    ├── provider.py    # TracerProvider + OTLP exporter (graceful no-op without collector)
    ├── propagation.py # W3C traceparent inject/extract; bridges X-Request-ID
    └── instrument.py  # @traced decorator, span() context manager, exemplar helper
```

Companion web package: `apps/web/src/telemetry/` (`@llamatrade/telemetry`).

### 5.2 Public API

```python
from llamatrade_telemetry import init_telemetry, get_logger, metrics

# one call — replaces setup_observability / enable_db_pool_metrics / hand-rolled /metrics
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
with metrics.trading.fill_latency.time():
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
| `TELEMETRY_METRICS_ENABLED` | `true` | kill-switch |
| `SERVICE_VERSION` / git sha | from build | `service_info` / resource |

### 5.4 Integration seams (where the lib plugs in)

1. `libs/common/middleware.py` — RED middleware + trace context start; propagate
   `traceparent` + `X-Tenant-ID`/`X-User-ID` to downstream `ServiceClient` calls.
2. `libs/db` session/pool — query span + timing; `get_pool_stats` → pool gauges.
3. `libs/common/eventbus.py` — publish/consume recorders + span links; inject
   `traceparent` into stream entry metadata so a trace follows a fill into the ledger.
4. `libs/alpaca` — the single Alpaca call metric + a client span per request.
5. Celery app (`services/backtest`) — task lifecycle + queue depth.
6. `apps/web` Connect client — interceptor: client RPC latency, errors, trace inject.

### 5.5 Back-compat during migration

`llamatrade_common.{metrics,observability,logging}` keep working as **thin
re-export shims** pointing at `llamatrade_telemetry` so the workspace stays green
while services migrate one by one. Shims are deleted in the final cleanup once no
service imports them.

---

## 6. Metric catalog

### Tier 0 — Cross-cutting (emitted automatically by the lib for every service)

**Inbound requests (RED)** — HTTP + Connect + gRPC, one schema:
- `llamatrade_http_requests_total{transport,method,route,status_code,status_class}`
- `llamatrade_http_request_duration_seconds{transport,method,route}` (histogram, RPC buckets)
- `llamatrade_http_requests_in_progress{transport,method,route}` (gauge)
- `llamatrade_http_request_size_bytes` / `_response_size_bytes` (histogram, optional)
- streaming RPCs: `llamatrade_grpc_stream_active{method}` (gauge),
  `llamatrade_grpc_stream_messages_total{method,direction}`,
  `llamatrade_grpc_stream_duration_seconds{method}`

**Outbound dependencies** (uniform across db/redis/peer/external):
- `llamatrade_dependency_requests_total{target,operation,status}`
- `llamatrade_dependency_duration_seconds{target,operation}`

**Database:**
- `llamatrade_db_query_duration_seconds{operation,table}`
- `llamatrade_db_connections{state}` (`active`/`idle`/`max` — folds today's 3 gauges)
- `llamatrade_db_pool_acquire_wait_seconds`
- `llamatrade_db_pool_exhausted_total`
- `llamatrade_db_transactions_total{result}` · `llamatrade_db_errors_total{type}`

**Cache / Redis:**
- `llamatrade_cache_operations_total{cache,op,result}` (folds hits/misses)
- `llamatrade_cache_op_duration_seconds{cache,op}`

**Events (`llamatrade_events`, Redis Streams):** the lib's `observability.py`
metrics (plain `prometheus_client`, bridged into the telemetry export), labelled by
the stream's logical prefix only (bounded cardinality):
- `events_published_total{stream}`
- `events_consumed_total{stream,group,outcome}` (outcome: `ok`/`deduped`/`dlq`/`error`)
- `events_reconnects_total{stream,mode}` (tail/consume reconnects)
- `events_consumer_lag{stream,group}` (gauge — delivered-but-unacked pending count;
  the single event-lag metric, supersedes both `llamatrade_eventbus_*` and
  `portfolio_ledger_stream_pending`)

**Async runtime** (async-first → critical):
- `llamatrade_runtime_event_loop_lag_seconds` · `llamatrade_runtime_asyncio_tasks`
- process CPU/RSS/FDs/GC (default collectors)

**Workers / Celery:**
- `llamatrade_celery_tasks_total{task,state}` · `llamatrade_celery_task_duration_seconds{task}`
- `llamatrade_celery_queue_depth{queue}` · `llamatrade_celery_task_queue_wait_seconds{task}`
- `llamatrade_celery_workers_active` · `llamatrade_celery_task_retries_total{task}`

**Meta:** `llamatrade_service_info{service,version,git_sha,environment}` (existing
`SERVICE_INFO`), `up`, scrape duration.

### Tier 1 — Per-domain business metrics

**Trading** (`metrics.trading.*`) — the crown jewels
- `order_submissions_total{side,type,status}` · `order_submission_latency_seconds` (signal→Alpaca)
- `order_fill_latency_seconds` (submit→fill) · `order_slippage_bps{side}` · `fills_total{side,fill_type}`
- `order_rejections_total{reason}` · fill/partial/cancel ratios derivable from the above
- risk: `risk_checks_total{result}`, `risk_violations_total{type}`,
  `daily_pnl_dollars` (top-N gauge), `drawdown_pct` (top-N gauge)
- runner: `active_runners` (gauge), `signals_generated_total{signal_type}`,
  `bar_processing_duration_seconds`, `strategy_errors_total{error_type}`
- streams: `bar_stream_reconnects_total`, `bar_stream_connected` (gauge),
  `trade_stream_reconnects_total`, `trade_stream_connected`, `bar_stream_latency_seconds`
- reconciliation: `position_reconciliation_total{result}`,
  `position_drift_detected_total{drift_type}`, `position_drift_quantity_pct{}` (bounded)
- `idempotent_replay_total` (validates crash recovery: ~0 steady-state, >0 after deploy)
- circuit breaker: `circuit_breaker_state` (gauge 0/1/2), `circuit_breaker_triggered_total{reason}`

**Ledger / portfolio** (`metrics.ledger.*`) — integrity is everything
- `events_ingested_total{result}` (existing) · `event_append_latency_seconds`
- `projection_fold_duration_seconds`
- `reconciliation_drift_total{kind}` + `drift_actions_total{action}` (existing)
- `ledger_vs_broker_mismatch_dollars` (gauge, should be ~0) · `sleeves_frozen_total`
- `capital_allocated_dollars` / `capital_unallocated_dollars` (gauge),
  `capital_insufficient_events_total`
- per-strategy realized/unrealized P&L + Sharpe/Sortino/maxDD → **ledger/Postgres**,
  surfaced as bounded top-N gauges only if dashboards need them

**Market data** (`metrics.marketdata.*`)
- `cache_hit_ratio{data_type}` (derived) · `alpaca_request_duration_seconds{endpoint}` (via libs/alpaca)
- `rate_limit_tokens_available` (gauge) · `circuit_breaker_state` (gauge)
- streams: `stream_connections` (gauge), `stream_subscriptions{type}` (gauge),
  `stream_reconnects_total`, `stream_message_lag_seconds` (Alpaca ts→received),
  `client_queue_dropped_total` (backpressure loss)
- data quality: `data_staleness_seconds{data_type}` (bounded), `data_gaps_detected_total`,
  `missing_symbol_errors_total`

**Strategy / DSL / compiler** (`metrics.strategy.*`)
- `strategies_total{status}` (gauge) · `versions_minted_total`
- `dsl_parse_errors_total{kind}` · `compile_duration_seconds` · `max_lookback_bars` (histogram)
- `indicator_compute_duration_seconds{indicator}` · `signal_eval_duration_seconds`
- `template_instantiations_total{template}`

**Backtest** (`metrics.backtest.*`)
- `jobs_total{state}` · `queue_depth` (gauge) · `execution_duration_seconds`
- `bar_throughput_bars_per_second` · `cache_hit_ratio{tier}` (lru/redis/timescale/parquet)
- `market_data_fetch_failures_total` · `progress_publish_failures_total`
- data quality: `data_gaps_detected_total`, `missing_symbol_errors_total`

**Billing** (`metrics.billing.*`)
- `subscriptions_total{plan,state}` (gauge) · churn/trial-conversion derived
- `invoice_payment_failed_total{plan}` · `invoice_paid_total{plan}`
- `webhook_received_total{event_type}` · `webhook_signature_failures_total` (security)
- `webhook_handler_duration_seconds{event_type}` · `webhook_idempotency_duplicates_total`
- `plan_limit_exceeded_total{limit}` · `mrr_dollars` / `arr_dollars` (gauge)
- `stripe_request_duration_seconds{operation}` (via dependency metrics, `target=stripe`)

**Auth / security** (`metrics.auth.*`)
- `registrations_total` · `logins_total` · `login_failures_total{reason}` (brute-force)
- `tokens_issued_total{type}` · `token_validation_failures_total{reason}`
- `bcrypt_hash_duration_seconds`
- `credential_decryption_failures_total` · `api_key_validation_failures_total{reason}`
- `cross_tenant_access_attempts_total` (**security alarm**)

**Notification** (`metrics.notification.*`)
- `alerts_total{type}` (gauge) · `alerts_triggered_total{type}` · `alerts_cooldown_skipped_total`
- `alert_eval_latency_seconds`
- `deliveries_total{channel}` · `delivery_failures_total{channel,error}` · `delivery_latency_seconds{channel}`
- `unread_backlog` (gauge — alert-fatigue signal)

**Agent / LLM** (`metrics.agent.*`) — net-new for the final product
- `llm_requests_total{model,result}` · `llm_latency_seconds{model}` · `llm_ttft_seconds{model}`
- `llm_tokens_total{model,direction}` · `llm_cost_dollars{model}`
- `llm_errors_total{type}` (rate_limit/refusal/timeout/cutoff) · `tool_calls_total{result}`

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

JSON (existing `JSONFormatter`) on every service, with fields:
`timestamp, level, logger, message, service, request_id, tenant_id, user_id,
trace_id, span_id, location, exception, extra`.

- `trace_id`/`span_id` injected from the active OTel span (new) → click from a log
  to its trace.
- Context via `contextvars` set by the RED middleware (existing
  `set_request_context` extended with trace ids).
- Noise suppression for `uvicorn.access`, `httpx`, `httpcore` (existing).
- Log-based metrics/alerts (Loki ruler / Cloud Logging) cover per-tenant slices
  that must not become Prometheus labels.

---

## 8. Traces

- **Propagation:** W3C `traceparent`/`tracestate`. Inbound middleware extracts;
  `ServiceClient` + `libs/alpaca` + EventBus inject. `X-Request-ID` is bridged to
  the trace for back-compat.
- **Key spans (the money path):** `connect.SubmitOrder` → `risk.check` →
  `alpaca.submit_order` → (async) `trade_stream.fill` → `eventbus.publish ledger:fills`
  → `ledger.ingest` → `ledger.project`. EventBus carries `traceparent` in the
  stream entry so the async fill→ledger hop stays in one trace via span links.
- **Span attributes:** `tenant_id`, `session_id`, `client_order_id`, `symbol`,
  `sleeve_id` (high-cardinality is fine on spans).
- **Sampling:** parent-based ratio (default 10%), with always-sample for errors;
  exemplars on latency histograms point into sampled traces.
- **Export:** OTLP → OTel Collector → Tempo/Cloud Trace. No endpoint configured →
  tracing no-ops (dev default).

---

## 9. Infrastructure

- **docker-compose (dev):** add `prometheus`, `grafana`, `otel-collector`,
  `alertmanager`. Prometheus scrapes each service `/metrics`; collector receives
  OTLP traces.
- **Kubernetes:** `PodMonitor`/`ServiceMonitor` per deployment (scrape `/metrics`),
  `PrometheusRule` for SLO/burn-rate alerts, collector as a Deployment/DaemonSet.
- **GCP:** OTLP → Cloud Trace; Prometheus → Managed Service for Prometheus, or keep
  self-hosted Prometheus + Grafana. Existing Terraform uptime checks stay.
- **Dashboards-as-code:** one folder per domain (Platform/RED, Trading, Ledger,
  Market Data, Backtest, Billing, Auth-Security, Notification, Agent, SLOs).

---

## 10. Migration plan (the "one pass")

Ordered because services import the lib:

1. **Lib foundation** — `libs/telemetry` core (config, conventions, metrics
   bridge, logging, runtime) + tests. *(this lands first; everything imports it)*
2. **Instrumentation + tracing + domain namespaces + `init_telemetry`** + tests.
3. **Back-compat shims** in `llamatrade_common` → green workspace.
4. **Libs migrate**: `alpaca` (collapse 3 Alpaca metrics → 1), `eventbus`
   (add lag/ack/dlq, keep names), `db` (query/pool via telemetry).
5. **Services migrate** (parallelizable, one per agent): swap setup → `init_telemetry`,
   delete per-service `metrics.py`, wire domain metrics + tracing + JSON logs.
6. **Frontend** `@llamatrade/telemetry`.
7. **Infra** compose + k8s + dashboards + alerts.
8. **Cleanup**: delete shims once unused; `./scripts/ci-local.sh` green; lib ≥80% cov.

---

## 11. Rules of thumb (for contributors)

- Adding a metric? Pick the domain namespace in `metrics/domain.py`, name it per
  §4.1, use only §4.2 labels. The `conventions` test will reject violations.
- Never put an id/email/url/symbol on a counter or histogram label.
- Need per-tenant numbers on a dashboard? Use logs/traces or a bounded top-N
  gauge — never a `tenant_id` label.
- Telemetry must never raise into the request path. Recorders swallow their own
  errors (like `_collect_db_pool_metrics` does today).
