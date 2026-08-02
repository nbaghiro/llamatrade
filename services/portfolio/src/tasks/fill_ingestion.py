"""Wiring for fill ingestion over the Kafka ledger-fills consumer group.

The pure translation (``fill_to_append`` / ``reservation_to_append``, routed by
``append_from_message``) lives in ``src.ledger.ingestion``. This module supplies
the **handler** that persists a translated append — open a fresh session, append
the balanced event idempotently via ``LedgerWriter``, commit (each fill gets its
own short transaction so one bad fill can't poison a batch) — and composes the
events lib's ``StreamConsumer`` around it.

``persist_append`` is the unit-tested core; ``make_fill_handler`` binds it to a
session factory; ``make_entry_handler`` wraps it as the per-envelope consumer
handler (translate, quarantine, ingest metrics); ``fill_retry_policy`` is the
``RetryForever`` policy (transient failures redeliver indefinitely, poison parks
on the ledger DLQ); ``consume_fill_stream`` drives the consumer group. The
consumer runtime extracts the producer's trace context and records
``llamatrade_events_consumed_total``; parity with the previous hand-rolled loop
is pinned by ``tests/test_fill_ingestion_parity.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import (
    advisory_unlock,
    holds_advisory_lock,
    tenant_session,
    try_advisory_lock,
)
from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import (
    ErrorDisposition,
    EventBus,
    EventEnvelope,
    FillEvents,
    LedgerFill,
    LedgerReservation,
    PoisonError,
    QuarantineHandler,
    RetryForever,
)
from llamatrade_telemetry import counter, gauge

from src.ledger.ids import deterministic_event_id
from src.ledger.ingestion import (
    FillHandler,
    FillQuarantineError,
    LedgerAppend,
    append_from_message,
    enrich_sell_fill,
    needs_cost_basis,
)
from src.ledger.projector import LedgerProjector
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

# One durable topic keyed by ``account_id``, consumed via a Kafka group: Kafka assigns each account's partition to exactly one member, so per-account ordering (buy-before-sell for FIFO cost basis) holds while the fold runs N-way parallel across accounts; the coordinator handles failover.
LEDGER_FILLS_STREAM = "ledger:fills"
PORTFOLIO_LEDGER_GROUP = "portfolio-ledger"
# Unrecordable entries (undecodable bytes / quarantined fills) are parked here instead of silently lost — recoverable for operator review.
LEDGER_FILLS_DLQ_STREAM = "ledger:fills:dlq"


async def _dead_letter(bus: EventBus, raw: bytes, *, key: str | None = None) -> None:
    """Park an unrecordable raw entry on the DLQ topic (best-effort).

    ``key`` is the fill's ``account_id`` when the entry decoded — keying the DLQ
    like the main topic keeps per-account order through park → replay; only
    undecodable bytes park unkeyed. A DLQ publish failure must not wedge the
    consumer, so it's swallowed (logged).
    """
    try:
        await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, raw, key=key)
    except Exception:
        logger.exception("failed to dead-letter ledger entry to %s", LEDGER_FILLS_DLQ_STREAM)


# Process-wide advisory-lock id electing the single ledger-WRITER pod (reconciliation drift + equity-snapshot loops); replicas would otherwise double-write drift events and duplicate equity-curve points. A stable bigint ("ledger" in hex).
_LEDGER_WRITER_LOCK_KEY = 0x6C6564676572


LEDGER_WRITER_ACTIVE = gauge(
    "llamatrade_ledger_writer_active",
    (),
    "Whether this pod currently holds the ledger-writer election lock (1/0)",
)
LEDGER_WRITER_FENCED = counter(
    "llamatrade_ledger_writer_fenced_total",
    (),
    "Sweep passes refused because the writer lock was lost mid-leadership",
)


async def acquire_ledger_writer_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncSession | None:
    """Try to become the single ledger-writer pod via a Postgres advisory lock.

    Gates the reconciliation and equity-snapshot loops only (fill ingestion runs
    on every pod as a Kafka consumer-group member). Returns the holding session if
    acquired (keep it open for the lock's lifetime; release with
    :func:`release_ledger_writer_lock`), else None — another pod holds it.
    """
    db = session_factory()
    try:
        got = await try_advisory_lock(db, _LEDGER_WRITER_LOCK_KEY)
    except Exception:
        await db.close()
        raise
    if got:
        return db
    await db.close()
    return None


async def release_ledger_writer_lock(db: AsyncSession) -> None:
    """Release the ledger-writer advisory lock and close the holding session.

    A torn connection is absorbed (warned, never raised): the lock died with the
    backend anyway, and shutdown still has a Kafka client and a pool to close.
    """
    try:
        await advisory_unlock(db, _LEDGER_WRITER_LOCK_KEY)
    except Exception:
        logger.warning("could not release the ledger-writer advisory lock", exc_info=True)
    finally:
        with contextlib.suppress(Exception):
            await db.close()


class LedgerWriterLease:
    """Leadership handle over the ledger-writer lock, probed on its own connection.

    Election is not a one-shot: a leader whose backend dies (failover, a
    server-side timeout) reconnects through the pre-pinging pool and looks
    healthy while holding nothing. Every sweep asks :meth:`is_leader` before it
    writes, so a torn leader fences itself instead of sweeping alongside its
    successor. Losing leadership latches — :attr:`lost` wakes the sweeps out of
    their interval sleeps so the pod re-enters election promptly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._probe = asyncio.Lock()
        self.lost = asyncio.Event()

    @property
    def db(self) -> AsyncSession:
        """The connection holding the lock (tests inspect its backend)."""
        return self._db

    async def is_leader(self) -> bool:
        """Whether this pod still holds the writer lock, asked on the lock's connection.

        Serialized: the sweeps share one lease connection and an ``AsyncSession``
        is not safe for concurrent use.
        """
        if self.lost.is_set():
            return False
        async with self._probe:
            if self.lost.is_set():
                return False
            held = await holds_advisory_lock(self._db, _LEDGER_WRITER_LOCK_KEY)
            if not held:
                self.lost.set()
                LEDGER_WRITER_FENCED.inc()
                logger.warning(
                    "lost the ledger-writer lock; stopping sweeps and re-entering election"
                )
        return held

    async def release(self) -> None:
        """Release the lock and close its connection (never raises)."""
        self.lost.set()
        await release_ledger_writer_lock(self._db)


async def acquire_ledger_writer_lease(
    session_factory: async_sessionmaker[AsyncSession],
) -> LedgerWriterLease | None:
    """Stand for election; the lease is None when another pod holds the lock."""
    db = await acquire_ledger_writer_lock(session_factory)
    return LedgerWriterLease(db) if db is not None else None


async def persist_append(db: AsyncSession, append: LedgerAppend) -> None:
    """Append one translated fill to the ledger (idempotent, balance-checked).

    A fill whose target sleeve was already closed (a stray/late fill) is
    re-homed to the account's Unmanaged sleeve so it can't resurrect a retired
    sleeve. Sells without a publisher-resolved ``cost_basis`` are then enriched
    here via FIFO against the (possibly re-homed) sleeve's open lots, resolved
    incrementally from the projection checkpoint + the delta since it (O(delta),
    not the account's full history), so the persisted event is self-contained
    (portfolio-ledger.md, amendment 3A).
    """
    append = await _reroute_if_sleeve_closed(db, append)
    writer = LedgerWriter(db)
    if needs_cost_basis(append):
        lots = await LedgerProjector(db).open_lots_incremental(
            append.tenant_id, append.account_id, append.sleeve_id, str(append.data["symbol"])
        )
        append = enrich_sell_fill(append, lots)
    await writer.append(
        tenant_id=append.tenant_id,
        account_id=append.account_id,
        event_type=append.event_type,
        data=append.data,
        sleeve_id=append.sleeve_id,
        event_id=append.event_id,
        occurred_at=append.occurred_at,
    )
    if append.event_type is LedgerEventType.ORDER_FILLED:
        await _freeze_if_invariant_violated(db, append)
    await db.commit()


async def _freeze_if_invariant_violated(db: AsyncSession, append: LedgerAppend) -> None:
    """Freeze the affected sleeve if this fill drove it into an impossible state.

    Fund ops can't overdraw (the planners guard free cash), so a negative-cash or
    negative-position sleeve means a fill escaped trading's reservation/risk guard
    (or an oversell). Freeze it (orders on frozen sleeves are rejected by trading)
    and record a ``SLEEVE_FROZEN`` audit event for human review. Idempotent: an
    already-FROZEN sleeve is left alone, and the freeze event id derives from the
    triggering fill so a re-ingested fill never double-freezes.
    """
    from llamatrade_db.models.ledger import SleeveStatus
    from llamatrade_telemetry import metrics

    from src.ledger.invariants import check_sleeve_invariants
    from src.repositories import SqlSleeveRepository

    # Read-only incremental fold (seeded from the committed checkpoint; this session's delta sees the just-appended fill) instead of folding full history per fill; never persists or seeds the shared cache from this uncommitted session.
    projection = await LedgerProjector(db).project_account_incremental(
        append.tenant_id, append.account_id, persist=False
    )
    violations = check_sleeve_invariants(projection.sleeve(str(append.sleeve_id)))
    if not violations:
        return

    repo = SqlSleeveRepository(db)
    sleeve = await repo.get_sleeve(append.tenant_id, append.sleeve_id)
    if sleeve is None or sleeve.status == SleeveStatus.FROZEN.value:
        return  # already frozen (or re-homed away) — nothing to do

    await repo.set_sleeve_status(sleeve, SleeveStatus.FROZEN.value)
    reason = "; ".join(f"{v.kind}({v.detail})" for v in violations)
    freeze_event_id = deterministic_event_id(f"{append.event_id}:invariant_freeze")
    await LedgerWriter(db).append(
        tenant_id=append.tenant_id,
        account_id=append.account_id,
        event_type=LedgerEventType.SLEEVE_FROZEN,
        data={"sleeve_id": str(append.sleeve_id), "reason": f"invariant violation — {reason}"},
        sleeve_id=append.sleeve_id,
        event_id=freeze_event_id,
    )
    metrics.ledger.sleeve_frozen()
    logger.critical(
        "froze sleeve %s (account=%s) after fill: invariant violation — %s; manual review required",
        append.sleeve_id,
        append.account_id,
        reason,
    )
    from src.alerts import LedgerIncident, get_ledger_alert_dispatcher

    try:
        await get_ledger_alert_dispatcher().dispatch(
            append.tenant_id,
            LedgerIncident(
                kind="sleeve_frozen",
                message=f"Sleeve frozen after an invariant violation: {reason}",
                context={
                    "sleeve_id": str(append.sleeve_id),
                    "account_id": str(append.account_id),
                },
            ),
        )
    except Exception:
        logger.exception("sleeve-freeze alert dispatch failed; the freeze stands")


async def _reroute_if_sleeve_closed(db: AsyncSession, append: LedgerAppend) -> LedgerAppend:
    """Re-home a fill targeting a CLOSED sleeve to the account's Unmanaged sleeve.

    A sleeve is closed on strategy stop/archive (its holdings re-homed to
    Unmanaged). A fill that arrives afterwards — a stray or out-of-band fill —
    must not resurrect the retired sleeve, so it is attributed to Unmanaged
    instead (the same destination the sleeve's positions were moved to). No-op
    for live (ACTIVE/FROZEN) sleeves; if the Unmanaged sleeve is somehow absent,
    leave the append untouched and let reconciliation surface it.
    """
    from dataclasses import replace

    from llamatrade_db.models.ledger import SleeveStatus, SleeveType

    from src.repositories import SqlSleeveRepository

    repo = SqlSleeveRepository(db)
    sleeve = await repo.get_sleeve(append.tenant_id, append.sleeve_id)
    if sleeve is None or sleeve.status != SleeveStatus.CLOSED.value:
        return append

    unmanaged = await repo.get_sleeve_by_type(
        append.tenant_id, append.account_id, SleeveType.UNMANAGED
    )
    if unmanaged is None:
        logger.error(
            "fill for closed sleeve %s but account %s has no Unmanaged sleeve; "
            "applying to the closed sleeve",
            append.sleeve_id,
            append.account_id,
        )
        return append

    logger.warning(
        "fill arrived for closed sleeve %s; re-homing to Unmanaged sleeve %s",
        append.sleeve_id,
        unmanaged.id,
    )
    data = dict(append.data)
    data["sleeve_id"] = str(unmanaged.id)
    return replace(append, sleeve_id=unmanaged.id, data=data)


def make_fill_handler(session_factory: async_sessionmaker[AsyncSession]) -> FillHandler:
    """Bind ``persist_append`` to a session factory for the stream consumer."""

    async def handle(append: LedgerAppend) -> None:
        async with tenant_session(append.tenant_id, session_factory) as db:
            await persist_append(db, append)
        logger.debug(
            "ingested fill into ledger (account=%s symbol=%s event_id=%s)",
            append.account_id,
            append.data.get("symbol"),
            append.event_id,
        )

    return handle


async def _interruptible_sleep(
    stop_event: asyncio.Event, seconds: float
) -> None:  # pragma: no cover - timing shell
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def _dispatch_quarantine_alert(message: LedgerFill | LedgerReservation, detail: str) -> None:
    """Tell the tenant a fill was parked; a quarantine only an operator sees is invisible money."""
    from src.alerts import LedgerIncident, get_ledger_alert_dispatcher

    tenant_raw = getattr(message, "tenant_id", "")
    try:
        tenant_id = UUID(str(tenant_raw))
    except ValueError, TypeError:
        return
    try:
        await get_ledger_alert_dispatcher().dispatch(
            tenant_id,
            LedgerIncident(
                kind="fill_quarantined",
                message=f"A fill could not be recorded and was parked for review: {detail}",
                context={"client_order_id": str(getattr(message, "client_order_id", ""))},
            ),
        )
    except Exception:
        logger.exception("quarantine alert dispatch failed; the drop verdict stands")


def classify_fill_error(_exc: BaseException) -> ErrorDisposition:
    """Every failure the entry handler didn't declare poison is transient.

    A fill is money: a persistence failure (DB down, pool exhausted) must
    redeliver until it lands, never dead-letter. The entry handler raises
    ``PoisonError`` explicitly for the only structurally-wrong cases
    (untranslatable payloads, quarantined fills).
    """
    return "transient"


def make_entry_handler(handler: FillHandler) -> Callable[[EventEnvelope], Awaitable[None]]:
    """The ``StreamConsumer`` handler for one consumed fill-stream envelope.

    Parse → translate → persist. Translation failures and quarantined fills
    (a sell with no resolvable cost basis) raise ``PoisonError`` after their
    metric/alert bookkeeping — the retry policy hands them to the quarantine
    park. Anything else re-raises as transient (retried in place, forever).
    """

    async def handle(env: EventEnvelope) -> None:
        from src.metrics import record_ingest

        try:
            message = FillEvents.payload(env)
            append = append_from_message(message)
        except Exception as exc:
            logger.exception("poison ledger stream entry; quarantining")
            record_ingest("poison")
            raise PoisonError(str(exc)) from exc
        try:
            await handler(append)
        except FillQuarantineError as e:
            # A balanced-but-wrong record (or an infinite retry) is worse than a surfaced, recoverable drop; log at ERROR with the order id so the fill is identifiable for reconciliation.
            logger.error(
                "quarantining unrecordable ledger fill (client_order_id=%s): %s",
                getattr(message, "client_order_id", "?"),
                e,
            )
            record_ingest("quarantine")
            await _dispatch_quarantine_alert(message, str(e))
            raise PoisonError(str(e)) from e
        except Exception:
            logger.exception("transient failure persisting ledger stream entry; retrying in place")
            record_ingest("retry")
            raise
        record_ingest("success")

    return handle


def make_fill_quarantine(bus: EventBus) -> QuarantineHandler:
    """Quarantine for the fill stream: park the RAW entry on the ledger DLQ.

    Keyed by ``account_id`` when the payload is readable so park → replay
    preserves per-account order; undecodable/unparseable entries park unkeyed.
    Undecodable bytes never reached the entry handler, so their poison ingest
    metric is recorded here.
    """

    async def quarantine(raw: bytes, env: EventEnvelope | None, _exc: BaseException) -> None:
        from src.metrics import record_ingest

        key: str | None = None
        if env is None:
            record_ingest("poison")
        else:
            with contextlib.suppress(Exception):
                key = FillEvents.payload(env).account_id or None
        await _dead_letter(bus, raw, key=key)

    return quarantine


# In-place retry backoff for a transient persistence failure. On Kafka an
# uncommitted offset is NOT redelivered to a live consumer (only on
# restart/rebalance), so the RetryForever policy retries a fill until it lands —
# which is what "never skip a fill" requires. Handling is sequential, so the
# retry stalls EVERY partition assigned to this pod, not just the account's: the
# consumer pauses the record's partition so the fetcher stops prefetching it,
# and the transport's max_poll_interval_ms is raised so a long DB outage can't
# evict the member and trigger a rebalance storm. The writer is idempotent, so a
# re-run is safe.
_RETRY_BASE_DELAY_SECONDS = 0.5
_RETRY_MAX_DELAY_SECONDS = 30.0


def fill_retry_policy(
    bus: EventBus,
    *,
    base_delay_seconds: float | None = None,
    max_delay_seconds: float | None = None,
) -> RetryForever:
    """The fill stream's never-give-up retry policy (see ``classify_fill_error``)."""
    return RetryForever(
        classify=classify_fill_error,
        quarantine=make_fill_quarantine(bus),
        base_delay_seconds=(
            _RETRY_BASE_DELAY_SECONDS if base_delay_seconds is None else base_delay_seconds
        ),
        max_delay_seconds=(
            _RETRY_MAX_DELAY_SECONDS if max_delay_seconds is None else max_delay_seconds
        ),
    )


async def consume_fill_stream(
    fills: FillEvents,
    handler: FillHandler,
    *,
    consumer_name: str,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Consume the ledger fill topic as a Kafka consumer-group member.

    A ``StreamConsumer`` under the ``RetryForever`` policy: it extracts the
    producer's trace context (CONSUMER span per entry), records
    ``llamatrade_events_consumed_total``, retries transient failures in place
    forever (entry partition paused), quarantines poison via the ledger DLQ
    park, and commits the offset only after the handler returns. Entries are
    handled strictly serially, so per-account order (buy-before-sell for FIFO
    cost basis) holds; Kafka assigns each account's partition to one member and
    the group coordinator handles failover. ``group_start`` = begin so a fresh
    group never misses a published fill (the writer dedupes redelivery). Runs
    until cancelled (or ``stop_event`` is set).
    """
    logger.info(
        "ledger fill consumer started (stream=%s group=%s consumer=%s)",
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        consumer_name,
    )
    consumer = fills.consumer(consumer_name=consumer_name, policy=fill_retry_policy(fills.bus))
    await consumer.run(make_entry_handler(handler), stop_event=stop_event)


LAG_SAMPLE_INTERVAL_SECONDS = 30.0


class FillLagTracker:
    """Tracks the fill consumer-group lag so the health probe can fail on a stall.

    A *hung* (not crashed) group member silently stops draining its partitions —
    only the growing lag reveals it. When the backlog stays above ``threshold``
    for ``sustained_samples`` consecutive samples, :attr:`is_backlogged` trips so
    the liveness probe can fail and let K8s recycle the pod (Kafka then reassigns
    its partitions to a healthy member).
    """

    def __init__(self, *, threshold: int = 1000, sustained_samples: int = 3) -> None:
        self.threshold = threshold
        self.sustained_samples = sustained_samples
        self.pending = 0
        self._consecutive_high = 0

    def record(self, pending: int) -> None:
        self.pending = pending
        self._consecutive_high = self._consecutive_high + 1 if pending > self.threshold else 0

    @property
    def is_backlogged(self) -> bool:
        return self._consecutive_high >= self.sustained_samples


async def monitor_stream_lag(
    bus: EventBus,
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = LAG_SAMPLE_INTERVAL_SECONDS,
    tracker: FillLagTracker | None = None,
) -> None:  # pragma: no cover - timing shell over pending_count
    """Sample the consumer group's uncommitted-entry count into a gauge (and tracker).

    Consumer-group lag is the signal: sustained growth means the group is down
    or stuck and fills are accumulating unbooked. The optional ``tracker`` lets
    the health probe see a sustained backlog and fail liveness for a hung group
    member.
    """
    from llamatrade_telemetry import metrics

    from src.metrics import LEDGER_STREAM_PENDING

    last_dlq_depth = 0
    while not stop_event.is_set():
        try:
            pending = await bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)
            LEDGER_STREAM_PENDING.set(pending)
            if tracker is not None:
                tracker.record(pending)
        except Exception:  # sampling is best-effort
            logger.debug("stream lag sample failed", exc_info=True)
        try:
            dlq_depth = await bus.length(LEDGER_FILLS_DLQ_STREAM)
            metrics.ledger.dlq_depth.set(float(dlq_depth))
            if dlq_depth > last_dlq_depth:
                logger.warning(
                    "%d fill(s) parked on the ledger DLQ (%s) — un-booked; replay after "
                    "fixing the cause (python -m src.tasks.dlq_replay)",
                    dlq_depth,
                    LEDGER_FILLS_DLQ_STREAM,
                )
            last_dlq_depth = dlq_depth
        except Exception:  # sampling is best-effort
            logger.debug("dlq depth sample failed", exc_info=True)
        await _interruptible_sleep(stop_event, interval_seconds)
