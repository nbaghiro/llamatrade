"""Progress tracking and publishing for backtests."""

import json
import os
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@dataclass
class ProgressTracker:
    """Tracks progress and calculates ETA for a backtest."""

    total_items: int
    start_time: float = field(default_factory=time.monotonic)
    _last_report_time: float = field(default_factory=time.monotonic)
    _last_report_progress: float = 0.0
    _min_report_interval: float = 0.5  # Minimum seconds between reports

    def calculate_eta(self, current_item: int) -> int | None:
        """Calculate estimated seconds remaining.

        Args:
            current_item: Current item number (1-indexed).

        Returns:
            Estimated seconds remaining, or None if cannot calculate.
        """
        if current_item <= 0 or self.total_items <= 0:
            return None

        elapsed = time.monotonic() - self.start_time
        if elapsed < 0.1:  # Not enough time elapsed
            return None

        items_per_second = current_item / elapsed
        if items_per_second <= 0:
            return None

        remaining_items = self.total_items - current_item
        eta_seconds = int(remaining_items / items_per_second)
        return max(0, eta_seconds)

    def should_report(self, current_progress: float) -> bool:
        """Check if we should report progress (rate limiting).

        Args:
            current_progress: Current progress percentage (0-100).

        Returns:
            True if enough time has passed since last report.
        """
        now = time.monotonic()

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


@dataclass
class ProgressUpdate:
    """Progress update message."""

    backtest_id: str
    progress: float  # 0-100
    message: str
    eta_seconds: int | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "backtest_id": self.backtest_id,
            "progress": self.progress,
            "message": self.message,
            "eta_seconds": self.eta_seconds,
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
        }


class ProgressPublisher:
    """Publishes progress updates to Redis pub/sub."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def publish(
        self,
        backtest_id: str,
        progress: float,
        message: str,
        eta_seconds: int | None = None,
    ) -> None:
        """Publish a progress update."""
        redis = await self._get_redis()
        update = ProgressUpdate(
            backtest_id=backtest_id,
            progress=progress,
            message=message,
            eta_seconds=eta_seconds,
        )
        await redis.publish(
            f"backtest:progress:{backtest_id}",
            json.dumps(update.to_dict()),
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class ProgressSubscriber:
    """Subscribes to progress updates from Redis pub/sub."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def subscribe(self, backtest_id: str) -> AsyncIterator[ProgressUpdate]:
        """Subscribe to progress updates for a backtest.

        Yields ProgressUpdate objects as they come in.
        """
        redis = await self._get_redis()
        self._pubsub = redis.pubsub()
        channel = f"backtest:progress:{backtest_id}"

        await self._pubsub.subscribe(channel)

        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield ProgressUpdate(
                        backtest_id=data["backtest_id"],
                        progress=data["progress"],
                        message=data["message"],
                        eta_seconds=data.get("eta_seconds"),
                        timestamp=data.get("timestamp"),
                    )
                    # Stop if we hit 100%
                    if data["progress"] >= 100:
                        break
        finally:
            await self._pubsub.unsubscribe(channel)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None


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
        self._tracker: ProgressTracker | None = None
        self._pending_updates: list[tuple[float, str, int | None]] = []

    async def publish_phase(
        self,
        message: str,
        progress: float,
        eta_seconds: int | None = None,
    ) -> None:
        """Publish a phase progress update (e.g., 'Loading strategy').

        Args:
            message: Status message.
            progress: Progress percentage (0-100).
            eta_seconds: Optional ETA in seconds.
        """
        await self._publisher.publish(
            self.backtest_id,
            progress,
            message,
            eta_seconds,
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
        """
        # Import here to avoid circular imports
        from datetime import datetime as dt

        def callback(current_bar: int, total_bars: int, current_date: dt) -> None:
            # Update tracker if total changed
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

            # Calculate ETA
            eta = self._tracker.calculate_eta(current_bar)

            # Format message with current date
            date_str = current_date.strftime("%Y-%m-%d")
            message = f"Processing {date_str} ({current_bar}/{total_bars})"

            # Queue update for async publishing
            self._pending_updates.append((progress, message, eta))

        return callback

    async def flush(self) -> None:
        """Publish all pending progress updates."""
        for progress, message, eta in self._pending_updates:
            await self._publisher.publish(self.backtest_id, progress, message, eta)
        self._pending_updates.clear()

    async def close(self) -> None:
        """Close the publisher connection."""
        await self._publisher.close()
