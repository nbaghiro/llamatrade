"""The transport seam contract."""

from __future__ import annotations

from conftest import FakeTransport

from llamatrade_events.transport.base import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    EventTransport,
    OutgoingRecord,
)
from llamatrade_events.transport.kafka import KafkaTransport


def test_sentinels() -> None:
    assert CURSOR_NEW == "$"
    assert CURSOR_BEGIN == "0"


def test_all_backends_satisfy_protocol() -> None:
    # runtime_checkable Protocol → every backend is interchangeable to the bus.
    assert isinstance(FakeTransport(), EventTransport)
    assert isinstance(KafkaTransport(), EventTransport)


def test_kafka_transport_namespaces_topic() -> None:
    t = KafkaTransport()
    assert t.topic("ledger:fills") == "lt.ledger.fills"


async def test_fake_publish_assigns_monotonic_cursors() -> None:
    t = FakeTransport()
    c1 = await t.publish("s", b"a", maxlen=10)
    c2 = await t.publish("s", b"b", maxlen=10)
    assert (c1, c2) == ("1", "2")


async def test_fake_publish_many_appends_in_order_and_honors_maxlen() -> None:
    t = FakeTransport()
    cursors = await t.publish_many(
        "s",
        [OutgoingRecord(str(i).encode(), "k") for i in range(5)],
        maxlen=2,
    )
    assert cursors == ["1", "2", "3", "4", "5"]  # one cursor per record, in order
    assert [v for _, v in t.entries("s")] == [b"3", b"4"]  # maxlen trims like publish


async def test_fake_maxlen_trims() -> None:
    t = FakeTransport()
    for i in range(5):
        await t.publish("s", str(i).encode(), maxlen=2)
    assert [v for _, v in t.entries("s")] == [b"3", b"4"]


async def test_fake_pause_resume_mirrors_calls() -> None:
    t = FakeTransport()
    await t.pause_partition("s", "g", "0:7")
    assert ("s", "g") in t.paused
    await t.resume_partition("s", "g", "0:7")
    assert t.paused == set()
    assert t.pause_calls == [("s", "g", "0:7")]
    assert t.resume_calls == [("s", "g", "0:7")]


async def test_fake_purge_clears_the_whole_stream() -> None:
    t = FakeTransport()
    for i in range(3):
        await t.publish("s", f"f{i}".encode())
    await t.purge("s")
    assert await t.length("s") == 0


async def test_fake_purge_up_to_cursor_leaves_later_entries() -> None:
    t = FakeTransport()
    for i in range(5):
        await t.publish("s", f"f{i}".encode())  # cursors "1".."5"
    await t.purge("s", up_to_cursor="3")  # drops cursors 1..3
    assert [v for _, v in t.entries("s")] == [b"f3", b"f4"]
    assert await t.length("s") == 2
