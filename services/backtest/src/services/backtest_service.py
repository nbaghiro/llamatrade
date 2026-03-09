"""Backtest service - manages backtest runs with database persistence."""

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable
from uuid import UUID

import numpy as np

if TYPE_CHECKING:
    from llamatrade_proto import MarketDataClient

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_PAUSED,
    StrategyStatus,
)

from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.benchmarks import BenchmarkBarData, BenchmarkCalculator
from src.engine.strategy_adapter import create_strategy_function
from src.models import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    VALID_TIMEFRAMES,
    BacktestMetrics,
    BacktestResponse,
    BacktestResultResponse,
    BacktestStatus,
    BenchmarkEquityPoint,
    EquityPoint,
    TradeRecord,
)
from src.progress import BacktestProgressReporter

# Feature flags

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


USE_CELERY = os.getenv("BACKTEST_USE_CELERY", "false").lower() == "true"
MARKET_DATA_GRPC_TARGET = os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")


class MarketDataError(Exception):
    """Error fetching market data."""

    pass


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
        """Fetch historical bars using gRPC."""
        from datetime import datetime

        try:
            client = await self._get_client()

            # Convert timeframe to gRPC format
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
            grpc_timeframe = tf_map.get(timeframe, "1DAY")

            result: dict[str, list[dict[str, object]]] = {}

            for symbol in symbols:
                bars = await client.get_historical_bars(
                    symbol=symbol,
                    start=datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC),
                    end=datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC),
                    timeframe=grpc_timeframe,
                )

                result[symbol] = [
                    {
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": bar.volume,
                    }
                    for bar in bars
                ]

            return result

        except Exception as e:
            raise MarketDataError(f"Failed to fetch bars: {e}") from e

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
            await reporter.publish_phase("Starting backtest", 0)

        # Update status to running
        backtest.status = BACKTEST_STATUS_RUNNING
        backtest.started_at = datetime.now(UTC)
        await self.db.commit()

        try:
            # Validate symbols before running (Phase 3)
            if reporter:
                await reporter.publish_phase("Validating symbols", 5)

            # Cast symbols since JSONB returns untyped list
            symbols_list: list[str] = backtest.symbols
            symbols_to_validate = list(symbols_list)
            if include_benchmark and benchmark_symbol:
                symbols_to_validate.append(benchmark_symbol)

            await self._validate_symbols(symbols_to_validate)

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

            # Create strategy function
            strategy_fn, _min_bars = create_strategy_function(config_sexpr)

            if reporter:
                await reporter.publish_phase("Strategy compiled", 20)

            # Fetch historical bars using timeframe from config (Phase 1)
            # Include benchmark symbol in the same request to avoid duplicate API call
            if reporter:
                await reporter.publish_phase("Fetching market data", 30)

            symbols_to_fetch = list(symbols_list)
            if include_benchmark and benchmark_symbol and benchmark_symbol not in symbols_to_fetch:
                symbols_to_fetch.append(benchmark_symbol)

            all_bars = await self.market_data_client.fetch_bars(
                symbols=symbols_to_fetch,
                timeframe=timeframe,
                start_date=backtest.start_date,
                end_date=backtest.end_date,
            )

            if not all_bars:
                raise ValueError("No market data available for specified period")

            # Separate strategy bars from benchmark bars
            # Cast to BarData since market_data_client returns properly structured dicts
            from src.engine.backtester import BarData

            bars: dict[str, list[BarData]] = {
                s: cast(list[BarData], all_bars[s]) for s in symbols_list if s in all_bars
            }

            # Calculate total bars for progress tracking
            total_bars = sum(len(symbol_bars) for symbol_bars in bars.values())
            if reporter:
                reporter.set_total_bars(total_bars)
                await reporter.publish_phase("Running simulation", 40)

            # Run backtest with progress callback
            @runtime_checkable
            class _SupportsFloat(Protocol):
                def __float__(self) -> float: ...

            def _safe_float(val: object, default: float = 0.0) -> float:
                """Safely convert object to float."""
                if val is None:
                    return default
                if isinstance(val, (int, float)):
                    return float(val)
                if isinstance(val, str):
                    try:
                        return float(val)
                    except ValueError:
                        return default
                if isinstance(val, _SupportsFloat):
                    try:
                        return float(val)
                    except TypeError, ValueError:
                        return default
                return default

            backtest_config = BacktestConfig(
                initial_capital=float(backtest.initial_capital),
                commission_rate=_safe_float(config.get("commission", 0)),
                slippage_rate=_safe_float(config.get("slippage", 0)),
            )
            engine = BacktestEngine(backtest_config)

            # Create progress callback if reporting is enabled
            progress_callback = reporter.create_engine_callback() if reporter else None

            result = engine.run(
                bars=bars,
                strategy_fn=strategy_fn,
                start_date=datetime.combine(backtest.start_date, datetime.min.time()),
                end_date=datetime.combine(backtest.end_date, datetime.max.time()),
                progress_callback=progress_callback,
            )

            # Flush pending progress updates
            if reporter:
                await reporter.flush()
                await reporter.publish_phase("Calculating metrics", 85)

            # Calculate benchmark metrics if enabled (Phase 4)
            benchmark_return_val: float = 0
            benchmark_equity_curve: list[dict[str, object]] = []
            alpha_val: float = 0
            beta_val: float = 0
            information_ratio_val: float = 0

            if include_benchmark and benchmark_symbol:
                if reporter:
                    await reporter.publish_phase("Calculating benchmark comparison", 90)

                try:
                    # Use benchmark bars from the combined fetch (no duplicate API call)
                    benchmark_bars_list = all_bars.get(benchmark_symbol, [])

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
                                    "close": _safe_float(close_val),
                                }
                            )

                        # Calculate buy & hold return and equity curve
                        calculator = BenchmarkCalculator()
                        benchmark_return_val, benchmark_ec = calculator.calculate_spy_buy_hold(
                            benchmark_bars, float(backtest.initial_capital)
                        )

                        # Convert to storable format
                        benchmark_equity_curve = [
                            {"date": dt.isoformat(), "equity": eq} for dt, eq in benchmark_ec
                        ]

                        # Calculate alpha, beta, information ratio using strategy daily returns
                        if result.daily_returns:
                            strategy_returns = np.array(result.daily_returns)
                            benchmark_closes = np.array([b["close"] for b in benchmark_bars])

                            if len(benchmark_closes) > 1:
                                benchmark_returns = (
                                    np.diff(benchmark_closes) / benchmark_closes[:-1]
                                )
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

            # Save results with benchmark data
            backtest_result = BacktestResult(
                backtest_id=backtest.id,
                total_return=Decimal(str(result.total_return)),
                annual_return=Decimal(str(result.annual_return)),
                sharpe_ratio=Decimal(str(result.sharpe_ratio)),
                sortino_ratio=Decimal(str(result.sortino_ratio)) if result.sortino_ratio else None,
                max_drawdown=Decimal(str(result.max_drawdown)),
                max_drawdown_duration=result.max_drawdown_duration,
                win_rate=Decimal(str(result.win_rate)),
                profit_factor=Decimal(str(result.profit_factor)) if result.profit_factor else None,
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
                    {"date": ec[0].isoformat(), "equity": ec[1]} for ec in result.equity_curve
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
                # Benchmark comparison data (Phase 4)
                benchmark_return=Decimal(str(benchmark_return_val))
                if benchmark_return_val
                else None,
                benchmark_symbol=benchmark_symbol if include_benchmark else None,
                alpha=Decimal(str(alpha_val)) if alpha_val else None,
                beta=Decimal(str(beta_val)) if beta_val else None,
                information_ratio=Decimal(str(information_ratio_val))
                if information_ratio_val
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
                await reporter.publish_phase("Completed", 100)
                await reporter.close()

            return self._to_result_response(backtest, backtest_result)

        except MarketDataError as e:
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = f"Market data error: {e}"
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            if reporter:
                await reporter.publish_phase(f"Failed: {e}", 100)
                await reporter.close()
            raise ValueError(str(e)) from e

        except Exception as e:
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = str(e)
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            if reporter:
                await reporter.publish_phase(f"Failed: {e}", 100)
                await reporter.close()
            raise

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

    async def _validate_symbols(self, symbols: list[str]) -> None:
        """Validate symbols exist by attempting to fetch recent bars.

        Validates all symbols concurrently for better performance.

        Args:
            symbols: List of symbols to validate

        Raises:
            ValueError: If any symbols are invalid
        """

        async def validate_single(symbol: str) -> str | None:
            """Return symbol if invalid, None if valid."""
            try:
                await self.market_data_client.fetch_bars(
                    symbols=[symbol],
                    timeframe="1D",
                    start_date=date.today() - timedelta(days=7),
                    end_date=date.today(),
                )
                return None
            except MarketDataError:
                return symbol

        # Validate all symbols concurrently
        results = await asyncio.gather(*[validate_single(s) for s in symbols])
        invalid = [s for s in results if s is not None]

        if invalid:
            raise ValueError(f"Invalid symbols: {', '.join(invalid)}")

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

    def _to_result_response(  # noqa: C901
        self, b: Backtest, r: BacktestResult
    ) -> BacktestResultResponse:
        """Convert backtest result to response."""
        # SQLAlchemy JSONB columns return untyped structures, cast to expected types
        raw_equity_curve = cast(list[dict[str, object]] | None, r.equity_curve)
        raw_benchmark_curve = cast(list[dict[str, object]] | None, r.benchmark_equity_curve)
        raw_trades = cast(list[dict[str, object]] | None, r.trades)
        raw_monthly_returns = cast(dict[str, float] | None, r.monthly_returns)

        def _result_safe_float(val: object, default: float = 0.0) -> float:
            """Safely convert object to float."""
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default

        # Build equity curve
        equity_curve: list[EquityPoint] = []
        if raw_equity_curve:
            peak = float(b.initial_capital)
            for point in raw_equity_curve:
                equity = _result_safe_float(point.get("equity", 0))
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

        # Build benchmark equity curve (Phase 5)
        benchmark_equity_curve: list[BenchmarkEquityPoint] = []
        if raw_benchmark_curve:
            for point in raw_benchmark_curve:
                benchmark_equity_curve.append(
                    BenchmarkEquityPoint(
                        date=datetime.fromisoformat(str(point["date"])),
                        equity=_result_safe_float(point.get("equity", 0)),
                    )
                )

        # Build trades
        def _safe_float(val: object, default: float = 0.0) -> float:
            """Safely convert object to float."""
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default

        trades: list[TradeRecord] = []
        if raw_trades:
            for t in raw_trades:
                exit_date_val = t.get("exit_date")
                exit_price_val = t.get("exit_price")
                trades.append(
                    TradeRecord(
                        entry_date=datetime.fromisoformat(str(t["entry_date"])),
                        exit_date=datetime.fromisoformat(str(exit_date_val))
                        if exit_date_val
                        else None,
                        symbol=str(t["symbol"]),
                        side=str(t["side"]),
                        entry_price=_safe_float(t["entry_price"]),
                        exit_price=_safe_float(exit_price_val)
                        if exit_price_val is not None
                        else None,
                        quantity=_safe_float(t["quantity"]),
                        pnl=_safe_float(t.get("pnl", 0)),
                        pnl_percent=_safe_float(t.get("pnl_percent", 0)),
                        commission=_safe_float(t.get("commission", 0)),
                    )
                )

        # Calculate additional metrics
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 0
        largest_win = max((t.pnl for t in wins), default=0)
        largest_loss = abs(min((t.pnl for t in losses), default=0))

        # Average holding period in days
        holding_periods: list[int] = []
        for t in trades:
            if t.exit_date:
                delta = t.exit_date - t.entry_date
                holding_periods.append(delta.days)
        avg_holding = sum(holding_periods) / len(holding_periods) if holding_periods else 0

        # Extract benchmark metrics with defaults
        benchmark_return = float(r.benchmark_return) if r.benchmark_return else 0
        benchmark_symbol = r.benchmark_symbol or "SPY"
        alpha = float(r.alpha) if r.alpha else 0
        beta = float(r.beta) if r.beta else 0
        information_ratio = float(r.information_ratio) if r.information_ratio else 0
        excess_return = float(r.total_return) - benchmark_return

        # Infer benchmark data availability from the stored data
        # Benchmark is considered available if we have benchmark equity curve data
        # or if benchmark_return is non-zero
        benchmark_data_available = bool(raw_benchmark_curve) or benchmark_return != 0

        metrics = BacktestMetrics(
            total_return=float(r.total_return),
            annual_return=float(r.annual_return),
            sharpe_ratio=float(r.sharpe_ratio),
            sortino_ratio=float(r.sortino_ratio) if r.sortino_ratio else 0,
            max_drawdown=float(r.max_drawdown),
            max_drawdown_duration=r.max_drawdown_duration or 0,
            win_rate=float(r.win_rate),
            profit_factor=float(r.profit_factor) if r.profit_factor else 0,
            total_trades=r.total_trades,
            winning_trades=r.winning_trades,
            losing_trades=r.losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_holding_period=avg_holding,
            exposure_time=float(r.exposure_time) if r.exposure_time else 0,
            # Benchmark comparison metrics (Phase 5)
            benchmark_return=benchmark_return,
            benchmark_symbol=benchmark_symbol,
            alpha=alpha,
            beta=beta,
            information_ratio=information_ratio,
            excess_return=excess_return,
            benchmark_data_available=benchmark_data_available,
        )

        return BacktestResultResponse(
            id=r.id,
            backtest_id=b.id,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=raw_monthly_returns or {},
            created_at=r.created_at,
            benchmark_equity_curve=benchmark_equity_curve,
        )


async def get_backtest_service(
    db: AsyncSession = Depends(get_db),
) -> BacktestService:
    """Dependency to get backtest service."""
    return BacktestService(db)
