"""StreamConsumer runtime: happy path, dedupe, and dead-letter."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import pytest
from conftest import FakeTransport, PublishRecord, metric_value

from llamatrade_events import observability
from llamatrade_events.bus import EventBus
from llamatrade_events.codec import (
    EventEnvelope,
    UnknownEventTypeError,
    make_envelope,
    parse_payload,
)
from llamatrade_events.consumer import (
    DlqDepthSampler,
    ErrorDisposition,
    PoisonError,
    RetryForever,
    StreamConsumer,
)
from llamatrade_events.idempotency import InMemoryDedupStore, derive_event_id
from llamatrade_events.transport.base import CURSOR_NEW
from llamatrade_proto.generated import events_pb2

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"
ACCOUNT = "acct-1"


def _outcome_count(stream: str, group: str, outcome: str) -> float:
    return metric_value(
        "llamatrade_events_consumed_total",
        stream=observability.stream_label(stream),
        group=group,
        outcome=outcome,
    )


def _dlq_records(transport: FakeTransport) -> list[PublishRecord]:
    return [r for r in transport.records if r.stream == STREAM + ":dlq"]


# Importing llamatrade_events above ran the package __init__, which imports the
# catalog and registers LedgerFill for EVENT_TYPE_LEDGER_FILL.


def _fill_env(client_order_id: str) -> EventEnvelope:
    fill = events_pb2.LedgerFill(
        client_order_id=client_order_id, tenant_id="t1", account_id=ACCOUNT
    )
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

    # Each run() redelivers the unacked entry (FakeTransport mimics reclaim).
    for _ in range(3):
        await consumer.run(boom)

    assert attempts == 3
    assert len(transport.entries(STREAM + ":dlq")) == 1  # dead-lettered
    assert _dlq_records(transport)[0].key == ACCOUNT  # keyed like the source stream
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
    assert _dlq_records(transport)[0].key is None  # undecodable → no recoverable key
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
    assert _dlq_records(transport)[0].key == ACCOUNT  # per-account order survives the park
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
    assert _dlq_records(transport)[0].key is None  # unparseable payload → unkeyed
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
    lag = metric_value(
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


async def test_lag_sample_transport_failure_does_not_stop_the_loop(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A broker blip while sampling lag is logged at debug and skipped — the gauge
    is observability and the fill → ledger projection must keep consuming."""
    await bus.publish_envelope(STREAM, _fill_env("lagfail"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    async def failing_pending(stream: str, group: str) -> int:
        raise ConnectionResetError("broker went away")

    monkeypatch.setattr(bus, "pending", failing_pending)
    handled: list[str] = []

    async def handler(env: EventEnvelope) -> None:
        handled.append(parse_payload(env).client_order_id)

    with caplog.at_level(logging.DEBUG, logger="llamatrade_events.consumer"):
        await consumer.run(handler)

    assert handled == ["lagfail"]
    assert "ConnectionResetError" in caplog.text


async def test_unexpected_lag_sample_error_propagates(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the transport's own failure types are contained; a bug in the sampling
    path surfaces rather than hiding behind the gauge."""
    await bus.publish_envelope(STREAM, _fill_env("lagbug"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    async def buggy_pending(stream: str, group: str) -> int:
        raise ValueError("programming error")

    monkeypatch.setattr(bus, "pending", buggy_pending)

    async def handler(_: EventEnvelope) -> None:
        return None

    with pytest.raises(ValueError):
        await consumer.run(handler)


# --- RetryForever policy (money-path streams) ---


class _QuarantineRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, EventEnvelope | None, BaseException]] = []

    async def __call__(self, raw: bytes, env: EventEnvelope | None, exc: BaseException) -> None:
        self.calls.append((raw, env, exc))


def _transient_only(_exc: BaseException) -> ErrorDisposition:
    return "transient"


def _forever(
    quarantine: _QuarantineRecorder,
    classify: Callable[[BaseException], ErrorDisposition] = _transient_only,
) -> RetryForever:
    return RetryForever(
        classify=classify, quarantine=quarantine, base_delay_seconds=0.0, max_delay_seconds=0.0
    )


async def test_forever_transient_retries_in_place_until_success(
    bus: EventBus, transport: FakeTransport
) -> None:
    """A transient failure never dead-letters: the entry retries in place (its
    partition paused meanwhile) and acks exactly once when the handler lands."""
    await bus.publish_envelope(STREAM, _fill_env("f1"), maxlen=100)
    quarantine = _QuarantineRecorder()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=_forever(quarantine))

    failures = 3
    handled: list[str] = []

    async def flaky(env: EventEnvelope) -> None:
        nonlocal failures
        if failures > 0:
            failures -= 1
            raise ConnectionError("db hiccup")
        handled.append(parse_payload(env).client_order_id)

    before_err = _outcome_count(STREAM, GROUP, "error")
    before_ok = _outcome_count(STREAM, GROUP, "ok")
    await consumer.run(flaky)

    assert handled == ["f1"]
    assert transport.entries(STREAM + ":dlq") == []  # NEVER dead-lettered
    assert quarantine.calls == []
    assert await bus.pending(STREAM, GROUP) == 0  # acked after success
    assert len(transport.pause_calls) == 1  # paused once, not per attempt
    assert len(transport.resume_calls) == 1
    assert _outcome_count(STREAM, GROUP, "error") == before_err + 3
    assert _outcome_count(STREAM, GROUP, "ok") == before_ok + 1


async def test_forever_backoff_grows_exponentially_to_the_cap(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    from llamatrade_events import consumer as consumer_mod

    await bus.publish_envelope(STREAM, _fill_env("f2"), maxlen=100)
    quarantine = _QuarantineRecorder()
    policy = RetryForever(
        classify=_transient_only,
        quarantine=quarantine,
        base_delay_seconds=0.5,
        max_delay_seconds=2.0,
    )
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=policy)

    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(consumer_mod.asyncio, "sleep", fake_sleep)

    failures = 4

    async def flaky(_: EventEnvelope) -> None:
        nonlocal failures
        if failures > 0:
            failures -= 1
            raise ConnectionError("still down")

    await consumer.run(flaky)
    assert delays == [0.5, 1.0, 2.0, 2.0]  # doubles, then capped


async def test_forever_poison_error_goes_to_quarantine_not_dlq(
    bus: EventBus, transport: FakeTransport
) -> None:
    await bus.publish_envelope(STREAM, _fill_env("p9"), maxlen=100)
    quarantine = _QuarantineRecorder()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=_forever(quarantine))

    async def handler(_: EventEnvelope) -> None:
        raise PoisonError("structurally wrong")

    before = _outcome_count(STREAM, GROUP, "poison")
    await consumer.run(handler)

    assert transport.entries(STREAM + ":dlq") == []  # lib DLQ not used
    assert len(quarantine.calls) == 1
    _raw, env, exc = quarantine.calls[0]
    assert env is not None and parse_payload(env).client_order_id == "p9"
    assert isinstance(exc, PoisonError)
    assert await bus.pending(STREAM, GROUP) == 0  # acked past it
    assert _outcome_count(STREAM, GROUP, "poison") == before + 1


async def test_forever_classifier_can_declare_poison(
    bus: EventBus, transport: FakeTransport
) -> None:
    await bus.publish_envelope(STREAM, _fill_env("p10"), maxlen=100)
    quarantine = _QuarantineRecorder()

    def classify(exc: BaseException) -> ErrorDisposition:
        return "poison" if isinstance(exc, ValueError) else "transient"

    consumer = StreamConsumer(
        bus, STREAM, GROUP, consumer_name="c1", policy=_forever(quarantine, classify)
    )

    attempts = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("bad payload")

    await consumer.run(handler)

    assert attempts == 1  # classified poison → no retry
    assert len(quarantine.calls) == 1
    assert transport.entries(STREAM + ":dlq") == []
    assert await bus.pending(STREAM, GROUP) == 0


async def test_forever_undecodable_bytes_quarantined_with_no_envelope(
    bus: EventBus, transport: FakeTransport
) -> None:
    garbage = b"\xff\xfe not an envelope"
    await bus.publish_raw(STREAM, garbage, maxlen=100)
    quarantine = _QuarantineRecorder()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=_forever(quarantine))

    handled = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal handled
        handled += 1

    before = _outcome_count(STREAM, GROUP, "poison")
    await consumer.run(handler)

    assert handled == 0
    assert quarantine.calls[0][0] == garbage
    assert quarantine.calls[0][1] is None  # undecodable → no envelope
    assert transport.entries(STREAM + ":dlq") == []
    assert await bus.pending(STREAM, GROUP) == 0
    assert _outcome_count(STREAM, GROUP, "poison") == before + 1


async def test_forever_quarantine_failure_still_acks(
    bus: EventBus, transport: FakeTransport, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing quarantine handler must not wedge the partition: logged, acked."""
    await bus.publish_envelope(STREAM, _fill_env("q1"), maxlen=100)

    async def broken_quarantine(raw: bytes, env: EventEnvelope | None, exc: BaseException) -> None:
        raise RuntimeError("dlq broker down")

    policy = RetryForever(
        classify=_transient_only,
        quarantine=broken_quarantine,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
    )
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=policy)

    async def handler(_: EventEnvelope) -> None:
        raise PoisonError("unrecordable")

    with caplog.at_level(logging.ERROR, logger="llamatrade_events.consumer"):
        await consumer.run(handler)

    assert await bus.pending(STREAM, GROUP) == 0  # acked anyway
    assert "Quarantine handler failed" in caplog.text


async def test_forever_dedup_skips_and_marks(bus: EventBus) -> None:
    env = _fill_env("fd1")
    await bus.publish_envelope(STREAM, env, maxlen=100)
    dedup = InMemoryDedupStore()
    await dedup.mark(env.id)
    quarantine = _QuarantineRecorder()
    consumer = StreamConsumer(
        bus, STREAM, GROUP, consumer_name="c1", dedup=dedup, policy=_forever(quarantine)
    )

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await consumer.run(handler)
    assert called == 0
    assert await bus.pending(STREAM, GROUP) == 0


async def test_forever_preserves_producer_trace_context(bus: EventBus) -> None:
    """The CONSUMER span + context extraction hold under the forever policy."""
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
        await bus.publish_envelope(STREAM, _fill_env("ftrace"), maxlen=100)

    quarantine = _QuarantineRecorder()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", policy=_forever(quarantine))
    await consumer.run(handler)

    assert seen["trace_id"] == producer_trace


# --- DLQ depth sampler ---

DLQ_DEPTH = "llamatrade_events_dlq_depth"


async def _eventually(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.005)


async def test_dlq_sampler_sets_gauge_per_stream(bus: EventBus, transport: FakeTransport) -> None:
    for i in range(3):
        await transport.publish("ledger:fills:dlq", f"p{i}".encode())
    await transport.publish("notifications:dlq", b"n0")
    sampler = DlqDepthSampler(bus, ["ledger:fills:dlq", "notifications:dlq"])

    await sampler.sample_once()

    # labels are the bounded stream_label of each DLQ stream name
    assert metric_value(DLQ_DEPTH, stream="ledger:fills") == 3.0
    assert metric_value(DLQ_DEPTH, stream="notifications:dlq") == 1.0


async def test_dlq_sampler_tracks_depth_down_and_up(
    bus: EventBus, transport: FakeTransport
) -> None:
    """The gauge is set, not incremented: a drained DLQ reads zero again."""
    await transport.publish("ledger:fills:dlq", b"parked")
    sampler = DlqDepthSampler(bus, ["ledger:fills:dlq"])

    await sampler.sample_once()
    assert metric_value(DLQ_DEPTH, stream="ledger:fills") == 1.0

    await transport.purge("ledger:fills:dlq")
    await sampler.sample_once()
    assert metric_value(DLQ_DEPTH, stream="ledger:fills") == 0.0


async def test_dlq_sampler_survives_a_depth_failure(
    bus: EventBus, transport: FakeTransport, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing depth call is logged and skipped; the other streams still sample."""
    await transport.publish("orders:audit:dlq", b"x")
    transport.length_errors["ledger:fills:dlq"] = RuntimeError("depth read failed")
    sampler = DlqDepthSampler(bus, ["ledger:fills:dlq", "orders:audit:dlq"])

    with caplog.at_level(logging.WARNING, logger="llamatrade_events.consumer"):
        await sampler.sample_once()  # must not raise

    assert metric_value(DLQ_DEPTH, stream="orders:audit") == 1.0
    assert "RuntimeError" in caplog.text


async def test_dlq_sampler_run_samples_immediately_and_stops(
    bus: EventBus, transport: FakeTransport
) -> None:
    stream = "backtest:progress:dlq"
    await transport.publish(stream, b"x")
    stop = asyncio.Event()
    sampler = DlqDepthSampler(bus, [stream], interval_seconds=0.01)
    task = asyncio.create_task(sampler.run(stop_event=stop))

    await _eventually(lambda: metric_value(DLQ_DEPTH, stream="backtest:progress") == 1.0)
    await transport.publish(stream, b"y")
    await _eventually(lambda: metric_value(DLQ_DEPTH, stream="backtest:progress") == 2.0)

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)


async def test_dlq_sampler_run_keeps_sampling_past_a_failure(
    bus: EventBus, transport: FakeTransport
) -> None:
    """The loop outlives a depth-call exception and recovers once the fault clears."""
    stream = "market:bars:dlq"
    transport.length_errors[stream] = RuntimeError("broker blip")
    stop = asyncio.Event()
    sampler = DlqDepthSampler(bus, [stream], interval_seconds=0.01)
    task = asyncio.create_task(sampler.run(stop_event=stop))

    await asyncio.sleep(0.05)  # a few failing samples
    assert not task.done()

    del transport.length_errors[stream]
    await transport.publish(stream, b"x")
    await _eventually(lambda: metric_value(DLQ_DEPTH, stream="market:bars") == 1.0)

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)
