"""Portfolio ledger runtime metrics, on the unified telemetry library.

Thin adapters over ``llamatrade_telemetry`` that keep the same public surface
the ledger tasks already call (``record_ingest`` / ``record_drift`` /
``record_drift_action`` and the ``LEDGER_STREAM_PENDING`` gauge handle). The
underlying instruments are the OTel-native, Prometheus-exported counters and
gauges defined in the shared library:

* ingestion throughput/failures -> ``llamatrade_ledger_events_ingested_total``
* reconciliation drift by classification -> ``llamatrade_ledger_reconciliation_drift_total``
* drift-policy actions -> ``llamatrade_ledger_drift_actions_total``
* consumer-group pending lag -> ``llamatrade_events_consumer_lag`` (the events lib's gauge)

This is the rollout dashboard for the shadow soak.
"""

from __future__ import annotations

import logging
from uuid import UUID

from llamatrade_events.observability import EVENTS_CONSUMER_LAG
from llamatrade_telemetry import counter, gauge, metrics

logger = logging.getLogger(__name__)

# The durable fill stream and consumer group the pending-lag gauge is keyed on; kept here (not imported from ``tasks.fill_ingestion``) to avoid a metrics -> tasks import cycle.
_LEDGER_FILLS_STREAM = "ledger:fills"
_PORTFOLIO_LEDGER_GROUP = "portfolio-ledger"


# Aggregate count only — per-account/tenant labels are forbidden (cardinality contract); the reconciliation task logs the offending account ids.
_RECONCILE_STALE_ACCOUNTS = gauge(
    "llamatrade_ledger_reconcile_stale_accounts",
    (),
    "Accounts whose last successful reconcile is older than 3x the reconcile interval",
)


# Aggregate count only (no account/tenant labels — cardinality contract); the warning log names the degraded account.
_INCOMPLETE_PROJECTION_READS = counter(
    "llamatrade_ledger_incomplete_projection_reads_total",
    (),
    "Reads served from an account projection degraded by skipped poison events",
)


def record_projection_read(account_id: UUID | str, poison_events: int) -> None:
    """Surface a degraded projection served to a read: metric + warning.

    Reads are never blocked — a degraded projection is served, but never
    silently. No-op when the projection folded cleanly (``poison_events == 0``).
    """
    if poison_events == 0:
        return
    _INCOMPLETE_PROJECTION_READS.inc()
    logger.warning(
        "serving INCOMPLETE ledger projection for account %s (%d poison events skipped)",
        account_id,
        poison_events,
    )


def record_ingest(status: str) -> None:
    """Record one fill-channel ingestion attempt (success / retry / poison)."""
    metrics.ledger.event_ingested(status)


def set_reconcile_stale_accounts(count: int) -> None:
    """Publish how many accounts lack a successful reconcile within the staleness window."""
    _RECONCILE_STALE_ACCOUNTS.set(count)


def record_drift(kind: str) -> None:
    """Record one reconciliation drift finding."""
    metrics.ledger.reconciliation_drift(kind)


def record_drift_action(action: str) -> None:
    """Record one drift-policy action (``froze:N`` collapses to ``froze``)."""
    metrics.ledger.drift_action(action.split(":")[0])


class _StreamPendingGauge:
    """``.set(entries)`` handle for the consumer-group pending-lag gauge.

    Preserves the call site (``LEDGER_STREAM_PENDING.set(...)``) while routing to
    the events lib's ``llamatrade_events_consumer_lag`` gauge under the portfolio-ledger
    stream/group labels (the single event-lag metric across the system).
    """

    def set(self, entries: int) -> None:
        EVENTS_CONSUMER_LAG.labels(stream=_LEDGER_FILLS_STREAM, group=_PORTFOLIO_LEDGER_GROUP).set(
            entries
        )


# Delivered-but-unacked entries in the portfolio-ledger consumer group (lag signal; alert before MAXLEN could trim unacked entries).
LEDGER_STREAM_PENDING = _StreamPendingGauge()
