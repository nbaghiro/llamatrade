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

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_events import EventBus, EventEnvelope, FillEvents, LedgerFill, LedgerReservation

from src.ledger.ingestion import (
    FillHandler,
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
    await db.commit()


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
        async with session_factory() as db:
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
    - ``drop``: poison payload (translation failed) — ack anyway after logging,
      or it would redeliver forever.
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

    Parses each envelope to its ``LedgerFill`` / ``LedgerReservation`` and drives
    the translation. Manual ack (not the lib's ``StreamConsumer``): a transient
    failure is left pending and redelivers indefinitely — the ledger self-heals
    when the DB recovers, rather than dead-lettering a fill. Runs until cancelled
    (the lifespan cancels it on shutdown); a dead pod's pending entries are
    reclaimed via the transport's XAUTOCLAIM pass.
    """
    logger.info(
        "ledger fill stream consumer started (stream=%s group=%s consumer=%s)",
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        consumer_name,
    )
    bus = fills.bus
    async for entry_id, env in bus.consume_envelopes(
        LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, consumer_name
    ):
        message = _payload_of(env)
        verdict = await process_stream_entry(handler, message)
        if verdict in ("ack", "drop"):
            await bus.ack(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, entry_id)


def _payload_of(env: EventEnvelope) -> LedgerFill | LedgerReservation:
    """Parse an envelope to its ledger message (narrowed from the registry)."""
    return FillEvents.payload(env)


LAG_SAMPLE_INTERVAL_SECONDS = 30.0


async def monitor_stream_lag(
    bus: EventBus,
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = LAG_SAMPLE_INTERVAL_SECONDS,
) -> None:  # pragma: no cover - timing shell over pending_count
    """Sample the consumer group's pending-entry count into a gauge.

    The pending list (PEL) is the lag signal: sustained growth means the
    consumer is down or stuck, and it must alert before MAXLEN trimming could
    drop unacked entries.
    """
    from src.metrics import LEDGER_STREAM_PENDING

    while not stop_event.is_set():
        try:
            LEDGER_STREAM_PENDING.set(
                await bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)
            )
        except Exception:  # sampling is best-effort
            logger.debug("stream lag sample failed", exc_info=True)
        await _interruptible_sleep(stop_event, interval_seconds)
