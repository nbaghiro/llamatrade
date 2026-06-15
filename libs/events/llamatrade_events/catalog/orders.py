"""Order lifecycle events — trading → UI (per-session tail fan-out).

Producer: trading order executor / live runner. Consumer: trading gRPC servicer's
``StreamOrderUpdates``, fanned out to each browser. The payload is the same
``OrderUpdate`` RPC message the gRPC edge already streams, so the bus and the wire
share one definition.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from llamatrade_events.bus import EventBus
from llamatrade_events.catalog._base import EnvelopeTailChannel
from llamatrade_events.channels import ORDERS
from llamatrade_events.codec import register_payload
from llamatrade_events.transport.base import CURSOR_NEW, Cursor
from llamatrade_proto.generated import events_pb2, trading_pb2

OrderUpdate = trading_pb2.OrderUpdate

# OrderUpdate.event_type (the producer's update kind) → semantic EventType.
_EVENT_TYPE: dict[str, int] = {
    "submitted": events_pb2.EVENT_TYPE_ORDER_SUBMITTED,
    "new": events_pb2.EVENT_TYPE_ORDER_SUBMITTED,
    "filled": events_pb2.EVENT_TYPE_ORDER_FILLED,
    "partial_fill": events_pb2.EVENT_TYPE_ORDER_FILLED,
    "cancelled": events_pb2.EVENT_TYPE_ORDER_CANCELLED,
    "canceled": events_pb2.EVENT_TYPE_ORDER_CANCELLED,
    "rejected": events_pb2.EVENT_TYPE_ORDER_REJECTED,
}
_DEFAULT = events_pb2.EVENT_TYPE_ORDER_UPDATED

# Every order EventType carries an OrderUpdate payload.
for _t in {_DEFAULT, *_EVENT_TYPE.values()}:
    register_payload(_t, OrderUpdate)


def event_type_for(update_kind: str) -> int:
    """Map an ``OrderUpdate.event_type`` string to its semantic EventType."""
    return _EVENT_TYPE.get(update_kind.lower(), _DEFAULT)


class OrderEvents(EnvelopeTailChannel[trading_pb2.OrderUpdate]):
    """Per-session order lifecycle stream."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        super().__init__(ORDERS, bus=bus)

    async def publish(
        self,
        session_id: str | UUID,
        update: OrderUpdate,
        *,
        tenant_id: str = "",
        user_id: str = "",
        event_id: str | None = None,
    ) -> Cursor:
        return await self._publish(
            ORDERS.key(session_id=session_id),
            event_type_for(update.event_type),
            update,
            tenant_id=tenant_id,
            user_id=user_id,
            event_id=event_id,
        )

    async def tail(
        self, session_id: str | UUID, *, from_cursor: Cursor = CURSOR_NEW
    ) -> AsyncIterator[tuple[Cursor, OrderUpdate]]:
        async for cursor, update in self._tail(
            ORDERS.key(session_id=session_id), from_cursor=from_cursor
        ):
            yield cursor, update
