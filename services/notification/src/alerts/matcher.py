"""Event-driven alert matching, run inside the notification consumer.

Maps arriving notification categories onto the event-shaped alert condition
types and fires matching alerts. STRATEGY_SIGNAL has no backbone event yet
and stays unmatched until one exists.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.notification import Alert
from llamatrade_proto.generated import events_pb2, notification_pb2

from src.alerts.engine import trigger_alert
from src.pipeline import AlertMatcher, Dispatcher

_E = events_pb2
_C = notification_pb2

CONDITIONS_BY_CATEGORY: dict[int, int] = {
    _E.NOTIFICATION_CATEGORY_ORDER_FILLED: _C.ALERT_CONDITION_TYPE_ORDER_FILLED,
    _E.NOTIFICATION_CATEGORY_POSITION_DRIFT: _C.ALERT_CONDITION_TYPE_RECONCILIATION_DRIFT,
    _E.NOTIFICATION_CATEGORY_RECONCILIATION_DRIFT: (_C.ALERT_CONDITION_TYPE_RECONCILIATION_DRIFT),
    _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN: _C.ALERT_CONDITION_TYPE_SLEEVE_FROZEN,
}


class EventAlertMatcher(AlertMatcher):
    """Fires event-shaped user alerts for a just-persisted notification."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        dispatcher: Dispatcher,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher

    async def match(self, tenant_id: UUID, event: events_pb2.NotificationEvent) -> None:
        condition_type = CONDITIONS_BY_CATEGORY.get(event.category)
        if condition_type is None:
            return
        async with tenant_session(tenant_id, self._session_factory) as db:
            candidates = await self._candidates(db, tenant_id, condition_type, event)
        for alert_id in candidates:
            await trigger_alert(
                self._session_factory,
                self._dispatcher,
                alert_id=alert_id,
                tenant_id=tenant_id,
                reason=event.reason or _E.NotificationCategory.Name(event.category).lower(),
                bucket=f"event:{event.category}:{event.symbol}:{event.session_id}",
            )

    @staticmethod
    async def _candidates(
        db: AsyncSession,
        tenant_id: UUID,
        condition_type: int,
        event: events_pb2.NotificationEvent,
    ) -> list[UUID]:
        stmt = select(Alert.id, Alert.symbol, Alert.condition).where(
            Alert.tenant_id == tenant_id,
            Alert.alert_type == condition_type,
            Alert.status == _C.ALERT_STATUS_ACTIVE,
        )
        matched = []
        for alert_id, symbol, condition in (await db.execute(stmt)).all():
            if symbol and event.symbol and symbol != event.symbol:
                continue
            strategy_filter = (condition or {}).get("strategy_id")
            if strategy_filter and event.strategy_id and strategy_filter != event.strategy_id:
                continue
            matched.append(alert_id)
        return matched
