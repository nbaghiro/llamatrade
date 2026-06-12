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
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ledger.ingestion import (
    FILL_CHANNEL_PREFIX,
    FillHandler,
    LedgerAppend,
    fill_to_append,
)
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

# Pattern matching every account's fill channel (ledger:fills:{account_id}).
FILL_CHANNEL_PATTERN = f"{FILL_CHANNEL_PREFIX}:*"


async def persist_append(db: AsyncSession, append: LedgerAppend) -> None:
    """Append one translated fill to the ledger (idempotent, balance-checked)."""
    writer = LedgerWriter(db)
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
        except Exception:  # noqa: BLE001 - reconnect on any transport error
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
    try:
        text = raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)
        payload = json.loads(text)
        await handler(fill_to_append(payload))
        return True
    except Exception:  # noqa: BLE001 - never let one bad fill kill the loop
        logger.exception("failed to ingest fill")
        return False
