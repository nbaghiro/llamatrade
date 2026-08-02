"""DLQ depth sampler wiring: run_dlq_sampler gauges the notifications DLQ."""

import asyncio
import time
from collections.abc import Callable

from metrics_util import metric_value

from llamatrade_events import EventBus
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport

from src.tasks.consumer import NOTIFICATIONS_DLQ_STREAM, run_dlq_sampler

DLQ_DEPTH = "llamatrade_events_dlq_depth"


async def _eventually(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(0.005)


def test_dlq_stream_matches_consumer_convention() -> None:
    """The sampled stream is the consumer's DLQ (stream + default dlq_suffix)."""
    assert NOTIFICATIONS_DLQ_STREAM == "notifications:dlq"


async def test_run_dlq_sampler_gauges_parked_entries_and_stops() -> None:
    """The sampler sets the depth gauge on start and exits when stop is set."""
    transport = FakeTransport()
    events = NotificationEvents(bus=EventBus(transport))
    await transport.publish(NOTIFICATIONS_DLQ_STREAM, b"p0")
    await transport.publish(NOTIFICATIONS_DLQ_STREAM, b"p1")
    stop = asyncio.Event()
    task = asyncio.create_task(run_dlq_sampler(events, stop_event=stop))

    await _eventually(lambda: metric_value(DLQ_DEPTH, stream="notifications:dlq") == 2.0)

    stop.set()
    await asyncio.wait_for(task, timeout=5.0)
