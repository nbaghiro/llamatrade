"""Live bar events — market-data → consumers (raw payload, tail fan-out by symbol).

The highest-volume channel, so it skips the envelope: the value is a serialized
``Bar`` message directly (one field, ~80 bytes, no envelope overhead). Producer:
market-data's bar streamer. Consumers: trading's live runner and the market-data
gRPC bar stream, which routes per-symbol through a :class:`StreamFanout`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from llamatrade_events.bus import EventBus
from llamatrade_events.channels import BARS
from llamatrade_events.transport.base import CURSOR_NEW, Cursor
from llamatrade_proto.generated import market_data_pb2

Bar = market_data_pb2.Bar


class BarEvents:
    """The global live-bar stream (raw ``Bar`` payload, no envelope)."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus()
        self._stream = BARS.key()

    @property
    def stream(self) -> str:
        return self._stream

    async def publish(self, bar: Bar) -> Cursor:
        return await self._bus.publish_raw(
            self._stream, bar.SerializeToString(), maxlen=BARS.maxlen
        )

    async def tail(self, *, from_cursor: Cursor = CURSOR_NEW) -> AsyncIterator[tuple[Cursor, Bar]]:
        async for cursor, value in self._bus.tail_raw(self._stream, from_cursor=from_cursor):
            yield cursor, Bar.FromString(value)

    async def close(self) -> None:
        await self._bus.close()
