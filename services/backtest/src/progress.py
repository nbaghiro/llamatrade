"""Progress tracking and publishing for backtests."""

import logging
import os
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from datetime import UTC, datetime
from typing import cast

import redis.asyncio as aioredis

from llamatrade_events import CURSOR_BEGIN, EventBus, ProgressEvents, RedisStreamsTransport
from llamatrade_proto.generated import backtest_pb2, common_pb2
from llamatrade_telemetry import metrics

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class ProgressTracker:
    """Tracks progress and calculates ETA for a backtest.

    Thread-safe: all state mutations are protected by a lock.
    """

    def __init__(
        self,
        total_items: int,
        min_report_interval: float = 0.5,
    ):
        """Initialize the progress tracker.

        Args:
            total_items: Total number of items to process.
            min_report_interval: Minimum seconds between reports.
        """
        self.total_items = total_items
        self.start_time = time.monotonic()
        self._last_report_time = time.monotonic()
        self._last_report_progress = 0.0
        self._min_report_interval = min_report_interval
        self._lock = threading.Lock()

    def should_report(self, current_progress: float) -> bool:
        """Check if we should report progress (rate limiting).

        Thread-safe: uses lock to protect _last_report_time and _last_report_progress.

        Args:
            current_progress: Current progress percentage (0-100).

        Returns:
            True if enough time has passed since last report.
        """
        now = time.monotonic()

        with self._lock:
            # Always report on significant progress jumps (5% or more)
            if current_progress - self._last_report_progress >= 5.0:
                self._last_report_time = now
                self._last_report_progress = current_progress
                return True

            # Rate limit frequent reports
            if now - self._last_report_time >= self._min_report_interval:
                self._last_report_time = now
                self._last_report_progress = current_progress
                return True

            return False


class ProgressPublisher:
    """Publishes progress updates to a bounded, replayable Redis Stream.

    The wire payload is the ``BacktestProgressUpdate`` proto on the events lib's
    ``BACKTEST_PROGRESS`` channel; that channel owns the stream key and retention.
    """

    def __init__(self, redis_url: str | None = None, progress_events: ProgressEvents | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._events: ProgressEvents | None = progress_events

    def _get_events(self) -> ProgressEvents:
        if self._events is None:
            self._events = ProgressEvents(bus=EventBus(RedisStreamsTransport(self.redis_url)))
        return self._events

    async def publish(
        self,
        backtest_id: str,
        progress: float,
        message: str,
        status: int | None = None,
    ) -> None:
        """Publish a progress update to the backtest's progress stream.

        A short bounded stream so a late-joining UI replays from the start and
        catches up immediately.
        """
        # `status` is a plain int on the caller side; the proto field is the
        # BacktestStatus enum ValueType. They share the same wire integers, so a
        # cast is the right narrowing here.
        status_value = cast(
            "backtest_pb2.BacktestStatus.ValueType",
            status if status is not None else backtest_pb2.BACKTEST_STATUS_RUNNING,
        )
        update = backtest_pb2.BacktestProgressUpdate(
            backtest_id=backtest_id,
            status=status_value,
            progress_percent=int(progress),
            message=message,
            timestamp=common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp())),
        )
        try:
            await self._get_events().publish(backtest_id, update)
        except Exception:
            # Record the failure for observability, then preserve existing
            # behavior by re-raising (the caller maps it to a FAILED run).
            metrics.backtest.progress_publish_failure()
            raise

    async def close(self) -> None:
        """Close the progress channel, if created."""
        if self._events is not None:
            await self._events.close()
            self._events = None


class ProgressSubscriber:
    """Tail-reads progress updates from the backtest's Redis Stream."""

    def __init__(self, redis_url: str | None = None, progress_events: ProgressEvents | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._events: ProgressEvents | None = progress_events

    def _get_events(self) -> ProgressEvents:
        if self._events is None:
            self._events = ProgressEvents(bus=EventBus(RedisStreamsTransport(self.redis_url)))
        return self._events

    async def tail(
        self,
        backtest_id: str,
        idle_timeout: float = 300.0,
    ) -> AsyncIterator[backtest_pb2.BacktestProgressUpdate]:
        """Tail the progress stream from the start.

        Replaying from ``CURSOR_BEGIN`` means a client that connects mid-run
        catches up on all prior updates immediately — the late-joiner gap
        pub/sub had. Ends on a terminal update (progress >= 100) or after
        ``idle_timeout`` seconds of silence (orphaned run).
        """
        import asyncio

        # The channel returns an async generator of (cursor, proto) tuples;
        # typed as AsyncGenerator so the finally-close is visible to the type
        # checker.
        entries = cast(
            "AsyncGenerator[tuple[str, backtest_pb2.BacktestProgressUpdate]]",
            self._get_events().tail(backtest_id, from_cursor=CURSOR_BEGIN),
        )
        try:
            while True:
                try:
                    _, update = await asyncio.wait_for(anext(entries), timeout=idle_timeout)
                except TimeoutError, StopAsyncIteration:
                    break
                yield update
                if update.progress_percent >= 100:
                    break
        finally:
            await entries.aclose()

    async def close(self) -> None:
        """Close the progress channel, if created."""
        if self._events is not None:
            await self._events.close()
            self._events = None


class BacktestProgressReporter:
    """Creates progress callbacks for backtest engine integration.

    This class bridges the synchronous BacktestEngine progress callback
    with the async ProgressPublisher, handling rate limiting and ETA calculation.

    Usage:
        reporter = BacktestProgressReporter(backtest_id, total_bars)

        # In async context, publish setup phases
        await reporter.publish_phase("Fetching market data", 30)

        # Create callback for engine (sync function that queues updates)
        callback = reporter.create_engine_callback()

        # Pass to engine
        engine.run(bars, strategy_fn, start, end, progress_callback=callback)

        # After engine completes, publish any remaining updates
        await reporter.flush()
    """

    def __init__(
        self,
        backtest_id: str,
        total_bars: int = 0,
        simulation_start_pct: float = 40.0,
        simulation_end_pct: float = 90.0,
        redis_url: str | None = None,
    ):
        """Initialize the progress reporter.

        Args:
            backtest_id: UUID of the backtest.
            total_bars: Expected total number of bars to process.
            simulation_start_pct: Progress percentage when simulation starts.
            simulation_end_pct: Progress percentage when simulation ends.
            redis_url: Redis URL for publishing.
        """
        self.backtest_id = backtest_id
        self.total_bars = total_bars
        self.simulation_start_pct = simulation_start_pct
        self.simulation_end_pct = simulation_end_pct
        self._publisher = ProgressPublisher(redis_url)
        self._tracker: ProgressTracker | None = ProgressTracker(total_items=total_bars)
        self._pending_updates: list[tuple[float, str]] = []
        self._lock = threading.Lock()  # Thread-safe access to _pending_updates
        self._max_pending = 100  # Auto-flush threshold to bound memory usage

    async def publish_phase(
        self,
        message: str,
        progress: float,
        status: int | None = None,
    ) -> None:
        """Publish a phase progress update (e.g., 'Loading strategy').

        Args:
            message: Status message.
            progress: Progress percentage (0-100).
            status: Explicit BacktestStatus proto value for this update.
        """
        await self._publisher.publish(
            self.backtest_id,
            progress,
            message,
            status=status,
        )

    def set_total_bars(self, total_bars: int) -> None:
        """Set the total number of bars after data is loaded.

        Args:
            total_bars: Total bars to process.
        """
        self.total_bars = total_bars
        self._tracker = ProgressTracker(total_items=total_bars)

    def create_engine_callback(self) -> Callable[[int, int, datetime], None]:
        """Create a callback function for the backtest engine.

        Returns:
            A synchronous callback that queues progress updates.
            Thread-safe: uses lock to protect _pending_updates.
            Auto-trims queue when it exceeds _max_pending to bound memory.
        """
        # Import here to avoid circular imports
        from datetime import datetime as dt

        def callback(current_bar: int, total_bars: int, current_date: dt) -> None:
            # Update tracker if total changed (thread-safe read)
            if self._tracker is None or self._tracker.total_items != total_bars:
                self._tracker = ProgressTracker(total_items=total_bars)

            # Calculate progress within simulation range
            if total_bars > 0:
                sim_progress = current_bar / total_bars
                progress = self.simulation_start_pct + (
                    sim_progress * (self.simulation_end_pct - self.simulation_start_pct)
                )
            else:
                progress = self.simulation_start_pct

            # Rate limit updates
            if not self._tracker.should_report(progress):
                return

            # Format message with current date
            date_str = current_date.strftime("%Y-%m-%d")
            message = f"Processing {date_str} ({current_bar}/{total_bars})"

            # Queue update for async publishing (thread-safe)
            with self._lock:
                self._pending_updates.append((progress, message))

                # Auto-trim queue if it exceeds limit to bound memory usage.
                # Keep only the most recent half of updates (discarding older ones).
                # This ensures progress stays bounded even if flush() isn't called.
                if len(self._pending_updates) > self._max_pending:
                    # Keep the most recent updates (second half)
                    trim_count = self._max_pending // 2
                    self._pending_updates = self._pending_updates[-trim_count:]

        return callback

    async def flush(self) -> None:
        """Publish all pending progress updates.

        Thread-safe: acquires lock to drain _pending_updates.
        """
        # Atomically grab all pending updates
        with self._lock:
            updates = list(self._pending_updates)
            self._pending_updates.clear()

        # Publish outside the lock to avoid blocking callbacks
        for progress, message in updates:
            await self._publisher.publish(self.backtest_id, progress, message)

    async def close(self) -> None:
        """Close the publisher connection."""
        await self._publisher.close()


class CancellationFlag:
    """Redis-backed cancellation flag for cooperative backtest cancellation.

    `request_cancel` is async (called from the API on CancelBacktest).
    `make_should_abort` returns a SYNCHRONOUS, rate-limited checker suitable
    for the engine's hot loop, which runs in the Celery worker (no event
    loop to starve). Redis errors fail open: a broken Redis must not be able
    to abort or hang running backtests.
    """

    KEY_PREFIX = "backtest:cancel"
    # Flag outlives the longest plausible run; cancellation of a dead run is moot
    TTL_SECONDS = 2 * 3600

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or REDIS_URL

    @classmethod
    def _key(cls, backtest_id: str) -> str:
        return f"{cls.KEY_PREFIX}:{backtest_id}"

    async def request_cancel(self, backtest_id: str) -> None:
        """Mark a backtest as cancellation-requested."""
        redis = await aioredis.from_url(self.redis_url)
        try:
            await redis.setex(self._key(backtest_id), self.TTL_SECONDS, "1")
        finally:
            await redis.aclose()

    def make_should_abort(
        self,
        backtest_id: str,
        check_interval: float = 1.0,
    ) -> Callable[[], bool]:
        """Create a sync, rate-limited cancellation checker for the engine.

        The checker hits Redis at most once per `check_interval` seconds and
        latches True once cancellation is observed.
        """
        import redis as sync_redis

        key = self._key(backtest_id)
        client = sync_redis.from_url(self.redis_url)
        last_check = 0.0
        cancelled = False

        def should_abort() -> bool:
            nonlocal last_check, cancelled
            if cancelled:
                return True
            now = time.monotonic()
            if now - last_check < check_interval:
                return False
            last_check = now
            try:
                cancelled = client.get(key) is not None
            except Exception:
                # Fail open: Redis being down must not abort runs
                return False
            return cancelled

        return should_abort
