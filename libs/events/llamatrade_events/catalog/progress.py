"""Backtest progress events — backtest worker → UI (per-backtest tail replay).

Producer: the Celery backtest worker. Consumer: backtest gRPC
``StreamBacktestProgress``. A late joiner replays the whole short stream from the
start (default ``from_cursor`` = begin), so the UI never misses early progress.
Reuses the ``BacktestProgressUpdate`` RPC message.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from llamatrade_events.bus import EventBus
from llamatrade_events.catalog._base import EnvelopeTailChannel
from llamatrade_events.channels import BACKTEST_PROGRESS
from llamatrade_events.codec import register_payload
from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_proto.generated import backtest_pb2, events_pb2

BacktestProgressUpdate = backtest_pb2.BacktestProgressUpdate

register_payload(events_pb2.EVENT_TYPE_BACKTEST_PROGRESS, BacktestProgressUpdate)


class ProgressEvents(EnvelopeTailChannel[backtest_pb2.BacktestProgressUpdate]):
    """Per-backtest progress stream (short, replay-from-start for late joiners)."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        super().__init__(BACKTEST_PROGRESS, bus=bus)

    async def publish(
        self,
        backtest_id: str,
        update: BacktestProgressUpdate,
        *,
        tenant_id: str = "",
        event_id: str | None = None,
    ) -> Cursor:
        return await self._publish(
            BACKTEST_PROGRESS.key(backtest_id=backtest_id),
            events_pb2.EVENT_TYPE_BACKTEST_PROGRESS,
            update,
            tenant_id=tenant_id,
            event_id=event_id,
        )

    async def tail(
        self, backtest_id: str, *, from_cursor: Cursor = CURSOR_BEGIN
    ) -> AsyncIterator[tuple[Cursor, BacktestProgressUpdate]]:
        async for cursor, update in self._tail(
            BACKTEST_PROGRESS.key(backtest_id=backtest_id), from_cursor=from_cursor
        ):
            yield cursor, update
