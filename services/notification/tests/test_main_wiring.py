"""Lifespan wiring: the background loops start supervised and join on shutdown.

The infra seams (RLS verify, DB factory/engine, Kafka-backed events, the loop
bodies) are patched; the real lifespan runs, so the test pins what main.py owns:
task creation, the shared stop event, transport exposure on app.state, and the
shutdown join/close sequence.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import llamatrade_db
from llamatrade_events import EventBus
from llamatrade_events.catalog import notifications as notifications_catalog
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport

import src.alerts.market_loop as market_loop_module
import src.grpc.servicer as servicer_module
import src.main as main_module
import src.tasks.consumer as consumer_module
from src.delivery import DeliveryDispatcher

pytestmark = pytest.mark.asyncio


class LoopRecorder:
    """Stands in for a supervised loop: record the call, park until stop."""

    def __init__(self) -> None:
        self.args: tuple[object, ...] = ()
        self.stop_event: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.stopped_cleanly = False

    async def __call__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        stop = kwargs.get("stop_event")
        assert isinstance(stop, asyncio.Event)
        self.stop_event = stop
        self.started.set()
        await stop.wait()
        self.stopped_cleanly = True


async def test_lifespan_starts_loops_and_joins_them_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer_loop, market_loop, dlq_loop = LoopRecorder(), LoopRecorder(), LoopRecorder()
    transport = FakeTransport()
    events = NotificationEvents(bus=EventBus(transport))
    fake_maker = MagicMock(spec=async_sessionmaker)
    fake_engine = MagicMock(spec=AsyncEngine)
    rls_verified = asyncio.Event()
    close_db_calls: list[bool] = []

    async def fake_verify_rls() -> None:
        rls_verified.set()

    async def fake_close_db() -> None:
        close_db_calls.append(True)

    monkeypatch.setattr(main_module, "verify_rls_enforcement", fake_verify_rls)
    monkeypatch.setattr(main_module, "close_db", fake_close_db)
    monkeypatch.setattr(main_module, "get_session_maker", lambda: fake_maker)
    monkeypatch.setattr(servicer_module, "get_session_maker", lambda: fake_maker)
    monkeypatch.setattr(llamatrade_db, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(notifications_catalog, "NotificationEvents", lambda: events)
    monkeypatch.setattr(consumer_module, "run_notification_consumer", consumer_loop)
    monkeypatch.setattr(consumer_module, "run_dlq_sampler", dlq_loop)
    monkeypatch.setattr(market_loop_module, "run_market_loop", market_loop)

    app = main_module.app
    routes_before = list(app.router.routes)
    try:
        async with app.router.lifespan_context(app):
            assert rls_verified.is_set()
            await asyncio.wait_for(consumer_loop.started.wait(), timeout=5.0)
            await asyncio.wait_for(market_loop.started.wait(), timeout=5.0)
            await asyncio.wait_for(dlq_loop.started.wait(), timeout=5.0)

            assert app.state.kafka_transport is transport
            assert consumer_loop.args == (events, fake_maker)
            engine_arg, maker_arg, dispatcher_arg = market_loop.args
            assert engine_arg is fake_engine
            assert maker_arg is fake_maker
            assert isinstance(dispatcher_arg, DeliveryDispatcher)
            assert dlq_loop.args == (events,)
            stop_events = {consumer_loop.stop_event, market_loop.stop_event, dlq_loop.stop_event}
            assert len(stop_events) == 1
    finally:
        app.router.routes = routes_before

    assert consumer_loop.stopped_cleanly
    assert market_loop.stopped_cleanly
    assert dlq_loop.stopped_cleanly
    assert transport.closed
    assert close_db_calls == [True]
