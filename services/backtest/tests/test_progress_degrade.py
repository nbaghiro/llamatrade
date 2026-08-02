"""A progress publish failure must degrade to logging, never fail the run."""

from unittest.mock import AsyncMock

import pytest

from src.progress import ProgressPublisher


@pytest.mark.asyncio
async def test_publish_failure_does_not_raise() -> None:
    events = AsyncMock()
    events.publish = AsyncMock(side_effect=ConnectionError("broker down"))
    publisher = ProgressPublisher(progress_events=events)

    await publisher.publish("bt-1", 42.0, "simulating")
    await publisher.publish("bt-1", 43.0, "simulating")

    assert events.publish.await_count == 2


@pytest.mark.asyncio
async def test_success_resets_failure_streak() -> None:
    events = AsyncMock()
    events.publish = AsyncMock(side_effect=[ConnectionError("down"), None])
    publisher = ProgressPublisher(progress_events=events)

    await publisher.publish("bt-1", 10.0, "loading")
    await publisher.publish("bt-1", 20.0, "loading")

    assert publisher._consecutive_failures == 0
