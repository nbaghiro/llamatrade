"""Async runtime metrics: event-loop lag and task count.

Process CPU/memory/GC come for free from prometheus_client's default collectors
(``process_*``, ``python_*``); this module adds the async-specific signals that
matter for an async-first codebase. The monitor is started lazily on the first
HTTP request (when an event loop is guaranteed to be running), so it needs no
lifespan wiring.
"""

from __future__ import annotations

import asyncio
from time import perf_counter

from llamatrade_telemetry import registry

EVENT_LOOP_LAG = registry.histogram(
    "llamatrade_runtime_event_loop_lag_seconds",
    (),
    "Scheduling delay of the asyncio event loop",
)
ASYNCIO_TASKS = registry.gauge(
    "llamatrade_runtime_asyncio_tasks",
    (),
    "Number of asyncio tasks currently alive",
)

_monitor_task: asyncio.Task[None] | None = None
_MONITOR_INTERVAL_SECONDS = 5.0


async def _monitor() -> None:
    while True:
        start = perf_counter()
        await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)
        lag = (perf_counter() - start) - _MONITOR_INTERVAL_SECONDS
        EVENT_LOOP_LAG.observe(max(lag, 0.0))
        ASYNCIO_TASKS.set(len(asyncio.all_tasks()))


def ensure_runtime_monitor() -> None:
    """Start the event-loop monitor once, if an event loop is running."""
    global _monitor_task
    if _monitor_task is not None and not _monitor_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _monitor_task = loop.create_task(_monitor())


def stop_runtime_monitor() -> None:
    """Cancel the monitor (for shutdown / tests)."""
    global _monitor_task
    if _monitor_task is not None:
        _monitor_task.cancel()
        _monitor_task = None
