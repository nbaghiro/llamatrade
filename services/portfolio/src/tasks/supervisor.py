"""Crash-restart supervision for the long-running ledger loops.

A bare ``asyncio.create_task`` whose coroutine raises dies silently — the ledger
runtime would then stop ingesting / reconciling / snapshotting until the pod is
recycled. ``supervise`` restarts the loop with capped exponential backoff so a
transient crash self-heals in-process, while still honoring cooperative shutdown
via ``stop_event`` (and letting ``CancelledError`` propagate on hard shutdown).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def supervise(
    make_coro: Callable[[], Awaitable[None]],
    *,
    name: str,
    stop_event: asyncio.Event,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> None:
    """Run ``make_coro()``, restarting it on unexpected failure until stop.

    Returns when ``stop_event`` is set or the coroutine completes normally.
    ``asyncio.CancelledError`` propagates (shutdown cancellation). Each
    consecutive crash doubles the restart delay up to ``max_delay``.
    """
    delay = base_delay
    while not stop_event.is_set():
        try:
            await make_coro()
            return  # clean completion — nothing to restart
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ledger loop %r crashed; restarting in %.1fs", name, delay)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except TimeoutError:
                pass
            delay = min(delay * 2, max_delay)
