"""Prometheus metrics for the portfolio ledger runtime.

Exported via the service's existing /metrics endpoint (default registry).
These are the rollout dashboard for the shadow soak: ingestion throughput and
failures, reconciliation drift by classification, and drift-policy actions.
"""

from prometheus_client import Counter

LEDGER_EVENTS_INGESTED_TOTAL = Counter(
    "portfolio_ledger_events_ingested_total",
    "Fill-channel payloads ingested into the ledger",
    ["status"],  # success / failure
)

RECONCILIATION_DRIFT_TOTAL = Counter(
    "portfolio_ledger_reconciliation_drift_total",
    "Per-symbol drift findings from reconciliation passes",
    ["kind"],  # ok/dust/qty_mismatch/missing_at_broker/missing_in_ledger
)

DRIFT_ACTIONS_TOTAL = Counter(
    "portfolio_ledger_drift_actions_total",
    "Actions taken by the drift policy on material drift",
    ["action"],  # observed/adopted/skipped/froze
)


def record_ingest(status: str) -> None:
    """Record one fill-channel ingestion attempt."""
    LEDGER_EVENTS_INGESTED_TOTAL.labels(status=status).inc()


def record_drift(kind: str) -> None:
    """Record one reconciliation drift finding."""
    RECONCILIATION_DRIFT_TOTAL.labels(kind=kind).inc()


def record_drift_action(action: str) -> None:
    """Record one drift-policy action (froze:N collapses to froze)."""
    DRIFT_ACTIONS_TOTAL.labels(action=action.split(":")[0]).inc()
