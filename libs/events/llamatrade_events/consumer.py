"""StreamConsumer — the durable-consumer runtime services stop hand-rolling.

Generalizes portfolio's bespoke fill-ingestion loop: group consumption, dedupe,
ack, bounded retry, dead-letter on poison, lag gauge, graceful drain. A consumer
service writes a handler; the runtime owns the plumbing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope
from llamatrade_events.idempotency import DedupStore
from llamatrade_events.observability import EVENTS_CONSUMED_TOTAL, EVENTS_CONSUMER_LAG

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], Awaitable[None]]


class StreamConsumer:
    """Durable consumption of one stream by one group, with dedupe + DLQ."""

    def __init__(
        self,
        bus: EventBus,
        stream: str,
        group: str,
        *,
        consumer_name: str,
        dedup: DedupStore | None = None,
        max_attempts: int = 5,
        dlq_suffix: str = ":dlq",
    ) -> None:
        self._bus = bus
        self._stream = stream
        self._group = group
        self._consumer = consumer_name
        self._dedup = dedup
        self._max_attempts = max_attempts
        self._dlq_stream = stream + dlq_suffix
        self._attempts: dict[str, int] = {}

    def _record(self, outcome: str) -> None:
        EVENTS_CONSUMED_TOTAL.labels(
            stream=self._stream.split(":")[0], group=self._group, outcome=outcome
        ).inc()

    async def run(self, handler: Handler, *, stop_event: asyncio.Event | None = None) -> None:
        """Consume until ``stop_event`` is set (or the transport stream ends)."""
        stop = stop_event or asyncio.Event()
        await self._bus.ensure_group(self._stream, self._group)
        async for cursor, env in self._bus.consume_envelopes(
            self._stream, self._group, self._consumer
        ):
            if stop.is_set():
                break
            await self._handle_one(handler, cursor, env)
            await self._update_lag()

    async def _handle_one(self, handler: Handler, cursor: str, env: EventEnvelope) -> None:
        if self._dedup is not None and await self._dedup.seen(env.id):
            await self._bus.ack(self._stream, self._group, cursor)
            self._record("deduped")
            return
        try:
            await handler(env)
        except Exception:
            await self._on_failure(cursor, env)
            return
        if self._dedup is not None:
            await self._dedup.mark(env.id)
        await self._bus.ack(self._stream, self._group, cursor)
        self._attempts.pop(env.id, None)
        self._record("ok")

    async def _on_failure(self, cursor: str, env: EventEnvelope) -> None:
        attempts = self._attempts.get(env.id, 0) + 1
        self._attempts[env.id] = attempts
        if attempts >= self._max_attempts:
            # Poison: move to DLQ and ack so it stops blocking the group.
            await self._bus.publish_envelope(self._dlq_stream, env, maxlen=10_000)
            await self._bus.ack(self._stream, self._group, cursor)
            self._attempts.pop(env.id, None)
            self._record("dlq")
            logger.error("Dead-lettered event %s after %d attempts", env.id, attempts)
        else:
            # Don't ack → the entry redelivers (XAUTOCLAIM / rebalance).
            self._record("error")
            logger.warning("Handler failed for event %s (attempt %d)", env.id, attempts)

    async def _update_lag(self) -> None:
        try:
            lag = await self._bus.pending(self._stream, self._group)
            EVENTS_CONSUMER_LAG.labels(stream=self._stream.split(":")[0], group=self._group).set(
                lag
            )
        except Exception:
            pass  # lag is observability, never fail the loop
