"""Tests for progress tracking module."""

import json
import time
from datetime import datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_common.eventbus import EventBus

from src.progress import (
    BacktestProgressReporter,
    ProgressPublisher,
    ProgressSubscriber,
    ProgressTracker,
    ProgressUpdate,
)


class TestProgressUpdate:
    """Tests for ProgressUpdate dataclass."""

    def test_basic_creation(self):
        """Test creating a progress update."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=50.0,
            message="Processing...",
        )

        assert update.backtest_id == "bt-123"
        assert update.progress == 50.0
        assert update.message == "Processing..."
        assert update.eta_seconds is None

    def test_with_eta(self):
        """Test creating with ETA."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=25.0,
            message="Loading data",
            eta_seconds=120,
        )

        assert update.eta_seconds == 120

    def test_with_timestamp(self):
        """Test creating with timestamp."""
        ts = "2024-01-01T12:00:00+00:00"
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Complete",
            timestamp=ts,
        )

        assert update.timestamp == ts

    def test_to_dict_basic(self):
        """Test converting to dict."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=75.0,
            message="Calculating metrics",
        )

        result = update.to_dict()

        assert result["backtest_id"] == "bt-123"
        assert result["progress"] == 75.0
        assert result["message"] == "Calculating metrics"
        assert result["eta_seconds"] is None
        assert "timestamp" in result  # Auto-generated

    def test_to_dict_with_provided_timestamp(self):
        """Test to_dict uses provided timestamp."""
        ts = "2024-01-01T12:00:00+00:00"
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Done",
            timestamp=ts,
        )

        result = update.to_dict()

        assert result["timestamp"] == ts

    def test_to_dict_auto_timestamp(self):
        """Test to_dict generates timestamp when not provided."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=50.0,
            message="Working",
        )

        result = update.to_dict()

        # Should be an ISO format timestamp
        assert "T" in result["timestamp"]


class TestProgressPublisher:
    """Tests for ProgressPublisher class."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        publisher = ProgressPublisher()
        assert publisher.redis_url == "redis://localhost:6379/0"
        assert publisher._redis is None

    def test_init_custom_url(self):
        """Test initialization with custom URL."""
        publisher = ProgressPublisher(redis_url="redis://custom:6379/1")
        assert publisher.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_get_redis_creates_connection(self):
        """Test that _get_redis creates connection on first call."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            result = await publisher._get_redis()

            assert result == mock_redis
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_reuses_connection(self):
        """Test that _get_redis reuses existing connection."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher._get_redis()
            await publisher._get_redis()

            # Should only create connection once
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publishing progress update."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.publish = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher.publish(
                backtest_id="bt-123",
                progress=50.0,
                message="Halfway there",
                eta_seconds=60,
            )

            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "backtest:progress:bt-123"

            # Verify published data
            published_data = json.loads(call_args[0][1])
            assert published_data["backtest_id"] == "bt-123"
            assert published_data["progress"] == 50.0
            assert published_data["message"] == "Halfway there"
            assert published_data["eta_seconds"] == 60

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing publisher."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher._get_redis()  # Create connection
            await publisher.close()

            mock_redis.close.assert_called_once()
            assert publisher._redis is None

    @pytest.mark.asyncio
    async def test_close_without_connection(self):
        """Test closing without connection is safe."""
        publisher = ProgressPublisher()
        await publisher.close()  # Should not raise


class TestProgressSubscriber:
    """Tests for ProgressSubscriber class."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        subscriber = ProgressSubscriber()
        assert subscriber.redis_url == "redis://localhost:6379/0"
        assert subscriber._redis is None
        assert subscriber._pubsub is None

    def test_init_custom_url(self):
        """Test initialization with custom URL."""
        subscriber = ProgressSubscriber(redis_url="redis://custom:6379/1")
        assert subscriber.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_get_redis_creates_connection(self):
        """Test that _get_redis creates connection on first call."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()
            result = await subscriber._get_redis()

            assert result == mock_redis
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing subscriber."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_pubsub = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()
            subscriber._redis = mock_redis
            subscriber._pubsub = mock_pubsub

            await subscriber.close()

            mock_pubsub.close.assert_called_once()
            mock_redis.close.assert_called_once()
            assert subscriber._redis is None
            assert subscriber._pubsub is None

    @pytest.mark.asyncio
    async def test_close_without_connections(self):
        """Test closing without connections is safe."""
        subscriber = ProgressSubscriber()
        await subscriber.close()  # Should not raise


class TestProgressIntegration:
    """Integration-style tests for progress module."""

    @pytest.mark.asyncio
    async def test_publisher_subscriber_flow(self):
        """Test publisher and subscriber work together."""
        with patch("src.progress.aioredis") as mock_aioredis:
            # Set up mock Redis
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            # Queue of pubsub messages; None once drained
            messages = [
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 50.0,
                            "message": "Processing",
                            "eta_seconds": 30,
                            "timestamp": "2024-01-01T12:00:00Z",
                        }
                    ),
                },
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Complete",
                            "eta_seconds": 0,
                            "timestamp": "2024-01-01T12:01:00Z",
                        }
                    ),
                },
            ]

            async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
                return messages.pop(0) if messages else None

            mock_pubsub.get_message = mock_get_message
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            assert len(updates) == 2
            assert updates[0].progress == 50.0
            assert updates[1].progress == 100.0
            assert updates[1].message == "Complete"

    @pytest.mark.asyncio
    async def test_subscribe_stops_at_100_percent(self):
        """Test that subscribe stops when progress reaches 100%."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            # 100% progress first; the second message must never be read
            messages = [
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Done",
                        }
                    ),
                },
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Still done",
                        }
                    ),
                },
            ]

            async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
                return messages.pop(0) if messages else None

            mock_pubsub.get_message = mock_get_message
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            # Should only get one update (stops at 100%)
            assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_subscribe_ignores_non_message_types(self):
        """Test that subscribe ignores non-message type events."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            messages = [
                {"type": "subscribe", "channel": "backtest:progress:bt-123"},
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Done",
                        }
                    ),
                },
            ]

            async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
                return messages.pop(0) if messages else None

            mock_pubsub.get_message = mock_get_message
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            # Should only get message type events
            assert len(updates) == 1
            assert updates[0].progress == 100.0


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    def test_init(self):
        """Test initialization creates lock."""
        tracker = ProgressTracker(total_items=100)
        assert tracker.total_items == 100
        assert tracker._lock is not None
        assert tracker._min_report_interval == 0.5

    def test_init_custom_interval(self):
        """Test initialization with custom interval."""
        tracker = ProgressTracker(total_items=100, min_report_interval=1.0)
        assert tracker._min_report_interval == 1.0

    def test_calculate_eta_no_progress(self):
        """Test ETA returns None when no progress made."""
        tracker = ProgressTracker(total_items=100)
        assert tracker.calculate_eta(0) is None

    def test_calculate_eta_insufficient_time(self):
        """Test ETA returns None when not enough time elapsed."""
        tracker = ProgressTracker(total_items=100)
        # Immediately check - not enough time
        assert tracker.calculate_eta(1) is None

    def test_calculate_eta_with_progress(self):
        """Test ETA calculation with some progress."""
        tracker = ProgressTracker(total_items=100)
        # Simulate time passing
        tracker.start_time = time.monotonic() - 10  # 10 seconds ago

        eta = tracker.calculate_eta(50)

        # 50 items in 10 seconds = 5 items/second
        # 50 remaining items at 5/sec = 10 seconds
        assert eta is not None
        assert 8 <= eta <= 12  # Allow some variance

    def test_calculate_eta_near_completion(self):
        """Test ETA near completion."""
        tracker = ProgressTracker(total_items=100)
        tracker.start_time = time.monotonic() - 100

        eta = tracker.calculate_eta(99)

        assert eta is not None
        assert eta <= 2  # Very small ETA

    def test_should_report_initial(self):
        """Test should_report returns True initially."""
        tracker = ProgressTracker(total_items=100)
        # First report should always be allowed
        assert tracker.should_report(5.0) is True

    def test_should_report_rate_limiting(self):
        """Test should_report rate limits rapid calls."""
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)  # First call

        # Immediate second call with small increment should be rate limited
        assert tracker.should_report(5.1) is False

    def test_should_report_significant_jump(self):
        """Test should_report allows significant progress jumps."""
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)

        # 5% jump should be reported even without time passing
        assert tracker.should_report(10.0) is True

    def test_should_report_after_interval(self):
        """Test should_report allows after time interval."""
        tracker = ProgressTracker(total_items=100)
        tracker.should_report(5.0)

        # Simulate time passing
        with tracker._lock:
            tracker._last_report_time = time.monotonic() - 1.0

        assert tracker.should_report(5.5) is True

    def test_should_report_thread_safety(self):
        """Test should_report is thread-safe with concurrent calls."""
        import threading

        tracker = ProgressTracker(total_items=100)
        results = []
        errors = []

        def call_should_report(progress):
            try:
                result = tracker.should_report(progress)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads calling should_report simultaneously
        threads = []
        for i in range(20):
            t = threading.Thread(target=call_should_report, args=(i * 5.0,))
            threads.append(t)

        # Start all threads at once
        for t in threads:
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0
        # All calls should have returned a result
        assert len(results) == 20


class TestBacktestProgressReporter:
    """Tests for BacktestProgressReporter class."""

    def test_init(self):
        """Test initialization."""
        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        assert reporter.backtest_id == "bt-123"
        assert reporter.total_bars == 1000
        assert reporter.simulation_start_pct == 40.0
        assert reporter.simulation_end_pct == 90.0

    def test_set_total_bars(self):
        """Test setting total bars after initialization."""
        reporter = BacktestProgressReporter("bt-123")
        assert reporter.total_bars == 0

        reporter.set_total_bars(500)

        assert reporter.total_bars == 500
        assert reporter._tracker is not None
        assert reporter._tracker.total_items == 500

    @pytest.mark.asyncio
    async def test_publish_phase(self):
        """Test publishing a phase update."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.publish = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            reporter = BacktestProgressReporter("bt-123")
            await reporter.publish_phase("Loading data", 30)

            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            data = json.loads(call_args[0][1])
            assert data["progress"] == 30
            assert data["message"] == "Loading data"

    def test_create_engine_callback(self):
        """Test creating engine callback."""
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        callback = reporter.create_engine_callback()

        assert callable(callback)

    def test_engine_callback_queues_updates(self):
        """Test engine callback queues progress updates."""
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        callback = reporter.create_engine_callback()

        # Call callback with progress
        test_date = datetime(2024, 1, 15)
        callback(50, 100, test_date)

        # Should have queued an update
        assert len(reporter._pending_updates) == 1
        progress, message, eta = reporter._pending_updates[0]
        # 50% through simulation (40% to 90% range) = 40 + 25 = 65%
        assert 64 <= progress <= 66
        assert "2024-01-15" in message

    def test_engine_callback_rate_limits(self):
        """Test engine callback rate limits updates."""
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        callback = reporter.create_engine_callback()

        # Call callback rapidly with small increments
        test_date = datetime(2024, 1, 15)
        for i in range(10):
            callback(i + 1, 100, test_date)

        # Should have rate limited - not all 10 updates
        assert len(reporter._pending_updates) < 10

    @pytest.mark.asyncio
    async def test_flush(self):
        """Test flushing pending updates."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.publish = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            reporter = BacktestProgressReporter("bt-123", total_bars=100)

            # Queue some updates manually
            reporter._pending_updates = [
                (50.0, "Test 1", 30),
                (75.0, "Test 2", 15),
            ]

            await reporter.flush()

            # Should have published both
            assert mock_redis.publish.call_count == 2
            assert len(reporter._pending_updates) == 0

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing reporter."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            reporter = BacktestProgressReporter("bt-123")
            await reporter._publisher._get_redis()  # Create connection
            await reporter.close()

            mock_redis.close.assert_called_once()

    def test_engine_callback_auto_trims_queue(self):
        """Test engine callback auto-trims queue when exceeding max_pending."""
        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        reporter._max_pending = 10  # Set low limit for testing

        callback = reporter.create_engine_callback()

        # Generate many updates that bypass rate limiting (5% jumps)
        test_date = datetime(2024, 1, 15)
        for i in range(100):
            # Force should_report to return True by simulating significant jumps
            if reporter._tracker:
                with reporter._tracker._lock:
                    reporter._tracker._last_report_progress = 0.0
                    reporter._tracker._last_report_time = 0.0
            callback(i * 10, 1000, test_date)

        # Queue should be trimmed to at most max_pending
        assert len(reporter._pending_updates) <= reporter._max_pending

    def test_engine_callback_keeps_recent_updates_on_trim(self):
        """Test that auto-trim keeps the most recent updates."""
        reporter = BacktestProgressReporter("bt-123", total_bars=100)
        reporter._max_pending = 10

        # Directly add updates to simulate exceeding the limit
        for i in range(15):
            reporter._pending_updates.append((float(i), f"Update {i}", i))

        # Trigger a callback that will cause auto-trim
        callback = reporter.create_engine_callback()
        test_date = datetime(2024, 1, 15)

        # Reset tracker to force a report
        if reporter._tracker:
            with reporter._tracker._lock:
                reporter._tracker._last_report_progress = 0.0
                reporter._tracker._last_report_time = 0.0

        callback(99, 100, test_date)

        # Queue should be trimmed, keeping recent updates
        # After trim, we should have at most max_pending entries
        assert len(reporter._pending_updates) <= reporter._max_pending

    def test_engine_callback_thread_safety(self):
        """Test engine callback is thread-safe with concurrent calls."""
        import threading

        reporter = BacktestProgressReporter("bt-123", total_bars=1000)
        errors = []

        def call_callback(bar_num):
            try:
                callback = reporter.create_engine_callback()
                test_date = datetime(2024, 1, 15)
                callback(bar_num, 1000, test_date)
            except Exception as e:
                errors.append(e)

        # Create multiple threads calling callback simultaneously
        threads = []
        for i in range(20):
            t = threading.Thread(target=call_callback, args=(i * 50,))
            threads.append(t)

        # Start all threads at once
        for t in threads:
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0


class TestSubscriberIdleTimeout:
    """An orphaned stream (publisher died) must end, not hang forever."""

    @pytest.mark.asyncio
    async def test_subscribe_ends_after_idle_timeout(self):
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            async def never_a_message(ignore_subscribe_messages=True, timeout=1.0):
                return None

            mock_pubsub.get_message = never_a_message
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-orphan", idle_timeout=3.0):
                updates.append(update)

            assert updates == []
            mock_pubsub.unsubscribe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_carries_explicit_status(self):
        """Subscriber must surface the publisher's explicit status field."""
        from llamatrade_proto.generated.backtest_pb2 import BACKTEST_STATUS_FAILED

        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            messages = [
                {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Failed: boom",
                            "status": BACKTEST_STATUS_FAILED,
                        }
                    ),
                },
            ]

            async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
                return messages.pop(0) if messages else None

            mock_pubsub.get_message = mock_get_message
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            # Regression: a failed run publishes progress=100; the OLD code
            # inferred COMPLETED from the percentage. Status must be explicit.
            assert len(updates) == 1
            assert updates[0].status == BACKTEST_STATUS_FAILED


class _StubBus:
    """EventBus stand-in: records publishes; tail yields canned entries."""

    def __init__(self, entries: list[tuple[str, dict[str, str]]] | None = None) -> None:
        self.published: list[tuple[str, dict[str, str], int | None]] = []
        self._entries = entries or []
        self.tail_calls: list[tuple[str, str]] = []
        self.closed = False

    async def publish(self, stream, fields, *, maxlen=None, approximate=True):
        self.published.append((stream, fields, maxlen))
        return "1-0"

    async def tail(self, stream, *, last_id="$", block_ms=5000, count=100):
        self.tail_calls.append((stream, last_id))
        for entry in self._entries:
            yield entry

    async def close(self):
        self.closed = True


def _progress_entry(progress: float, *, status: int | None = None) -> tuple[str, dict[str, str]]:
    import json

    body = {
        "backtest_id": "bt-1",
        "progress": progress,
        "message": f"at {progress}%",
        "eta_seconds": None,
        "timestamp": "2026-06-12T14:30:00+00:00",
        "status": status,
    }
    return (f"{int(progress)}-0", {"payload": json.dumps(body)})


class TestProgressStreamDualWrite:
    @pytest.mark.asyncio
    async def test_flag_on_dual_writes(self, monkeypatch) -> None:
        from src.progress import PROGRESS_STREAM_MAXLEN, ProgressPublisher

        monkeypatch.setenv("STREAMS_BACKTEST", "1")
        bus = _StubBus()
        publisher = ProgressPublisher(event_bus=cast("EventBus", bus))
        publisher._redis = AsyncMock()
        publisher._redis.publish = AsyncMock(return_value=1)

        await publisher.publish("bt-1", 42.0, "almost half")

        assert len(bus.published) == 1
        stream, fields, maxlen = bus.published[0]
        assert stream == "backtest:progress:bt-1"
        assert maxlen == PROGRESS_STREAM_MAXLEN
        publisher._redis.publish.assert_awaited_once()  # pub/sub still primary

    @pytest.mark.asyncio
    async def test_flag_off_skips_stream(self, monkeypatch) -> None:
        from src.progress import ProgressPublisher

        monkeypatch.delenv("STREAMS_BACKTEST", raising=False)
        bus = _StubBus()
        publisher = ProgressPublisher(event_bus=cast("EventBus", bus))
        publisher._redis = AsyncMock()
        publisher._redis.publish = AsyncMock(return_value=1)

        await publisher.publish("bt-1", 42.0, "almost half")

        assert bus.published == []


class TestProgressStreamTail:
    @pytest.mark.asyncio
    async def test_late_joiner_replays_from_start_and_terminates(self) -> None:
        from src.progress import ProgressSubscriber

        bus = _StubBus(
            entries=[_progress_entry(25.0), _progress_entry(75.0), _progress_entry(100.0, status=3)]
        )
        subscriber = ProgressSubscriber(event_bus=cast("EventBus", bus))

        updates = [u async for u in subscriber.tail("bt-1")]

        # Tail starts from "0": the late joiner caught all three updates
        assert bus.tail_calls == [("backtest:progress:bt-1", "0")]
        assert [u.progress for u in updates] == [25, 75, 100]
        assert updates[-1].status == 3  # explicit terminal status, not inferred

    @pytest.mark.asyncio
    async def test_tail_stops_at_terminal_even_with_more_entries(self) -> None:
        from src.progress import ProgressSubscriber

        bus = _StubBus(entries=[_progress_entry(100.0), _progress_entry(100.0)])
        subscriber = ProgressSubscriber(event_bus=cast("EventBus", bus))

        updates = [u async for u in subscriber.tail("bt-1")]
        assert len(updates) == 1
