"""The transport seam: sentinels, protocol conformance, and fake-only behaviors.

The semantics both backends share are pinned by the parametrized contract suite
in ``test_transport_contract.py``; this module keeps what is specific to the
seam itself and to the fake (advisory ``maxlen`` trimming, monotonic cursors).
"""

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
