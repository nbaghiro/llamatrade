"""StreamConsumer — the durable-consumer runtime services stop hand-rolling.

Generalizes portfolio's bespoke fill-ingestion loop: group consumption, dedupe,
ack, bounded retry, dead-letter on poison, lag gauge, graceful drain. A consumer
service writes a handler; the runtime owns the plumbing.

Failure handling (each delivered entry):
- **undecodable bytes** → dead-lettered as raw + acked (never crashes the loop);
- handler raises :class:`PoisonError` → dead-lettered immediately (no retries);
- handler raises anything else → left un-acked → redelivered, up to
  ``max_attempts``, then dead-lettered;
- handler returns → acked (and ``dedup``-marked).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from opentelemetry import context as _otel_context
from opentelemetry.trace import SpanKind

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, decode_envelope
from llamatrade_events.idempotency import DedupStore
from llamatrade_events.observability import (
    EVENTS_CONSUMED_TOTAL,
    EVENTS_CONSUMER_LAG,
    stream_label,
)
from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_telemetry import extract_context
from llamatrade_telemetry import span as trace_span

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], Awaitable[None]]

# Sample the lag gauge at most this often (an XPENDING round-trip), rather than
# once per message — keeps the consume loop's Redis overhead bounded.
LAG_SAMPLE_INTERVAL_SECONDS = 5.0
DLQ_MAXLEN = 10_000


class PoisonError(Exception):
    """A handler raises this to declare an entry permanently unprocessable —
    the consumer dead-letters it immediately, with no retries."""


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
        group_start: Cursor = CURSOR_BEGIN,
        claim_min_idle_ms: int = 60_000,
    ) -> None:
        self._bus = bus
        self._stream = stream
        self._group = group
        self._consumer = consumer_name
        self._dedup = dedup
        self._max_attempts = max_attempts
        self._dlq_stream = stream + dlq_suffix
        # A brand-new group replays from the start by default so a consumer that
        # first starts after the producer never misses entries (safe with an
        # idempotent handler / dedup). Has no effect once the group exists.
        self._group_start = group_start
        self._claim_min_idle_ms = claim_min_idle_ms
        self._attempts: dict[str, int] = {}
        self._last_lag_sample = 0.0

    def _record(self, outcome: str) -> None:
        EVENTS_CONSUMED_TOTAL.labels(
            stream=stream_label(self._stream), group=self._group, outcome=outcome
        ).inc()

    async def _run_handler(self, handler: Handler, env: EventEnvelope) -> None:
        """Run the handler under the producer's trace context, in a CONSUMER span.

        Links this service's processing to the producer that published the entry
        (e.g. the fill that triggered a ledger projection).
        """
        token = _otel_context.attach(extract_context(dict(env.metadata)))
        try:
            with trace_span(
                f"consume {stream_label(self._stream)}",
                kind=SpanKind.CONSUMER,
                attributes={"event.id": env.id, "messaging.system": "redis_streams"},
            ):
                await handler(env)
        finally:
            _otel_context.detach(token)

    async def run(self, handler: Handler, *, stop_event: asyncio.Event | None = None) -> None:
        """Consume until ``stop_event`` is set (or the transport stream ends)."""
        stop = stop_event or asyncio.Event()
        async for cursor, raw in self._bus.consume_raw(
            self._stream, self._group, self._consumer, group_start_id=self._group_start
        ):
            if stop.is_set():
                break
            await self._handle_one(handler, cursor, raw)
            await self._maybe_update_lag()

    async def _handle_one(self, handler: Handler, cursor: str, raw: bytes) -> None:
        # Decode inside the error boundary: a corrupt entry is poison, not a
        # crash. (decode_envelope is plain protobuf parsing — never blocks.)
        try:
            env = decode_envelope(raw)
        except Exception:
            await self._bus.publish_raw(self._dlq_stream, raw, maxlen=DLQ_MAXLEN)
            await self._bus.ack(self._stream, self._group, cursor)
            self._record("poison")
            logger.error("Dead-lettered undecodable entry %s on %s", cursor, self._stream)
            return

        if self._dedup is not None and await self._dedup.seen(env.id):
            await self._bus.ack(self._stream, self._group, cursor)
            self._record("deduped")
            return
        try:
            await self._run_handler(handler, env)
        except PoisonError:
            await self._dead_letter(cursor, env, outcome="poison")
            return
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
            await self._dead_letter(cursor, env, outcome="dlq", attempts=attempts)
        else:
            # Don't ack → the entry redelivers (XAUTOCLAIM / rebalance).
            self._record("error")
            logger.warning("Handler failed for event %s (attempt %d)", env.id, attempts)

    async def _dead_letter(
        self, cursor: str, env: EventEnvelope, *, outcome: str, attempts: int | None = None
    ) -> None:
        """Move a poison entry to the DLQ and ack so it stops blocking the group."""
        await self._bus.publish_envelope(self._dlq_stream, env, maxlen=DLQ_MAXLEN)
        await self._bus.ack(self._stream, self._group, cursor)
        self._attempts.pop(env.id, None)
        self._record(outcome)
        logger.error(
            "Dead-lettered event %s (%s%s)",
            env.id,
            outcome,
            f", {attempts} attempts" if attempts is not None else "",
        )

    async def _maybe_update_lag(self) -> None:
        now = time.monotonic()
        if now - self._last_lag_sample < LAG_SAMPLE_INTERVAL_SECONDS:
            return
        self._last_lag_sample = now
        try:
            lag = await self._bus.pending(self._stream, self._group)
            EVENTS_CONSUMER_LAG.labels(stream=stream_label(self._stream), group=self._group).set(
                lag
            )
        except Exception:
            pass  # lag is observability, never fail the loop
