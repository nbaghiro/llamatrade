"""Broker-backed Celery smoke tier (D2): a real worker over a real Redis broker.

A programmatically-started worker (threads pool) executes submitted tasks end to
end, proving queue-name routing on the wire, effective acks-late delivery, W3C
trace propagation joined across the broker, JSON serialization round-trips, and
that duplicate delivery of a run cannot produce a second result row.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from typing import cast
from uuid import UUID, uuid4

import pytest
import redis as sync_redis
import redis.asyncio as aioredis
from celery import Celery
from celery.contrib.testing.worker import start_worker
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from src import worker_telemetry
from src.celery_app import EXECUTION_QUEUE
from src.services.backtest_service import _enqueue_run_backtest
from src.workers import celery_tasks

pytestmark = pytest.mark.integration

RUN_TASK_NAME = "src.workers.celery_tasks.run_backtest_task"
# Kombu's Redis transport tracks delivered-but-unacked messages in this hash.
UNACKED_KEY = "unacked"


def _reset_cached_broker_state(app: Celery) -> None:
    """Drop the cached amqp/backend/pool so new conf URLs take effect."""
    app._pool = None
    for cached in ("amqp", "backend"):
        app.__dict__.pop(cached, None)


@pytest.fixture
def broker_app(redis_url: str) -> Iterator[tuple[Celery, str]]:
    """The service's Celery app pointed at the container broker (logical DB 1)."""
    from src.celery_app import celery_app

    broker_url = redis_url.rsplit("/", 1)[0] + "/1"
    old_broker = celery_app.conf.broker_url
    old_backend = celery_app.conf.result_backend
    _reset_cached_broker_state(celery_app)
    celery_app.conf.broker_url = broker_url
    celery_app.conf.result_backend = broker_url
    try:
        yield celery_app, broker_url
    finally:
        _reset_cached_broker_state(celery_app)
        celery_app.conf.broker_url = old_broker
        celery_app.conf.result_backend = old_backend


@pytest.fixture
def broker_redis(broker_app: tuple[Celery, str]) -> Iterator[sync_redis.Redis]:
    """A flushed sync client on the broker's logical DB for wire-level assertions."""
    _, broker_url = broker_app
    client = sync_redis.Redis.from_url(broker_url)
    client.flushdb()
    try:
        yield client
    finally:
        client.close()


def _worker(app: Celery):
    return start_worker(
        app,
        pool="threads",
        concurrency=1,
        perform_ping_check=False,
        queues=[EXECUTION_QUEUE],
        loglevel="warning",
        shutdown_timeout=30.0,
    )


def _wait_until(predicate, timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestBrokerSmoke:
    def test_routing_and_json_round_trip(
        self,
        broker_app: tuple[Celery, str],
        broker_redis: sync_redis.Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The enqueue lands on the configured queue's Redis list and a worker bound to
        that queue executes it, round-tripping args and result through JSON."""
        app, _ = broker_app
        backtest_id, tenant_id = str(uuid4()), str(uuid4())
        summary: dict[str, str | float | int] = {
            "status": "completed",
            "backtest_id": backtest_id,
            "total_return": 0.125,
            "total_trades": 4,
        }

        async def fake_execute(got_backtest_id: str, got_tenant_id: str):
            assert got_backtest_id == backtest_id
            assert got_tenant_id == tenant_id
            return summary

        monkeypatch.setattr(celery_tasks, "_execute_backtest", fake_execute)

        task_id = _enqueue_run_backtest(UUID(backtest_id), UUID(tenant_id))

        # Routed by task_routes: the message sits on the "backtest" Redis list.
        assert EXECUTION_QUEUE == "backtest"
        assert broker_redis.llen(EXECUTION_QUEUE) == 1

        with _worker(app):
            result = app.AsyncResult(task_id).get(timeout=60)

        assert result == summary
        assert broker_redis.llen(EXECUTION_QUEUE) == 0

    def test_acks_late_holds_the_message_until_completion(
        self,
        broker_app: tuple[Celery, str],
        broker_redis: sync_redis.Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With acks_late the delivery stays in the unacked hash while the task runs
        and is acked only after it finishes."""
        app, _ = broker_app
        started = threading.Event()
        release = threading.Event()

        async def blocking_execute(backtest_id: str, tenant_id: str):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.02)
            return {"status": "completed", "backtest_id": backtest_id}

        monkeypatch.setattr(celery_tasks, "_execute_backtest", blocking_execute)

        with _worker(app):
            task_id = _enqueue_run_backtest(uuid4(), uuid4())
            assert started.wait(30), "worker never picked up the task"

            assert _wait_until(lambda: broker_redis.hlen(UNACKED_KEY) >= 1), (
                "acks_late must keep the executing delivery unacked"
            )

            release.set()
            result = app.AsyncResult(task_id).get(timeout=60)
            assert result["status"] == "completed"

            assert _wait_until(lambda: broker_redis.hlen(UNACKED_KEY) == 0), (
                "the delivery must be acked after completion"
            )

    def test_trace_context_joins_across_the_wire(
        self,
        broker_app: tuple[Celery, str],
        broker_redis: sync_redis.Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The worker's CONSUMER span parents to the enqueue-side span via the
        traceparent header carried through the broker."""
        app, _ = broker_app
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        monkeypatch.setattr(worker_telemetry, "get_tracer", provider.get_tracer)

        async def fake_execute(backtest_id: str, tenant_id: str):
            return {"status": "completed", "backtest_id": backtest_id}

        monkeypatch.setattr(celery_tasks, "_execute_backtest", fake_execute)

        backtest_id = uuid4()
        with _worker(app):
            tracer = provider.get_tracer("smoke-enqueue")
            with tracer.start_as_current_span("enqueue-side") as enqueue_span:
                task_id = _enqueue_run_backtest(backtest_id, uuid4())
            app.AsyncResult(task_id).get(timeout=60)

            def worker_spans() -> list[ReadableSpan]:
                return [s for s in exporter.get_finished_spans() if s.name == RUN_TASK_NAME]

            assert _wait_until(lambda: len(worker_spans()) == 1), "worker span never exported"

        span = worker_spans()[0]
        enqueue_ctx = enqueue_span.get_span_context()
        assert span.context is not None
        assert span.context.trace_id == enqueue_ctx.trace_id, "trace must join across the broker"
        assert span.parent is not None
        assert span.parent.span_id == enqueue_ctx.span_id, "worker span must parent to the enqueue"
        assert span.kind == SpanKind.CONSUMER
        assert span.attributes is not None
        assert span.attributes["backtest.id"] == str(backtest_id)

    async def test_duplicate_delivery_cannot_produce_a_second_result(
        self,
        broker_app: tuple[Celery, str],
        broker_redis: sync_redis.Redis,
        session_factory,
        postgres_url: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The same run delivered twice executes once; the duplicate is refused by the
        status guard and exactly one result row exists (the unique constraint's backstop
        is proven separately on the schema)."""
        from llamatrade_proto.generated.backtest_pb2 import (
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_PENDING,
        )
        from tests.integration.seeding import (
            get_status,
            market_client,
            result_count,
            seed_backtest,
        )

        app, broker_url = broker_app
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING, with_strategy=True
        )

        monkeypatch.setattr(celery_tasks, "DATABASE_URL", postgres_url)
        monkeypatch.setattr(celery_tasks, "_create_market_data_client", market_client)
        monkeypatch.setattr(
            celery_tasks,
            "_create_redis",
            lambda: aioredis.from_url(broker_url),
        )

        # Progress is advisory; keep the smoke off the event backbone.
        async def quiet_publish(
            self: object,
            backtest_id: str,
            progress: float,
            message: str,
            status: int | None = None,
        ) -> None:
            return None

        async def quiet_close(self: object) -> None:
            return None

        monkeypatch.setattr("src.progress.ProgressPublisher.publish", quiet_publish)
        monkeypatch.setattr("src.progress.ProgressPublisher.close", quiet_close)
        monkeypatch.setattr(
            "src.services.backtest_service.CancellationFlag.make_should_abort",
            lambda self, bid, check_interval=1.0: lambda: False,
        )

        first_id = _enqueue_run_backtest(backtest_id, tenant_id)
        second_id = _enqueue_run_backtest(backtest_id, tenant_id)
        assert broker_redis.llen(EXECUTION_QUEUE) == 2

        with _worker(app):
            first = await asyncio.to_thread(app.AsyncResult(first_id).get, 120)
            assert first["status"] == "completed"
            assert cast(int, first["total_trades"]) >= 1

            with pytest.raises(ValueError, match="cannot run"):
                await asyncio.to_thread(app.AsyncResult(second_id).get, 120)

        status, _ = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_COMPLETED
        assert await result_count(session_factory, backtest_id) == 1
