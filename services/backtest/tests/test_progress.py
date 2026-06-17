"""Tests for progress tracking module (Redis Streams transport)."""

import asyncio
import time
from datetime import datetime
from typing import cast

import pytest

from llamatrade_events import ProgressEvents
from llamatrade_proto.generated import backtest_pb2

from src.progress import (
    BacktestProgressReporter,
    ProgressPublisher,
    ProgressSubscriber,
    ProgressTracker,
)


class _StubEvents:
    """ProgressEvents stand-in: records publishes; tail yields canned entries."""

    def __init__(
        self,
        entries: list[tuple[str, backtest_pb2.BacktestProgressUpdate]] | None = None,
    ) -> None:
        self.published: list[tuple[str, backtest_pb2.BacktestProgressUpdate]] = []
        self._entries = entries or []
        self.tail_calls: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, backtest_id, update, *, tenant_id="", event_id=None):
        self.published.append((backtest_id, update))
        return "1-0"

    async def tail(self, backtest_id, *, from_cursor="0"):
        self.tail_calls.append((backtest_id, from_cursor))
        for entry in self._entries:
            yield entry

    async def close(self):
        self.closed = True


class _BlockingEvents(_StubEvents):
    """Tail blocks forever after its canned entries (orphaned-stream sim)."""

    async def tail(self, backtest_id, *, from_cursor="0"):
        self.tail_calls.append((backtest_id, from_cursor))
        for entry in self._entries:
            yield entry
        await asyncio.Event().wait()  # never resolves → forces idle timeout


def _progress_entry(
    progress: float, *, status: int | None = None
) -> tuple[str, backtest_pb2.BacktestProgressUpdate]:
    update = backtest_pb2.BacktestProgressUpdate(
        backtest_id="bt-1",
        progress_percent=int(progress),
        message=f"at {progress}%",
        status=status if status is not None else backtest_pb2.BACKTEST_STATUS_RUNNING,
    )
    return (f"{int(progress)}-0", update)


class TestProgressPublisher:
    """Tests for ProgressPublisher (streams transport)."""

    def test_init_default_url(self):
        """Defaults to the module's env-derived REDIS_URL (CI overrides it)."""
        from src.progress import REDIS_URL

        publisher = ProgressPublisher()
        assert publisher.redis_url == REDIS_URL

    def test_init_custom_url(self):
        publisher = ProgressPublisher(redis_url="redis://custom:6379/1")
        assert publisher.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_publish_writes_to_stream(self):
        events = _StubEvents()
        publisher = ProgressPublisher(progress_events=cast("ProgressEvents", events))

        await publisher.publish("bt-123", 50.0, "Halfway there")

        assert len(events.published) == 1
        backtest_id, update = events.published[0]
        assert backtest_id == "bt-123"
        # The wire payload is the BacktestProgressUpdate proto.
        assert update.backtest_id == "bt-123"
        assert update.progress_percent == 50
        assert update.message == "Halfway there"
        assert update.status == backtest_pb2.BACKTEST_STATUS_RUNNING

    @pytest.mark.asyncio
    async def test_publish_carries_explicit_status(self):
        events = _StubEvents()
        publisher = ProgressPublisher(progress_events=cast("ProgressEvents", events))

        await publisher.publish(
            "bt-123", 100.0, "Failed", status=backtest_pb2.BACKTEST_STATUS_FAILED
        )

        _, update = events.published[0]
        assert update.status == backtest_pb2.BACKTEST_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_close_closes_events(self):
        events = _StubEvents()
        publisher = ProgressPublisher(progress_events=cast("ProgressEvents", events))
        await publisher.close()
        assert events.closed is True

    @pytest.mark.asyncio
    async def test_close_without_connection(self):
        await ProgressPublisher().close()  # Should not raise


class TestProgressSubscriber:
    """Tests for ProgressSubscriber (streams tail)."""

    def test_init_default_url(self):
        from src.progress import REDIS_URL

        subscriber = ProgressSubscriber()
        assert subscriber.redis_url == REDIS_URL

    def test_init_custom_url(self):
        subscriber = ProgressSubscriber(redis_url="redis://custom:6379/1")
        assert subscriber.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_close_without_connection(self):
        await ProgressSubscriber().close()  # Should not raise


class TestProgressStreamTail:
    @pytest.mark.asyncio
    async def test_late_joiner_replays_from_start_and_terminates(self) -> None:
        events = _StubEvents(
            entries=[_progress_entry(25.0), _progress_entry(75.0), _progress_entry(100.0, status=3)]
        )
        subscriber = ProgressSubscriber(progress_events=cast("ProgressEvents", events))

        updates = [u async for u in subscriber.tail("bt-1")]

        # Tail starts from CURSOR_BEGIN: the late joiner caught all three updates
        assert events.tail_calls == [("bt-1", "0")]
        assert [u.progress_percent for u in updates] == [25, 75, 100]
        assert updates[-1].status == 3  # explicit terminal status, not inferred

    @pytest.mark.asyncio
    async def test_tail_stops_at_terminal_even_with_more_entries(self) -> None:
        events = _StubEvents(entries=[_progress_entry(100.0), _progress_entry(100.0)])
        subscriber = ProgressSubscriber(progress_events=cast("ProgressEvents", events))

        updates = [u async for u in subscriber.tail("bt-1")]
        assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_update_carries_explicit_status(self) -> None:
        """Regression: a failed run publishes progress=100; status must be explicit."""
        from llamatrade_proto.generated.backtest_pb2 import BACKTEST_STATUS_FAILED

        events = _StubEvents(entries=[_progress_entry(100.0, status=BACKTEST_STATUS_FAILED)])
        subscriber = ProgressSubscriber(progress_events=cast("ProgressEvents", events))

        updates = [u async for u in subscriber.tail("bt-1")]
        assert len(updates) == 1
        assert updates[0].status == BACKTEST_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_orphaned_stream_ends_after_idle_timeout(self) -> None:
        """A publisher that died mid-run must not hang the tail forever."""
        events = _BlockingEvents(entries=[_progress_entry(25.0)])
        subscriber = ProgressSubscriber(progress_events=cast("ProgressEvents", events))

        updates = [u async for u in subscriber.tail("bt-1", idle_timeout=0.2)]
        # The one prior update is replayed, then the idle timeout ends the tail.
        assert [u.progress_percent for u in updates] == [25]


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_init(self):
        tracker = ProgressTracker(total_items=100)
        assert tracker.total_items == 100
        assert tracker._lock is not None
        assert tracker._min_report_interval == 0.5

    def test_init_custom_interval(self):
        tracker = ProgressTracker(total_items=100, min_report_interval=1.0)
        assert tracker._min_report_interval == 1.0

    def test_should_report_initial(self):
        assert ProgressTracker(total_items=100).should_report(5.0) is True

    def test_should_report_rate_limiting(self):
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)
        assert tracker.should_report(5.1) is False

    def test_should_report_significant_jump(self):
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)
        assert tracker.should_report(10.0) is True

    def test_should_report_after_interval(self):
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)
        with tracker._lock:
            tracker._last_report_time = time.monotonic() - 1.0
        assert tracker.should_report(5.5) is True

    def test_should_report_thread_safety(self):
        import threading

        tracker = ProgressTracker(total_items=100)
        results = []
        errors = []

        def call_should_report(progress):
            try:
                results.append(tracker.should_report(progress))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_should_report, args=(i * 5.0,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20


class TestBacktestProgressReporter:
    """Tests for BacktestProgressReporter class."""

    @staticmethod
    def _reporter_with_events() -> tuple[BacktestProgressReporter, _StubEvents]:
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        events = _StubEvents()
        reporter._publisher._events = cast("ProgressEvents", events)
        return reporter, events

    def test_init(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        assert reporter.backtest_id == "bt-123"
        assert reporter.total_bars == 1000
        assert reporter.simulation_start_pct == 40.0
        assert reporter.simulation_end_pct == 90.0

    def test_set_total_bars(self):
        reporter = BacktestProgressReporter("bt-123")
        assert reporter.total_bars == 0
        reporter.set_total_bars(500)
        assert reporter.total_bars == 500
        assert reporter._tracker is not None
        assert reporter._tracker.total_items == 500

    @pytest.mark.asyncio
    async def test_publish_phase(self):
        reporter, events = self._reporter_with_events()
        await reporter.publish_phase("Loading data", 30)

        assert len(events.published) == 1
        _, update = events.published[0]
        assert update.progress_percent == 30
        assert update.message == "Loading data"

    def test_create_engine_callback(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        assert callable(reporter.create_engine_callback())

    def test_engine_callback_queues_updates(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        callback = reporter.create_engine_callback()
        callback(50, 100, datetime(2024, 1, 15))

        assert len(reporter._pending_updates) == 1
        progress, message = reporter._pending_updates[0]
        # 50% through simulation (40% to 90% range) = 40 + 25 = 65%
        assert 64 <= progress <= 66
        assert "2024-01-15" in message

    def test_engine_callback_rate_limits(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        callback = reporter.create_engine_callback()
        for i in range(10):
            callback(i + 1, 100, datetime(2024, 1, 15))
        assert len(reporter._pending_updates) < 10

    @pytest.mark.asyncio
    async def test_flush(self):
        reporter, events = self._reporter_with_events()
        reporter._pending_updates = [(50.0, "Test 1"), (75.0, "Test 2")]

        await reporter.flush()

        assert len(events.published) == 2
        assert len(reporter._pending_updates) == 0

    @pytest.mark.asyncio
    async def test_close(self):
        reporter, events = self._reporter_with_events()
        await reporter.close()
        assert events.closed is True

    def test_engine_callback_auto_trims_queue(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        reporter._max_pending = 10
        callback = reporter.create_engine_callback()
        for i in range(100):
            if reporter._tracker:
                with reporter._tracker._lock:
                    reporter._tracker._last_report_progress = 0.0
                    reporter._tracker._last_report_time = 0.0
            callback(i * 10, 1000, datetime(2024, 1, 15))
        assert len(reporter._pending_updates) <= reporter._max_pending

    def test_engine_callback_keeps_recent_updates_on_trim(self):
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        reporter._max_pending = 10
        for i in range(15):
            reporter._pending_updates.append((float(i), f"Update {i}"))
        callback = reporter.create_engine_callback()
        if reporter._tracker:
            with reporter._tracker._lock:
                reporter._tracker._last_report_progress = 0.0
                reporter._tracker._last_report_time = 0.0
        callback(99, 100, datetime(2024, 1, 15))
        assert len(reporter._pending_updates) <= reporter._max_pending

    def test_engine_callback_thread_safety(self):
        import threading

        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        errors = []

        def call_callback(bar_num):
            try:
                reporter.create_engine_callback()(bar_num, 1000, datetime(2024, 1, 15))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_callback, args=(i * 50,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
