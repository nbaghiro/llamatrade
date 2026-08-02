"""Operator tool: replay DLQ'd ledger fills back onto the main topic.

Fills that couldn't be booked (undecodable bytes / unresolvable cost basis) are
parked on ``ledger:fills:dlq`` instead of being lost. Once the root cause is
fixed, this re-publishes them onto ``ledger:fills`` for re-ingestion, keyed by
``account_id`` so replayed fills land on the account's partition and fold in
order; only entries too corrupt to decode replay unkeyed. Re-publishing is
idempotent at the ledger (event-id dedupe), so it is safe to re-run; the DLQ is
cleared only once fully drained.

Run from the portfolio service:  ``python -m src.tasks.dlq_replay [--max N]``
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from llamatrade_events import CURSOR_BEGIN, Cursor, EventBus, FillEvents, decode_envelope

from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM, LEDGER_FILLS_STREAM

logger = logging.getLogger(__name__)


def _replay_key(raw: bytes) -> str | None:
    """The account partition key recovered from a parked entry (None if undecodable)."""
    try:
        message = FillEvents.payload(decode_envelope(raw))
    except Exception:
        return None
    return message.account_id or None


def _cursor_partition_offset(cursor: Cursor) -> tuple[str, int]:
    """Split a transport cursor into ``(partition-key, numeric offset)``.

    Kafka cursors are ``"partition:offset"``; the in-memory fake uses a single
    monotonic ``"seq"`` (no partition, one global log). ``purge(up_to_cursor=)``
    is single-partition, so the replay tracks the highest drained cursor per
    partition and purges each — a lone scalar would clear only one partition.
    """
    prefix, sep, suffix = cursor.rpartition(":")
    if sep:
        return prefix, int(suffix)
    return "", int(cursor)


async def replay_dlq(bus: EventBus, *, max_entries: int = 1000) -> int:
    """Re-drive DLQ'd ledger entries through the main topic; purge exactly what drained.

    Returns the number of entries replayed. The live consumer re-parks
    still-unrecordable fills onto the DLQ during the run (at cursors past the ones
    read here). A cursor-bounded purge removes only entries at or below the highest
    cursor drained this run, so those re-parks (at later cursors) survive and a
    follow-up run drains them. Because a cursor addresses a single partition, the
    highest drained cursor is tracked PER partition and each is purged. A
    null/tombstone entry counts as read (it advances the per-partition high-water
    mark so it is purged) but is never republished.
    """
    depth = await bus.length(LEDGER_FILLS_DLQ_STREAM)
    if depth == 0:
        return 0

    target = min(depth, max_entries)
    read = 0
    replayed = 0
    # partition -> (highest offset drained, its cursor) for the bounded purge.
    high_water: dict[str, tuple[int, Cursor]] = {}
    async for cursor, raw in bus.tail_raw(LEDGER_FILLS_DLQ_STREAM, from_cursor=CURSOR_BEGIN):
        read += 1
        partition, offset = _cursor_partition_offset(cursor)
        current = high_water.get(partition)
        if current is None or offset > current[0]:
            high_water[partition] = (offset, cursor)
        if not raw:
            logger.warning("skipping null/empty DLQ entry at cursor %s", cursor)
        else:
            await bus.publish_raw(LEDGER_FILLS_STREAM, raw, key=_replay_key(raw))
            replayed += 1
        if read >= target:
            break

    # Purge only up to the highest cursor drained on each partition; entries re-parked at later cursors during the run are past the high-water mark and survive for a follow-up run.
    for _offset, cursor in high_water.values():
        await bus.purge(LEDGER_FILLS_DLQ_STREAM, up_to_cursor=cursor)
    if read < depth:
        logger.info(
            "replayed %d of %d DLQ ledger entr(ies) to %s; more remain — re-run to drain",
            replayed,
            depth,
            LEDGER_FILLS_STREAM,
        )
    else:
        logger.info("replayed %d DLQ ledger entr(ies) to %s", replayed, LEDGER_FILLS_STREAM)
    return replayed


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay DLQ'd ledger fills onto the main topic.")
    parser.add_argument("--max", type=int, default=1000, help="Maximum entries to replay")
    args = parser.parse_args()

    bus = EventBus()
    try:
        count = await replay_dlq(bus, max_entries=args.max)
        logger.info("DLQ replay complete: %d entr(ies) replayed", count)
    finally:
        await bus.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
