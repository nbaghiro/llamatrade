"""Wiring for fill ingestion (shadow mode).

The pure translation (``fill_to_append``) and the Redis pub/sub adapter
(``FillConsumer``) live in ``src.ledger.ingestion``. This module supplies the
**handler** that persists a translated append: open a fresh session, append the
balanced event idempotently via ``LedgerWriter``, and commit. Each fill gets its
own short transaction so one bad fill can't poison a batch.

``persist_append`` is the unit-tested core; ``make_fill_handler`` binds it to a
session factory for the consumer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_common.eventbus import EventBus

from src.ledger.ingestion import (
    FILL_CHANNEL_PREFIX,
    FillHandler,
    LedgerAppend,
    enrich_sell_fill,
    needs_cost_basis,
    payload_to_append,
)
from src.ledger.projection import LedgerEventLike, open_lots
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

# Pattern matching every account's fill channel (ledger:fills:{account_id}).
FILL_CHANNEL_PATTERN = f"{FILL_CHANNEL_PREFIX}:*"

# Durable Streams transport (STREAMS_LEDGER_FILLS): one global stream — the
# trading publisher XADDs every fill/lifecycle payload to it, and this service
# consumes via a consumer group. Entries are the §1a payload as flat fields
# (no JSON envelope). Run a SINGLE active consumer in the group: per-account
# ordering (buy-before-sell for FIFO cost basis) relies on it; a replacement
# pod takes over pending entries via XAUTOCLAIM.
LEDGER_FILLS_STREAM = "ledger:fills"
PORTFOLIO_LEDGER_GROUP = "portfolio-ledger"


async def persist_append(db: AsyncSession, append: LedgerAppend) -> None:
    """Append one translated fill to the ledger (idempotent, balance-checked).

    Sells without a publisher-resolved ``cost_basis`` are enriched here via
    FIFO against the sleeve's open lots, so the persisted event is
    self-contained (CONTRACTS.md §1, amendment 3A).
    """
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


def make_fill_handler(session_factory: async_sessionmaker[AsyncSession]) -> FillHandler:
    """Bind ``persist_append`` to a session factory for use by ``FillConsumer``."""

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


RECONNECT_BACKOFF_SECONDS = 5.0


async def consume_fills(
    redis: Any,
    handler: FillHandler,
    *,
    stop_event: asyncio.Event,
    reconnect_backoff_seconds: float = RECONNECT_BACKOFF_SECONDS,
) -> None:  # pragma: no cover - IO loop, logic covered via persist_append/dispatch_fill
    """Pattern-subscribe to every account's fill channel and drive ``handler``.

    A pattern subscription (``ledger:fills:*``) covers accounts onboarded after
    startup without re-subscribing. One bad fill is logged and skipped, and a
    Redis connection drop is recovered by re-subscribing after a backoff — so a
    transient outage never permanently kills ingestion. Returns when
    ``stop_event`` is set.
    """
    while not stop_event.is_set():
        try:
            await _subscribe_and_consume(redis, handler, stop_event=stop_event)
        except Exception:  # reconnect on any transport error
            logger.exception("fill consumer connection error; reconnecting")
            await _interruptible_sleep(stop_event, reconnect_backoff_seconds)
    logger.info("ledger fill consumer stopped")


async def _subscribe_and_consume(
    redis: Any, handler: FillHandler, *, stop_event: asyncio.Event
) -> None:  # pragma: no cover - IO loop
    pubsub = redis.pubsub()
    await pubsub.psubscribe(FILL_CHANNEL_PATTERN)
    logger.info("ledger fill consumer subscribed to pattern %s", FILL_CHANNEL_PATTERN)
    try:
        while not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None or message.get("type") != "pmessage":
                continue
            await dispatch_fill(handler, message["data"])
    finally:
        await pubsub.punsubscribe(FILL_CHANNEL_PATTERN)
        await pubsub.aclose()


async def _interruptible_sleep(
    stop_event: asyncio.Event, seconds: float
) -> None:  # pragma: no cover - timing shell
    """Sleep up to ``seconds``, waking early if ``stop_event`` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        pass


async def dispatch_fill(handler: FillHandler, raw: object) -> bool:
    """Decode one raw pub/sub payload and drive the handler. Returns success.

    Pure enough to unit-test: bad JSON / malformed payloads are swallowed (logged)
    so the surrounding loop survives.
    """
    from src.metrics import record_ingest

    try:
        text = raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
        payload = json.loads(text)
        await handler(payload_to_append(payload))
        record_ingest("success")
        return True
    except Exception:  # never let one bad fill kill the loop
        logger.exception("failed to ingest fill")
        record_ingest("failure")
        return False


async def process_stream_entry(
    handler: FillHandler, fields: dict[str, str]
) -> Literal["ack", "drop", "retry"]:
    """Process one consumer-group entry; the verdict drives acking.

    - ``ack``: persisted (or deduped) — remove from the pending list.
    - ``drop``: poison payload (translation failed) — ack anyway after logging,
      or it would redeliver forever; the pub/sub path swallows these too.
    - ``retry``: transient persistence failure — leave pending so the group
      redelivers (idempotent at the writer, so a half-applied retry is safe).
    """
    from src.metrics import record_ingest

    try:
        append = payload_to_append(fields)
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
    bus: EventBus,
    handler: FillHandler,
    *,
    consumer_name: str,
) -> None:  # pragma: no cover - IO loop, logic covered via process_stream_entry
    """Durable counterpart of :func:`consume_fills` over the global stream.

    Runs until cancelled (the lifespan cancels it on shutdown). Unacked
    entries survive restarts; a dead pod's pending entries are reclaimed via
    the bus's XAUTOCLAIM pass.
    """
    logger.info(
        "ledger fill stream consumer started (stream=%s group=%s consumer=%s)",
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        consumer_name,
    )
    async for entry_id, fields in bus.consume(
        LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, consumer_name
    ):
        verdict = await process_stream_entry(handler, fields)
        if verdict in ("ack", "drop"):
            await bus.ack(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, entry_id)


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
                await bus.pending_count(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP)
            )
        except Exception:  # sampling is best-effort
            logger.debug("stream lag sample failed", exc_info=True)
        await _interruptible_sleep(stop_event, interval_seconds)
