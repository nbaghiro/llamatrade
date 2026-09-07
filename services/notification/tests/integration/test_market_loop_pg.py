"""Market-loop body over real Postgres and an in-memory bar tail.

The leadership lock pair itself is pinned in test_alerts_pg.py; these tests
drive ``run_market_loop`` end to end: bars published on the ``BarEvents``
catalog over a blocking ``FakeTransport`` tail, evaluated by the real engine
against seeded alerts, with leadership, symbol-refresh cadence, re-election,
and stop-event shutdown all observable through the database and the lock.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from llamatrade_db import tenant_session
from llamatrade_db.models.auth import Tenant, User
from llamatrade_db.models.notification import Alert, Notification
from llamatrade_events import EventBus
from llamatrade_events.catalog.bars import BarEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_events.transport.base import CURSOR_BEGIN, CURSOR_NEW, Cursor
from llamatrade_proto.generated import common_pb2, market_data_pb2, notification_pb2

import src.alerts.market_loop as market_loop_module
from src.alerts.market_loop import (
    release_leadership,
    run_market_loop,
    try_acquire_leadership,
)
from src.pipeline import Dispatcher, PendingDelivery

pytestmark = pytest.mark.integration

TENANT_ID = UUID("41111111-1111-1111-1111-111111111111")
USER_ID = UUID("42222222-2222-2222-2222-222222222222")
_C = notification_pb2


class RecordingDispatcher(Dispatcher):
    def __init__(self) -> None:
        self.dispatched: list[PendingDelivery] = []

    async def dispatch(self, pending: list[PendingDelivery]) -> None:
        self.dispatched.extend(pending)


class TailingFakeTransport(FakeTransport):
    """FakeTransport whose tail blocks for new entries, like a live broker.

    ``tail_started`` marks the loop's snapshot point (safe to publish after);
    ``end_tail`` terminates the stream the way a closing broker connection ends
    the real tail, letting tests join the loop deterministically.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tail_started = asyncio.Event()
        self._arrived = asyncio.Event()
        self._ended = False

    async def publish(
        self,
        stream: str,
        value: bytes,
        *,
        key: str | None = None,
        maxlen: int | None = None,
    ) -> Cursor:
        cursor = await super().publish(stream, value, key=key, maxlen=maxlen)
        self._arrived.set()
        return cursor

    def end_tail(self) -> None:
        self._ended = True
        self._arrived.set()

    async def tail(
        self,
        stream: str,
        *,
        from_cursor: Cursor = CURSOR_NEW,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        if from_cursor == CURSOR_NEW:
            position = self._seq
        elif from_cursor == CURSOR_BEGIN:
            position = 0
        else:
            position = int(from_cursor)
        self.tail_started.set()
        while True:
            pending = [(c, v) for c, v in self.entries(stream) if int(c) > position]
            for cursor, value in pending:
                position = int(cursor)
                yield cursor, value
            if self._ended:
                return
            if pending:
                continue
            self._arrived.clear()
            if any(int(c) > position for c, _ in self.entries(stream)):
                continue
            await self._arrived.wait()


def _bar(symbol: str, close: str, *, minute: int, volume: int = 1000) -> market_data_pb2.Bar:
    return market_data_pb2.Bar(
        symbol=symbol,
        timestamp=common_pb2.Timestamp(seconds=minute * 60),
        close=common_pb2.Decimal(value=close),
        volume=volume,
    )


async def _seed(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        db.add(Tenant(id=TENANT_ID, name="t", slug="t4"))
        db.add(
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email="owner@test",
                password_hash="x",
                is_active=True,
            )
        )
        await db.commit()


async def _make_alert(
    session_factory: async_sessionmaker,
    *,
    symbol: str = "SPY",
    threshold: str = "500",
    channels: list[int] | None = None,
) -> UUID:
    alert_id = uuid4()
    async with session_factory() as db:
        db.add(
            Alert(
                id=alert_id,
                tenant_id=TENANT_ID,
                name="watch",
                alert_type=_C.ALERT_CONDITION_TYPE_PRICE_ABOVE,
                symbol=symbol,
                condition={"threshold": threshold},
                channels=channels or [int(_C.CHANNEL_TYPE_EMAIL)],
                cooldown_minutes=60,
                created_by=USER_ID,
            )
        )
        await db.commit()
    return alert_id


async def _notification_count(session_factory: async_sessionmaker) -> int:
    async with tenant_session(TENANT_ID, session_factory) as db:
        return int(await db.scalar(select(func.count()).select_from(Notification)) or 0)


async def _assert_lock_free(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        conn = await try_acquire_leadership(engine)
        assert conn is not None
        await release_leadership(conn)
    finally:
        await engine.dispose()


async def test_loop_tails_bars_and_triggers_matching_alert(
    session_factory: async_sessionmaker, postgres_url: str
) -> None:
    """Unwatched, below-threshold, and unparseable bars pass; the hit fires once."""
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory)
    dispatcher = RecordingDispatcher()
    transport = TailingFakeTransport()
    bars = BarEvents(bus=EventBus(transport))
    stop = asyncio.Event()
    engine: AsyncEngine = create_async_engine(postgres_url)
    try:
        task = asyncio.create_task(
            run_market_loop(engine, session_factory, dispatcher, bars=bars, stop_event=stop)
        )
        await asyncio.wait_for(transport.tail_started.wait(), timeout=10.0)

        await bars.publish(_bar("QQQ", "501", minute=1))
        await bars.publish(_bar("SPY", "", minute=2))
        await bars.publish(_bar("SPY", "499", minute=3))
        await bars.publish(_bar("SPY", "501", minute=4))
        transport.end_tail()
        await asyncio.wait_for(task, timeout=10.0)

        assert await _notification_count(session_factory) == 1
        async with tenant_session(TENANT_ID, session_factory) as db:
            alert = await db.get(Alert, alert_id)
            assert alert is not None and alert.trigger_count == 1
        assert [d.channel for d in dispatcher.dispatched] == [_C.CHANNEL_TYPE_EMAIL]
        assert dispatcher.dispatched[0].destination == "owner@test"
        await _assert_lock_free(postgres_url)
    finally:
        stop.set()
        transport.end_tail()
        await engine.dispose()


async def test_symbol_refresh_picks_up_alert_created_mid_loop(
    session_factory: async_sessionmaker, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the refresh due, an alert created after the initial sweep still fires."""
    monkeypatch.setattr(market_loop_module, "SYMBOL_REFRESH_SECONDS", 0.0)
    await _seed(session_factory)
    dispatcher = RecordingDispatcher()
    transport = TailingFakeTransport()
    bars = BarEvents(bus=EventBus(transport))
    stop = asyncio.Event()
    engine: AsyncEngine = create_async_engine(postgres_url)
    try:
        task = asyncio.create_task(
            run_market_loop(engine, session_factory, dispatcher, bars=bars, stop_event=stop)
        )
        await asyncio.wait_for(transport.tail_started.wait(), timeout=10.0)

        await _make_alert(session_factory)
        await bars.publish(_bar("SPY", "501", minute=1))
        transport.end_tail()
        await asyncio.wait_for(task, timeout=10.0)

        assert await _notification_count(session_factory) == 1
    finally:
        stop.set()
        transport.end_tail()
        await engine.dispose()


async def test_watched_set_stays_stale_within_refresh_interval(
    session_factory: async_sessionmaker, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the refresh cadence elapses, a newly created alert is not evaluated."""
    monkeypatch.setattr(market_loop_module, "SYMBOL_REFRESH_SECONDS", 3600.0)
    await _seed(session_factory)
    dispatcher = RecordingDispatcher()
    transport = TailingFakeTransport()
    bars = BarEvents(bus=EventBus(transport))
    stop = asyncio.Event()
    engine: AsyncEngine = create_async_engine(postgres_url)
    try:
        task = asyncio.create_task(
            run_market_loop(engine, session_factory, dispatcher, bars=bars, stop_event=stop)
        )
        await asyncio.wait_for(transport.tail_started.wait(), timeout=10.0)

        await _make_alert(session_factory)
        await bars.publish(_bar("SPY", "501", minute=1))
        transport.end_tail()
        await asyncio.wait_for(task, timeout=10.0)

        assert await _notification_count(session_factory) == 0
        assert dispatcher.dispatched == []
    finally:
        stop.set()
        transport.end_tail()
        await engine.dispose()


async def test_leader_stop_releases_lock_and_standby_takes_over(
    session_factory: async_sessionmaker, postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stopped leader stops tailing and releases; the polling standby is elected."""
    monkeypatch.setattr(market_loop_module, "LEADERSHIP_RETRY_SECONDS", 0.02)
    await _seed(session_factory)
    await _make_alert(session_factory)
    engine_a: AsyncEngine = create_async_engine(postgres_url)
    engine_b: AsyncEngine = create_async_engine(postgres_url)
    probe: AsyncEngine = create_async_engine(postgres_url)
    transport_a, transport_b = TailingFakeTransport(), TailingFakeTransport()
    bars_a = BarEvents(bus=EventBus(transport_a))
    bars_b = BarEvents(bus=EventBus(transport_b))
    stop_a, stop_b = asyncio.Event(), asyncio.Event()
    dispatcher_a, dispatcher_b = RecordingDispatcher(), RecordingDispatcher()
    try:
        task_a = asyncio.create_task(
            run_market_loop(engine_a, session_factory, dispatcher_a, bars=bars_a, stop_event=stop_a)
        )
        await asyncio.wait_for(transport_a.tail_started.wait(), timeout=10.0)

        task_b = asyncio.create_task(
            run_market_loop(engine_b, session_factory, dispatcher_b, bars=bars_b, stop_event=stop_b)
        )
        # Let the standby poll a few times; the lock held by A keeps it out.
        await asyncio.sleep(0.1)
        assert not transport_b.tail_started.is_set()
        assert await try_acquire_leadership(probe) is None

        transport_a.end_tail()
        await asyncio.wait_for(task_a, timeout=10.0)
        await asyncio.wait_for(transport_b.tail_started.wait(), timeout=10.0)

        await bars_b.publish(_bar("SPY", "501", minute=1))
        transport_b.end_tail()
        await asyncio.wait_for(task_b, timeout=10.0)

        assert await _notification_count(session_factory) == 1
        assert dispatcher_a.dispatched == []
        assert [d.channel for d in dispatcher_b.dispatched] == [_C.CHANNEL_TYPE_EMAIL]
        await _assert_lock_free(postgres_url)
    finally:
        stop_a.set()
        stop_b.set()
        transport_a.end_tail()
        transport_b.end_tail()
        await engine_a.dispose()
        await engine_b.dispose()
        await probe.dispose()


async def test_stop_event_mid_tail_exits_without_evaluating(
    session_factory: async_sessionmaker, postgres_url: str
) -> None:
    """A bar arriving after stop is not evaluated; the lock is released on exit."""
    await _seed(session_factory)
    await _make_alert(session_factory)
    dispatcher = RecordingDispatcher()
    transport = TailingFakeTransport()
    bars = BarEvents(bus=EventBus(transport))
    stop = asyncio.Event()
    engine: AsyncEngine = create_async_engine(postgres_url)
    try:
        task = asyncio.create_task(
            run_market_loop(engine, session_factory, dispatcher, bars=bars, stop_event=stop)
        )
        await asyncio.wait_for(transport.tail_started.wait(), timeout=10.0)

        stop.set()
        await bars.publish(_bar("SPY", "501", minute=1))
        await asyncio.wait_for(task, timeout=10.0)

        assert await _notification_count(session_factory) == 0
        assert dispatcher.dispatched == []
        await _assert_lock_free(postgres_url)
    finally:
        transport.end_tail()
        await engine.dispose()


async def test_stop_event_set_before_election_returns_without_acquiring(
    session_factory: async_sessionmaker, postgres_url: str
) -> None:
    """Shutdown during standby: the loop returns without taking the lock or tailing."""
    transport = TailingFakeTransport()
    bars = BarEvents(bus=EventBus(transport))
    stop = asyncio.Event()
    stop.set()
    engine: AsyncEngine = create_async_engine(postgres_url)
    try:
        await asyncio.wait_for(
            run_market_loop(
                engine, session_factory, RecordingDispatcher(), bars=bars, stop_event=stop
            ),
            timeout=10.0,
        )
        assert not transport.tail_started.is_set()
        await _assert_lock_free(postgres_url)
    finally:
        await engine.dispose()
