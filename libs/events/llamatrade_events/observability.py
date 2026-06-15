"""Event-system metrics.

Plain ``prometheus_client`` counters/gauges — ``llamatrade_telemetry`` bridges
the default Prometheus registry into its OTel export, so these surface on every
service's ``/metrics`` without this lib depending on the telemetry stack.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

# Labeled by the stream's logical prefix only (e.g. "trading:orders"), never the
# full per-session key — bounded metric cardinality.
EVENTS_PUBLISHED_TOTAL = Counter(
    "events_published_total",
    "Events published to the bus",
    ["stream"],
)
EVENTS_RECONNECTS_TOTAL = Counter(
    "events_reconnects_total",
    "Transport-error reconnects in bus readers",
    ["stream", "mode"],  # mode: tail / consume
)
EVENTS_CONSUMED_TOTAL = Counter(
    "events_consumed_total",
    "Events handled by a consumer group",
    ["stream", "group", "outcome"],  # outcome: ok / deduped / dlq / error
)
EVENTS_CONSUMER_LAG = Gauge(
    "events_consumer_lag",
    "Delivered-but-unacked entries per consumer group (PEL depth)",
    ["stream", "group"],
)
