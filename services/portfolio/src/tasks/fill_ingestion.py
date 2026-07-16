"""Wiring for fill ingestion over the Redis Streams consumer group.

The pure translation (``fill_to_append`` / ``reservation_to_append``, routed by
``append_from_message``) lives in ``src.ledger.ingestion``. This module parses
each envelope to its proto and supplies the **handler** that persists a
translated append: open a fresh session, append the balanced event idempotently
via ``LedgerWriter``, and commit. Each fill gets its own short transaction so one
bad fill can't poison a batch.

``persist_append`` is the unit-tested core; ``make_fill_handler`` binds it to a
session factory; ``process_stream_entry`` decides ack/drop/retry per entry;
``consume_fill_stream`` drives the consumer group.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import (
    CURSOR_BEGIN,
    EventBus,
    FillEvents,
    LedgerFill,
    LedgerReservation,
    decode_envelope,
)

from src.ledger.ingestion import (
    FillHandler,
    FillQuarantineError,
    LedgerAppend,
    append_from_message,
    enrich_sell_fill,
    needs_cost_basis,
)
from src.ledger.projection import LedgerEventLike, open_lots
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

# One global durable stream — the trading publisher XADDs every fill/lifecycle
# payload to it, and this service consumes via a consumer group. Entries are the
# §1a payload as flat fields (no JSON envelope). Run a SINGLE active consumer in
# the group: per-account ordering (buy-before-sell for FIFO cost basis) relies
# on it; a replacement pod takes over pending entries via XAUTOCLAIM.
LEDGER_FILLS_STREAM = "ledger:fills"
PORTFOLIO_LEDGER_GROUP = "portfolio-ledger"
# Unrecordable entries (undecodable bytes / quarantined fills) are parked here
# instead of being silently lost — recoverable for operator review.
LEDGER_FILLS_DLQ_STREAM = "ledger:fills:dlq"
_DLQ_MAXLEN = 10_000


async def _dead_letter(bus: EventBus, raw: bytes) -> None:
    """Park an unrecordable raw stream entry on the DLQ (best-effort).

    Dropping a poison/quarantined entry keeps the single FIFO consumer alive, but
    losing it outright is worse than a recoverable parking spot. A DLQ publish
    failure must not wedge the consumer, so it's swallowed (logged).
    """
    try:
        await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, raw, maxlen=_DLQ_MAXLEN)
    except Exception:
        logger.exception("failed to dead-letter ledger entry to %s", LEDGER_FILLS_DLQ_STREAM)


# Process-wide advisory-lock id for the single active fill consumer. Per-account
# FIFO (buy-before-sell for cost basis) requires exactly one consumer; a second
# pod that loses the lock serves reads only. A stable bigint ("ledger" in hex).
_FILL_CONSUMER_LOCK_KEY = 0x6C6564676572


async def acquire_fill_consumer_lock(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncSession | None:
    """Try to become the single active fill consumer via a Postgres advisory lock.

    Returns the holding session if acquired (keep it open for the lock's lifetime;
    release with :func:`release_fill_consumer_lock`), else None — another pod holds
    it and this one should not ingest. Failover is via the consumer group's
    XAUTOCLAIM once the active pod dies and its lock releases on connection close.
    """
    db = session_factory()
    try:
        got = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _FILL_CONSUMER_LOCK_KEY}
        )
    except Exception:
        await db.close()
        raise
    if got:
        return db
    await db.close()
    return None


async def release_fill_consumer_lock(db: AsyncSession) -> None:
    """Release the fill-consumer advisory lock and close the holding session."""
    try:
        await db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": _FILL_CONSUMER_LOCK_KEY})
    finally:
        await db.close()


async def persist_append(db: AsyncSession, append: LedgerAppend) -> None:
    """Append one translated fill to the ledger (idempotent, balance-checked).

    A fill whose target sleeve was already closed (a stray/late fill) is
    re-homed to the account's Unmanaged sleeve so it can't resurrect a retired
    sleeve. Sells without a publisher-resolved ``cost_basis`` are then enriched
    here via FIFO against the (possibly re-homed) sleeve's open lots, so the
    persisted event is self-contained (CONTRACTS.md §1, amendment 3A).
    """
    append = await _reroute_if_sleeve_closed(db, append)
    writer = LedgerWriter(db)
    if needs_cost_basis(append):
        # ORM rows duck-type the kernel protocol; cast bridges Mapped descriptors
        events = cast(
            "list[LedgerEventLike]",
            await writer.read_account_events(append.tenant_id, append.account_id),
        )
        lots = open_lots(events, str(append.sleeve_id), str(append.data["symbol"]))
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
    import hashlib
    from uuid import UUID

    from llamatrade_db.models.ledger import SleeveStatus
    from llamatrade_telemetry import metrics

    from src.ledger.invariants import check_sleeve_invariants
    from src.ledger.projector import LedgerProjector
    from src.repositories import SqlSleeveRepository

    projection = await LedgerProjector(db).project_account(append.tenant_id, append.account_id)
    violations = check_sleeve_invariants(projection.sleeve(str(append.sleeve_id)))
    if not violations:
        return

    repo = SqlSleeveRepository(db)
    sleeve = await repo.get_sleeve(append.tenant_id, append.sleeve_id)
    if sleeve is None or sleeve.status == SleeveStatus.FROZEN.value:
        return  # already frozen (or re-homed away) — nothing to do

    await repo.set_sleeve_status(sleeve, SleeveStatus.FROZEN.value)
    reason = "; ".join(f"{v.kind}({v.detail})" for v in violations)
    freeze_event_id = UUID(
        bytes=hashlib.sha256(f"{append.event_id}:invariant_freeze".encode()).digest()[:16]
    )
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


async def process_stream_entry(
    handler: FillHandler, message: LedgerFill | LedgerReservation
) -> Literal["ack", "drop", "retry"]:
    """Process one parsed ledger message; the verdict drives acking.

    - ``ack``: persisted (or deduped) — remove from the pending list.
    - ``drop``: poison payload (translation failed) or a quarantined fill (a
      sell with no resolvable cost basis) — ack anyway after alerting, or it
      would redeliver forever and wedge the single-consumer FIFO ingestion.
    - ``retry``: transient persistence failure — leave pending so the group
      redelivers (idempotent at the writer, so a half-applied retry is safe).
    """
    from src.metrics import record_ingest

    try:
        append = append_from_message(message)
    except Exception:
        logger.exception("poison ledger stream entry; dropping")
        record_ingest("poison")
        return "drop"
    try:
        await handler(append)
    except FillQuarantineError as e:
        # A balanced-but-wrong record (or an infinite retry) is worse than a
        # surfaced, recoverable drop. Log at ERROR with the order id so the fill
        # is identifiable for reconciliation / manual review.
        logger.error(
            "quarantining unrecordable ledger fill (client_order_id=%s): %s",
            getattr(message, "client_order_id", "?"),
            e,
        )
        record_ingest("quarantine")
        return "drop"
    except Exception:
        logger.exception("transient failure persisting ledger stream entry; leaving pending")
        record_ingest("retry")
        return "retry"
    record_ingest("success")
    return "ack"


async def consume_fill_stream(
    fills: FillEvents,
    handler: FillHandler,
    *,
    consumer_name: str,
) -> None:  # pragma: no cover - IO loop, logic covered via process_stream_entry
    """Durably consume the global fill stream via the consumer group.

    Decodes each entry to its ``LedgerFill`` / ``LedgerReservation`` and drives
    the translation. Consumes the RAW bytes (``consume_raw``) so a corrupt /
    unknown-type entry is dropped (acked) instead of crash-looping the single
    ledger consumer. Manual ack (not the lib's ``StreamConsumer``): a transient
    failure is left pending and redelivers indefinitely — the ledger self-heals
    when the DB recovers, rather than dead-lettering a fill. ``group_start`` =
    begin so a fresh group never misses a published fill (writer dedupes).
    Runs until cancelled (the lifespan cancels it on shutdown); a dead pod's
    pending entries are reclaimed via the transport's XAUTOCLAIM pass.
    """
    logger.info(
        "ledger fill stream consumer started (stream=%s group=%s consumer=%s)",
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        consumer_name,
    )
    from src.metrics import record_ingest

    bus = fills.bus
    async for entry_id, raw in bus.consume_raw(
        LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, consumer_name, group_start_id=CURSOR_BEGIN
    ):
        message = _decode_message(raw)
        if message is None:
            # Undecodable / unknown-type entry: poison, not transient — dead-letter
            # for review and drop so one bad entry can't wedge the FIFO consumer.
            await _dead_letter(bus, raw)
            record_ingest("poison")
            await bus.ack(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, entry_id)
            continue
        verdict = await process_stream_entry(handler, message)
        if verdict == "drop":
            # Translation poison or a quarantined fill — park it before acking so
            # it's recoverable rather than silently lost.
            await _dead_letter(bus, raw)
        if verdict in ("ack", "drop"):
            await bus.ack(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, entry_id)


def _decode_message(raw: bytes) -> LedgerFill | LedgerReservation | None:
    """Decode raw bytes → ledger message, or ``None`` if undecodable / unknown type."""
    try:
        return FillEvents.payload(decode_envelope(raw))
    except Exception:
        logger.exception("undecodable or unknown-type ledger stream entry; dropping")
        return None


LAG_SAMPLE_INTERVAL_SECONDS = 30.0


class FillLagTracker:
    """Tracks the fill-stream backlog so the health probe can fail on a stall.

    The active consumer holds an advisory lock for its whole life, so a *hung*
    (not crashed) consumer keeps the lock and silently stops draining — only the
    growing pending count reveals it. When the backlog stays above ``threshold``
    for ``sustained_samples`` consecutive samples, :attr:`is_backlogged` trips so
    the liveness probe can fail and let K8s recycle the pod (releasing the lock
    to a standby).
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
    """Sample the consumer group's pending-entry count into a gauge (and tracker).

    The pending list (PEL) is the lag signal: sustained growth means the
    consumer is down or stuck, and it must alert before MAXLEN trimming could
    drop unacked entries. The optional ``tracker`` lets the health probe see a
    sustained backlog and fail liveness for a hung active consumer.
    """
    from src.metrics import LEDGER_STREAM_PENDING

    while not stop_event.is_set():
        try:
            pending = await bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)
            LEDGER_STREAM_PENDING.set(pending)
            if tracker is not None:
                tracker.record(pending)
        except Exception:  # sampling is best-effort
            logger.debug("stream lag sample failed", exc_info=True)
        await _interruptible_sleep(stop_event, interval_seconds)
