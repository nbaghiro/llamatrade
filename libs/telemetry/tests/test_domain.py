from __future__ import annotations

from llamatrade_telemetry import metrics
from tests.conftest import scrape


def test_trading_domain() -> None:
    t = metrics.trading
    t.order_submitted(side="buy", type="market", status="accepted")
    t.fill(side="buy", fill_type="full")
    t.order_rejected(reason="risk")
    t.risk_check(result="passed")
    t.risk_violation(violation_type="max_order_value")
    t.signal_generated(signal_type="entry")
    t.strategy_error(error_type="eval")
    t.bar_processed()
    t.bar_stream_reconnect()
    t.trade_stream_reconnect()
    t.position_reconciled(result="ok")
    t.position_drift(drift_type="qty")
    t.idempotent_replay()
    t.circuit_breaker_triggered(reason="daily_loss")
    t.ledger_event_published(kind="order_filled", status="success")
    t.order_submission_latency.observe(0.01)
    with t.fill_latency.time():
        pass
    t.slippage_bps.labels(side="buy").observe(3.0)
    t.bar_processing_duration.observe(0.005)
    t.bar_stream_latency.observe(0.01)
    t.risk_check_duration.observe(0.001)
    t.fill_processing_duration.observe(0.002)
    t.position_drift_quantity_pct.observe(1.5)
    t.active_runners.set(3)
    t.bar_stream_connected.set(1)
    t.trade_stream_connected.set(1)
    t.circuit_breaker_state.set(0)
    out = scrape()
    assert "llamatrade_trading_order_submissions_total" in out
    assert "llamatrade_trading_active_runners 3.0" in out


def test_ledger_domain() -> None:
    g = metrics.ledger
    g.event_ingested(result="success")
    g.reconciliation_drift(kind="qty_mismatch")
    g.drift_action(action="adopted")
    g.sleeve_frozen()
    g.capital_insufficient()
    g.event_append_latency.observe(0.01)
    g.projection_fold_duration.observe(0.02)
    g.vs_broker_mismatch_dollars.set(0)
    g.capital_allocated_dollars.set(1000)
    g.capital_unallocated_dollars.set(250)
    assert "llamatrade_ledger_events_ingested_total" in scrape()


def test_marketdata_domain() -> None:
    m = metrics.marketdata
    m.cache_op(data_type="bars", result="hit")
    m.stream_reconnect()
    m.queue_dropped()
    m.data_gap()
    m.missing_symbol()
    m.stream_message_lag.observe(0.01)
    m.data_staleness.labels(data_type="bars").observe(5.0)
    m.stream_connections.set(1)
    m.stream_subscriptions.labels(type="trade").set(10)
    m.rate_limit_tokens.set(180)
    m.circuit_breaker_state.set(0)
    assert "llamatrade_marketdata_cache_operations_total" in scrape()


def test_strategy_domain() -> None:
    s = metrics.strategy
    s.parse_error(kind="syntax")
    s.version_minted()
    s.template_instantiated(template="ma_crossover")
    s.compile_duration.observe(0.01)
    s.indicator_compute_duration.labels(indicator="sma").observe(0.001)
    s.signal_eval_duration.observe(0.001)
    s.max_lookback_bars.observe(50)
    s.active_strategies.labels(status="active").set(12)
    assert "llamatrade_strategy_versions_minted_total" in scrape()


def test_backtest_domain() -> None:
    b = metrics.backtest
    b.job(state="completed")
    b.fetch_failure()
    b.progress_publish_failure()
    b.cache_op(tier="redis", result="hit")
    b.execution_duration.observe(30)
    b.bar_throughput.observe(50000)
    b.queue_depth.set(2)
    assert "llamatrade_backtest_jobs_total" in scrape()


def test_billing_domain() -> None:
    b = metrics.billing
    b.invoice_paid(plan="pro")
    b.invoice_payment_failed(plan="pro")
    b.webhook_received(event_type="invoice.paid")
    b.webhook_signature_failure()
    b.webhook_duplicate()
    b.plan_limit_exceeded(limit="backtests")
    b.webhook_handler_duration.labels(event_type="invoice.paid").observe(0.05)
    b.subscriptions.labels(plan="pro", state="active").set(100)
    b.mrr_dollars.set(12345)
    b.arr_dollars.set(148140)
    assert "llamatrade_billing_mrr_dollars 12345.0" in scrape()


def test_auth_domain() -> None:
    a = metrics.auth
    a.registration()
    a.login()
    a.login_failure(reason="wrong_password")
    a.token_issued(type="access")
    a.token_validation_failure(reason="expired")
    a.credential_decryption_failure()
    a.api_key_validation_failure(reason="not_found")
    a.cross_tenant_access_attempt()
    a.bcrypt_hash_duration.observe(0.2)
    assert "llamatrade_auth_cross_tenant_access_attempts_total" in scrape()


def test_notification_domain() -> None:
    n = metrics.notification
    n.alert_triggered(type="price")
    n.cooldown_skipped()
    n.delivered(channel="email")
    n.delivery_failed(channel="sms", reason="invalid_phone")
    n.alert_eval_latency.observe(0.1)
    n.delivery_latency.labels(channel="email").observe(0.5)
    n.unread_backlog.set(5)
    assert "llamatrade_notification_deliveries_total" in scrape()


def test_agent_domain() -> None:
    a = metrics.agent
    a.llm_request(model="claude-opus-4-8", result="success")
    a.llm_error(type="rate_limit")
    a.llm_tokens(model="claude-opus-4-8", direction="output", count=120)
    a.tool_call(result="success")
    a.llm_cost(model="claude-opus-4-8", dollars=0.05)
    a.llm_latency.labels(model="claude-opus-4-8").observe(1.2)
    a.llm_ttft.labels(model="claude-opus-4-8").observe(0.3)
    assert "llamatrade_agent_llm_requests_total" in scrape()
