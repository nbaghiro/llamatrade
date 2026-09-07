"""Real-Kafka integration tests for ``KafkaTransport`` and the runtime.

These run actual producer/consumer/commit calls against a throwaway broker — the
in-memory fake suite (``test_kafka.py``) proves the adapter's branching, this proves
the calls behave as we assume against a real Kafka.

Gated behind ``@pytest.mark.integration`` and self-skips when Docker / testcontainers
is unavailable, so the default unit run stays green without a daemon.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from conftest import take

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, decode_envelope, make_envelope, parse_payload
from llamatrade_events.consumer import (
    BoundedRetry,
    ErrorDisposition,
    PoisonError,
    RetryForever,
    StreamConsumer,
)
from llamatrade_events.idempotency import derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN, OutgoingRecord
from llamatrade_events.transport.kafka import KafkaTransport
from llamatrade_proto.generated import events_pb2

pytestmark = pytest.mark.integration

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"


@pytest.fixture
async def transport(
    bootstrap: str, request: pytest.FixtureRequest
) -> AsyncIterator[KafkaTransport]:
    """A transport on a per-test namespace so topics never collide across tests."""
    namespace = f"itest{abs(hash(request.node.nodeid)) % 1_000_000}"
    t = KafkaTransport(bootstrap, namespace=namespace)
    try:
        yield t
    finally:
        await t.close()


def _fill_env(client_order_id: str, account_id: str = "") -> EventEnvelope:
    fill = events_pb2.LedgerFill(
        client_order_id=client_order_id, tenant_id="t1", account_id=account_id
    )
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id(client_order_id)
    )


# -- publish / consume / ack / pending --
# (The shared publish/consume/ack, per-key order, redelivery, length and purge
# semantics run against this broker via test_transport_contract.py.)


async def test_publish_many_delivers_the_whole_batch_in_per_key_order(
    transport: KafkaTransport,
) -> None:
    """A single ``publish_many`` on a real broker lands every record and keeps
    per-key order (same key → one partition → FIFO)."""
    await transport.ensure_group(STREAM, GROUP)
    records = [OutgoingRecord(f"m{i}".encode(), key="acctA") for i in range(10)]
    cursors = await transport.publish_many(STREAM, records)
    assert len(cursors) == len(records)  # one cursor per record

    got = await take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 10)
    assert [v for _, v in got] == [f"m{i}".encode() for i in range(10)]


async def test_publish_many_keeps_per_key_order_across_partitions(
    transport: KafkaTransport, bootstrap: str
) -> None:
    """On a multi-partition topic, records batched through ``publish_many`` stick
    to one partition per key (the structural basis for per-key order) and each
    key's records are consumed in publish order."""
    await _create_topic(bootstrap, transport.topic(STREAM), partitions=4)
    keys = ("acctA", "acctB")
    batch = [OutgoingRecord(f"{k}:{i}".encode(), key=k) for i in range(4) for k in keys]

    cursors = await transport.publish_many(STREAM, batch)
    assert len(cursors) == len(batch)

    partition_of: dict[str | None, int] = {}
    for record, cursor in zip(batch, cursors, strict=True):
        partition_of.setdefault(record.key, _partition_of(cursor))
        assert _partition_of(cursor) == partition_of[record.key]  # sticky per key

    got = await take(
        transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), len(batch)
    )
    for key in keys:
        seq = [v.decode() for _, v in got if v.decode().startswith(f"{key}:")]
        assert seq == [f"{key}:{i}" for i in range(4)]  # per-key publish order holds


async def test_tail_filters_by_routing_key(transport: KafkaTransport) -> None:
    await transport.publish("trading:orders:sessA", b"a1", key="sessA")
    await transport.publish("trading:orders:sessB", b"b1", key="sessB")
    await transport.publish("trading:orders:sessA", b"a2", key="sessA")
    got = await take(transport.tail("trading:orders:sessA", from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in got] == [b"a1", b"a2"]  # only sessA


async def test_tail_resumes_from_concrete_cursor(transport: KafkaTransport) -> None:
    """Reconnect replay: a stored "partition:offset" cursor resumes exactly after it."""
    stream = "trading:orders:sessR"
    for i in range(3):
        await transport.publish(stream, f"m{i}".encode(), key="sessR")

    got = await take(transport.tail(stream, from_cursor=CURSOR_BEGIN), 1)
    cursor, first = got[0]
    assert first == b"m0"

    for i in range(3, 5):
        await transport.publish(stream, f"m{i}".encode(), key="sessR")

    rest = await take(transport.tail(stream, from_cursor=cursor), 4)
    assert [v for _, v in rest] == [b"m1", b"m2", b"m3", b"m4"]  # the whole gap, in order


# -- StreamConsumer runtime end-to-end --


async def test_stream_consumer_handles_and_acks(bootstrap: str) -> None:
    bus = EventBus(KafkaTransport(bootstrap, namespace="itestsc"))
    try:
        await bus.publish_envelope(STREAM, _fill_env("o1"), maxlen=100, key="acctA")
        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", group_start=CURSOR_BEGIN)

        done = asyncio.Event()
        received: list[str] = []

        async def handler(env: EventEnvelope) -> None:
            received.append(parse_payload(env).client_order_id)
            done.set()

        task = asyncio.create_task(consumer.run(handler))
        try:
            await asyncio.wait_for(done.wait(), timeout=30.0)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert received == ["o1"]
    finally:
        await bus.close()


# -- multi-partition ordering / rebalance survival / DLQ --


async def _create_topic(bootstrap: str, topic: str, *, partitions: int) -> None:
    """Create a topic with an explicit partition count (namespaces are per-test)."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
        )
    finally:
        await admin.close()


def _partition_of(cursor: str) -> int:
    return int(cursor.split(":", 1)[0])


async def _drains_to_zero(transport: KafkaTransport, *, timeout: float) -> bool:
    """Whether the group's lag reaches zero within ``timeout`` (commits are async)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await transport.pending(STREAM, GROUP) == 0:
            return True
        await asyncio.sleep(0.25)
    return False


async def test_key_routing_across_partitions_preserves_per_key_order(
    transport: KafkaTransport, bootstrap: str
) -> None:
    """On a 4-partition topic, keys stick to one partition each (per-key FIFO)
    while distinct keys spread across partitions."""
    await _create_topic(bootstrap, transport.topic(STREAM), partitions=4)

    candidates = [f"acct{i}" for i in range(16)]
    first_partition: dict[str, int] = {}
    for key in candidates:
        cursor = await transport.publish(STREAM, f"{key}:0".encode(), key=key)
        first_partition[key] = _partition_of(cursor)
    # Keyed publishing must actually spread load: 16 keys on 4 partitions.
    assert len(set(first_partition.values())) > 1

    key_a = candidates[0]
    key_b = next(k for k in candidates if first_partition[k] != first_partition[key_a])
    for i in (1, 2, 3):
        for key in (key_a, key_b):
            cursor = await transport.publish(STREAM, f"{key}:{i}".encode(), key=key)
            assert _partition_of(cursor) == first_partition[key]  # sticky per key

    total = len(candidates) + 6
    got = await take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), total)

    def per_key(key: str) -> list[tuple[int, int]]:
        prefix = f"{key}:"
        return [
            (_partition_of(cursor), int(value.decode().split(":", 1)[1]))
            for cursor, value in got
            if value.decode().startswith(prefix)
        ]

    seq_a, seq_b = per_key(key_a), per_key(key_b)
    assert [n for _, n in seq_a] == [0, 1, 2, 3]  # per-key order holds
    assert [n for _, n in seq_b] == [0, 1, 2, 3]
    assert {p for p, _ in seq_a} == {first_partition[key_a]}
    assert {p for p, _ in seq_b} == {first_partition[key_b]}
    assert first_partition[key_a] != first_partition[key_b]  # different partitions


async def test_group_member_kill_leaves_no_record_unconsumed(bootstrap: str) -> None:
    """Two group members on a 4-partition topic; one dies mid-stream. The group
    rebalances and every record is eventually consumed — exactly once after the
    writer-side dedup these ids simulate."""
    namespace = f"itkill{uuid4().hex[:12]}"
    victim_transport = KafkaTransport(bootstrap, namespace=namespace)
    survivor_transport = KafkaTransport(bootstrap, namespace=namespace)
    try:
        await _create_topic(bootstrap, victim_transport.topic(STREAM), partitions=4)

        total = 40
        expected = {f"r{i}" for i in range(total)}
        for i in range(total):
            await victim_transport.publish(STREAM, f"r{i}".encode(), key=f"acct{i % 8}")

        victim_seen: set[str] = set()
        victim_started = asyncio.Event()
        survivor_seen: set[str] = set()
        drained = asyncio.Event()

        async def victim() -> None:
            # Consumes but never commits: its records must redeliver after the kill.
            async for _cursor, value in victim_transport.consume(
                STREAM, GROUP, "victim", group_start_id=CURSOR_BEGIN
            ):
                victim_seen.add(value.decode())
                victim_started.set()

        async def survivor() -> None:
            async for cursor, value in survivor_transport.consume(
                STREAM, GROUP, "survivor", group_start_id=CURSOR_BEGIN
            ):
                survivor_seen.add(value.decode())
                await survivor_transport.ack(STREAM, GROUP, cursor)
                if survivor_seen >= expected:
                    drained.set()

        victim_task = asyncio.create_task(victim())
        survivor_task = asyncio.create_task(survivor())
        try:
            # Let the victim demonstrably join and consume, then kill it mid-stream.
            try:
                await asyncio.wait_for(victim_started.wait(), timeout=30.0)
            except TimeoutError:
                pass  # its partitions may hold no records; the kill still rebalances
            victim_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await victim_task
            await victim_transport.close()

            await asyncio.wait_for(drained.wait(), timeout=120.0)
        finally:
            for task in (victim_task, survivor_task):
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await survivor_task

        assert survivor_seen >= expected  # nothing lost across the rebalance
        assert survivor_seen == expected  # dedup by id → exactly once
    finally:
        await survivor_transport.close()
        await victim_transport.close()


async def test_poison_handler_parks_record_on_dlq_keyed_like_source(bootstrap: str) -> None:
    """A handler raising PoisonError dead-letters the entry to the DLQ topic,
    keyed like the source record, and commits past it on the source group."""
    namespace = f"itdlq{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    bus = EventBus(transport)
    try:
        await _create_topic(bootstrap, transport.topic(STREAM), partitions=2)
        fill = events_pb2.LedgerFill(client_order_id="poison-1", tenant_id="t1", account_id="acctZ")
        envelope = make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id("poison-1")
        )
        await bus.publish_envelope(STREAM, envelope, key="acctZ")

        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", group_start=CURSOR_BEGIN)

        async def poison_handler(env: EventEnvelope) -> None:
            raise PoisonError("permanently unprocessable")

        task = asyncio.create_task(consumer.run(poison_handler))
        dlq_topic = transport.topic(STREAM + ":dlq")
        reader = AIOKafkaConsumer(
            dlq_topic,
            bootstrap_servers=bootstrap,
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await reader.start()
        try:
            record = await asyncio.wait_for(reader.getone(), timeout=60.0)
            # The commit follows the DLQ publish, so let it land on the live
            # member before the consumer task (and its group membership) ends.
            drained = await _drains_to_zero(transport, timeout=30.0)
        finally:
            await reader.stop()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert record.key == b"acctZ"  # DLQ keyed like the source partition key
        assert record.value is not None
        parked = decode_envelope(record.value)
        assert parked.id == envelope.id
        parked_fill = parse_payload(parked)
        assert isinstance(parked_fill, events_pb2.LedgerFill)
        assert parked_fill.client_order_id == "poison-1"
        # The source group committed past the poison entry — it cannot wedge.
        assert drained
    finally:
        await bus.close()


async def test_tail_cursor_resume_reads_every_partition(bootstrap: str) -> None:
    """A concrete cursor resumes the whole topic, not just the cursor's partition.

    Trading's order/position topics are provisioned with several partitions, so a
    reader that stored a cursor and reconnects must assign all of them: the
    cursor's from ``offset + 1``, the rest from their end. Assigning only the
    cursor's partition leaves the reader silently blind to the others.
    """
    namespace = f"itseek{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    try:
        await _create_topic(bootstrap, transport.topic(STREAM), partitions=3)

        # One key per partition, learned from the cursors publishing hands back.
        key_for: dict[int, str] = {}
        for i in range(32):
            cursor = await transport.publish(STREAM, b"seed", key=f"acct{i}")
            key_for.setdefault(_partition_of(cursor), f"acct{i}")
        assert set(key_for) == {0, 1, 2}, "keys did not spread over all three partitions"

        resume_from = await transport.publish(STREAM, b"seed", key=key_for[0])
        assert _partition_of(resume_from) == 0
        seen: set[int] = set()

        async def read() -> None:
            async for cursor, _value in transport.tail(STREAM, from_cursor=resume_from):
                seen.add(_partition_of(cursor))

        async def publish_until_every_partition_arrives() -> None:
            # The non-cursor partitions resume at their end, so only records
            # published after the assignment are guaranteed to arrive; republish
            # until the reader has seen all three (a resume that assigned one
            # partition never gets there).
            while seen != {0, 1, 2}:
                for key in key_for.values():
                    await transport.publish(STREAM, b"after", key=key)
                await asyncio.sleep(0.5)

        reader = asyncio.create_task(read())
        try:
            await asyncio.wait_for(publish_until_every_partition_arrives(), timeout=60.0)
        finally:
            reader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reader

        assert seen == {0, 1, 2}
    finally:
        await transport.close()


# -- retry policies on the real broker (R0.1 / I3) --


async def test_bounded_retry_parks_failed_record_despite_later_ack_in_partition(
    bootstrap: str,
) -> None:
    """A record that keeps failing under BoundedRetry retries in place and parks
    to the DLQ — it is NOT silently lost when a later record in the same
    partition acks. (Kafka's ack commits ``offset + 1``: an entry merely left
    un-acked would be committed past by that later ack and never redeliver.)"""
    namespace = f"itbr{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    bus = EventBus(transport)
    try:
        await transport.ensure_group(STREAM, GROUP)
        # Same key → same partition: "fine" acks behind the failing "doomed".
        await bus.publish_envelope(STREAM, _fill_env("doomed", "acctA"), key="acctA")
        await bus.publish_envelope(STREAM, _fill_env("fine", "acctA"), key="acctA")

        consumer = StreamConsumer(
            bus,
            STREAM,
            GROUP,
            consumer_name="c1",
            group_start=CURSOR_BEGIN,
            policy=BoundedRetry(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.05),
        )
        attempts = 0
        handled: list[str] = []
        done = asyncio.Event()

        async def handler(env: EventEnvelope) -> None:
            nonlocal attempts
            if parse_payload(env).client_order_id == "doomed":
                attempts += 1
                raise RuntimeError("transient-looking failure")
            handled.append(parse_payload(env).client_order_id)
            done.set()

        task = asyncio.create_task(consumer.run(handler))
        reader = AIOKafkaConsumer(
            transport.topic(STREAM + ":dlq"),
            bootstrap_servers=bootstrap,
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await reader.start()
        try:
            record = await asyncio.wait_for(reader.getone(), timeout=60.0)
            await asyncio.wait_for(done.wait(), timeout=30.0)
            drained = await _drains_to_zero(transport, timeout=30.0)
        finally:
            await reader.stop()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert attempts == 3  # retried in place, bounded
        assert handled == ["fine"]  # the later record still lands
        assert record.key == b"acctA"  # DLQ keyed like the source
        assert record.value is not None
        parked = parse_payload(decode_envelope(record.value))
        assert isinstance(parked, events_pb2.LedgerFill)
        assert parked.client_order_id == "doomed"  # parked, not lost
        assert drained  # the group committed past both records
    finally:
        await bus.close()


async def test_retry_forever_transient_failure_folds_exactly_once(bootstrap: str) -> None:
    """A transient failure under RetryForever rides the real pause → backoff →
    resume path on the live member and folds the entry exactly once: no
    quarantine, no DLQ, offset committed past it."""
    namespace = f"itrf{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    bus = EventBus(transport)
    quarantined: list[bytes] = []

    async def quarantine(raw: bytes, env: EventEnvelope | None, exc: BaseException) -> None:
        quarantined.append(raw)

    def classify(_exc: BaseException) -> ErrorDisposition:
        return "transient"

    try:
        await transport.ensure_group(STREAM, GROUP)
        await bus.publish_envelope(STREAM, _fill_env("flaky"), key="acctA")
        consumer = StreamConsumer(
            bus,
            STREAM,
            GROUP,
            consumer_name="c1",
            group_start=CURSOR_BEGIN,
            policy=RetryForever(
                classify=classify,
                quarantine=quarantine,
                base_delay_seconds=0.05,
                max_delay_seconds=0.2,
            ),
        )
        attempts = 0
        folds: list[str] = []
        done = asyncio.Event()

        async def handler(env: EventEnvelope) -> None:
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise ConnectionError("db hiccup")
            folds.append(parse_payload(env).client_order_id)
            done.set()

        task = asyncio.create_task(consumer.run(handler))
        try:
            await asyncio.wait_for(done.wait(), timeout=60.0)
            drained = await _drains_to_zero(transport, timeout=30.0)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert folds == ["flaky"]  # exactly one fold
        assert attempts == 3  # two transient failures retried in place
        assert quarantined == []
        assert await transport.length(STREAM + ":dlq") == 0
        assert drained  # committed past the entry after the fold
    finally:
        await bus.close()
