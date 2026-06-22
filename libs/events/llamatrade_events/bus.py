"""EventBus — proto-aware publish/tail/consume over a pluggable transport.

Ties the codec (envelope ⇄ bytes) to a :class:`EventTransport` (bytes ⇄ backend).
The catalog and consumer sit on top of this; nothing here knows the backend.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from llamatrade_events.codec import EventEnvelope, decode_envelope, encode_envelope
from llamatrade_events.transport.base import CURSOR_NEW, Cursor, EventTransport
from llamatrade_events.transport.redis_streams import RedisStreamsTransport
from llamatrade_telemetry import inject_context


class EventBus:
    """Publish/consume the EventEnvelope over a swappable transport."""

    def __init__(self, transport: EventTransport | None = None) -> None:
        self._transport: EventTransport = transport or RedisStreamsTransport()

    @property
    def transport(self) -> EventTransport:
        return self._transport

    # ---- publish ----

    async def publish_envelope(
        self, stream: str, envelope: EventEnvelope, *, maxlen: int, key: str | None = None
    ) -> Cursor:
        # Carry the current trace context in the envelope so a consumer can link
        # its processing span to the producer (e.g. fill → ledger projection).
        carrier: dict[str, str] = {}
        inject_context(carrier)
        for header, value in carrier.items():
            envelope.metadata[header] = value
        return await self._transport.publish(
            stream, encode_envelope(envelope), key=key, maxlen=maxlen
        )

    async def publish_raw(
        self, stream: str, value: bytes, *, maxlen: int, key: str | None = None
    ) -> Cursor:
        """For raw (un-enveloped) channels like the high-volume bar stream."""
        return await self._transport.publish(stream, value, key=key, maxlen=maxlen)

    # ---- tail (independent fan-out) ----

    async def tail_envelopes(
        self, stream: str, *, from_cursor: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, EventEnvelope]]:
        async for cursor, value in self._transport.tail(stream, from_cursor=from_cursor):
            yield cursor, decode_envelope(value)

    async def tail_raw(
        self, stream: str, *, from_cursor: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        async for cursor, value in self._transport.tail(stream, from_cursor=from_cursor):
            yield cursor, value

    # ---- consume (durable consumer group) ----

    async def ensure_group(self, stream: str, group: str) -> None:
        await self._transport.ensure_group(stream, group)

    async def consume_raw(
        self, stream: str, group: str, consumer: str, *, group_start_id: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        """Durable consume yielding the raw entry bytes (undecoded).

        Lets the caller decode inside its own error boundary so a corrupt entry
        is handled (DLQ/skip) instead of crashing the loop. ``group_start_id``
        sets where a brand-new group begins.
        """
        async for cursor, value in self._transport.consume(
            stream, group, consumer, group_start_id=group_start_id
        ):
            yield cursor, value

    async def consume_envelopes(
        self, stream: str, group: str, consumer: str, *, group_start_id: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, EventEnvelope]]:
        """Durable consume yielding decoded envelopes. NOTE: a corrupt entry
        raises out of this generator — use :meth:`consume_raw` if the caller
        needs to handle undecodable entries gracefully."""
        async for cursor, value in self._transport.consume(
            stream, group, consumer, group_start_id=group_start_id
        ):
            yield cursor, decode_envelope(value)

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        await self._transport.ack(stream, group, cursor)

    async def pending(self, stream: str, group: str) -> int:
        return await self._transport.pending(stream, group)

    async def close(self) -> None:
        await self._transport.close()
