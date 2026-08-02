"""Celery queue-depth sampling.

The API process is the only long-lived backtest process Prometheus scrapes, so
it is where the broker backlog is measured. Workers and beat expose no HTTP
listener, and a worker cannot report its own queue depth once it is saturated,
which is exactly when the number matters.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Sequence
from typing import Protocol, cast

import redis.asyncio as aioredis

from llamatrade_telemetry.instrumentation import celery as celery_metrics

from src.celery_app import REDIS_URL, WORKER_QUEUES

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL_SECONDS = float(os.getenv("BACKTEST_QUEUE_DEPTH_INTERVAL", "10"))

# Cap warning-log volume during a sustained broker outage; the gauge stays stale.
_FAILURE_LOG_LIMIT = 5


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


class QueueDepthSampler:
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
        self._broker = broker
        self._redis_url = redis_url or REDIS_URL
        self._queues = tuple(queues)
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._consecutive_failures = 0

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

    async def _run(self) -> None:
        while True:
            try:
                await self.sample_once()
            except Exception:
                self._consecutive_failures += 1
                if self._consecutive_failures <= _FAILURE_LOG_LIMIT:
                    logger.warning(
                        "queue depth sample failed (failure %d)",
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
            logger.warning("initial queue depth sample failed")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the loop and release the broker connection."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._broker is not None:
            await self._broker.aclose()
            self._broker = None
