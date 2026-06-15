"""The transport seam contract."""

from __future__ import annotations

from conftest import FakeTransport

from llamatrade_events.transport.base import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    EventTransport,
)
from llamatrade_events.transport.redis_streams import RedisStreamsTransport


def test_sentinels() -> None:
    assert CURSOR_NEW == "$"
    assert CURSOR_BEGIN == "0"


def test_fake_and_redis_satisfy_protocol() -> None:
    # runtime_checkable Protocol → both backends are interchangeable to the bus.
    assert isinstance(FakeTransport(), EventTransport)
    assert isinstance(RedisStreamsTransport(), EventTransport)


def test_redis_transport_namespaces_keys() -> None:
    t = RedisStreamsTransport()
    assert t.key("ledger:fills") == "lt:ledger:fills"


async def test_fake_publish_assigns_monotonic_cursors() -> None:
    t = FakeTransport()
    c1 = await t.publish("s", b"a", maxlen=10)
    c2 = await t.publish("s", b"b", maxlen=10)
    assert (c1, c2) == ("1", "2")


async def test_fake_maxlen_trims() -> None:
    t = FakeTransport()
    for i in range(5):
        await t.publish("s", str(i).encode(), maxlen=2)
    assert [v for _, v in t.entries("s")] == [b"3", b"4"]
