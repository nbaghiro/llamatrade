"""Operator tool: replay DLQ'd ledger fills back onto the main stream.

Fills that couldn't be booked (undecodable bytes / unresolvable cost basis) are
parked on ``ledger:fills:dlq`` instead of being lost. Once the root cause is
fixed, this re-publishes them onto ``ledger:fills`` for re-ingestion. Re-publishing
is idempotent at the ledger (event-id dedupe), so it is safe to re-run; the DLQ is
cleared only once fully drained.

Run from the portfolio service:  ``python -m src.tasks.dlq_replay [--max N]``
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from llamatrade_events import CURSOR_BEGIN, LEDGER_FILLS, EventBus

from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM, LEDGER_FILLS_STREAM

logger = logging.getLogger(__name__)


async def replay_dlq(bus: EventBus, *, max_entries: int = 1000) -> int:
    """Re-drive DLQ'd ledger entries through the main stream; clear the DLQ on full drain.

    Returns the number of entries replayed. The DLQ is purged only when the whole
    backlog was drained, so entries that arrive mid-replay are preserved.
    """
    depth = await bus.length(LEDGER_FILLS_DLQ_STREAM)
    if depth == 0:
        return 0

    target = min(depth, max_entries)
    replayed = 0
    async for _cursor, raw in bus.tail_raw(LEDGER_FILLS_DLQ_STREAM, from_cursor=CURSOR_BEGIN):
        await bus.publish_raw(LEDGER_FILLS_STREAM, raw, maxlen=LEDGER_FILLS.maxlen)
        replayed += 1
        if replayed >= target:
            break

    if replayed >= depth:
        await bus.purge(LEDGER_FILLS_DLQ_STREAM)
    logger.info("replayed %d DLQ ledger entr(ies) to %s", replayed, LEDGER_FILLS_STREAM)
    return replayed


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay DLQ'd ledger fills onto the main stream.")
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
