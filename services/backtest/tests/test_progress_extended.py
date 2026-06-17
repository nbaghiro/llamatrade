"""Extended tests for progress module to improve coverage."""

import time
from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from llamatrade_events import ProgressEvents
from llamatrade_proto.generated import backtest_pb2

from src.progress import (
    BacktestProgressReporter,
    ProgressPublisher,
    ProgressSubscriber,
    ProgressTracker,
)

# === ProgressTracker Tests ===


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_should_report_significant_progress(self):
        """Test reporting on significant progress jumps."""
        tracker = ProgressTracker(total_items=100)

        # First report should always happen
        assert tracker.should_report(5.0) is True

        # Another significant jump should report
        assert tracker.should_report(10.0) is True

    def test_should_report_rate_limited(self):
        """Test rate limiting of progress reports."""
        tracker = ProgressTracker(total_items=100)

        # First report - need a significant progress jump (5%+)
        assert tracker.should_report(5.0) is True

        # Immediate second report with tiny increment should be rate limited
        assert tracker.should_report(5.5) is False

    def test_should_report_after_interval(self):
        """Test reporting after minimum interval."""
        tracker = ProgressTracker(total_items=100)
        tracker._min_report_interval = 0.01  # Very short for testing

        tracker.should_report(1.0)
        time.sleep(0.02)

        assert tracker.should_report(2.0) is True


# === ProgressPublisher Tests ===


class TestProgressPublisher:
    """Tests for ProgressPublisher class."""

    async def test_publish_success(self):
        """Test publishing a progress update to the stream."""
        events = AsyncMock()
        events.publish = AsyncMock(return_value="1-0")
        publisher = ProgressPublisher(progress_events=cast("ProgressEvents", events))

        await publisher.publish(
            backtest_id="test-123",
            progress=50.0,
            message="Processing",
        )

        events.publish.assert_awaited_once()
        backtest_id, update = events.publish.await_args.args
        assert backtest_id == "test-123"
        assert update.backtest_id == "test-123"
        assert update.progress_percent == 50
        assert update.message == "Processing"
        assert update.status == backtest_pb2.BACKTEST_STATUS_RUNNING

    async def test_close(self):
        """Test closing publisher closes the channel."""
        events = AsyncMock()
        publisher = ProgressPublisher(progress_events=cast("ProgressEvents", events))
        await publisher.close()
        events.close.assert_awaited_once()


# === ProgressSubscriber Tests ===


class TestProgressSubscriber:
    """Tests for ProgressSubscriber class."""

    async def test_close(self):
        """Test closing subscriber closes the channel."""
        events = AsyncMock()
        subscriber = ProgressSubscriber(progress_events=cast("ProgressEvents", events))
        await subscriber.close()
        events.close.assert_awaited_once()


# === BacktestProgressReporter Tests ===


class TestBacktestProgressReporter:
    """Tests for BacktestProgressReporter class."""

    async def test_publish_phase(self):
        """Test publishing a phase update."""
        reporter = BacktestProgressReporter("test-123")
        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        reporter._publisher = mock_publisher

        await reporter.publish_phase("Loading data", 30)

        mock_publisher.publish.assert_called_once_with("test-123", 30, "Loading data", status=None)

    def test_set_total_bars(self):
        """Test setting total bars."""
        reporter = BacktestProgressReporter("test-123")

        reporter.set_total_bars(1000)

        assert reporter.total_bars == 1000
        assert reporter._tracker is not None
        assert reporter._tracker.total_items == 1000

    def test_create_engine_callback(self):
        """Test creating engine callback."""
        reporter = BacktestProgressReporter("test-123", total_bars=100)

        callback = reporter.create_engine_callback()

        assert callable(callback)

    def test_engine_callback_queues_updates(self):
        """Test that engine callback queues progress updates."""
        reporter = BacktestProgressReporter(
            "test-123",
            total_bars=100,
            simulation_start_pct=40.0,
            simulation_end_pct=90.0,
        )
        reporter._tracker = ProgressTracker(total_items=100)
        reporter._tracker._min_report_interval = 0  # Disable rate limiting

        callback = reporter.create_engine_callback()

        # Simulate progress
        callback(50, 100, datetime(2024, 1, 15))

        # Should have queued an update
        assert len(reporter._pending_updates) > 0

    async def test_flush_publishes_pending(self):
        """Test flushing pending updates."""
        reporter = BacktestProgressReporter("test-123")
        mock_publisher = MagicMock()
        mock_publisher.publish = AsyncMock()
        reporter._publisher = mock_publisher
        reporter._pending_updates = [(50.0, "Processing")]

        await reporter.flush()

        mock_publisher.publish.assert_called_once()
        assert len(reporter._pending_updates) == 0

    async def test_close_publisher(self):
        """Test closing the reporter."""
        reporter = BacktestProgressReporter("test-123")
        mock_publisher = MagicMock()
        mock_publisher.close = AsyncMock()
        reporter._publisher = mock_publisher

        await reporter.close()

        mock_publisher.close.assert_called_once()
