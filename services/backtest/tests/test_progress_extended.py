"""Extended tests for progress module to improve coverage."""

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.progress import (
    BacktestProgressReporter,
    ProgressPublisher,
    ProgressSubscriber,
    ProgressTracker,
    ProgressUpdate,
)

# === ProgressTracker Tests ===


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_calculate_eta_basic(self):
        """Test ETA calculation."""
        tracker = ProgressTracker(total_items=100)
        # Simulate some time passing
        tracker.start_time = time.monotonic() - 10  # 10 seconds ago

        eta = tracker.calculate_eta(50)  # Half done

        assert eta is not None
        assert eta > 0

    def test_calculate_eta_zero_items(self):
        """Test ETA with zero items."""
        tracker = ProgressTracker(total_items=0)

        eta = tracker.calculate_eta(0)

        assert eta is None

    def test_calculate_eta_negative_current(self):
        """Test ETA with negative current item."""
        tracker = ProgressTracker(total_items=100)

        eta = tracker.calculate_eta(-1)

        assert eta is None

    def test_calculate_eta_not_enough_time(self):
        """Test ETA when not enough time has elapsed."""
        tracker = ProgressTracker(total_items=100)
        # start_time is basically now

        eta = tracker.calculate_eta(1)

        assert eta is None

    def test_calculate_eta_at_end(self):
        """Test ETA at end returns 0."""
        tracker = ProgressTracker(total_items=100)
        tracker.start_time = time.monotonic() - 10

        eta = tracker.calculate_eta(100)  # Completed

        assert eta == 0

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


# === ProgressUpdate Tests ===


class TestProgressUpdate:
    """Tests for ProgressUpdate class."""

    def test_to_dict(self):
        """Test converting update to dictionary."""
        update = ProgressUpdate(
            backtest_id="test-123",
            progress=50.0,
            message="Processing",
            eta_seconds=60,
        )

        result = update.to_dict()

        assert result["backtest_id"] == "test-123"
        assert result["progress"] == 50.0
        assert result["message"] == "Processing"
        assert result["eta_seconds"] == 60
        assert "timestamp" in result

    def test_to_dict_with_timestamp(self):
        """Test dictionary with explicit timestamp."""
        update = ProgressUpdate(
            backtest_id="test-123",
            progress=100.0,
            message="Done",
            timestamp="2024-01-01T00:00:00Z",
        )

        result = update.to_dict()

        assert result["timestamp"] == "2024-01-01T00:00:00Z"


# === ProgressPublisher Tests ===


class TestProgressPublisher:
    """Tests for ProgressPublisher class."""

    async def test_publish_success(self):
        """Test publishing progress update."""
        publisher = ProgressPublisher()
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        publisher._redis = mock_redis

        await publisher.publish(
            backtest_id="test-123",
            progress=50.0,
            message="Processing",
            eta_seconds=60,
        )

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert "backtest:progress:test-123" in call_args[0]

    async def test_close(self):
        """Test closing publisher."""
        publisher = ProgressPublisher()
        mock_redis = MagicMock()
        mock_redis.close = AsyncMock()
        publisher._redis = mock_redis

        await publisher.close()

        mock_redis.close.assert_called_once()
        assert publisher._redis is None


# === ProgressSubscriber Tests ===


class TestProgressSubscriber:
    """Tests for ProgressSubscriber class."""

    async def test_close(self):
        """Test closing subscriber."""
        subscriber = ProgressSubscriber()
        mock_pubsub = MagicMock()
        mock_pubsub.close = AsyncMock()
        mock_redis = MagicMock()
        mock_redis.close = AsyncMock()

        subscriber._pubsub = mock_pubsub
        subscriber._redis = mock_redis

        await subscriber.close()

        mock_pubsub.close.assert_called_once()
        mock_redis.close.assert_called_once()


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

        mock_publisher.publish.assert_called_once_with("test-123", 30, "Loading data", None)

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
        reporter._pending_updates = [(50.0, "Processing", 30)]

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
