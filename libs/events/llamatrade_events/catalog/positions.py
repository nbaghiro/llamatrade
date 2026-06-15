"""Position lifecycle events — trading → UI (per-session tail fan-out).

Producer: trading position service / live runner. Consumer: trading gRPC
``StreamPositionUpdates``. Reuses the ``PositionUpdate`` RPC message.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from llamatrade_events.bus import EventBus
from llamatrade_events.catalog._base import EnvelopeTailChannel
from llamatrade_events.channels import POSITIONS
from llamatrade_events.codec import register_payload
from llamatrade_events.transport.base import CURSOR_NEW, Cursor
from llamatrade_proto.generated import events_pb2, trading_pb2

PositionUpdate = trading_pb2.PositionUpdate

_EVENT_TYPE: dict[str, int] = {
    "opened": events_pb2.EVENT_TYPE_POSITION_OPENED,
    "closed": events_pb2.EVENT_TYPE_POSITION_CLOSED,
    "updated": events_pb2.EVENT_TYPE_POSITION_UPDATED,
}
_DEFAULT = events_pb2.EVENT_TYPE_POSITION_UPDATED

for _t in {_DEFAULT, *_EVENT_TYPE.values()}:
    register_payload(_t, PositionUpdate)


def event_type_for(update_kind: str) -> int:
    """Map a ``PositionUpdate.event_type`` string to its semantic EventType."""
    return _EVENT_TYPE.get(update_kind.lower(), _DEFAULT)


class PositionEvents(EnvelopeTailChannel[trading_pb2.PositionUpdate]):
    """Per-session position lifecycle stream."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        super().__init__(POSITIONS, bus=bus)

    async def publish(
        self,
        session_id: str | UUID,
        update: PositionUpdate,
        *,
        tenant_id: str = "",
        user_id: str = "",
        event_id: str | None = None,
    ) -> Cursor:
        return await self._publish(
            POSITIONS.key(session_id=session_id),
            event_type_for(update.event_type),
            update,
            tenant_id=tenant_id,
            user_id=user_id,
            event_id=event_id,
        )

    async def tail(
        self, session_id: str | UUID, *, from_cursor: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, PositionUpdate]]:
        async for cursor, update in self._tail(
            POSITIONS.key(session_id=session_id), from_cursor=from_cursor
        ):
            yield cursor, update
