"""Event-system metrics, on the unified telemetry library.

Counters/gauges are created through ``llamatrade_telemetry`` so event metrics
share the platform's OTel→Prometheus pipeline, the ``llamatrade_events_*`` naming
convention, and label-cardinality validation. ``stream_label`` keeps the
``stream`` label bounded. The public handle names are unchanged, so call sites
(transport / consumer / fan-out) keep their ``.labels(...).inc()/.set()`` shape.
"""

from __future__ import annotations

from llamatrade_telemetry import counter, gauge


def stream_label(stream: str) -> str:
    """The bounded metric label for a stream: its logical prefix (first two
    colon-segments), never the full per-entity key.

    ``"trading:orders:<sid>"`` → ``"trading:orders"``; ``"ledger:fills"`` →
    ``"ledger:fills"``. Shared by the transport and the consumer so the same
    logical stream carries one label value across every event metric.
    """
    return ":".join(stream.split(":")[:2])


# --- publish / read transport ---
EVENTS_PUBLISHED_TOTAL = counter(
    "llamatrade_events_published_total",
    ["stream"],
    "Events published to the bus",
)
EVENTS_RECONNECTS_TOTAL = counter(
    "llamatrade_events_reconnects_total",
    ["stream", "mode"],  # mode: tail / consume
    "Transport-error reconnects in bus readers",
)

# --- durable consumer group ---
EVENTS_CONSUMED_TOTAL = counter(
    "llamatrade_events_consumed_total",
    ["stream", "group", "outcome"],  # outcome: ok / deduped / error / dlq / poison
    "Events handled by a consumer group",
)
EVENTS_CONSUMER_LAG = gauge(
    "llamatrade_events_consumer_lag",
    ["stream", "group"],
    "Delivered-but-unacked entries per consumer group (PEL depth)",
)

# --- gRPC fan-out ---
EVENTS_FANOUT_DROPPED_TOTAL = counter(
    "llamatrade_events_fanout_dropped_total",
    ["fanout"],
    "Items dropped because a client's fan-out queue was full (slow consumer)",
)
EVENTS_FANOUT_CLIENTS = gauge(
    "llamatrade_events_fanout_clients",
    ["fanout"],
    "Connected gRPC clients on a fan-out",
)
