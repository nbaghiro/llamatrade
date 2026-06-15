"""StreamFanout: keyed routing, drop-on-full backpressure, pump from a source."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from llamatrade_events.fanout import StreamFanout


async def test_routes_by_key_and_broadcasts_to_wildcard() -> None:
    fo: StreamFanout[str] = StreamFanout()
    q_aapl = await fo.connect(1, ["AAPL"])
    q_all = await fo.connect(2)  # empty keys = all

    await fo.broadcast("AAPL", "bar-a")
    await fo.broadcast("MSFT", "bar-m")

    assert q_aapl.get_nowait() == "bar-a"
    assert q_aapl.empty()  # MSFT filtered out
    assert q_all.get_nowait() == "bar-a"
    assert q_all.get_nowait() == "bar-m"


async def test_key_matching_is_case_insensitive() -> None:
    fo: StreamFanout[str] = StreamFanout()
    q = await fo.connect(1, ["aapl"])
    await fo.broadcast("AAPL", "x")
    assert q.get_nowait() == "x"


async def test_drop_on_full_does_not_raise() -> None:
    fo: StreamFanout[str] = StreamFanout(queue_max=1)
    q = await fo.connect(1)
    await fo.broadcast("K", "first")
    await fo.broadcast("K", "second")  # dropped, no raise
    assert q.qsize() == 1
    assert q.get_nowait() == "first"


async def test_disconnect_removes_client() -> None:
    fo: StreamFanout[str] = StreamFanout()
    await fo.connect(1)
    assert fo.client_count == 1
    await fo.disconnect(1)
    assert fo.client_count == 0
    await fo.broadcast("K", "x")  # no clients, no error


async def test_pump_drives_broadcast_from_source() -> None:
    async def source() -> AsyncIterator[tuple[str, str]]:
        yield ("AAPL", "b1")
        yield ("AAPL", "b2")
        yield ("MSFT", "b3")

    fo: StreamFanout[str] = StreamFanout()
    q = await fo.connect(9, ["AAPL"])
    await fo.pump(source())
    assert q.qsize() == 2
    assert [q.get_nowait(), q.get_nowait()] == ["b1", "b2"]


async def test_stream_yields_then_cleans_up_on_cancel() -> None:
    fo: StreamFanout[str] = StreamFanout()
    received: list[str] = []

    async def consume() -> None:
        async for item in fo.stream(7, ["AAPL"]):
            received.append(item)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let stream() subscribe
    await fo.broadcast("AAPL", "hello")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert received == ["hello"]
    assert fo.client_count == 0  # stream()'s finally disconnected
