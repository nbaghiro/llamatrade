"""Backtest service - manages backtest runs with database persistence."""

import logging
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast
from uuid import UUID

if TYPE_CHECKING:
    from llamatrade_proto import MarketDataClient

from fastapi import Depends
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from llamatrade_events.catalog.notifications import NotificationEvent, shared_notification_events
from llamatrade_proto.generated import common_pb2, events_pb2
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_PAUSED,
    StrategyStatus,
)
from llamatrade_runtime import (
    Bar,
    HistoricalBarFeed,
    NullObserver,
    Portfolio,
    RuntimeCancelled,
    SimulatedExecution,
    SizingMode,
    StrategyRuntime,
    StrategySession,
    build_session,
)
from llamatrade_runtime.metrics import resample_daily
from llamatrade_telemetry import counter, metrics

from src.convert import safe_float
from src.dataset import DatasetSpec, DatasetStore, RedisLike, get_dataset_store, prepare_dataset
from src.engine.bars import BarData
from src.engine.benchmarks import BenchmarkBarData, BenchmarkCalculator, align_daily_returns
from src.engine.validation import log_validation_result, validate_bars
from src.models import VALID_TIMEFRAMES
from src.progress import BacktestProgressReporter, CancellationFlag

MARKET_DATA_GRPC_TARGET = os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")
# Max bars per symbol requested in the single batched GetMultiBars call.
# Set well above realistic backtest windows; the server applies its own cap too.
MARKET_DATA_MAX_BARS_PER_SYMBOL = int(os.getenv("BACKTEST_MAX_BARS_PER_SYMBOL", "100000"))

# Max page size accepted by GetBacktestTrades; larger requests are clamped.
MAX_TRADES_PAGE_SIZE = int(os.getenv("BACKTEST_MAX_TRADES_PAGE_SIZE", "200"))

# --- Reaper thresholds ---------------------------------------------------
# A RUNNING row whose worker was lost (OOM, eviction, hard kill) never runs the
# run_backtest except handlers, so it is stranded forever. We only reap RUNNING
# rows whose started_at predates the hard time limit by a safe grace, so a
# legitimately long (but still alive) run is never reaped — Celery would have
# killed it at the hard limit anyway.
_TASK_TIME_LIMIT_SECONDS = int(os.getenv("BACKTEST_TASK_TIME_LIMIT", "3600"))
_REAPER_RUNNING_GRACE_SECONDS = int(os.getenv("BACKTEST_REAPER_RUNNING_GRACE", "300"))
# A PENDING row older than this (but younger than the fail threshold) is assumed
# to have lost its enqueue and is re-driven; older than the fail threshold it is
# failed as "never picked up".
_REAPER_PENDING_REQUEUE_SECONDS = int(os.getenv("BACKTEST_REAPER_PENDING_REQUEUE", "300"))
_REAPER_PENDING_FAIL_SECONDS = int(os.getenv("BACKTEST_REAPER_PENDING_FAIL", "3600"))

# Session health counters. The result row has no column for either, so a finished run
# reports them here and on its completion log line.
DEGRADED_EVALS_TOTAL = counter(
    "llamatrade_backtest_strategy_degraded_evals_total",
    (),
    "Strategy conditions a run could not evaluate (NaN/missing data) and treated as False",
)
SUB_NOTIONAL_SKIPS_TOTAL = counter(
    "llamatrade_backtest_strategy_sub_notional_skips_total",
    (),
    "Intended orders a run skipped for falling under the minimum order notional",
)

logger = logging.getLogger(__name__)


async def notify_backtest_terminal(backtest: Backtest, *, failed: bool, reason: str = "") -> None:
    """Publish the terminal-state notification for a run (fire-and-forget)."""
    category = (
        events_pb2.NOTIFICATION_CATEGORY_BACKTEST_FAILED
        if failed
        else events_pb2.NOTIFICATION_CATEGORY_BACKTEST_COMPLETED
    )
    await shared_notification_events().publish_safe(
        NotificationEvent(category=category, backtest_id=str(backtest.id), reason=reason),
        tenant_id=str(backtest.tenant_id),
        user_id=str(backtest.created_by) if backtest.created_by else "",
        dedup_parts=(str(backtest.id), "failed" if failed else "completed"),
    )


class MarketDataError(Exception):
    """Error fetching market data."""

    pass


# Approximate regular-session bars per trading day for intraday timeframes
_BARS_PER_TRADING_DAY: dict[str, int] = {
    "1Min": 390,
    "5Min": 78,
    "15Min": 26,
    "30Min": 13,
    "1H": 7,
    "1Hour": 7,
    "4H": 2,
}


# Stored equity curves are daily-resampled; this cap is a backstop against
# pathological row sizes (e.g. decade-long backtests)
_MAX_STORED_EQUITY_POINTS = 5000


def _cap_equity_curve(
    curve: list[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """Downsample a curve by even stride if it exceeds the storage cap.

    The final point is always preserved so total return stays exact.
    """
    if len(curve) <= _MAX_STORED_EQUITY_POINTS:
        return curve

    stride = -(-len(curve) // _MAX_STORED_EQUITY_POINTS)  # ceil division
    sampled = curve[::stride]
    if sampled[-1] != curve[-1]:
        sampled.append(curve[-1])
    return sampled


def _to_compiler_bars(bars: dict[str, list[BarData]]) -> dict[str, list[Bar]]:
    """Convert fetched OHLCV dicts to compiler bars for the runtime feed."""
    return {
        symbol: [
            Bar(
                timestamp=b["timestamp"],
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                volume=b["volume"],
            )
            for b in series
        ]
        for symbol, series in bars.items()
    }


def _report_session_health(backtest_id: UUID, session: StrategySession) -> None:
    """Surface a finished run's degraded evaluations and sub-notional skips.

    Both are silent inside the engine: conditions that could not be evaluated turn into
    "no signal" and orders under the notional floor disappear, so a run that traded far
    less than expected looks like a strategy decision. The counts have nowhere to live on
    the result row, so they go to the log line (with the run id) and to fleet counters.
    """
    degraded = session.degraded_eval_count
    skipped = session.sub_notional_skip_count
    DEGRADED_EVALS_TOTAL.inc(degraded)
    SUB_NOTIONAL_SKIPS_TOTAL.inc(skipped)
    log = logger.warning if degraded or skipped else logger.info
    log(
        "Backtest %s finished: degraded_evals=%d sub_notional_skips=%d",
        backtest_id,
        degraded,
        skipped,
    )


class _RuntimeProgressObserver(NullObserver):
    """Bridge runtime tick events to the buffered progress reporter."""

    def __init__(self, reporter: BacktestProgressReporter) -> None:
        self._on_bar = reporter.create_engine_callback()

    def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
        self._on_bar(index, total or 0, date)


# Trailing window (days) that market-data re-pulls each night for corporate actions.
# A dataset ending inside it can be silently restated, so its snapshot is versioned.
_DATASET_VINTAGE_WINDOW_DAYS = int(os.getenv("BACKTEST_DATASET_VINTAGE_WINDOW_DAYS", "10"))


def _last_closed_session(now: datetime) -> date:
    """Most recent session known fully closed (conservative: the prior UTC day).

    Clamps a dataset's ``end`` so the currently-forming bar is never snapshotted as a
    close and reused by a later run. A market calendar would be tighter, but "yesterday
    UTC" is safe for daily bars and never includes today's partial bar.
    """
    return (now - timedelta(days=1)).date()


def _dataset_adjustment(timeframe: str) -> str:
    """Price adjustment market-data serves: split-adjusted daily, raw intraday.

    Mirrors the market-data ``adjustment_for`` mapping so the dataset key labels what
    the stored bars actually are, rather than the old always-"raw" default.
    """
    return "split" if timeframe in ("1D", "1d") else "raw"


def _dataset_vintage(
    end: date, now: datetime, window_days: int = _DATASET_VINTAGE_WINDOW_DAYS
) -> str:
    """A cache-busting vintage for datasets that overlap the corporate-action self-heal window.

    Market-data re-pulls a trailing window of adjusted daily bars nightly, rewriting the
    same (symbol, date) with no key change. A dataset whose ``end`` falls in that window can
    be restated, so it is tagged with the materialization date and re-fetched on a later run;
    closed history older than the window keeps a stable key and reuses its warm snapshot.
    """
    if end >= (now - timedelta(days=window_days)).date():
        return now.date().isoformat()
    return ""


class _SizingOverrides(TypedDict, total=False):
    """build_session sizing kwargs; an absent key keeps the engine default."""

    sizing_mode: SizingMode
    drift_tolerance: float
    min_order_notional: float


def _sizing_overrides(config: dict[str, object]) -> _SizingOverrides:
    """Map stored proto sizing config to build_session kwargs; unset fields keep defaults."""
    overrides: _SizingOverrides = {}
    mode = int(cast(int, config.get("sizing_mode", 0)) or 0)
    if mode == common_pb2.SIZING_MODE_BINARY:
        overrides["sizing_mode"] = SizingMode.BINARY
    elif mode == common_pb2.SIZING_MODE_DRIFT:
        overrides["sizing_mode"] = SizingMode.DRIFT
    drift_tolerance = config.get("drift_tolerance")
    if drift_tolerance is not None:
        overrides["drift_tolerance"] = float(cast(float, drift_tolerance))
    min_order_notional = config.get("min_order_notional")
    if min_order_notional is not None:
        overrides["min_order_notional"] = float(cast(float, min_order_notional))
    return overrides


def warmup_padding_days(timeframe: str, min_bars: int) -> int:
    """Calendar days of extra history to fetch so indicators can warm up.

    Converts an indicator lookback (in bars of `timeframe`) to calendar days,
    padding by 1.5x plus a small buffer to absorb weekends, holidays, and
    missing bars.

    Args:
        timeframe: Bar timeframe (e.g. "1D", "1H", "1W")
        min_bars: Minimum number of bars the strategy's indicators need

    Returns:
        Number of calendar days to extend the fetch start back by
    """
    if min_bars <= 0:
        return 0

    if timeframe in ("1W",):
        trading_days_needed = min_bars * 5
    elif timeframe in ("1D", "1d"):
        trading_days_needed = min_bars
    else:
        bars_per_day = _BARS_PER_TRADING_DAY.get(timeframe, 390)
        trading_days_needed = -(-min_bars // bars_per_day)  # ceil division

    # 1.5x for weekends/holidays plus a fixed buffer
    return int(trading_days_needed * 1.5) + 5


class MarketDataFetcher(Protocol):
    """Protocol for market data fetchers."""

    async def fetch_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[dict[str, object]]]:
        """Fetch historical bars for symbols."""
        ...

    async def close(self) -> None:
        """Close the client. Optional for implementations."""
        ...


def get_market_data_client() -> MarketDataFetcher:
    """Get the market-data client."""
    return ProtoMarketDataClient(MARKET_DATA_GRPC_TARGET)


class ProtoMarketDataClient:
    """Market-data client (over the Connect transport)."""

    def __init__(self, target: str = "market-data:8840"):
        self._target = target
        self._client = None

    async def _get_client(self) -> MarketDataClient:
        """Lazy initialization of the underlying client."""
        if self._client is None:
            from llamatrade_proto import MarketDataClient

            self._client = MarketDataClient(self._target)
        return self._client

    async def fetch_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[dict[str, object]]]:
        """Fetch historical bars for all symbols in a single batched RPC.

        The market-data service fans out across symbols server-side, so one
        ``GetMultiBars`` call replaces N per-symbol round-trips. A symbol with no
        data maps to an empty list; the run path surfaces truly-missing data.

        Raises:
            MarketDataError: If the timeframe is unsupported or the fetch fails.
        """
        from datetime import datetime

        # Convert timeframe to the market-data request format. Unknown timeframes are an error —
        # silently falling back to daily would produce a plausible-looking but
        # wrong backtest.
        tf_map = {
            "1D": "1DAY",
            "1d": "1DAY",
            "1Min": "1MIN",
            "5Min": "5MIN",
            "15Min": "15MIN",
            "30Min": "30MIN",
            "1H": "1HOUR",
            "1Hour": "1HOUR",
            "4H": "4HOUR",
            "1W": "1WEEK",
        }
        grpc_timeframe = tf_map.get(timeframe)
        if grpc_timeframe is None:
            raise MarketDataError(
                f"Unsupported timeframe '{timeframe}'. Must be one of: {', '.join(sorted(tf_map))}"
            )

        # Pre-seed every requested symbol so absent ones map to an empty list;
        # the run path surfaces truly-missing data.
        result: dict[str, list[dict[str, object]]] = {symbol: [] for symbol in symbols}
        requested = set(symbols)

        try:
            client = await self._get_client()
            # Consume the server-streamed bars incrementally: each bar is
            # converted and appended, so we never buffer the whole response as a
            # single list before building the engine's input. The stream arrives
            # in timestamp order, so each symbol's list stays chronological.
            async for bar in client.stream_historical_bars(
                symbols=symbols,
                start=datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC),
                end=datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC),
                timeframe=grpc_timeframe,
                limit=MARKET_DATA_MAX_BARS_PER_SYMBOL,
            ):
                if bar.symbol not in requested:
                    continue
                result[bar.symbol].append(
                    {
                        # Normalize to tz-aware UTC so comparisons with the
                        # backtest window are well-defined
                        "timestamp": bar.timestamp
                        if bar.timestamp.tzinfo is not None
                        else bar.timestamp.replace(tzinfo=UTC),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": bar.volume,
                    }
                )
        except Exception as e:
            raise MarketDataError(f"Failed to fetch bars: {e}") from e

        return result

    async def close(self) -> None:
        """Close the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None


class BacktestService:
    """Service for managing backtest runs.

    This service manages backtest execution and requires proper cleanup.
    Use as an async context manager to ensure resources are released:

        async with BacktestService(db) as service:
            backtest = await service.create_backtest(...)

    Or call close() explicitly when done:

        service = BacktestService(db)
        try:
            backtest = await service.create_backtest(...)
        finally:
            await service.close()
    """

    def __init__(
        self,
        db: AsyncSession,
        market_data_client: MarketDataFetcher | None = None,
        dataset_store: DatasetStore | None = None,
        redis: RedisLike | None = None,
    ):
        self.db = db
        self.market_data_client = market_data_client or get_market_data_client()
        # Track if we own the client (created it ourselves) vs received it
        self._owns_market_data_client = market_data_client is None
        # Dataset snapshot store + optional Redis for cross-worker prepare coalescing.
        self._dataset_store = dataset_store or get_dataset_store()
        self._redis = redis

    async def _fetch_bars(
        self, symbols: list[str], timeframe: str, start: date, end: date
    ) -> dict[str, list[BarData]]:
        """Fetcher adapter for prepare_dataset → the market-data service."""
        return cast(
            dict[str, list[BarData]],
            await self.market_data_client.fetch_bars(
                symbols=symbols, timeframe=timeframe, start_date=start, end_date=end
            ),
        )

    async def close(self) -> None:
        """Clean up resources.

        Closes the market data client if we own it.
        Should be called when done using the service.
        """
        if self._owns_market_data_client and hasattr(self.market_data_client, "close"):
            await self.market_data_client.close()

    async def __aenter__(self) -> BacktestService:
        """Enter async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context, cleaning up resources."""
        await self.close()

    async def create_backtest(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int | None,
        name: str,
        start_date: date,
        end_date: date,
        initial_capital: float,
        symbols: list[str] | None,
        commission: float,
        slippage: float,
        timeframe: str | None = None,
        benchmark_symbol: str | None = "SPY",
        include_benchmark: bool = True,
        sizing_mode: int = 0,
        drift_tolerance: float | None = None,
        min_order_notional: float | None = None,
    ) -> Backtest:
        """Create a new backtest job.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            strategy_id: Strategy ID
            strategy_version: Strategy version (uses current if None)
            name: Backtest name
            start_date: Start date
            end_date: End date
            initial_capital: Initial capital
            symbols: Symbols to trade (uses strategy symbols if None)
            commission: Commission per trade
            slippage: Slippage percentage
            timeframe: Data timeframe (uses strategy timeframe if None)
            benchmark_symbol: Symbol for benchmark comparison (default: SPY)
            include_benchmark: Whether to calculate benchmark comparison
            sizing_mode: SizingMode proto value (0 = unset, keeps engine default)
            drift_tolerance: DRIFT-mode band (None keeps engine default)
            min_order_notional: dollar floor under which an order is skipped (None keeps default)
        """
        if end_date <= start_date:
            raise ValueError("End date must be after start date")

        if drift_tolerance is not None and drift_tolerance < 0:
            raise ValueError("drift_tolerance must be non-negative")
        if min_order_notional is not None and min_order_notional < 0:
            raise ValueError("min_order_notional must be non-negative")

        # Validate timeframe if provided
        if timeframe and timeframe not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"
            )

        # Verify strategy exists and belongs to tenant
        strategy = await self._get_strategy(tenant_id, strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Verify strategy is in a runnable state (not DRAFT or ARCHIVED)
        if strategy.status not in (STRATEGY_STATUS_ACTIVE, STRATEGY_STATUS_PAUSED):
            status_name = StrategyStatus.Name(strategy.status)
            raise ValueError(
                f"Cannot backtest strategy with status {status_name}. "
                "Strategy must be ACTIVE or PAUSED."
            )

        # Use current version if not specified
        version = strategy_version or strategy.current_version

        # Verify version exists
        strategy_ver = await self._get_strategy_version(strategy_id, version)
        if not strategy_ver:
            raise ValueError(f"Strategy version {version} not found")

        # Use symbols from strategy if not provided
        actual_symbols = symbols or strategy_ver.symbols or []
        if not actual_symbols:
            raise ValueError("No symbols specified")

        # Backtest bar granularity is a run parameter: explicit request value, else daily.
        actual_timeframe = timeframe or "1D"

        backtest = Backtest(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            strategy_version=version,
            name=name,
            status=BACKTEST_STATUS_PENDING,
            config={
                "commission": commission,
                "slippage": slippage,
                "timeframe": actual_timeframe,
                "benchmark_symbol": benchmark_symbol,
                "include_benchmark": include_benchmark,
                # Sizing overrides (unset keys fall back to engine defaults at run time).
                "sizing_mode": sizing_mode,
                "drift_tolerance": drift_tolerance,
                "min_order_notional": min_order_notional,
            },
            symbols=actual_symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(initial_capital)),
            created_by=user_id,
        )
        self.db.add(backtest)
        await self.db.commit()
        await self.db.refresh(backtest)

        return backtest

    async def get_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> Backtest | None:
        """Get backtest by ID."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        return backtest if backtest else None

    async def list_backtests(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        status: int | None = None,  # BacktestStatus proto value
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Backtest], int]:
        """List backtests for tenant."""
        stmt = select(Backtest).where(Backtest.tenant_id == tenant_id)

        if strategy_id:
            stmt = stmt.where(Backtest.strategy_id == strategy_id)
        if status is not None:
            stmt = stmt.where(Backtest.status == status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginate
        stmt = stmt.order_by(Backtest.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        backtests = result.scalars().all()

        return list(backtests), total

    async def get_result_rows(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> tuple[Backtest, BacktestResult] | None:
        """Return the persisted backtest + result rows (mapped to proto by the servicer)."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            return None

        stmt = select(BacktestResult).where(BacktestResult.backtest_id == backtest_id)
        result = await self.db.execute(stmt)
        backtest_result = result.scalar_one_or_none()
        if not backtest_result:
            return None

        return backtest, backtest_result

    async def get_backtest_trades(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, object]], int]:
        """Return one page of a completed backtest's raw trade records plus the total.

        Tenant-scoped via ``get_result_rows``. Pagination bounds the response size
        so a pathological trade count never bloats a single read. Raw trade
        dicts are mapped to proto by the servicer.
        """
        rows = await self.get_result_rows(backtest_id, tenant_id)
        if rows is None:
            return [], 0
        _, result = rows

        raw_trades = cast(list[dict[str, object]], result.trades or [])
        page = max(1, page)
        page_size = max(1, min(page_size, MAX_TRADES_PAGE_SIZE))
        start = (page - 1) * page_size
        total = len(raw_trades)
        return raw_trades[start : start + page_size], total

    async def run_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
        publish_progress: bool = True,
    ) -> BacktestResult:
        """Execute a pending backtest.

        Args:
            backtest_id: ID of the backtest to run.
            tenant_id: Tenant ID for isolation.
            publish_progress: Whether to publish progress updates to Redis.

        Returns:
            The persisted BacktestResult row.
        """
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != BACKTEST_STATUS_PENDING:
            raise ValueError(f"Backtest is {backtest.status}, cannot run")

        # Extract config - cast since JSONB returns untyped dict
        config = cast(dict[str, object], backtest.config)
        timeframe = str(config.get("timeframe", "1D"))
        benchmark_symbol_val = config.get("benchmark_symbol", "SPY")
        benchmark_symbol = str(benchmark_symbol_val) if benchmark_symbol_val else None
        include_benchmark = bool(config.get("include_benchmark", True))

        # Initialize progress reporter
        reporter: BacktestProgressReporter | None = None
        if publish_progress:
            reporter = BacktestProgressReporter(str(backtest_id))
            await reporter.publish_phase("Starting backtest", 0, status=BACKTEST_STATUS_RUNNING)

        # Update status to running
        backtest.status = BACKTEST_STATUS_RUNNING
        backtest.started_at = datetime.now(UTC)
        await self.db.commit()
        metrics.backtest.job(state="running")

        try:
            with metrics.backtest.execution_duration.time():
                return await self._run_backtest_inner(
                    backtest=backtest,
                    backtest_id=backtest_id,
                    reporter=reporter,
                    timeframe=timeframe,
                    benchmark_symbol=benchmark_symbol,
                    include_benchmark=include_benchmark,
                    config=config,
                )

        except RuntimeCancelled:
            metrics.backtest.job(state="cancelled")
            backtest.status = BACKTEST_STATUS_CANCELLED
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            if reporter:
                await reporter.publish_phase("Cancelled", 100, status=BACKTEST_STATUS_CANCELLED)
                await reporter.close()
            raise

        except MarketDataError as e:
            metrics.backtest.fetch_failure()
            metrics.backtest.job(state="failed")
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = f"Market data error: {e}"
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            if reporter:
                await reporter.publish_phase(f"Failed: {e}", 100, status=BACKTEST_STATUS_FAILED)
                await reporter.close()
            await notify_backtest_terminal(backtest, failed=True, reason=f"market data error: {e}")
            # Propagate typed so the Celery task can distinguish transient
            # market-data failures (retryable) from terminal errors
            raise

        except Exception as e:
            metrics.backtest.job(state="failed")
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = str(e)
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            if reporter:
                await reporter.publish_phase(f"Failed: {e}", 100, status=BACKTEST_STATUS_FAILED)
                await reporter.close()
            await notify_backtest_terminal(backtest, failed=True, reason=str(e))
            raise

    async def _run_backtest_inner(
        self,
        *,
        backtest: Backtest,
        backtest_id: UUID,
        reporter: BacktestProgressReporter | None,
        timeframe: str,
        benchmark_symbol: str | None,
        include_benchmark: bool,
        config: dict[str, object],
    ) -> BacktestResult:
        """Run the backtest simulation and persist results.

        Extracted from ``run_backtest`` so the wall-clock timer and terminal
        state-transition handling wrap a single call. Raises the same typed
        exceptions (``RuntimeCancelled``, ``MarketDataError``) the caller maps
        to backtest status.
        """
        # Get strategy version
        if reporter:
            await reporter.publish_phase("Loading strategy", 10)

        strategy_ver = await self._get_strategy_version(
            backtest.strategy_id, backtest.strategy_version
        )
        if not strategy_ver:
            raise ValueError("Strategy version not found")

        # Get S-expression config
        config_sexpr = strategy_ver.config_sexpr
        if not config_sexpr:
            raise ValueError("Strategy has no S-expression config")

        # Build the shared strategy session (multi-symbol: all bars per date at once).
        # Sizing overrides ride in the stored config; unset fields keep engine defaults.
        session, required_symbols, min_bars = build_session(
            config_sexpr, **_sizing_overrides(config)
        )

        if reporter:
            await reporter.publish_phase("Strategy compiled", 20)

        # Fetch historical bars using timeframe from config.
        # - includes indicator-only symbols the strategy references
        #   (e.g. RSI(SPY) while trading TLT)
        # - includes the benchmark symbol to avoid a duplicate API call
        # - extends the start back so indicators are warm on day one
        if reporter:
            await reporter.publish_phase("Fetching market data", 30)

        # Cast symbols since JSONB returns untyped list
        symbols_list: list[str] = backtest.symbols
        strategy_symbols = list(dict.fromkeys([*symbols_list, *sorted(required_symbols)]))
        symbols_to_fetch = list(strategy_symbols)
        if include_benchmark and benchmark_symbol and benchmark_symbol not in symbols_to_fetch:
            symbols_to_fetch.append(benchmark_symbol)

        padding_days = warmup_padding_days(timeframe, min_bars)
        fetch_start = backtest.start_date - timedelta(days=padding_days)

        # Clamp the fetch end to the last closed session so a forming bar is never
        # snapshotted as a close; label the real adjustment and add a vintage so a
        # corporate-action restatement cannot be served stale from the cache.
        now = datetime.now(UTC)
        dataset_end = min(backtest.end_date, _last_closed_session(now))

        # Materialize a complete, content-addressed snapshot (coalescing concurrent runs over
        # overlapping assets), then the sim reads pure warm data — no Alpaca in the loop.
        dataset_spec = DatasetSpec.create(
            symbols_to_fetch,
            timeframe,
            fetch_start,
            dataset_end,
            adjustment=_dataset_adjustment(timeframe),
            data_version=_dataset_vintage(dataset_end, now),
        )
        all_bars = await prepare_dataset(
            dataset_spec, self._fetch_bars, self._dataset_store, self._redis
        )

        if not all_bars:
            raise ValueError("No market data available for specified period")

        # Symbols the strategy needs must have data; a missing benchmark
        # only disables the benchmark comparison.
        missing_symbols = [s for s in strategy_symbols if not all_bars.get(s)]
        if missing_symbols:
            raise ValueError(f"No market data available for symbols: {', '.join(missing_symbols)}")

        # Separate strategy bars from benchmark bars
        # Cast to BarData since market_data_client returns properly structured dicts
        bars: dict[str, list[BarData]] = {s: all_bars[s] for s in strategy_symbols if s in all_bars}

        # Validate OHLCV data before simulating: errors abort the run,
        # warnings (gaps, suspected splits) are logged.
        validation = validate_bars(bars)
        log_validation_result(validation)
        if not validation.valid:
            raise ValueError(f"Market data validation failed: {validation.summary()}")

        # Calculate total bars for progress tracking
        total_bars = sum(len(symbol_bars) for symbol_bars in bars.values())
        if reporter:
            reporter.set_total_bars(total_bars)
            await reporter.publish_phase("Running simulation", 40)

        # Convert to the runtime's Bar representation once, extract the windowed
        # benchmark bars the post-sim comparison needs, then drop the dict dataset so
        # the heavy simulation phase holds a single copy of the strategy bars rather
        # than the BarData dicts and the Bar objects at the same time.
        compiler_bars = _to_compiler_bars(bars)
        window_start = datetime.combine(backtest.start_date, datetime.min.time(), tzinfo=UTC)
        benchmark_bars_list: list[BarData] = []
        if include_benchmark and benchmark_symbol:
            benchmark_bars_list = [
                b for b in all_bars.get(benchmark_symbol, []) if b["timestamp"] >= window_start
            ]
        del all_bars, bars

        portfolio = Portfolio(float(backtest.initial_capital))
        execution = SimulatedExecution(
            commission_rate=safe_float(config.get("commission", 0)),
            slippage_rate=safe_float(config.get("slippage", 0)),
        )

        # Bridge runtime lifecycle events to the buffered progress reporter.
        observer = _RuntimeProgressObserver(reporter) if reporter else None

        # Cooperative cancellation: CancelBacktest sets a Redis flag the runtime
        # polls between trading dates (fails open if Redis is unreachable).
        should_abort = CancellationFlag().make_should_abort(str(backtest_id))

        runtime = StrategyRuntime(session, portfolio, execution, observer=observer)
        result = await runtime.run(
            HistoricalBarFeed(
                compiler_bars,
                window_start,
                datetime.combine(backtest.end_date, datetime.max.time(), tzinfo=UTC),
            ),
            should_abort=should_abort,
        )

        _report_session_health(backtest_id, session)

        # Flush pending progress updates
        if reporter:
            await reporter.flush()
            await reporter.publish_phase("Calculating metrics", 85)

        # Benchmark comparison values. None means "not available" —
        # a computed 0.0 is a legitimate value and must be stored as 0.0.
        benchmark_return_val: float | None = None
        benchmark_equity_curve: list[dict[str, object]] = []
        alpha_val: float | None = None
        beta_val: float | None = None
        information_ratio_val: float | None = None

        if include_benchmark and benchmark_symbol:
            if reporter:
                await reporter.publish_phase("Calculating benchmark comparison", 90)

            try:
                # Benchmark bars were pulled in the combined fetch (no duplicate API
                # call) and windowed to the backtest range above, before the dict
                # dataset was released.
                if benchmark_bars_list:
                    # Convert to BenchmarkBarData format
                    benchmark_bars: list[BenchmarkBarData] = []
                    for b in benchmark_bars_list:
                        benchmark_bars.append(
                            {
                                "timestamp": b["timestamp"],
                                "close": safe_float(b["close"]),
                            }
                        )

                    # Calculate buy & hold return and equity curve
                    calculator = BenchmarkCalculator()
                    benchmark_return_val, benchmark_ec = calculator.calculate_spy_buy_hold(
                        benchmark_bars, float(backtest.initial_capital)
                    )

                    # Store the benchmark curve on the daily grid, matching
                    # the strategy equity curve resolution
                    benchmark_equity_curve = [
                        {"date": dt.isoformat(), "equity": eq}
                        for dt, eq in resample_daily(benchmark_ec)
                    ]

                    # Alpha, beta, information ratio on DATE-JOINED daily
                    # returns — positional alignment skews these whenever
                    # either series is missing a date
                    strategy_returns, benchmark_returns = align_daily_returns(
                        result.daily_equity_curve, benchmark_bars
                    )
                    if len(strategy_returns) > 1:
                        alpha_val, beta_val = calculator.calculate_alpha_beta(
                            strategy_returns, benchmark_returns
                        )
                        information_ratio_val = calculator.calculate_information_ratio(
                            strategy_returns, benchmark_returns
                        )

            except MarketDataError:
                # Benchmark data unavailable - continue without it
                pass

        if reporter:
            await reporter.publish_phase("Saving results", 95)

        # Guard the terminal write: if the row was cancelled while the
        # simulation was finishing, keep CANCELLED and discard the result
        await self.db.refresh(backtest)
        if backtest.status == BACKTEST_STATUS_CANCELLED:
            raise RuntimeCancelled("Backtest was cancelled during execution")

        # Save results with benchmark data
        backtest_result = BacktestResult(
            backtest_id=backtest.id,
            total_return=Decimal(str(result.total_return)),
            annual_return=Decimal(str(result.annual_return)),
            sharpe_ratio=Decimal(str(result.sharpe_ratio)),
            sortino_ratio=Decimal(str(result.sortino_ratio)),
            max_drawdown=Decimal(str(result.max_drawdown)),
            max_drawdown_duration=result.max_drawdown_duration,
            win_rate=Decimal(str(result.win_rate)),
            profit_factor=Decimal(str(result.profit_factor))
            if result.profit_factor is not None
            else None,
            total_trades=len(result.trades),
            winning_trades=len([t for t in result.trades if t.pnl > 0]),
            losing_trades=len([t for t in result.trades if t.pnl <= 0]),
            avg_trade_return=Decimal(
                str(
                    sum(t.pnl_percent for t in result.trades) / len(result.trades)
                    if result.trades
                    else 0
                )
            ),
            final_equity=Decimal(str(result.final_equity)),
            exposure_time=Decimal(str(result.exposure_time)),
            equity_curve=[
                {"date": ec[0].isoformat(), "equity": ec[1]}
                for ec in _cap_equity_curve(result.daily_equity_curve)
            ],
            trades=[
                {
                    "entry_date": t.entry_date.isoformat(),
                    "exit_date": t.exit_date.isoformat(),
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "pnl": t.pnl,
                    "pnl_percent": t.pnl_percent,
                    "commission": t.commission,
                }
                for t in result.trades
            ],
            daily_returns=result.daily_returns,
            monthly_returns=result.monthly_returns,
            # Benchmark comparison data: NULL only when unavailable
            benchmark_return=Decimal(str(benchmark_return_val))
            if benchmark_return_val is not None
            else None,
            benchmark_symbol=benchmark_symbol if include_benchmark else None,
            alpha=Decimal(str(alpha_val)) if alpha_val is not None else None,
            beta=Decimal(str(beta_val)) if beta_val is not None else None,
            information_ratio=Decimal(str(information_ratio_val))
            if information_ratio_val is not None
            else None,
            benchmark_equity_curve=benchmark_equity_curve if benchmark_equity_curve else None,
        )
        self.db.add(backtest_result)

        # Finalize atomically: only complete if the row is still RUNNING.
        # A CancelBacktest that committed CANCELLED between the refresh above and
        # here would otherwise be clobbered by an unconditional COMPLETED write.
        completed_at = datetime.now(UTC)
        finalize = cast(
            CursorResult[Any],
            await self.db.execute(
                update(Backtest)
                .where(
                    Backtest.id == backtest.id,
                    Backtest.status == BACKTEST_STATUS_RUNNING,
                )
                .values(status=BACKTEST_STATUS_COMPLETED, completed_at=completed_at)
            ),
        )
        if finalize.rowcount == 0:
            # Lost the race to a concurrent cancel — discard the result.
            await self.db.rollback()
            raise RuntimeCancelled("Backtest was cancelled during execution")
        await self.db.commit()
        await self.db.refresh(backtest)
        await self.db.refresh(backtest_result)

        # Publish completion
        if reporter:
            await reporter.publish_phase("Completed", 100, status=BACKTEST_STATUS_COMPLETED)
            await reporter.close()

        metrics.backtest.job(state="completed")
        await notify_backtest_terminal(backtest, failed=False)

        return backtest_result

    async def cancel_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Cancel a pending or running backtest."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            return False

        if backtest.status not in (BACKTEST_STATUS_PENDING, BACKTEST_STATUS_RUNNING):
            return False

        backtest.status = BACKTEST_STATUS_CANCELLED
        backtest.completed_at = datetime.now(UTC)
        await self.db.commit()
        metrics.backtest.job(state="cancelled")

        # Signal the (possibly running) worker to abort cooperatively. Redis
        # being down only delays the stop until the run finishes — the DB
        # status above already prevents a COMPLETED overwrite.
        try:
            await CancellationFlag().request_cancel(str(backtest_id))
        except Exception:
            logger.warning(
                "Could not set cancellation flag for backtest %s", backtest_id, exc_info=True
            )

        return True

    async def retry_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> Backtest | None:
        """Retry a failed backtest."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            return None

        if backtest.status != BACKTEST_STATUS_FAILED:
            raise ValueError("Only failed backtests can be retried")

        backtest.status = BACKTEST_STATUS_PENDING
        backtest.error_message = None
        backtest.started_at = None
        backtest.completed_at = None
        await self.db.commit()
        await self.db.refresh(backtest)

        return backtest

    async def queue_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> str:
        """Queue a backtest for async execution via Celery.

        Returns:
            Celery task ID
        """
        # Import inline to avoid circular imports; celery types are incomplete.
        from src.workers import celery_tasks

        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != BACKTEST_STATUS_PENDING:
            raise ValueError(f"Backtest is {backtest.status}, cannot queue")

        # The task is bound to the redis-configured ``celery_app`` (@celery_app.task),
        # so ``.delay()`` routes to our broker in the API process too — not Celery's
        # default app — and still honours eager mode under test.
        run_task = getattr(celery_tasks, "run_backtest_task")
        task = run_task.delay(str(backtest_id), str(tenant_id))
        metrics.backtest.job(state="enqueued")
        return str(task.id)

    async def fail_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
        error_message: str,
    ) -> bool:
        """Mark a backtest FAILED.

        Compensating action: ``create_backtest`` commits the PENDING row
        before the Celery enqueue, so a failed enqueue would strand a zombie
        PENDING row. Failing it here keeps the DB state consistent with the
        error the caller receives.
        """
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            return False
        backtest.status = BACKTEST_STATUS_FAILED
        backtest.error_message = error_message
        backtest.completed_at = datetime.now(UTC)
        await self.db.commit()
        metrics.backtest.job(state="failed")
        return True

    async def get_task_status(self, task_id: str) -> dict[str, object]:
        """Get the status of a Celery task.

        Returns:
            Dictionary with task status and result
        """
        from src.celery_app import celery_app

        # Celery types are incomplete
        result = celery_app.AsyncResult(task_id)
        status: str = str(result.status)
        is_ready: bool = bool(result.ready())
        return {
            "task_id": task_id,
            "status": status,
            "result": result.result if is_ready else None,
        }

    async def reap_stale_backtests(self, now: datetime | None = None) -> dict[str, int]:
        """Recover orphaned backtests; the only automatic recovery path.

        - **Stale RUNNING** (started_at older than the hard time limit + grace):
          the worker was lost before its except handlers could run, so the row
          is stranded. Fail it as worker-lost.
        - **Stale PENDING** in the requeue window: the enqueue was likely lost;
          re-drive it. (A duplicate run is harmless — the one-result-per-backtest
          unique constraint rejects a second result row.)
        - **Stale PENDING** past the fail threshold: never picked up; fail it.

        Args:
            now: Override for the current time (testing/time-travel). Defaults to
                ``datetime.now(UTC)``.

        Returns:
            Counts: ``running_failed`` / ``pending_requeued`` / ``pending_failed``.
        """
        now = now or datetime.now(UTC)
        running_cutoff = now - timedelta(
            seconds=_TASK_TIME_LIMIT_SECONDS + _REAPER_RUNNING_GRACE_SECONDS
        )
        requeue_cutoff = now - timedelta(seconds=_REAPER_PENDING_REQUEUE_SECONDS)
        fail_cutoff = now - timedelta(seconds=_REAPER_PENDING_FAIL_SECONDS)

        counts = {"running_failed": 0, "pending_requeued": 0, "pending_failed": 0}

        # 1) Orphaned RUNNING -> FAILED (worker lost).
        running_rows = (
            (
                await self.db.execute(
                    select(Backtest).where(
                        Backtest.status == BACKTEST_STATUS_RUNNING,
                        Backtest.started_at.is_not(None),
                        Backtest.started_at < running_cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        for bt in running_rows:
            bt.status = BACKTEST_STATUS_FAILED
            bt.error_message = "Backtest worker was lost; run reaped after exceeding the time limit"
            bt.completed_at = now
            counts["running_failed"] += 1
            await notify_backtest_terminal(bt, failed=True, reason=bt.error_message or "")

        # 2) Orphaned PENDING -> re-drive (requeue window) or FAIL (too old).
        pending_rows = (
            (
                await self.db.execute(
                    select(Backtest).where(
                        Backtest.status == BACKTEST_STATUS_PENDING,
                        Backtest.created_at < requeue_cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        to_requeue: list[Backtest] = []
        for bt in pending_rows:
            if bt.created_at < fail_cutoff:
                bt.status = BACKTEST_STATUS_FAILED
                bt.error_message = "Backtest was never picked up by a worker; failed by reaper"
                bt.completed_at = now
                counts["pending_failed"] += 1
                await notify_backtest_terminal(bt, failed=True, reason=bt.error_message or "")
            else:
                to_requeue.append(bt)

        # Durably persist the status writes before re-enqueueing, so a requeued
        # row is never lost if the broker call below fails mid-batch.
        await self.db.commit()

        if to_requeue:
            from src.workers import celery_tasks

            run_task = getattr(celery_tasks, "run_backtest_task")
            for bt in to_requeue:
                run_task.delay(str(bt.id), str(bt.tenant_id))
                counts["pending_requeued"] += 1

        for _ in range(counts["running_failed"] + counts["pending_failed"]):
            metrics.backtest.job(state="failed")
        for _ in range(counts["pending_requeued"]):
            metrics.backtest.job(state="enqueued")

        if any(counts.values()):
            logger.warning("Reaper recovered stale backtests: %s", counts)
        return counts

    # Private helpers

    async def _get_backtest_by_id(self, tenant_id: UUID, backtest_id: UUID) -> Backtest | None:
        """Get backtest ensuring tenant isolation."""
        stmt = (
            select(Backtest)
            .where(Backtest.id == backtest_id)
            .where(Backtest.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_strategy(self, tenant_id: UUID, strategy_id: UUID) -> Strategy | None:
        """Get strategy ensuring tenant isolation."""
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_strategy_version(
        self, strategy_id: UUID, version: int
    ) -> StrategyVersion | None:
        """Get a specific strategy version."""
        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


async def get_backtest_service(
    db: AsyncSession = Depends(get_db),
) -> BacktestService:
    """Dependency to get backtest service."""
    return BacktestService(db)
