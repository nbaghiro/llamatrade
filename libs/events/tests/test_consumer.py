"""StreamConsumer runtime: happy path, dedupe, and dead-letter."""

from __future__ import annotations

import re

import pytest
from conftest import FakeTransport

from llamatrade_events import observability
from llamatrade_events.bus import EventBus
from llamatrade_events.codec import (
    EventEnvelope,
    UnknownEventTypeError,
    make_envelope,
    parse_payload,
)
from llamatrade_events.consumer import PoisonError, StreamConsumer
from llamatrade_events.idempotency import InMemoryDedupStore, derive_event_id
from llamatrade_events.transport.base import CURSOR_NEW
from llamatrade_proto.generated import events_pb2
from llamatrade_telemetry import get_metrics

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"


def _metric_value(name: str, **labels: str) -> float:
    """Read a single metric value from the Prometheus exposition (0.0 if absent)."""
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    pattern = re.compile(rf"^{re.escape(name)}\{{{re.escape(label_str)}\}} (.+)$", re.M)
    match = pattern.search(get_metrics().decode())
    return float(match.group(1)) if match else 0.0


def _outcome_count(stream: str, group: str, outcome: str) -> float:
    return _metric_value(
        "llamatrade_events_consumed_total",
        stream=observability.stream_label(stream),
        group=group,
        outcome=outcome,
    )


# Importing llamatrade_events above ran the package __init__, which imports the
# catalog and registers LedgerFill for EVENT_TYPE_LEDGER_FILL.


def _fill_env(client_order_id: str) -> EventEnvelope:
    fill = events_pb2.LedgerFill(client_order_id=client_order_id, tenant_id="t1")
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id(client_order_id)
    )


async def test_trace_propagates_producer_to_consumer(bus: EventBus) -> None:
    """publish_envelope carries the producer's trace context; the consumer runs
    its handler under it (the async fill → ledger projection hop)."""
    from opentelemetry import trace as _trace
    from opentelemetry.sdk.resources import Resource

    from llamatrade_telemetry import tracing
    from llamatrade_telemetry.config import TelemetrySettings

    tracing.reset_for_testing()
    tracing.configure_tracing(
        Resource.create({"service.name": "evt"}),
        TelemetrySettings(OTEL_TRACES_SAMPLER="always_on"),
    )
    seen: dict[str, int] = {}

    async def handler(_env: EventEnvelope) -> None:
        seen["trace_id"] = _trace.get_current_span().get_span_context().trace_id

    with tracing.span("producer") as producer:
        producer_trace = producer.get_span_context().trace_id
        await bus.publish_envelope(STREAM, _fill_env("trace"), maxlen=100)

    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")
    await consumer.run(handler)

    assert seen["trace_id"] == producer_trace


async def test_happy_path_handles_and_acks(bus: EventBus, transport: FakeTransport) -> None:
    await bus.publish_envelope(STREAM, _fill_env("o1"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    received: list[str] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(parse_payload(env).client_order_id)

    await consumer.run(handler)
    assert received == ["o1"]
    assert await bus.pending(STREAM, GROUP) == 0  # acked


async def test_dedup_skips_already_applied(bus: EventBus) -> None:
    env = _fill_env("dup")
    await bus.publish_envelope(STREAM, env, maxlen=100)
    dedup = InMemoryDedupStore()
    await dedup.mark(env.id)  # pretend it was already applied
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", dedup=dedup)

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await consumer.run(handler)
    assert called == 0  # handler skipped
    assert await bus.pending(STREAM, GROUP) == 0  # but still acked


async def test_dedup_marks_after_success(bus: EventBus) -> None:
    env = _fill_env("once")
    await bus.publish_envelope(STREAM, env, maxlen=100)
    dedup = InMemoryDedupStore()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", dedup=dedup)

    async def handler(_: EventEnvelope) -> None:
        return None

    await consumer.run(handler)
    assert await dedup.seen(env.id) is True


async def test_poison_message_goes_to_dlq(bus: EventBus, transport: FakeTransport) -> None:
    await bus.publish_envelope(STREAM, _fill_env("bad"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", max_attempts=3)

    attempts = 0

    async def boom(_: EventEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("nope")

    # Each run() redelivers the unacked entry (FakeTransport mimics XAUTOCLAIM).
    for _ in range(3):
        await consumer.run(boom)

    assert attempts == 3
    assert len(transport.entries(STREAM + ":dlq")) == 1  # dead-lettered
    assert await bus.pending(STREAM, GROUP) == 0  # acked off the live stream


async def test_stop_event_halts_loop(bus: EventBus) -> None:
    import asyncio

    await bus.publish_envelope(STREAM, _fill_env("x"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")
    stop = asyncio.Event()
    stop.set()

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await consumer.run(handler, stop_event=stop)
    assert called == 0  # stopped before handling


# -- undecodable bytes (decode-time poison) --


async def test_undecodable_bytes_dead_lettered_as_raw(
    bus: EventBus, transport: FakeTransport
) -> None:
    """A corrupt entry can't even be decoded — it must DLQ + ack, never crash the
    loop. The raw bytes (not an envelope) are preserved for forensics."""
    garbage = b"\xff\xfe not a valid envelope"
    await bus.publish_raw(STREAM, garbage, maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    handled = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal handled
        handled += 1

    before = _outcome_count(STREAM, GROUP, "poison")
    await consumer.run(handler)

    assert handled == 0  # never reached the handler
    dlq = transport.entries(STREAM + ":dlq")
    assert len(dlq) == 1
    assert dlq[0][1] == garbage  # raw bytes preserved
    assert await bus.pending(STREAM, GROUP) == 0  # acked off the live stream
    assert _outcome_count(STREAM, GROUP, "poison") == before + 1


# -- PoisonError: immediate dead-letter, no retries --


async def test_poison_error_dead_letters_immediately(
    bus: EventBus, transport: FakeTransport
) -> None:
    await bus.publish_envelope(STREAM, _fill_env("p1"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", max_attempts=5)

    attempts = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        raise PoisonError("permanently unprocessable")

    before = _outcome_count(STREAM, GROUP, "poison")
    await consumer.run(handler)

    assert attempts == 1  # no redelivery despite max_attempts=5
    assert len(transport.entries(STREAM + ":dlq")) == 1
    assert await bus.pending(STREAM, GROUP) == 0
    assert _outcome_count(STREAM, GROUP, "poison") == before + 1


async def test_unknown_event_type_routed_to_dlq(bus: EventBus, transport: FakeTransport) -> None:
    """Schema skew (a type this consumer can't parse): the handler converts the
    UnknownEventTypeError into PoisonError so it dead-letters once, not retries."""
    env = make_envelope(events_pb2.EVENT_TYPE_UNSPECIFIED, events_pb2.LedgerFill())
    await bus.publish_envelope(STREAM, env, maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    async def handler(e: EventEnvelope) -> None:
        try:
            parse_payload(e)
        except UnknownEventTypeError as exc:
            raise PoisonError(str(exc)) from exc

    await consumer.run(handler)
    assert len(transport.entries(STREAM + ":dlq")) == 1
    assert await bus.pending(STREAM, GROUP) == 0


# -- bounded retry then DLQ (outcome metric) --


async def test_retry_exhaustion_records_dlq_outcome(
    bus: EventBus, transport: FakeTransport
) -> None:
    await bus.publish_envelope(STREAM, _fill_env("retry"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", max_attempts=3)

    async def boom(_: EventEnvelope) -> None:
        raise RuntimeError("transient-looking but persistent")

    before_err = _outcome_count(STREAM, GROUP, "error")
    before_dlq = _outcome_count(STREAM, GROUP, "dlq")
    for _ in range(3):
        await consumer.run(boom)

    # Two failed deliveries recorded "error", the third exhausted → "dlq".
    assert _outcome_count(STREAM, GROUP, "error") == before_err + 2
    assert _outcome_count(STREAM, GROUP, "dlq") == before_dlq + 1
    assert len(transport.entries(STREAM + ":dlq")) == 1


# -- group-start position --


async def test_group_start_new_skips_preexisting(bus: EventBus) -> None:
    """A fresh group with group_start=CURSOR_NEW ignores entries published before
    it existed (the opposite of the never-miss CURSOR_BEGIN default)."""
    await bus.publish_envelope(STREAM, _fill_env("old"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", group_start=CURSOR_NEW)

    handled = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal handled
        handled += 1

    await consumer.run(handler)
    assert handled == 0  # pre-existing entry not replayed


async def test_default_group_start_replays_preexisting(bus: EventBus) -> None:
    """The default (CURSOR_BEGIN) replays an entry published before the group —
    the never-miss guarantee for a consumer that boots after the producer."""
    await bus.publish_envelope(STREAM, _fill_env("early"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")  # default group_start

    handled = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal handled
        handled += 1

    await consumer.run(handler)
    assert handled == 1


# -- success outcome metric + lag gauge --


async def test_success_records_ok_outcome(bus: EventBus) -> None:
    await bus.publish_envelope(STREAM, _fill_env("ok1"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    before = _outcome_count(STREAM, GROUP, "ok")

    async def handler(_: EventEnvelope) -> None:
        return None

    await consumer.run(handler)
    assert _outcome_count(STREAM, GROUP, "ok") == before + 1


async def test_lag_gauge_sampled_after_handling(bus: EventBus) -> None:
    await bus.publish_envelope(STREAM, _fill_env("lag"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    async def handler(_: EventEnvelope) -> None:
        return None

    await consumer.run(handler)
    lag = _metric_value(
        "llamatrade_events_consumer_lag",
        stream=observability.stream_label(STREAM),
        group=GROUP,
    )
    assert lag == 0  # handled and acked → no pending


async def test_lag_sampling_is_throttled(bus: EventBus, monkeypatch: pytest.MonkeyPatch) -> None:
    """The PEL is sampled at most once per interval, not once per message — two
    entries handled within the same interval trigger a single pending() probe."""
    from llamatrade_events import consumer as consumer_mod

    await bus.publish_envelope(STREAM, _fill_env("a"), maxlen=100)
    await bus.publish_envelope(STREAM, _fill_env("b"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    # Freeze the clock so both _maybe_update_lag calls fall in one interval.
    monkeypatch.setattr(consumer_mod.time, "monotonic", lambda: 1000.0)

    probes = 0
    real_pending = bus.pending

    async def counting_pending(stream: str, group: str) -> int:
        nonlocal probes
        probes += 1
        return await real_pending(stream, group)

    monkeypatch.setattr(bus, "pending", counting_pending)

    async def handler(_: EventEnvelope) -> None:
        return None

    await consumer.run(handler)
    assert probes == 1  # first entry sampled; second within interval skipped
