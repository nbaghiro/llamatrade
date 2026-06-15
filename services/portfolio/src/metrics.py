"""Portfolio ledger runtime metrics, on the unified telemetry library.

Thin adapters over ``llamatrade_telemetry`` that keep the same public surface
the ledger tasks already call (``record_ingest`` / ``record_drift`` /
``record_drift_action`` and the ``LEDGER_STREAM_PENDING`` gauge handle). The
underlying instruments are the OTel-native, Prometheus-exported counters and
gauges defined in the shared library:

* ingestion throughput/failures -> ``llamatrade_ledger_events_ingested_total``
* reconciliation drift by classification -> ``llamatrade_ledger_reconciliation_drift_total``
* drift-policy actions -> ``llamatrade_ledger_drift_actions_total``
* consumer-group pending lag -> ``llamatrade_eventbus_consumer_lag_entries``

This is the rollout dashboard for the shadow soak.
"""

from __future__ import annotations

from llamatrade_telemetry import metrics
from llamatrade_telemetry.instrumentation.eventbus import set_consumer_lag

# The durable fill stream and consumer group the pending-lag gauge is keyed on.
# Kept here (not imported from ``tasks.fill_ingestion``) to avoid a metrics ->
# tasks import cycle; they mirror that module's constants.
_LEDGER_FILLS_STREAM = "ledger:fills"
_PORTFOLIO_LEDGER_GROUP = "portfolio-ledger"


def record_ingest(status: str) -> None:
    """Record one fill-channel ingestion attempt (success / retry / poison)."""
    metrics.ledger.event_ingested(status)


def record_drift(kind: str) -> None:
    """Record one reconciliation drift finding."""
    metrics.ledger.reconciliation_drift(kind)


def record_drift_action(action: str) -> None:
    """Record one drift-policy action (``froze:N`` collapses to ``froze``)."""
    metrics.ledger.drift_action(action.split(":")[0])


class _StreamPendingGauge:
    """``.set(entries)`` handle for the consumer-group pending-lag gauge.

    Preserves the call site (``LEDGER_STREAM_PENDING.set(...)``) while routing to
    the shared eventbus gauge ``llamatrade_eventbus_consumer_lag_entries`` under
    the portfolio-ledger stream/group labels.
    """

    def set(self, entries: int) -> None:
        set_consumer_lag(_LEDGER_FILLS_STREAM, _PORTFOLIO_LEDGER_GROUP, entries)


# Delivered-but-unacked entries in the portfolio-ledger consumer group (lag
# signal; alert before MAXLEN could trim unacked entries).
LEDGER_STREAM_PENDING = _StreamPendingGauge()
