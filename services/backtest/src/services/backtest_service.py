"""Backtest service - manages backtest runs with database persistence."""

import asyncio
import logging
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

if TYPE_CHECKING:
    from llamatrade_proto import MarketDataClient

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    BacktestStatus,
)
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_PAUSED,
    StrategyStatus,
)
from llamatrade_telemetry import metrics

from src.convert import safe_float
from src.engine.backtester import BacktestCancelled, BacktestConfig, BacktestEngine
from src.engine.benchmarks import BenchmarkBarData, BenchmarkCalculator, align_daily_returns
from src.engine.metrics import resample_daily
from src.engine.strategy_adapter import create_multi_symbol_strategy
from src.engine.validation import BarDataDict, log_validation_result, validate_bars
from src.models import (
    VALID_TIMEFRAMES,
    BacktestMetrics,
    BacktestResponse,
    BacktestResultResponse,
    BenchmarkEquityPoint,
    EquityPoint,
    TradeRecord,
)
from src.progress import BacktestProgressReporter, CancellationFlag

# Status string to proto int mapping
_STATUS_STR_TO_PROTO: dict[str, int] = {
    "pending": BACKTEST_STATUS_PENDING,
    "running": BACKTEST_STATUS_RUNNING,
    "completed": BACKTEST_STATUS_COMPLETED,
    "failed": BACKTEST_STATUS_FAILED,
    "cancelled": BACKTEST_STATUS_CANCELLED,
}


def _normalize_status(status: str | int) -> BacktestStatus.ValueType:
    """Convert status string or int to proto ValueType."""
    if isinstance(status, int):
        return cast(BacktestStatus.ValueType, status)
    result = _STATUS_STR_TO_PROTO.get(status.lower())
    return cast(BacktestStatus.ValueType, result if result is not None else BACKTEST_STATUS_PENDING)


MARKET_DATA_GRPC_TARGET = os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")
# Concurrent per-symbol fetches against market-data; capped so a large
# universe doesn't stampede the service (and Alpaca's rate limiter behind it)
MARKET_DATA_FETCH_CONCURRENCY = int(os.getenv("MARKET_DATA_FETCH_CONCURRENCY", "6"))

logger = logging.getLogger(__name__)


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
    """Get the gRPC market data client."""
    return GRPCMarketDataClient(MARKET_DATA_GRPC_TARGET)


class GRPCMarketDataClient:
    """gRPC-based market data client."""

    def __init__(self, target: str = "market-data:8840"):
        self._target = target
        self._client = None

    async def _get_client(self) -> MarketDataClient:
        """Lazy initialization of gRPC client."""
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
        """Fetch historical bars using gRPC.

        Raises:
            MarketDataError: If the timeframe is unsupported or the fetch fails.
        """
        from datetime import datetime

        # Convert timeframe to gRPC format. Unknown timeframes are an error —
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

        try:
            client = await self._get_client()
        except Exception as e:
            raise MarketDataError(f"Failed to fetch bars: {e}") from e

        # Fetch symbols concurrently over the shared channel, bounded by a
        # semaphore so large universes don't stampede the market-data service
        semaphore = asyncio.Semaphore(MARKET_DATA_FETCH_CONCURRENCY)

        async def fetch_symbol(symbol: str) -> list[dict[str, object]]:
            async with semaphore:
                bars = await client.get_historical_bars(
                    symbol=symbol,
                    start=datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC),
                    end=datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC),
                    timeframe=grpc_timeframe,
                )

                return [
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
                    for bar in bars
                ]

        fetched = await asyncio.gather(
            *(fetch_symbol(symbol) for symbol in symbols), return_exceptions=True
        )

        # Aggregate per-symbol failures into one error naming the symbols
        failures = [
            (symbol, res)
            for symbol, res in zip(symbols, fetched, strict=True)
            if isinstance(res, BaseException)
        ]
        if failures:
            failed_names = ", ".join(symbol for symbol, _ in failures)
            raise MarketDataError(
                f"Failed to fetch bars for: {failed_names} ({failures[0][1]})"
            ) from failures[0][1]

        return {
            symbol: cast(list[dict[str, object]], res)
            for symbol, res in zip(symbols, fetched, strict=True)
        }

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
    ):
        self.db = db
        self.market_data_client = market_data_client or get_market_data_client()
        # Track if we own the client (created it ourselves) vs received it
        self._owns_market_data_client = market_data_client is None

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
    ) -> BacktestResponse:
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
        """
        if end_date <= start_date:
            raise ValueError("End date must be after start date")

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

        # Determine timeframe: explicit > strategy > default
        actual_timeframe = timeframe or strategy_ver.timeframe or "1D"

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

        return self._to_response(backtest)

    async def get_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> BacktestResponse | None:
        """Get backtest by ID."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        return self._to_response(backtest) if backtest else None

    async def list_backtests(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        status: int | None = None,  # BacktestStatus proto value
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BacktestResponse], int]:
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

        return [self._to_response(b) for b in backtests], total

    async def get_results(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> BacktestResultResponse | None:
        """Get backtest results."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            return None

        # Get results
        stmt = select(BacktestResult).where(BacktestResult.backtest_id == backtest_id)
        result = await self.db.execute(stmt)
        backtest_result = result.scalar_one_or_none()

        if not backtest_result:
            return None

        return self._to_result_response(backtest, backtest_result)

    async def run_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
        publish_progress: bool = True,
    ) -> BacktestResultResponse:
        """Execute a pending backtest.

        Args:
            backtest_id: ID of the backtest to run.
            tenant_id: Tenant ID for isolation.
            publish_progress: Whether to publish progress updates to Redis.

        Returns:
            BacktestResultResponse with metrics and trades.
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

        except BacktestCancelled:
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
    ) -> BacktestResultResponse:
        """Run the backtest simulation and persist results.

        Extracted from ``run_backtest`` so the wall-clock timer and terminal
        state-transition handling wrap a single call. Raises the same typed
        exceptions (``BacktestCancelled``, ``MarketDataError``) the caller maps
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

        # Create strategy function (multi-symbol: all bars per date at once)
        strategy_fn, required_symbols, min_bars = create_multi_symbol_strategy(config_sexpr)

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

        all_bars = await self.market_data_client.fetch_bars(
            symbols=symbols_to_fetch,
            timeframe=timeframe,
            start_date=fetch_start,
            end_date=backtest.end_date,
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
        from src.engine.backtester import BarData

        bars: dict[str, list[BarData]] = {
            s: cast(list[BarData], all_bars[s]) for s in strategy_symbols if s in all_bars
        }

        # Validate OHLCV data before simulating: errors abort the run,
        # warnings (gaps, suspected splits) are logged.
        validation = validate_bars(cast(dict[str, list[BarData | BarDataDict]], bars))
        log_validation_result(validation)
        if not validation.valid:
            raise ValueError(f"Market data validation failed: {validation.summary()}")

        # Calculate total bars for progress tracking
        total_bars = sum(len(symbol_bars) for symbol_bars in bars.values())
        if reporter:
            reporter.set_total_bars(total_bars)
            await reporter.publish_phase("Running simulation", 40)

        backtest_config = BacktestConfig(
            initial_capital=float(backtest.initial_capital),
            commission_rate=safe_float(config.get("commission", 0)),
            slippage_rate=safe_float(config.get("slippage", 0)),
        )
        engine = BacktestEngine(backtest_config)

        # Create progress callback if reporting is enabled
        progress_callback = reporter.create_engine_callback() if reporter else None

        # Cooperative cancellation: CancelBacktest sets a Redis flag that
        # the engine polls between trading dates (fails open if Redis is
        # unreachable)
        should_abort = CancellationFlag().make_should_abort(str(backtest_id))

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime.combine(backtest.start_date, datetime.min.time(), tzinfo=UTC),
            end_date=datetime.combine(backtest.end_date, datetime.max.time(), tzinfo=UTC),
            progress_callback=progress_callback,
            should_abort=should_abort,
        )

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
                # Use benchmark bars from the combined fetch (no duplicate
                # API call), restricted to the backtest window so warm-up
                # padding does not distort the comparison.
                window_start = datetime.combine(
                    backtest.start_date, datetime.min.time(), tzinfo=UTC
                )
                benchmark_bars_list = [
                    b
                    for b in all_bars.get(benchmark_symbol, [])
                    if not isinstance(b["timestamp"], datetime) or b["timestamp"] >= window_start
                ]

                if benchmark_bars_list:
                    # Convert to BenchmarkBarData format
                    benchmark_bars: list[BenchmarkBarData] = []
                    for b in benchmark_bars_list:
                        ts = b["timestamp"]
                        close_val = b["close"]
                        benchmark_bars.append(
                            {
                                "timestamp": ts
                                if isinstance(ts, datetime)
                                else datetime.fromisoformat(str(ts)),
                                "close": safe_float(close_val),
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
            raise BacktestCancelled("Backtest was cancelled during execution")

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

        # Update backtest status
        backtest.status = BACKTEST_STATUS_COMPLETED
        backtest.completed_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(backtest_result)

        # Publish completion
        if reporter:
            await reporter.publish_phase("Completed", 100, status=BACKTEST_STATUS_COMPLETED)
            await reporter.close()

        metrics.backtest.job(state="completed")

        return self._to_result_response(backtest, backtest_result)

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
    ) -> BacktestResponse | None:
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

        return self._to_response(backtest)

    async def queue_backtest(
        self,
        backtest_id: UUID,
        tenant_id: UUID,
    ) -> str:
        """Queue a backtest for async execution via Celery.

        Returns:
            Celery task ID
        """
        # Import inline to avoid circular imports; celery types are incomplete
        from src.workers import celery_tasks

        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != BACKTEST_STATUS_PENDING:
            raise ValueError(f"Backtest is {backtest.status}, cannot queue")

        # Queue the task
        # Celery's @shared_task returns a task object with delay() method,
        # but type stubs are incomplete. Access via getattr for type safety.
        run_task = getattr(celery_tasks, "run_backtest_task")
        task = run_task.delay(str(backtest_id), str(tenant_id))
        metrics.backtest.job(state="enqueued")
        return str(task.id)

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

    # ===================
    # Private helpers
    # ===================

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

    def _to_response(self, b: Backtest) -> BacktestResponse:
        """Convert backtest to response."""
        status = _normalize_status(b.status)
        return BacktestResponse(
            id=b.id,
            tenant_id=b.tenant_id,
            strategy_id=b.strategy_id,
            strategy_version=b.strategy_version,
            start_date=datetime.combine(b.start_date, datetime.min.time()),
            end_date=datetime.combine(b.end_date, datetime.min.time()),
            initial_capital=float(b.initial_capital),
            status=status,
            progress=100.0 if status == BACKTEST_STATUS_COMPLETED else 0.0,
            error_message=b.error_message,
            created_at=b.created_at,
            started_at=b.started_at,
            completed_at=b.completed_at,
        )

    def _build_equity_curve(
        self, raw_curve: list[dict[str, object]] | None, initial_capital: float
    ) -> list[EquityPoint]:
        """Build equity curve with drawdown calculations."""
        if not raw_curve:
            return []

        equity_curve: list[EquityPoint] = []
        peak = initial_capital

        for point in raw_curve:
            equity = safe_float(point.get("equity", 0))
            peak = max(peak, equity)
            drawdown = peak - equity
            drawdown_pct = (drawdown / peak) if peak > 0 else 0

            equity_curve.append(
                EquityPoint(
                    date=datetime.fromisoformat(str(point["date"])),
                    equity=equity,
                    drawdown=drawdown,
                    drawdown_percent=drawdown_pct * 100,
                )
            )

        return equity_curve

    def _build_benchmark_curve(
        self, raw_curve: list[dict[str, object]] | None
    ) -> list[BenchmarkEquityPoint]:
        """Build benchmark equity curve."""
        if not raw_curve:
            return []

        return [
            BenchmarkEquityPoint(
                date=datetime.fromisoformat(str(point["date"])),
                equity=safe_float(point.get("equity", 0)),
            )
            for point in raw_curve
        ]

    def _build_trades(self, raw_trades: list[dict[str, object]] | None) -> list[TradeRecord]:
        """Build trade records from raw data."""
        if not raw_trades:
            return []

        trades: list[TradeRecord] = []
        for t in raw_trades:
            exit_date_val = t.get("exit_date")
            exit_price_val = t.get("exit_price")
            trades.append(
                TradeRecord(
                    entry_date=datetime.fromisoformat(str(t["entry_date"])),
                    exit_date=datetime.fromisoformat(str(exit_date_val)) if exit_date_val else None,
                    symbol=str(t["symbol"]),
                    side=str(t["side"]),
                    entry_price=safe_float(t["entry_price"]),
                    exit_price=safe_float(exit_price_val) if exit_price_val is not None else None,
                    quantity=safe_float(t["quantity"]),
                    pnl=safe_float(t.get("pnl", 0)),
                    pnl_percent=safe_float(t.get("pnl_percent", 0)),
                    commission=safe_float(t.get("commission", 0)),
                )
            )
        return trades

    def _build_metrics(
        self,
        r: BacktestResult,
        trades: list[TradeRecord],
        benchmark_curve_available: bool,
    ) -> BacktestMetrics:
        """Build metrics from result and trade data."""
        # Calculate trade statistics
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 0
        largest_win = max((t.pnl for t in wins), default=0)
        largest_loss = abs(min((t.pnl for t in losses), default=0))

        # Average holding period in days
        holding_periods = [(t.exit_date - t.entry_date).days for t in trades if t.exit_date]
        avg_holding = sum(holding_periods) / len(holding_periods) if holding_periods else 0

        # Benchmark metrics. Availability is explicit: a NULL benchmark_return
        # means the comparison was unavailable; a stored 0.0 is a real value.
        benchmark_data_available = r.benchmark_return is not None or benchmark_curve_available
        benchmark_return = float(r.benchmark_return) if r.benchmark_return is not None else 0
        benchmark_symbol = r.benchmark_symbol or "SPY"
        alpha = float(r.alpha) if r.alpha is not None else 0
        beta = float(r.beta) if r.beta is not None else 0
        information_ratio = float(r.information_ratio) if r.information_ratio is not None else 0
        excess_return = float(r.total_return) - benchmark_return if benchmark_data_available else 0

        return BacktestMetrics(
            total_return=float(r.total_return),
            annual_return=float(r.annual_return),
            sharpe_ratio=float(r.sharpe_ratio),
            sortino_ratio=float(r.sortino_ratio) if r.sortino_ratio is not None else 0,
            max_drawdown=float(r.max_drawdown),
            max_drawdown_duration=r.max_drawdown_duration or 0,
            win_rate=float(r.win_rate),
            profit_factor=float(r.profit_factor) if r.profit_factor is not None else None,
            total_trades=r.total_trades,
            winning_trades=r.winning_trades,
            losing_trades=r.losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding,
            exposure_time=float(r.exposure_time) if r.exposure_time is not None else 0,
            benchmark_return=benchmark_return,
            benchmark_symbol=benchmark_symbol,
            alpha=alpha,
            beta=beta,
            information_ratio=information_ratio,
            excess_return=excess_return,
            benchmark_data_available=benchmark_data_available,
        )

    def _to_result_response(self, b: Backtest, r: BacktestResult) -> BacktestResultResponse:
        """Convert backtest result to response."""
        # SQLAlchemy JSONB columns return untyped structures, cast to expected types
        raw_equity_curve = cast(list[dict[str, object]] | None, r.equity_curve)
        raw_benchmark_curve = cast(list[dict[str, object]] | None, r.benchmark_equity_curve)
        raw_trades = cast(list[dict[str, object]] | None, r.trades)
        raw_monthly_returns = cast(dict[str, float] | None, r.monthly_returns)

        equity_curve = self._build_equity_curve(raw_equity_curve, float(b.initial_capital))
        benchmark_curve = self._build_benchmark_curve(raw_benchmark_curve)
        trades = self._build_trades(raw_trades)
        metrics = self._build_metrics(r, trades, bool(raw_benchmark_curve))

        return BacktestResultResponse(
            id=r.id,
            backtest_id=b.id,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=raw_monthly_returns or {},
            created_at=r.created_at,
            benchmark_equity_curve=benchmark_curve,
        )


async def get_backtest_service(
    db: AsyncSession = Depends(get_db),
) -> BacktestService:
    """Dependency to get backtest service."""
    return BacktestService(db)
