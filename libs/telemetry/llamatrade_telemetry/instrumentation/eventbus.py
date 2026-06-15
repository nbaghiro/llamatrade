"""EventBus (Redis Streams) metrics.

Recorder functions are imported by the EventBus (``llamatrade_common.events``) so
the bus itself stays free of metric wiring. Streams are labelled by their logical
prefix (e.g. ``ledger:fills``), never the full per-entity key — bounded cardinality.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from llamatrade_telemetry import registry

PUBLISHED_TOTAL = registry.counter(
    "llamatrade_eventbus_published_total",
    ["stream", "event_type", "result"],
    "Entries published to Redis Streams",
)
CONSUMED_TOTAL = registry.counter(
    "llamatrade_eventbus_consumed_total",
    ["stream", "group", "result"],
    "Entries consumed via consumer groups",
)
ACK_TOTAL = registry.counter(
    "llamatrade_eventbus_ack_total",
    ["stream", "group"],
    "Entries acked",
)
NACK_TOTAL = registry.counter(
    "llamatrade_eventbus_nack_total",
    ["stream", "group"],
    "Entries negatively-acked / failed processing",
)
RECONNECTS_TOTAL = registry.counter(
    "llamatrade_eventbus_reconnects_total",
    ["stream", "mode"],
    "Transport-error reconnects in EventBus readers",
)
REDELIVERY_TOTAL = registry.counter(
    "llamatrade_eventbus_redelivery_total",
    ["stream", "group"],
    "Entries reclaimed from dead consumers (XAUTOCLAIM)",
)
DLQ_TOTAL = registry.counter(
    "llamatrade_eventbus_dlq_total",
    ["stream"],
    "Poison entries routed to a dead-letter destination",
)
PROCESSING_DURATION = registry.histogram(
    "llamatrade_eventbus_processing_duration_seconds",
    ["stream", "event_type"],
    "Time to process a consumed entry",
)
CONSUMER_LAG_ENTRIES = registry.gauge(
    "llamatrade_eventbus_consumer_lag_entries",
    ["stream", "group"],
    "Delivered-but-unacked entries (pending) for a consumer group",
)
CONSUMER_LAG_SECONDS = registry.gauge(
    "llamatrade_eventbus_consumer_lag_seconds",
    ["stream", "group"],
    "Age of the oldest unacked entry for a consumer group",
)


def record_published(stream: str, event_type: str = "", result: str = "success") -> None:
    PUBLISHED_TOTAL.labels(stream=stream, event_type=event_type, result=result).inc()


def record_consumed(stream: str, group: str, result: str = "success") -> None:
    CONSUMED_TOTAL.labels(stream=stream, group=group, result=result).inc()


def record_ack(stream: str, group: str) -> None:
    ACK_TOTAL.labels(stream=stream, group=group).inc()


def record_nack(stream: str, group: str) -> None:
    NACK_TOTAL.labels(stream=stream, group=group).inc()


def record_reconnect(stream: str, mode: str) -> None:
    RECONNECTS_TOTAL.labels(stream=stream, mode=mode).inc()


def record_redelivery(stream: str, group: str) -> None:
    REDELIVERY_TOTAL.labels(stream=stream, group=group).inc()


def record_dlq(stream: str) -> None:
    DLQ_TOTAL.labels(stream=stream).inc()


def set_consumer_lag(stream: str, group: str, entries: int, seconds: float | None = None) -> None:
    CONSUMER_LAG_ENTRIES.labels(stream=stream, group=group).set(entries)
    if seconds is not None:
        CONSUMER_LAG_SECONDS.labels(stream=stream, group=group).set(seconds)


@contextmanager
def time_processing(stream: str, event_type: str = "") -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    finally:
        PROCESSING_DURATION.labels(stream=stream, event_type=event_type).observe(
            perf_counter() - start
        )
