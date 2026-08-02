"""KafkaTransport unit tests.

Pure-logic tests (topic mapping, cursor framing, protocol) plus behavioural tests
against an in-memory fake broker (cursor resume, reconnect-with-backoff, the
topic auto-create gate, pause/resume). The real-broker command behaviour is
proven in ``test_integration_kafka.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest
from aiokafka import AIOKafkaConsumer, OffsetAndMetadata, TopicPartition
from aiokafka.admin import RecordsToDelete
from aiokafka.errors import KafkaError
from conftest import metric_value

from llamatrade_events.transport.base import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    EventTransport,
    OutgoingRecord,
)
from llamatrade_events.transport.kafka import (
    DEFAULT_PRODUCER_BATCH_SIZE,
    DEFAULT_PRODUCER_LINGER_MS,
    PRODUCER_COMPRESSION_TYPE,
    KafkaTransport,
    MissingTopicError,
    TransportAuthError,
    _cursor,
    _parse_cursor,
)

BROKEN_CREDENTIALS = "llamatrade_events_broken_credentials_total"
START_FAILURES = "llamatrade_events_client_start_failures_total"

# --- pure logic (no broker) ---


def test_satisfies_transport_protocol() -> None:
    assert isinstance(KafkaTransport(), EventTransport)


def test_topic_mapping_static_and_templated() -> None:
    t = KafkaTransport(namespace="lt")
    assert t.topic("ledger:fills") == "lt.ledger.fills"
    assert t.topic("market:bars:1m") == "lt.market.bars.1m"
    assert t.topic("trading:orders:abc-123") == "lt.trading.orders"
    assert t.topic("trading:positions:xyz") == "lt.trading.positions"
    assert t.topic("backtest:progress:run-9") == "lt.backtest.progress"
    # unknown streams (e.g. the DLQ side-topic) fall back to a dotted name
    assert t.topic("ledger:fills:dlq") == "lt.ledger.fills.dlq"


def test_cursor_round_trip() -> None:
    assert _cursor(3, 47) == "3:47"
    assert _parse_cursor("3:47") == (3, 47)
    assert _parse_cursor(_cursor(0, 0)) == (0, 0)


# --- in-memory fake broker ---


class _FakeRecord:
    def __init__(self, partition: int, offset: int, key: bytes | None, value: bytes) -> None:
        self.partition = partition
        self.offset = offset
        self.key = key
        self.value = value


class _FakeBroker:
    """A one-partition-per-topic in-memory log shared by fake producer/consumers."""

    def __init__(self) -> None:
        self.logs: dict[str, list[_FakeRecord]] = {}
        # Partition count the Admin API reports for a topic; topics default to one
        # partition, like an auto-created topic.
        self.partitions: dict[str, int] = {}
        # committed offsets live broker-side per (group, topic, partition), so any
        # consumer in the group sees them — as a real broker does.
        self.committed: dict[tuple[str, str, int], int] = {}
        # Each new consumer pops a fail-after count: raise KafkaError after that
        # many deliveries (0 = fail before the first). Empty = never fail.
        self.fail_plan: list[int] = []
        # How many further consumer starts must fail before one succeeds.
        self.start_failures = 0
        # Stop-path hooks: aiokafka's spurious cancellation, and a stop that
        # blocks so a test can cancel its caller mid-stop.
        self.stop_raises_cancelled = False
        self.stop_gate: asyncio.Event | None = None
        self.stop_entered = asyncio.Event()
        self.consumers: list[_FakeConsumer] = []
        self.producers: list[_FakeProducer] = []
        self.consumer_kwargs: list[dict[str, object]] = []
        self.producer_kwargs: list[dict[str, object]] = []

    def append(self, topic: str, key: bytes | None, value: bytes) -> _FakeRecord:
        log = self.logs.setdefault(topic, [])
        rec = _FakeRecord(0, len(log), key, value)
        log.append(rec)
        return rec


class _FakeClient:
    """The metadata handle a producer's liveness probe goes through."""

    def __init__(self, broker: _FakeBroker) -> None:
        self._broker = broker

    async def fetch_all_metadata(self) -> set[str]:
        return set(self._broker.logs)


class _FakeProducer:
    def __init__(self, broker: _FakeBroker) -> None:
        self._broker = broker
        self.client = _FakeClient(broker)
        self.flush_calls = 0
        broker.producers.append(self)

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def send(
        self, topic: str, value: bytes, key: bytes | None = None
    ) -> asyncio.Future[_FakeRecord]:
        rec = self._broker.append(topic, key, value)
        fut: asyncio.Future[_FakeRecord] = asyncio.get_running_loop().create_future()
        fut.set_result(rec)
        return fut

    async def flush(self) -> None:
        self.flush_calls += 1


class _FakeConsumer:
    def __init__(
        self,
        *topics: str,
        broker: _FakeBroker,
        group_id: str | None = None,
        auto_offset_reset: str = "latest",
    ) -> None:
        self._broker = broker
        self._topics = list(topics)
        self._group = group_id
        self._earliest = auto_offset_reset == "earliest"
        self._pos: dict[str, int] = {}
        self._fail_after = broker.fail_plan.pop(0) if broker.fail_plan else None
        self._delivered = 0
        self.paused: set[TopicPartition] = set()
        broker.consumers.append(self)

    def _seed(self, topic: str) -> None:
        log = self._broker.logs.get(topic, [])
        committed = self._broker.committed.get((self._group, topic, 0)) if self._group else None
        self._pos[topic] = (
            committed if committed is not None else (0 if self._earliest else len(log))
        )

    async def start(self) -> None:
        if self._broker.start_failures > 0:
            self._broker.start_failures -= 1
            raise KafkaError("injected start failure")
        for topic in self._topics:
            self._seed(topic)

    def subscribe(self, topics: list[str]) -> None:
        for topic in topics:
            if topic not in self._topics:
                self._topics.append(topic)
            self._seed(topic)

    async def stop(self) -> None:
        if self._broker.stop_raises_cancelled:
            raise asyncio.CancelledError
        gate = self._broker.stop_gate
        if gate is not None:
            self._broker.stop_entered.set()
            await gate.wait()

    def __aiter__(self) -> _FakeConsumer:
        return self

    async def __anext__(self) -> _FakeRecord:
        if self._fail_after is not None and self._delivered >= self._fail_after:
            self._fail_after = None
            raise KafkaError("injected broker failure")
        for topic in self._topics:
            log = self._broker.logs.get(topic, [])
            i = self._pos.get(topic, 0)
            if i < len(log):
                self._pos[topic] = i + 1
                self._delivered += 1
                return log[i]
        raise StopAsyncIteration  # fake drains rather than blocking

    def assign(self, partitions: list[TopicPartition]) -> None:
        for tp in partitions:
            if tp.topic not in self._topics:
                self._topics.append(tp.topic)
            self._pos.setdefault(tp.topic, 0)

    def seek(self, partition: TopicPartition, offset: int) -> None:
        self._pos[partition.topic] = offset

    async def seek_to_end(self, *partitions: TopicPartition) -> None:
        for tp in partitions:
            self._pos[tp.topic] = len(self._broker.logs.get(tp.topic, []))

    def pause(self, *partitions: TopicPartition) -> None:
        self.paused.update(partitions)

    def resume(self, *partitions: TopicPartition) -> None:
        self.paused.difference_update(partitions)

    async def topics(self) -> set[str]:
        return set(self._broker.logs)

    def partitions_for_topic(self, topic: str) -> set[int]:
        return {0} if topic in self._broker.logs else set()

    async def end_offsets(self, tps: list[TopicPartition]) -> dict[TopicPartition, int]:
        return {tp: len(self._broker.logs.get(tp.topic, [])) for tp in tps}

    async def beginning_offsets(self, tps: list[TopicPartition]) -> dict[TopicPartition, int]:
        return {tp: 0 for tp in tps}

    async def committed(self, tp: TopicPartition) -> int | None:
        return self._broker.committed.get((self._group or "", tp.topic, tp.partition))

    async def commit(self, offsets: dict[TopicPartition, OffsetAndMetadata]) -> None:
        for tp, oam in offsets.items():
            self._broker.committed[(self._group or "", tp.topic, tp.partition)] = oam.offset


class _FakeAdmin:
    def __init__(self, broker: _FakeBroker) -> None:
        self._broker = broker
        self.created: list[str] = []

    async def start(self) -> None: ...
    async def close(self) -> None: ...

    async def create_topics(self, topics: list[object]) -> None:
        for new_topic in topics:
            name = str(getattr(new_topic, "name", ""))
            if name in self._broker.logs:
                raise KafkaError(f"Topic '{name}' already exists")
            self._broker.logs.setdefault(name, [])
            self.created.append(name)

    async def list_topics(self) -> list[str]:
        return list(self._broker.logs)

    async def delete_records(
        self, records: dict[TopicPartition, RecordsToDelete]
    ) -> dict[TopicPartition, int]:
        for tp, spec in records.items():
            self._broker.logs[tp.topic] = self._broker.logs.get(tp.topic, [])[spec.before_offset :]
        return {tp: spec.before_offset for tp, spec in records.items()}

    async def describe_topics(self, topics: list[str]) -> list[dict[str, object]]:
        return [
            {
                "topic": topic,
                "error_code": 0 if topic in self._broker.logs else 3,
                "partitions": [
                    {"partition": p} for p in range(self._broker.partitions.get(topic, 1))
                ]
                if topic in self._broker.logs
                else [],
            }
            for topic in topics
        ]

    async def list_consumer_group_offsets(
        self, group_id: str
    ) -> dict[TopicPartition, OffsetAndMetadata]:
        return {
            TopicPartition(topic, partition): OffsetAndMetadata(offset, "")
            for (grp, topic, partition), offset in self._broker.committed.items()
            if grp == group_id
        }


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> _FakeBroker:
    b = _FakeBroker()

    def make_consumer(*topics: str, **kw: object) -> _FakeConsumer:
        b.consumer_kwargs.append(dict(kw))
        return _FakeConsumer(
            *topics,
            broker=b,
            group_id=cast("str | None", kw.get("group_id")),
            auto_offset_reset=cast("str", kw.get("auto_offset_reset", "latest")),
        )

    def make_producer(**kw: object) -> _FakeProducer:
        b.producer_kwargs.append(dict(kw))
        return _FakeProducer(b)

    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaProducer", make_producer)
    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaConsumer", make_consumer)
    monkeypatch.setattr(
        "llamatrade_events.transport.kafka.AIOKafkaAdminClient",
        lambda **kw: _FakeAdmin(b),
    )
    return b


async def _drain[T](agen: AsyncIterator[T], limit: int = 100) -> list[T]:
    out: list[T] = []
    async for item in agen:
        out.append(item)
        if len(out) >= limit:
            break
    await agen.aclose()
    return out


def _fast() -> KafkaTransport:
    """A transport whose reconnect backoff never sleeps (unit tests)."""
    return KafkaTransport(reconnect_base_delay_seconds=0.0, reconnect_max_delay_seconds=0.0)


async def test_publish_returns_partition_offset_cursor(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    c1 = await t.publish("ledger:fills", b"a", key="acctA")
    c2 = await t.publish("ledger:fills", b"b", key="acctA")
    assert (c1, c2) == ("0:0", "0:1")
    # key is encoded onto the record
    assert broker.logs["lt.ledger.fills"][0].key == b"acctA"


async def test_is_connected_reflects_started_producer(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    assert t.is_connected() is False
    await t.publish("ledger:fills", b"a", key="acctA")
    assert t.is_connected() is True


# --- batched publish (publish_many) ---


async def test_publish_many_appends_all_and_returns_ordered_cursors(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    cursors = await t.publish_many(
        "ledger:fills",
        [
            OutgoingRecord(b"f0", "acctA"),
            OutgoingRecord(b"f1", "acctA"),
            OutgoingRecord(b"f2", "acctB"),
        ],
    )
    # one partition on the fake → offsets are sequential in input order
    assert cursors == ["0:0", "0:1", "0:2"]
    log = broker.logs["lt.ledger.fills"]
    assert [r.value for r in log] == [b"f0", b"f1", b"f2"]
    assert [r.key for r in log] == [b"acctA", b"acctA", b"acctB"]


async def test_publish_many_preserves_per_key_order(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish_many(
        "market:bars:1m", [OutgoingRecord(f"b{i}".encode(), "AAPL") for i in range(4)]
    )
    got = await _drain(t.tail("market:bars:1m", from_cursor=CURSOR_BEGIN))
    assert [v for _, v in got] == [b"b0", b"b1", b"b2", b"b3"]


async def test_publish_many_empty_is_a_noop(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    assert await t.publish_many("ledger:fills", []) == []
    # an empty batch builds no producer and writes nothing
    assert "lt.ledger.fills" not in broker.logs
    assert broker.producer_kwargs == []


async def test_publish_many_counts_every_record_once(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    before = metric_value("llamatrade_events_published_total", stream="ledger:fills")
    await t.publish_many("ledger:fills", [OutgoingRecord(b"a", "k"), OutgoingRecord(b"b", "k")])
    after = metric_value("llamatrade_events_published_total", stream="ledger:fills")
    assert after == before + 2


async def test_publish_many_records_without_keys(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    cursors = await t.publish_many("market:bars:1m", [OutgoingRecord(b"x"), OutgoingRecord(b"y")])
    assert cursors == ["0:0", "0:1"]
    assert [r.key for r in broker.logs["lt.market.bars.1m"]] == [None, None]


# --- producer batching config ---


async def test_producer_configured_for_batched_throughput(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")  # builds the producer once
    kw = broker.producer_kwargs[-1]
    assert PRODUCER_COMPRESSION_TYPE == "lz4"
    assert kw["compression_type"] == "lz4"
    assert kw["linger_ms"] == DEFAULT_PRODUCER_LINGER_MS
    assert kw["max_batch_size"] == DEFAULT_PRODUCER_BATCH_SIZE
    # the money-path contract is untouched: still idempotent + acks=all
    assert kw["enable_idempotence"] is True
    assert kw["acks"] == "all"


async def test_producer_batching_is_env_tunable(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAFKA_PRODUCER_LINGER_MS", "3")
    monkeypatch.setenv("KAFKA_PRODUCER_BATCH_SIZE", "2048")
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    kw = broker.producer_kwargs[-1]
    assert kw["linger_ms"] == 3
    assert kw["max_batch_size"] == 2048


async def test_publish_flushes_the_solo_record_off_the_linger_floor(broker: _FakeBroker) -> None:
    """The money path forces its single record out immediately; ``publish_many``
    keeps relying on the linger to batch (it does not add a flush)."""
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    assert broker.producers[-1].flush_calls == 1

    await t.publish_many("ledger:fills", [OutgoingRecord(b"f2", "acctA")])
    assert broker.producers[-1].flush_calls == 1  # batch path added no flush


async def test_consume_ack_and_pending(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    got = await _drain(
        t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    )
    assert [v for _, v in got] == [b"f1"]
    # before ack: lag 1; after ack: lag 0 (fake tracks committed offsets)
    assert await t.pending("ledger:fills", "portfolio-ledger") == 1
    # re-open a consumer to register it, then ack the delivered cursor
    async for cursor, _ in t.consume(
        "ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN
    ):
        await t.ack("ledger:fills", "portfolio-ledger", cursor)
        break
    assert await t.pending("ledger:fills", "portfolio-ledger") == 0


async def test_pending_samples_lag_without_joining_the_group(broker: _FakeBroker) -> None:
    """Lag sampling must not join the group (a member start triggers a rebalance).

    The lag monitor runs on a separate loop every ~30s; if ``pending`` joined the
    ledger group it would rebalance the live fill consumer each sample.
    """
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    before = len(broker.consumer_kwargs)

    lag = await t.pending("ledger:fills", "portfolio-ledger")

    assert lag == 1  # one published, none committed
    made = broker.consumer_kwargs[before:]
    assert made, "pending should open a probe consumer"
    # every consumer pending opens is a non-member (group_id=None) → no rebalance
    assert all(kw.get("group_id") is None for kw in made)
    """Per-session fan-out: one topic, filtered to the session's key."""
    t = KafkaTransport()
    await t.publish("trading:orders:sessA", b"a1", key="sessA")
    await t.publish("trading:orders:sessB", b"b1", key="sessB")
    await t.publish("trading:orders:sessA", b"a2", key="sessA")
    got = await _drain(t.tail("trading:orders:sessA", from_cursor=CURSOR_BEGIN))
    assert [v for _, v in got] == [b"a1", b"a2"]  # only sessA, in order


async def test_tail_new_starts_at_end(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("market:bars:1m", b"old", key="AAPL")
    # CURSOR_NEW → only entries after now; the pre-existing "old" is skipped
    got = await _drain(t.tail("market:bars:1m", from_cursor=CURSOR_NEW))
    assert got == []


async def test_length_counts_topic_entries(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"a", key="x")
    await t.publish("ledger:fills", b"b", key="x")
    assert await t.length("ledger:fills") == 2


# --- cursor resume ---


async def test_tail_resumes_after_concrete_cursor(broker: _FakeBroker) -> None:
    """A "partition:offset" cursor replays everything AFTER that record."""
    t = KafkaTransport()
    for i in range(3):
        await t.publish("market:bars:1m", f"b{i}".encode(), key="AAPL")
    got = await _drain(t.tail("market:bars:1m", from_cursor="0:0"))
    assert [v for _, v in got] == [b"b1", b"b2"]


class _SeekRecorder:
    """Minimal consumer stub recording assign/seek calls for _seek_to_cursor."""

    def __init__(self) -> None:
        self.assigned: list[TopicPartition] = []
        self.seeks: list[tuple[TopicPartition, int]] = []
        self.sought_to_end: list[TopicPartition] = []

    def assign(self, partitions: list[TopicPartition]) -> None:
        self.assigned = partitions

    def seek(self, partition: TopicPartition, offset: int) -> None:
        self.seeks.append((partition, offset))

    async def seek_to_end(self, *partitions: TopicPartition) -> None:
        self.sought_to_end.extend(partitions)


async def test_seek_to_cursor_assigns_every_partition_of_the_topic(broker: _FakeBroker) -> None:
    """The cursor's partition resumes at offset+1; every other partition at its end.

    The partition list is read from the Admin API. A consumer's cached
    ``partitions_for_topic`` answers None here (an unsubscribed consumer never
    fills that cache), which would assign the cursor's partition alone and make a
    resuming tail on a multi-partition topic see nothing from the rest.
    """
    topic = "lt.market.bars.1m"
    broker.logs[topic] = []
    broker.partitions[topic] = 3
    t = KafkaTransport()
    rec = _SeekRecorder()

    await t._seek_to_cursor(cast(AIOKafkaConsumer, rec), topic, "1:41")

    assert rec.assigned == [TopicPartition(topic, p) for p in (0, 1, 2)]
    assert rec.seeks == [(TopicPartition(topic, 1), 42)]
    assert rec.sought_to_end == [TopicPartition(topic, 0), TopicPartition(topic, 2)]


async def test_seek_to_cursor_falls_back_to_cursor_partition(broker: _FakeBroker) -> None:
    """No topic metadata → assign just the cursor's partition (it provably existed)."""
    t = KafkaTransport()
    rec = _SeekRecorder()

    await t._seek_to_cursor(cast(AIOKafkaConsumer, rec), "lt.market.bars.1m", "3:9")

    assert rec.assigned == [TopicPartition("lt.market.bars.1m", 3)]
    assert rec.seeks == [(TopicPartition("lt.market.bars.1m", 3), 10)]
    assert rec.sought_to_end == []


# --- reconnect with backoff ---


async def test_tail_reconnects_after_broker_error(broker: _FakeBroker) -> None:
    t = _fast()
    await t.publish("market:bars:1m", b"live", key="AAPL")
    broker.fail_plan.append(0)  # first consumer dies before yielding anything
    # the stream label is the bounded logical prefix (first two segments)
    before = metric_value("llamatrade_events_reconnects_total", stream="market:bars", mode="tail")
    got = await _drain(t.tail("market:bars:1m", from_cursor=CURSOR_BEGIN))
    assert [v for _, v in got] == [b"live"]  # the tail survived the error
    after = metric_value("llamatrade_events_reconnects_total", stream="market:bars", mode="tail")
    assert after == before + 1


async def test_tail_reconnect_resumes_from_last_yielded_cursor(broker: _FakeBroker) -> None:
    t = _fast()
    for i in range(3):
        await t.publish("market:bars:1m", f"b{i}".encode(), key="AAPL")
    broker.fail_plan.append(1)  # yield one record, then die mid-stream
    got = await _drain(t.tail("market:bars:1m", from_cursor=CURSOR_BEGIN))
    # no loss, no duplicates: b0 before the failure, b1/b2 after the reconnect
    assert [v for _, v in got] == [b"b0", b"b1", b"b2"]


async def test_consume_reconnects_and_resumes_group_cleanly(broker: _FakeBroker) -> None:
    t = _fast()
    await t.publish("ledger:fills", b"f1", key="acctA")
    await t.publish("ledger:fills", b"f2", key="acctA")
    broker.fail_plan.append(1)  # die after delivering f1
    before = metric_value(
        "llamatrade_events_reconnects_total", stream="ledger:fills", mode="consume"
    )
    seen: list[bytes] = []
    agen = t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    async for cursor, value in agen:
        seen.append(value)
        await t.ack("ledger:fills", "portfolio-ledger", cursor)
    await agen.aclose()
    # committed offsets carry across the reconnect: lossless, no duplicates
    assert seen == [b"f1", b"f2"]
    after = metric_value(
        "llamatrade_events_reconnects_total", stream="ledger:fills", mode="consume"
    )
    assert after == before + 1


# --- topic auto-create gate ---


async def test_ensure_group_autocreates_topic_when_enabled(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KAFKA_AUTO_CREATE_TOPICS", raising=False)
    t = KafkaTransport()  # PLAINTEXT → auto-create defaults on
    await t.ensure_group("ledger:fills", "portfolio-ledger")
    assert "lt.ledger.fills" in broker.logs


async def test_missing_topic_raises_when_autocreate_disabled(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAFKA_AUTO_CREATE_TOPICS", "false")
    t = KafkaTransport()
    with pytest.raises(MissingTopicError, match=r"lt\.ledger\.fills.*Terraform"):
        await t.ensure_group("ledger:fills", "portfolio-ledger")
    assert "lt.ledger.fills" not in broker.logs


async def test_existing_topic_passes_when_autocreate_disabled(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KAFKA_AUTO_CREATE_TOPICS", "false")
    broker.logs["lt.ledger.fills"] = []
    t = KafkaTransport()
    await t.ensure_group("ledger:fills", "portfolio-ledger")  # must not raise


async def test_autocreate_defaults_off_outside_plaintext(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KAFKA_AUTO_CREATE_TOPICS", raising=False)
    t = KafkaTransport(security_protocol="SASL_SSL")
    with pytest.raises(MissingTopicError):
        await t.ensure_group("ledger:fills", "portfolio-ledger")


# --- partition pause/resume + poll interval ---


async def test_pause_and_resume_partition(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    tp = TopicPartition("lt.ledger.fills", 0)
    agen = t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    async for cursor, _value in agen:
        await t.pause_partition("ledger:fills", "portfolio-ledger", cursor)
        assert tp in broker.consumers[-1].paused
        await t.resume_partition("ledger:fills", "portfolio-ledger", cursor)
        assert broker.consumers[-1].paused == set()
        break
    await agen.aclose()


async def test_pause_resume_without_live_consumer_is_noop(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.pause_partition("ledger:fills", "portfolio-ledger", "0:0")  # must not raise
    await t.resume_partition("ledger:fills", "portfolio-ledger", "0:0")


async def test_consume_sets_max_poll_interval(broker: _FakeBroker) -> None:
    t = KafkaTransport(max_poll_interval_ms=123_000)
    await t.publish("ledger:fills", b"f1", key="acctA")
    await _drain(t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN))
    assert broker.consumer_kwargs[-1].get("max_poll_interval_ms") == 123_000


async def test_consume_default_max_poll_interval_allows_long_retries(
    broker: _FakeBroker,
) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"f1", key="acctA")
    await _drain(t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN))
    assert broker.consumer_kwargs[-1].get("max_poll_interval_ms") == 1_800_000


# --- bounded start + post-auth liveness ---


class _StalledMetadata:
    """A metadata handle that never answers (an authenticated but dead session)."""

    async def fetch_all_metadata(self) -> set[str]:
        await asyncio.Event().wait()
        return set()  # unreachable


class _StalledProducer:
    """A producer whose start (or first metadata fetch) never completes."""

    def __init__(self, *, stall_start: bool) -> None:
        self._stall_start = stall_start
        self.client = _StalledMetadata() if not stall_start else _FakeClient(_FakeBroker())
        self.stopped = False

    async def start(self) -> None:
        if self._stall_start:
            await asyncio.Event().wait()

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(
        self, topic: str, value: bytes, key: bytes | None = None
    ) -> _FakeRecord:
        return _FakeRecord(0, 0, key, value)


def _stalled_producers(
    monkeypatch: pytest.MonkeyPatch, *, stall_start: bool
) -> list[_StalledProducer]:
    built: list[_StalledProducer] = []

    def make(**kw: object) -> _StalledProducer:
        built.append(_StalledProducer(stall_start=stall_start))
        return built[-1]

    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaProducer", make)
    return built


async def test_a_start_that_never_completes_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected token authenticates without error and then retries metadata
    forever; the bounded start turns that into a typed failure and a metric."""
    built = _stalled_producers(monkeypatch, stall_start=True)
    t = KafkaTransport(client_start_timeout_seconds=0.05)
    before = metric_value(START_FAILURES, kind="producer", reason="start_timeout")

    with pytest.raises(TransportAuthError, match="start_timeout"):
        await asyncio.wait_for(t.publish("ledger:fills", b"x", key="acctA"), timeout=5.0)

    assert built[0].stopped  # the half-started client was released
    assert metric_value(START_FAILURES, kind="producer", reason="start_timeout") == before + 1


async def test_a_started_client_that_cannot_fetch_metadata_fails_liveness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _stalled_producers(monkeypatch, stall_start=False)
    t = KafkaTransport(client_start_timeout_seconds=0.05)
    before = metric_value(START_FAILURES, kind="producer", reason="liveness_timeout")

    with pytest.raises(TransportAuthError, match="liveness_timeout"):
        await asyncio.wait_for(t.publish("ledger:fills", b"x", key="acctA"), timeout=5.0)

    assert built[0].stopped
    assert metric_value(START_FAILURES, kind="producer", reason="liveness_timeout") == before + 1


async def test_a_stalled_start_leaves_no_cached_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The next publish must be able to build a fresh producer."""
    built = _stalled_producers(monkeypatch, stall_start=True)
    t = KafkaTransport(client_start_timeout_seconds=0.05)

    for _ in range(2):
        with pytest.raises(TransportAuthError):
            await t.publish("ledger:fills", b"x", key="acctA")

    assert len(built) == 2


async def test_a_consumer_that_cannot_start_is_bounded_too(
    broker: _FakeBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``length`` opens a probe consumer; a stalled probe must not hang it."""

    class _StalledConsumer:
        async def start(self) -> None:
            await asyncio.Event().wait()

        async def stop(self) -> None: ...

        async def topics(self) -> set[str]:
            return set()

    monkeypatch.setattr(
        "llamatrade_events.transport.kafka.AIOKafkaConsumer",
        lambda *a, **kw: _StalledConsumer(),
    )
    broker.logs["lt.ledger.fills"] = []
    t = KafkaTransport(client_start_timeout_seconds=0.05)

    with pytest.raises(TransportAuthError, match="start_timeout"):
        await asyncio.wait_for(t.length("ledger:fills"), timeout=5.0)


# --- spurious cancellation containment ---


async def test_stop_containment_swallows_a_spurious_cancellation() -> None:
    """aiokafka's ``NoGroupCoordinator.close()`` awaits a task it cancelled before
    it ever ran, so the CancelledError surfaces in a caller nobody cancelled."""
    t = KafkaTransport()
    calls: list[str] = []

    async def stop() -> None:
        calls.append("stop")
        raise asyncio.CancelledError

    await t._stop_contained(stop)  # must not raise
    assert calls == ["stop"]


async def test_stop_containment_reraises_a_real_cancellation() -> None:
    t = KafkaTransport()
    entered = asyncio.Event()

    async def stop() -> None:
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(t._stop_contained(stop))
    await asyncio.wait_for(entered.wait(), timeout=5.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_length_contains_the_probe_stops_spurious_cancellation(
    broker: _FakeBroker,
) -> None:
    """Portfolio's DLQ replay and fill ingestion read length/purge; a spurious
    CancelledError there would read as cooperative shutdown."""
    t = KafkaTransport()
    await t.publish("ledger:fills", b"a", key="x")
    broker.stop_raises_cancelled = True

    assert await t.length("ledger:fills") == 1
    await t.purge("ledger:fills")  # must not raise either
    assert await t.length("ledger:fills") == 0


async def test_length_still_propagates_a_real_cancellation(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    await t.publish("ledger:fills", b"a", key="x")
    broker.stop_gate = asyncio.Event()
    task = asyncio.create_task(t.length("ledger:fills"))

    await asyncio.wait_for(broker.stop_entered.wait(), timeout=5.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_purge_deletes_every_record_up_to_the_end(broker: _FakeBroker) -> None:
    t = KafkaTransport()
    for i in range(3):
        await t.publish("ledger:fills", f"f{i}".encode(), key="acctA")

    await t.purge("ledger:fills")

    assert await t.length("ledger:fills") == 0


async def test_purge_up_to_cursor_deletes_only_through_that_offset(broker: _FakeBroker) -> None:
    """Cursor-bounded purge clears only up to and including the cursor's offset,
    leaving records at later offsets (re-parked during a bounded drain)."""
    t = KafkaTransport()
    for i in range(5):
        await t.publish("ledger:fills", f"f{i}".encode(), key="acctA")

    await t.purge("ledger:fills", up_to_cursor="0:2")  # deletes offsets 0..2

    assert await t.length("ledger:fills") == 2


# --- broken-credentials signal ---


def _signalling(threshold: int) -> KafkaTransport:
    """A transport that never sleeps between reconnects and escalates early."""
    return KafkaTransport(
        reconnect_base_delay_seconds=0.0,
        reconnect_max_delay_seconds=0.0,
        auth_failure_alert_threshold=threshold,
    )


async def test_consume_keeps_retrying_and_flags_repeated_start_failures(
    broker: _FakeBroker,
) -> None:
    """Readers never give up on the money path, so the operator signal for a
    permanently broken credential is a counter, not a changed control flow."""
    t = _signalling(2)
    await t.publish("ledger:fills", b"f1", key="acctA")
    broker.start_failures = 3
    before = metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume")

    got = await _drain(
        t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    )

    assert [v for _, v in got] == [b"f1"]  # the reader recovered rather than dying
    # failures 1..3 with a threshold of 2: the second and third are escalated
    after = metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume")
    assert after == before + 2


async def test_tail_flags_repeated_start_failures(broker: _FakeBroker) -> None:
    t = _signalling(1)
    await t.publish("market:bars:1m", b"live", key="AAPL")
    broker.start_failures = 1
    before = metric_value(BROKEN_CREDENTIALS, stream="market:bars", mode="tail")

    got = await _drain(t.tail("market:bars:1m", from_cursor=CURSOR_BEGIN))

    assert [v for _, v in got] == [b"live"]
    assert metric_value(BROKEN_CREDENTIALS, stream="market:bars", mode="tail") == before + 1


async def test_a_mid_stream_failure_is_not_a_credentials_signal(broker: _FakeBroker) -> None:
    """A broker fault after the reader started says nothing about credentials."""
    t = _signalling(1)
    await t.publish("ledger:fills", b"f1", key="acctA")
    await t.publish("ledger:fills", b"f2", key="acctA")
    broker.fail_plan.append(1)  # die after delivering f1
    before = metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume")

    agen = t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    seen: list[bytes] = []
    async for cursor, value in agen:
        seen.append(value)
        await t.ack("ledger:fills", "portfolio-ledger", cursor)
    await agen.aclose()

    assert seen == [b"f1", b"f2"]
    assert metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume") == before


async def test_a_successful_start_resets_the_failure_run(broker: _FakeBroker) -> None:
    t = _signalling(2)
    await t.publish("ledger:fills", b"f1", key="acctA")
    # one failed start, then a success, then another failed start: never two in a row
    broker.start_failures = 1
    broker.fail_plan = [0, 0]
    before = metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume")

    got = await _drain(
        t.consume("ledger:fills", "portfolio-ledger", "c1", group_start_id=CURSOR_BEGIN)
    )

    assert [v for _, v in got] == [b"f1"]
    assert metric_value(BROKEN_CREDENTIALS, stream="ledger:fills", mode="consume") == before
