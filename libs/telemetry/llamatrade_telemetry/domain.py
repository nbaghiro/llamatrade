"""Business-domain metric namespaces.

Accessed as ``metrics.trading.order_submitted(...)`` etc. Convention:

* **counters** are recorded via methods (validate intent, enforce labels);
* **histograms / gauges** are exposed as handles so ``.time()`` / ``.observe()``
  / ``.set()`` / ``.labels()`` are available.

If a service needs a metric not defined here, prefer adding it to the relevant
class. As an escape hatch a service may call ``registry.counter(...)`` directly
(still validated by ``conventions``) rather than editing this shared module.
"""

from __future__ import annotations

from llamatrade_telemetry import registry


class TradingMetrics:
    """Live execution: orders, fills, risk, runners, streams, reconciliation."""

    def __init__(self) -> None:
        self._order_submissions = registry.counter(
            "llamatrade_trading_order_submissions", ["side", "type", "status"], "Orders submitted"
        )
        self._fills = registry.counter(
            "llamatrade_trading_fills_total", ["side", "fill_type"], "Fills processed"
        )
        self._rejections = registry.counter(
            "llamatrade_trading_order_rejections_total", ["reason"], "Order rejections"
        )
        self._risk_checks = registry.counter(
            "llamatrade_trading_risk_checks_total", ["result"], "Risk checks"
        )
        self._risk_violations = registry.counter(
            "llamatrade_trading_risk_violations_total", ["violation_type"], "Risk violations"
        )
        self._signals = registry.counter(
            "llamatrade_trading_signals_generated_total", ["signal_type"], "Signals generated"
        )
        self._strategy_errors = registry.counter(
            "llamatrade_trading_strategy_errors_total", ["error_type"], "Strategy runner errors"
        )
        self._bars_processed = registry.counter(
            "llamatrade_trading_bars_processed_total", (), "Bars processed by runners"
        )
        self._bar_stream_reconnects = registry.counter(
            "llamatrade_trading_bar_stream_reconnects_total", (), "Bar stream reconnects"
        )
        self._trade_stream_reconnects = registry.counter(
            "llamatrade_trading_trade_stream_reconnects_total", (), "Trade stream reconnects"
        )
        self._reconciliation = registry.counter(
            "llamatrade_trading_position_reconciliation_total", ["result"], "Position reconciles"
        )
        self._drift_detected = registry.counter(
            "llamatrade_trading_position_drift_detected_total", ["drift_type"], "Position drift"
        )
        self._idempotent_replay = registry.counter(
            "llamatrade_trading_idempotent_replay_total", (), "Idempotent order replays"
        )
        self._cb_triggered = registry.counter(
            "llamatrade_trading_circuit_breaker_triggered_total", ["reason"], "CB trips"
        )
        self._ledger_published = registry.counter(
            "llamatrade_trading_ledger_events_published_total",
            ["kind", "status"],
            "Ledger fill/reservation events published",
        )

        # Histograms / gauges (handles)
        self.order_submission_latency = registry.histogram(
            "llamatrade_trading_order_submission_latency_seconds", (), "Signal->Alpaca latency"
        )
        self.fill_latency = registry.histogram(
            "llamatrade_trading_order_fill_latency_seconds", (), "Submit->fill latency"
        )
        self.slippage_bps = registry.histogram(
            "llamatrade_trading_order_slippage_bps", ["side"], "Fill vs estimate slippage (bps)"
        )
        self.bar_processing_duration = registry.histogram(
            "llamatrade_trading_bar_processing_duration_seconds", (), "Per-bar processing time"
        )
        self.bar_stream_latency = registry.histogram(
            "llamatrade_trading_bar_stream_latency_seconds", (), "Alpaca bar -> received"
        )
        self.risk_check_duration = registry.histogram(
            "llamatrade_trading_risk_check_duration_seconds", (), "Risk check duration"
        )
        self.fill_processing_duration = registry.histogram(
            "llamatrade_trading_fill_processing_duration_seconds", (), "Fill processing time"
        )
        self.position_drift_quantity_pct = registry.histogram(
            "llamatrade_trading_position_drift_quantity_pct", (), "Drift magnitude (%)"
        )
        self.active_runners = registry.gauge(
            "llamatrade_trading_active_runners", (), "Active strategy runners"
        )
        self.bar_stream_connected = registry.gauge(
            "llamatrade_trading_bar_stream_connected", (), "Bar stream connected (1/0)"
        )
        self.trade_stream_connected = registry.gauge(
            "llamatrade_trading_trade_stream_connected", (), "Trade stream connected (1/0)"
        )
        self.circuit_breaker_state = registry.gauge(
            "llamatrade_trading_circuit_breaker_state", (), "CB state 0=closed 1=half 2=open"
        )

    def order_submitted(self, side: str, type: str, status: str) -> None:
        self._order_submissions.labels(side=side, type=type, status=status).inc()

    def fill(self, side: str, fill_type: str) -> None:
        self._fills.labels(side=side, fill_type=fill_type).inc()

    def order_rejected(self, reason: str) -> None:
        self._rejections.labels(reason=reason).inc()

    def risk_check(self, result: str) -> None:
        self._risk_checks.labels(result=result).inc()

    def risk_violation(self, violation_type: str) -> None:
        self._risk_violations.labels(violation_type=violation_type).inc()

    def signal_generated(self, signal_type: str) -> None:
        self._signals.labels(signal_type=signal_type).inc()

    def strategy_error(self, error_type: str) -> None:
        self._strategy_errors.labels(error_type=error_type).inc()

    def bar_processed(self) -> None:
        self._bars_processed.inc()

    def bar_stream_reconnect(self) -> None:
        self._bar_stream_reconnects.inc()

    def trade_stream_reconnect(self) -> None:
        self._trade_stream_reconnects.inc()

    def position_reconciled(self, result: str) -> None:
        self._reconciliation.labels(result=result).inc()

    def position_drift(self, drift_type: str) -> None:
        self._drift_detected.labels(drift_type=drift_type).inc()

    def idempotent_replay(self) -> None:
        self._idempotent_replay.inc()

    def circuit_breaker_triggered(self, reason: str) -> None:
        self._cb_triggered.labels(reason=reason).inc()

    def ledger_event_published(self, kind: str, status: str) -> None:
        self._ledger_published.labels(kind=kind, status=status).inc()


class LedgerMetrics:
    """Portfolio double-entry ledger: ingestion, projections, reconciliation."""

    def __init__(self) -> None:
        self._ingested = registry.counter(
            "llamatrade_ledger_events_ingested_total", ["result"], "Fill events ingested"
        )
        self._drift = registry.counter(
            "llamatrade_ledger_reconciliation_drift_total", ["kind"], "Reconciliation drift"
        )
        self._drift_actions = registry.counter(
            "llamatrade_ledger_drift_actions_total", ["action"], "Drift remediation actions"
        )
        self._sleeves_frozen = registry.counter(
            "llamatrade_ledger_sleeves_frozen_total", (), "Sleeves frozen on irreconcilable drift"
        )
        self._poison_events = registry.counter(
            "llamatrade_ledger_poison_events_total",
            (),
            "Unparseable events skipped during projection fold",
        )
        self.fill_consumer_active = registry.gauge(
            "llamatrade_ledger_fill_consumer_active",
            (),
            "1 on the pod holding the fill-consumer lock, else 0 (sum across pods should be 1)",
        )
        self._capital_insufficient = registry.counter(
            "llamatrade_ledger_capital_insufficient_total", (), "Under-capitalized allocations"
        )
        self.event_append_latency = registry.histogram(
            "llamatrade_ledger_event_append_latency_seconds", (), "Append latency"
        )
        self.projection_fold_duration = registry.histogram(
            "llamatrade_ledger_projection_fold_duration_seconds", (), "Projection fold time"
        )
        self.vs_broker_mismatch_dollars = registry.gauge(
            "llamatrade_ledger_vs_broker_mismatch_dollars", (), "Ledger vs broker mismatch ($)"
        )
        self.capital_allocated_dollars = registry.gauge(
            "llamatrade_ledger_capital_allocated_dollars", (), "Allocated capital ($)"
        )
        self.capital_unallocated_dollars = registry.gauge(
            "llamatrade_ledger_capital_unallocated_dollars", (), "Unallocated capital ($)"
        )

    def event_ingested(self, result: str) -> None:
        self._ingested.labels(result=result).inc()

    def reconciliation_drift(self, kind: str) -> None:
        self._drift.labels(kind=kind).inc()

    def drift_action(self, action: str) -> None:
        self._drift_actions.labels(action=action).inc()

    def poison_event(self) -> None:
        """An event was skipped during fold because its data couldn't be applied."""
        self._poison_events.inc()

    def sleeve_frozen(self) -> None:
        self._sleeves_frozen.inc()

    def capital_insufficient(self) -> None:
        self._capital_insufficient.inc()


class MarketDataMetrics:
    """Market data: cache, streams, freshness, data quality."""

    def __init__(self) -> None:
        self._cache_ops = registry.counter(
            "llamatrade_marketdata_cache_operations_total",
            ["data_type", "result"],
            "Cache ops by result",
        )
        self._stream_reconnects = registry.counter(
            "llamatrade_marketdata_stream_reconnects_total", (), "Stream reconnects"
        )
        self._queue_dropped = registry.counter(
            "llamatrade_marketdata_client_queue_dropped_total",
            (),
            "Messages dropped (backpressure)",
        )
        self._data_gaps = registry.counter(
            "llamatrade_marketdata_data_gaps_detected_total", (), "Detected gaps in bar series"
        )
        self._missing_symbol = registry.counter(
            "llamatrade_marketdata_missing_symbol_errors_total", (), "Missing-symbol errors"
        )
        self.stream_message_lag = registry.histogram(
            "llamatrade_marketdata_stream_message_lag_seconds", (), "Alpaca ts -> received"
        )
        self.data_staleness = registry.histogram(
            "llamatrade_marketdata_data_staleness_seconds", ["data_type"], "Age of served data"
        )
        self.stream_connections = registry.gauge(
            "llamatrade_marketdata_stream_connections", (), "Active upstream connections"
        )
        self.stream_subscriptions = registry.gauge(
            "llamatrade_marketdata_stream_subscriptions", ["type"], "Subscriptions by type"
        )
        self.rate_limit_tokens = registry.gauge(
            "llamatrade_marketdata_rate_limit_tokens_available", (), "Rate-limiter tokens"
        )
        self.circuit_breaker_state = registry.gauge(
            "llamatrade_marketdata_circuit_breaker_state", (), "CB state 0/1/2"
        )

    def cache_op(self, data_type: str, result: str) -> None:
        self._cache_ops.labels(data_type=data_type, result=result).inc()

    def stream_reconnect(self) -> None:
        self._stream_reconnects.inc()

    def queue_dropped(self) -> None:
        self._queue_dropped.inc()

    def data_gap(self) -> None:
        self._data_gaps.inc()

    def missing_symbol(self) -> None:
        self._missing_symbol.inc()


class StrategyMetrics:
    """Strategy CRUD, DSL parsing/compilation, indicator + signal evaluation."""

    def __init__(self) -> None:
        self._parse_errors = registry.counter(
            "llamatrade_strategy_dsl_parse_errors_total", ["kind"], "DSL parse/validate errors"
        )
        self._versions = registry.counter(
            "llamatrade_strategy_versions_minted_total", (), "Strategy versions minted"
        )
        self._templates = registry.counter(
            "llamatrade_strategy_template_instantiations_total", ["template"], "Template uses"
        )
        self.compile_duration = registry.histogram(
            "llamatrade_strategy_compile_duration_seconds", (), "DSL compile time"
        )
        self.indicator_compute_duration = registry.histogram(
            "llamatrade_strategy_indicator_compute_duration_seconds",
            ["indicator"],
            "Indicator compute time",
        )
        self.signal_eval_duration = registry.histogram(
            "llamatrade_strategy_signal_eval_duration_seconds", (), "Per-bar eval time"
        )
        self.max_lookback_bars = registry.histogram(
            "llamatrade_strategy_max_lookback_bars", (), "Warmup bars required"
        )
        self.active_strategies = registry.gauge(
            "llamatrade_strategy_active_total", ["status"], "Strategies by status"
        )

    def parse_error(self, kind: str) -> None:
        self._parse_errors.labels(kind=kind).inc()

    def version_minted(self) -> None:
        self._versions.inc()

    def template_instantiated(self, template: str) -> None:
        self._templates.labels(template=template).inc()


class BacktestMetrics:
    """Backtest jobs, throughput, cache tiers, data quality."""

    def __init__(self) -> None:
        self._jobs = registry.counter(
            "llamatrade_backtest_jobs_total", ["state"], "Backtest jobs by state"
        )
        self._fetch_failures = registry.counter(
            "llamatrade_backtest_market_data_fetch_failures_total", (), "Market-data fetch failures"
        )
        self._progress_publish_failures = registry.counter(
            "llamatrade_backtest_progress_publish_failures_total", (), "Progress publish failures"
        )
        self._cache = registry.counter(
            "llamatrade_backtest_cache_operations_total", ["tier", "result"], "Cache ops by tier"
        )
        self.execution_duration = registry.histogram(
            "llamatrade_backtest_execution_duration_seconds", (), "Wall-clock job duration"
        )
        self.bar_throughput = registry.histogram(
            "llamatrade_backtest_bar_throughput_bars_per_second", (), "Simulation throughput"
        )
        self.queue_depth = registry.gauge(
            "llamatrade_backtest_queue_depth", (), "Pending backtest jobs"
        )

    def job(self, state: str) -> None:
        self._jobs.labels(state=state).inc()

    def fetch_failure(self) -> None:
        self._fetch_failures.inc()

    def progress_publish_failure(self) -> None:
        self._progress_publish_failures.inc()

    def cache_op(self, tier: str, result: str) -> None:
        self._cache.labels(tier=tier, result=result).inc()


class BillingMetrics:
    """Subscriptions, payments, webhooks, plan enforcement, revenue."""

    def __init__(self) -> None:
        self._invoice_paid = registry.counter(
            "llamatrade_billing_invoice_paid_total", ["plan"], "Invoices paid"
        )
        self._invoice_failed = registry.counter(
            "llamatrade_billing_invoice_payment_failed_total", ["plan"], "Invoice payment failures"
        )
        self._webhook_received = registry.counter(
            "llamatrade_billing_webhook_received_total", ["event_type"], "Stripe webhooks received"
        )
        self._webhook_sig_failures = registry.counter(
            "llamatrade_billing_webhook_signature_failures_total", (), "Webhook signature failures"
        )
        self._webhook_dupes = registry.counter(
            "llamatrade_billing_webhook_idempotency_duplicates_total", (), "Duplicate webhooks"
        )
        self._plan_limit = registry.counter(
            "llamatrade_billing_plan_limit_exceeded_total", ["limit"], "Plan limit hits"
        )
        self.webhook_handler_duration = registry.histogram(
            "llamatrade_billing_webhook_handler_duration_seconds",
            ["event_type"],
            "Webhook handler time",
        )
        self.subscriptions = registry.gauge(
            "llamatrade_billing_subscriptions_total",
            ["plan", "state"],
            "Subscriptions by plan/state",
        )
        self.mrr_dollars = registry.gauge("llamatrade_billing_mrr_dollars", (), "MRR ($)")
        self.arr_dollars = registry.gauge("llamatrade_billing_arr_dollars", (), "ARR ($)")

    def invoice_paid(self, plan: str) -> None:
        self._invoice_paid.labels(plan=plan).inc()

    def invoice_payment_failed(self, plan: str) -> None:
        self._invoice_failed.labels(plan=plan).inc()

    def webhook_received(self, event_type: str) -> None:
        self._webhook_received.labels(event_type=event_type).inc()

    def webhook_signature_failure(self) -> None:
        self._webhook_sig_failures.inc()

    def webhook_duplicate(self) -> None:
        self._webhook_dupes.inc()

    def plan_limit_exceeded(self, limit: str) -> None:
        self._plan_limit.labels(limit=limit).inc()


class AuthMetrics:
    """Identity, tokens, credentials, tenant-isolation security signals."""

    def __init__(self) -> None:
        self._registrations = registry.counter(
            "llamatrade_auth_registrations_total", (), "User registrations"
        )
        self._logins = registry.counter("llamatrade_auth_logins_total", (), "Successful logins")
        self._login_failures = registry.counter(
            "llamatrade_auth_login_failures_total", ["reason"], "Failed logins"
        )
        self._tokens_issued = registry.counter(
            "llamatrade_auth_tokens_issued_total", ["type"], "Tokens issued"
        )
        self._token_validation_failures = registry.counter(
            "llamatrade_auth_token_validation_failures_total", ["reason"], "Token validation fails"
        )
        self._cred_decrypt_failures = registry.counter(
            "llamatrade_auth_credential_decryption_failures_total", (), "Credential decrypt fails"
        )
        self._api_key_failures = registry.counter(
            "llamatrade_auth_api_key_validation_failures_total", ["reason"], "API key fails"
        )
        self._cross_tenant = registry.counter(
            "llamatrade_auth_cross_tenant_access_attempts_total", (), "Cross-tenant access attempts"
        )
        self.bcrypt_hash_duration = registry.histogram(
            "llamatrade_auth_bcrypt_hash_duration_seconds", (), "Password hashing time"
        )

    def registration(self) -> None:
        self._registrations.inc()

    def login(self) -> None:
        self._logins.inc()

    def login_failure(self, reason: str) -> None:
        self._login_failures.labels(reason=reason).inc()

    def token_issued(self, type: str) -> None:
        self._tokens_issued.labels(type=type).inc()

    def token_validation_failure(self, reason: str) -> None:
        self._token_validation_failures.labels(reason=reason).inc()

    def credential_decryption_failure(self) -> None:
        self._cred_decrypt_failures.inc()

    def api_key_validation_failure(self, reason: str) -> None:
        self._api_key_failures.labels(reason=reason).inc()

    def cross_tenant_access_attempt(self) -> None:
        self._cross_tenant.inc()


class NotificationMetrics:
    """Alerts and multi-channel delivery."""

    def __init__(self) -> None:
        self._triggered = registry.counter(
            "llamatrade_notification_alerts_triggered_total", ["type"], "Alerts triggered"
        )
        self._cooldown = registry.counter(
            "llamatrade_notification_alerts_cooldown_skipped_total",
            (),
            "Cooldown-suppressed alerts",
        )
        self._deliveries = registry.counter(
            "llamatrade_notification_deliveries_total", ["channel"], "Notifications delivered"
        )
        self._delivery_failures = registry.counter(
            "llamatrade_notification_delivery_failures_total",
            ["channel", "reason"],
            "Delivery failures",
        )
        self.alert_eval_latency = registry.histogram(
            "llamatrade_notification_alert_eval_latency_seconds", (), "Condition->notification"
        )
        self.delivery_latency = registry.histogram(
            "llamatrade_notification_delivery_latency_seconds", ["channel"], "Delivery latency"
        )
        self.unread_backlog = registry.gauge(
            "llamatrade_notification_unread_backlog", (), "Unread notifications (fatigue signal)"
        )

    def alert_triggered(self, type: str) -> None:
        self._triggered.labels(type=type).inc()

    def cooldown_skipped(self) -> None:
        self._cooldown.inc()

    def delivered(self, channel: str) -> None:
        self._deliveries.labels(channel=channel).inc()

    def delivery_failed(self, channel: str, reason: str) -> None:
        self._delivery_failures.labels(channel=channel, reason=reason).inc()


class AgentMetrics:
    """AI copilot: LLM requests, latency, tokens, cost, tool calls."""

    def __init__(self) -> None:
        self._requests = registry.counter(
            "llamatrade_agent_llm_requests_total", ["model", "result"], "LLM requests"
        )
        self._errors = registry.counter("llamatrade_agent_llm_errors_total", ["type"], "LLM errors")
        self._tokens = registry.counter(
            "llamatrade_agent_llm_tokens_total", ["model", "direction"], "LLM tokens"
        )
        self._tool_calls = registry.counter(
            "llamatrade_agent_tool_calls_total", ["result"], "Tool calls"
        )
        self.llm_latency = registry.histogram(
            "llamatrade_agent_llm_latency_seconds", ["model"], "LLM latency"
        )
        self.llm_ttft = registry.histogram(
            "llamatrade_agent_llm_ttft_seconds", ["model"], "Time to first token"
        )
        self.llm_cost_dollars = registry.counter(
            "llamatrade_agent_llm_cost_dollars_total", ["model"], "LLM cost ($)"
        )

    def llm_request(self, model: str, result: str) -> None:
        self._requests.labels(model=model, result=result).inc()

    def llm_error(self, type: str) -> None:
        self._errors.labels(type=type).inc()

    def llm_tokens(self, model: str, direction: str, count: int) -> None:
        self._tokens.labels(model=model, direction=direction).inc(count)

    def tool_call(self, result: str) -> None:
        self._tool_calls.labels(result=result).inc()

    def llm_cost(self, model: str, dollars: float) -> None:
        self.llm_cost_dollars.labels(model=model).inc(dollars)


class Metrics:
    """Aggregate accessor: ``metrics.trading``, ``metrics.ledger``, …"""

    def __init__(self) -> None:
        self.trading = TradingMetrics()
        self.ledger = LedgerMetrics()
        self.marketdata = MarketDataMetrics()
        self.strategy = StrategyMetrics()
        self.backtest = BacktestMetrics()
        self.billing = BillingMetrics()
        self.auth = AuthMetrics()
        self.notification = NotificationMetrics()
        self.agent = AgentMetrics()


metrics = Metrics()
