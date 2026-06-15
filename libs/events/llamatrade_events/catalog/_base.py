"""Shared produce/tail plumbing for per-key enveloped UI streams.

Orders, positions, and backtest-progress all have the same shape: wrap a domain
proto in an envelope, publish to a per-entity key, and tail it back (reconnect
replays from a stored cursor). This base owns that mechanism so each family is
just its channel + its ``EventType`` mapping.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Generic, TypeVar, cast

from google.protobuf.message import Message

from llamatrade_events.bus import EventBus
from llamatrade_events.channels import Channel
from llamatrade_events.codec import make_envelope, parse_payload
from llamatrade_events.transport.base import CURSOR_NEW, Cursor

MsgT = TypeVar("MsgT", bound=Message)


class EnvelopeTailChannel(Generic[MsgT]):
    """Wrap/unwrap a single payload type on an enveloped, tail-delivered channel."""

    def __init__(self, channel: Channel, *, bus: EventBus | None = None) -> None:
        self._channel = channel
        self._bus = bus or EventBus()

    @property
    def bus(self) -> EventBus:
        return self._bus

    async def _publish(
        self,
        stream: str,
        event_type: int,
        payload: MsgT,
        *,
        tenant_id: str = "",
        user_id: str = "",
        event_id: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> Cursor:
        env = make_envelope(
            event_type,
            payload,
            event_id=event_id,
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata,
        )
        return await self._bus.publish_envelope(stream, env, maxlen=self._channel.maxlen)

    async def _tail(
        self, stream: str, *, from_cursor: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, MsgT]]:
        async for cursor, env in self._bus.tail_envelopes(stream, from_cursor=from_cursor):
            yield cursor, cast("MsgT", parse_payload(env))

    async def close(self) -> None:
        await self._bus.close()
