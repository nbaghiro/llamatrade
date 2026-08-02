"""API-side operator telemetry samplers: Celery queue depth and DB job states.

The API process is the only long-lived backtest process Prometheus scrapes, so
it is where the broker backlog and the job-state counts are measured. Workers
and beat expose no HTTP listener, and a worker cannot report its own queue
depth once it is saturated, which is exactly when the number matters.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import redis.asyncio as aioredis
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.backtest import Backtest
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)
from llamatrade_telemetry import gauge
from llamatrade_telemetry.instrumentation import celery as celery_metrics

from src.celery_app import REDIS_URL, WORKER_QUEUES

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL_SECONDS = float(os.getenv("BACKTEST_QUEUE_DEPTH_INTERVAL", "10"))
JOB_STATE_INTERVAL_SECONDS = float(os.getenv("BACKTEST_JOB_STATE_INTERVAL", "30"))

# Trailing window for the completed/failed counts on ``llamatrade_backtest_jobs``.
JOB_STATE_WINDOW_SECONDS = 3600

# Cap warning-log volume during a sustained broker/DB outage; the gauges stay stale.
_FAILURE_LOG_LIMIT = 5

JOBS_GAUGE = gauge(
    "llamatrade_backtest_jobs",
    ["state"],
    "Backtest jobs by state: running/pending now, completed/failed in the trailing window",
)

# Proto status -> gauge ``state`` label; live states are point-in-time counts,
# terminal states are counted over the trailing window.
_LIVE_STATES: dict[int, str] = {
    BACKTEST_STATUS_RUNNING: "running",
    BACKTEST_STATUS_PENDING: "pending",
}
_TERMINAL_STATES: dict[int, str] = {
    BACKTEST_STATUS_COMPLETED: "completed",
    BACKTEST_STATUS_FAILED: "failed",
}
_JOB_STATES: dict[int, str] = {**_LIVE_STATES, **_TERMINAL_STATES}


class BrokerLike(Protocol):
    """The subset of the async Redis client the sampler needs."""

    async def llen(self, name: str) -> int: ...

    async def aclose(self) -> None: ...


class _RedisBroker:
    """Narrows the async Redis client to the sampler's two operations."""

    def __init__(self, url: str) -> None:
        self._redis = aioredis.from_url(url)

    async def llen(self, name: str) -> int:
        return await cast("Awaitable[int]", self._redis.llen(name))

    async def aclose(self) -> None:
        await self._redis.aclose()


class _PeriodicSampler:
    """Shared sampler lifecycle: one sample on start, a resilient loop, stop."""

    def __init__(self, *, what: str, interval_seconds: float) -> None:
        self._what = what
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0

    async def sample_once(self) -> dict[str, int]:
        """Take one sample and publish it to the gauge(s)."""
        raise NotImplementedError

    async def _aclose(self) -> None:
        """Release sampler-owned resources on stop."""

    async def _run(self) -> None:
        while True:
            try:
                await self.sample_once()
            except Exception:
                self._consecutive_failures += 1
                if self._consecutive_failures <= _FAILURE_LOG_LIMIT:
                    logger.warning(
                        "%s sample failed (failure %d)",
                        self._what,
                        self._consecutive_failures,
                    )
            else:
                self._consecutive_failures = 0
            await asyncio.sleep(self._interval_seconds)

    async def start(self) -> None:
        """Start the sampling loop, taking one sample before returning."""
        if self._task is not None and not self._task.done():
            return
        try:
            await self.sample_once()
        except Exception:
            logger.warning("initial %s sample failed", self._what)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the loop and release sampler resources."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._aclose()


class QueueDepthSampler(_PeriodicSampler):
    """Publishes ``llamatrade_celery_queue_depth`` for every queue workers consume.

    Celery's Redis broker stores each queue as a list keyed by the queue name, so
    LLEN is the count of tasks waiting for a worker. Tasks a worker already picked
    up live in the broker's ``unacked`` hash and are excluded on purpose: the
    autoscaler needs the backlog, not the in-flight count.
    """

    def __init__(
        self,
        broker: BrokerLike | None = None,
        redis_url: str | None = None,
        queues: Sequence[str] = WORKER_QUEUES,
        interval_seconds: float = SAMPLE_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(what="queue depth", interval_seconds=interval_seconds)
        self._broker = broker
        self._redis_url = redis_url or REDIS_URL
        self._queues = tuple(queues)

    def _client(self) -> BrokerLike:
        if self._broker is None:
            self._broker = _RedisBroker(self._redis_url)
        return self._broker

    async def sample_once(self) -> dict[str, int]:
        """Read every queue's depth and publish it to the gauge."""
        client = self._client()
        depths = {queue: await client.llen(queue) for queue in self._queues}
        for queue, depth in depths.items():
            celery_metrics.set_queue_depth(queue, depth)
        return depths

    async def _aclose(self) -> None:
        if self._broker is not None:
            await self._broker.aclose()
            self._broker = None


class JobStateSampler(_PeriodicSampler):
    """Publishes ``llamatrade_backtest_jobs`` from the backtests table.

    Operator telemetry: counts are tenant-unscoped aggregates read under the
    audited RLS system bypass, and no tenant dimension ever reaches the metric.
    RUNNING/PENDING are point-in-time counts; COMPLETED/FAILED count rows whose
    ``completed_at`` falls in the trailing ``JOB_STATE_WINDOW_SECONDS`` window.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        interval_seconds: float = JOB_STATE_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(what="job state", interval_seconds=interval_seconds)
        self._session_maker = session_maker

    async def sample_once(self, now: datetime | None = None) -> dict[str, int]:
        """Count jobs per state and publish every series (absent states go to 0)."""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(seconds=JOB_STATE_WINDOW_SECONDS)
        stmt = (
            select(Backtest.status, func.count())
            .where(
                or_(
                    Backtest.status.in_(tuple(_LIVE_STATES)),
                    and_(
                        Backtest.status.in_(tuple(_TERMINAL_STATES)),
                        Backtest.completed_at >= cutoff,
                    ),
                )
            )
            .group_by(Backtest.status)
        )
        async with system_session(
            self._session_maker,
            reason="backtest job-state telemetry (cross-tenant aggregate counts)",
        ) as session:
            rows = (await session.execute(stmt)).all()
        by_status = {int(status): int(count) for status, count in rows}
        counts = {name: by_status.get(status, 0) for status, name in _JOB_STATES.items()}
        for name, value in counts.items():
            JOBS_GAUGE.labels(state=name).set(value)
        return counts
