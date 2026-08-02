"""StreamConsumer — the durable-consumer runtime services stop hand-rolling.

Generalizes portfolio's bespoke fill-ingestion loop: group consumption, dedupe,
ack, retry policy, dead-letter/quarantine on poison, lag gauge, graceful drain.
A consumer service writes a handler; the runtime owns the plumbing.

Failure handling under the default :class:`BoundedRetry` policy (each entry):
- **undecodable bytes** → dead-lettered as raw + acked (never crashes the loop);
- handler raises :class:`PoisonError` → dead-lettered immediately (no retries);
- handler raises anything else → left un-acked → redelivered, up to
  ``max_attempts``, then dead-lettered;
- handler returns → acked (and ``dedup``-marked).

:class:`RetryForever` replaces the give-up path for streams where dropping an
entry is not an option (money): transient failures retry in place indefinitely
with backoff (the entry's partition paused meanwhile), and poison entries go to
an owner-supplied quarantine handler instead of the lib's DLQ.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from opentelemetry import context as _otel_context
from opentelemetry.trace import SpanKind

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, decode_envelope, parse_payload
from llamatrade_events.idempotency import DedupStore
from llamatrade_events.observability import (
    EVENTS_CONSUMED_TOTAL,
    EVENTS_CONSUMER_LAG,
    EVENTS_DLQ_DEPTH,
    stream_label,
)
from llamatrade_events.transport import TRANSPORT_ERRORS
from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_telemetry import extract_context
from llamatrade_telemetry import span as trace_span

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], Awaitable[None]]

# Sample the lag gauge at most this often (a lag round-trip), rather than once per
# message — keeps the consume loop's transport overhead bounded.
LAG_SAMPLE_INTERVAL_SECONDS = 5.0


class PoisonError(Exception):
    """A handler raises this to declare an entry permanently unprocessable —
    the consumer dead-letters (or quarantines) it immediately, with no retries."""


ErrorDisposition = Literal["transient", "poison"]

ErrorClassifier = Callable[[BaseException], ErrorDisposition]

# (raw bytes, decoded envelope — None when the bytes were undecodable, failure).
QuarantineHandler = Callable[[bytes, "EventEnvelope | None", BaseException], Awaitable[None]]


@dataclass(frozen=True)
class BoundedRetry:
    """Default policy: up to ``max_attempts`` deliveries, then dead-letter."""

    max_attempts: int = 5


@dataclass(frozen=True)
class RetryForever:
    """Never-give-up policy for streams where dropping an entry loses money.

    ``classify`` maps a handler exception to ``"transient"`` (retry in place,
    indefinitely, with exponential backoff while the entry's partition is
    paused) or ``"poison"`` (hand the entry to ``quarantine`` and commit past
    it). :class:`PoisonError` is always poison, regardless of ``classify``.
    ``quarantine`` owns persistence of the parked entry (the lib's DLQ is not
    used); a quarantine failure is logged and the entry still acks so one bad
    entry can never wedge its partition.
    """

    classify: ErrorClassifier
    quarantine: QuarantineHandler
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0


RetryPolicy = BoundedRetry | RetryForever


def _dlq_key(env: EventEnvelope) -> str | None:
    """The DLQ partition key: the payload's ``account_id``, when it carries one.

    Keying the DLQ like the source stream keeps per-account order through
    park → replay; payloads without an ``account_id`` publish unkeyed.
    """
    try:
        payload = parse_payload(env)
    except Exception:
        return None
    account_id: object = getattr(payload, "account_id", None)
    if isinstance(account_id, str) and account_id:
        return account_id
    return None


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
        policy: RetryPolicy | None = None,
    ) -> None:
        self._bus = bus
        self._stream = stream
        self._group = group
        self._consumer = consumer_name
        self._dedup = dedup
        self._policy: RetryPolicy = policy if policy is not None else BoundedRetry(max_attempts)
        self._dlq_stream = stream + dlq_suffix
        # A brand-new group replays from the start by default so a consumer that
        # first starts after the producer never misses entries (safe with an
        # idempotent handler / dedup). Has no effect once the group exists.
        self._group_start = group_start
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
                attributes={"event.id": env.id, "messaging.system": "kafka"},
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
        policy = self._policy
        if isinstance(policy, RetryForever):
            await self._handle_one_retry_forever(policy, handler, cursor, raw)
            return
        # Decode inside the error boundary: a corrupt entry is poison, not a
        # crash. (decode_envelope is plain protobuf parsing — never blocks.)
        try:
            env = decode_envelope(raw)
        except Exception:
            # Undecodable bytes carry no recoverable partition key → unkeyed.
            await self._bus.publish_raw(self._dlq_stream, raw)
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
            await self._on_failure(cursor, env, max_attempts=policy.max_attempts)
            return
        if self._dedup is not None:
            await self._dedup.mark(env.id)
        await self._bus.ack(self._stream, self._group, cursor)
        self._attempts.pop(env.id, None)
        self._record("ok")

    async def _handle_one_retry_forever(
        self, policy: RetryForever, handler: Handler, cursor: str, raw: bytes
    ) -> None:
        """Handle one entry under :class:`RetryForever`.

        Transient failures loop in place with backoff — the entry's partition is
        paused for the duration so the fetcher stops prefetching it — and the
        offset commits only once the entry is handled or quarantined.
        """
        try:
            env = decode_envelope(raw)
        except Exception as exc:
            await self._quarantine(policy, cursor, raw, None, exc)
            return

        if self._dedup is not None and await self._dedup.seen(env.id):
            await self._bus.ack(self._stream, self._group, cursor)
            self._record("deduped")
            return

        attempt = 0
        paused = False
        failure: BaseException | None = None
        try:
            while True:
                try:
                    await self._run_handler(handler, env)
                    break
                except PoisonError as exc:
                    failure = exc
                    break
                except Exception as exc:
                    if policy.classify(exc) == "poison":
                        failure = exc
                        break
                    attempt += 1
                    self._record("error")
                    logger.warning(
                        "Handler failed for event %s (attempt %d); retrying in place",
                        env.id,
                        attempt,
                    )
                    if not paused:
                        await self._bus.pause_partition(self._stream, self._group, cursor)
                        paused = True
                    delay = min(
                        policy.base_delay_seconds * (2 ** (attempt - 1)),
                        policy.max_delay_seconds,
                    )
                    await asyncio.sleep(delay)
        finally:
            if paused:
                await self._bus.resume_partition(self._stream, self._group, cursor)

        if failure is not None:
            await self._quarantine(policy, cursor, raw, env, failure)
            return
        if self._dedup is not None:
            await self._dedup.mark(env.id)
        await self._bus.ack(self._stream, self._group, cursor)
        self._record("ok")

    async def _quarantine(
        self,
        policy: RetryForever,
        cursor: str,
        raw: bytes,
        env: EventEnvelope | None,
        exc: BaseException,
    ) -> None:
        """Hand a poison entry to the owner's quarantine, then commit past it.

        A quarantine failure is logged and the entry still acks — parking is
        best-effort by contract; wedging the partition on it would stall every
        entry behind this one.
        """
        try:
            await policy.quarantine(raw, env, exc)
        except Exception:
            logger.exception(
                "Quarantine handler failed for entry %s on %s; acking anyway",
                cursor,
                self._stream,
            )
        await self._bus.ack(self._stream, self._group, cursor)
        self._record("poison")
        logger.error(
            "Quarantined event %s on %s (%s)",
            env.id if env is not None else cursor,
            self._stream,
            exc,
        )

    async def _on_failure(self, cursor: str, env: EventEnvelope, *, max_attempts: int) -> None:
        attempts = self._attempts.get(env.id, 0) + 1
        self._attempts[env.id] = attempts
        if attempts >= max_attempts:
            await self._dead_letter(cursor, env, outcome="dlq", attempts=attempts)
        else:
            # Don't ack → the entry redelivers (uncommitted offset / rebalance).
            self._record("error")
            logger.warning("Handler failed for event %s (attempt %d)", env.id, attempts)

    async def _dead_letter(
        self, cursor: str, env: EventEnvelope, *, outcome: str, attempts: int | None = None
    ) -> None:
        """Move a poison entry to the DLQ (keyed like the source) and ack so it
        stops blocking the group."""
        await self._bus.publish_envelope(self._dlq_stream, env, key=_dlq_key(env))
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
        except TRANSPORT_ERRORS as exc:
            # The gauge is observability; a broker blip must not stop consuming.
            # Anything outside the transport's own failure types is a bug here
            # and propagates.
            logger.debug(
                "lag sample on %s/%s failed (%s: %s)",
                self._stream,
                self._group,
                type(exc).__name__,
                exc,
            )
            return
        EVENTS_CONSUMER_LAG.labels(stream=stream_label(self._stream), group=self._group).set(lag)


DLQ_DEPTH_SAMPLE_INTERVAL_SECONDS = 30.0


class DlqDepthSampler:
    """Samples dead-letter stream depths into ``EVENTS_DLQ_DEPTH`` on an interval.

    The owning service runs :meth:`run` as a background task beside its
    consumers and stops it with the same ``stop_event`` shape as
    :meth:`StreamConsumer.run`. Every sampling failure is logged and swallowed:
    the gauge is observability and must never take a consumer down with it.
    """

    def __init__(
        self,
        bus: EventBus,
        dlq_streams: Sequence[str],
        *,
        interval_seconds: float = DLQ_DEPTH_SAMPLE_INTERVAL_SECONDS,
    ) -> None:
        self._bus = bus
        self._streams = list(dlq_streams)
        self._interval = interval_seconds

    async def sample_once(self) -> None:
        """Read every DLQ's depth into the gauge; a failing stream is skipped."""
        for stream in self._streams:
            try:
                depth = await self._bus.length(stream)
            except Exception as exc:
                logger.warning(
                    "DLQ depth sample on %s failed (%s: %s)", stream, type(exc).__name__, exc
                )
                continue
            EVENTS_DLQ_DEPTH.labels(stream=stream_label(stream)).set(depth)

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Sample immediately and then every interval, until ``stop_event`` is set."""
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            await self.sample_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass
