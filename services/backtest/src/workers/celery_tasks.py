"""Celery tasks for backtest execution."""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import redis
from celery import Task, shared_task  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llamatrade_db.models.backtest import Backtest
from llamatrade_db.models.backtest import BacktestResult as DBBacktestResult
from llamatrade_db.models.strategy import StrategyVersion
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)

from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.strategy_adapter import create_strategy_function
from src.services.backtest_service import GRPCMarketDataClient, MarketDataError

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://llamatrade:llamatrade@localhost:5432/llamatrade",
)

# Redis for progress updates
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_redis() -> redis.Redis:  # type: ignore[type-arg]
    """Get Redis client for progress updates."""
    return redis.from_url(REDIS_URL)  # type: ignore[return-value]


def _publish_progress(
    backtest_id: str,
    progress: float,
    message: str,
    eta_seconds: int | None = None,
) -> None:
    """Publish progress update to Redis pub/sub."""
    try:
        r = _get_redis()
        payload = {
            "backtest_id": backtest_id,
            "progress": progress,
            "message": message,
            "eta_seconds": eta_seconds,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        r.publish(f"backtest:progress:{backtest_id}", json.dumps(payload))  # type: ignore[union-attr]
    except Exception as e:
        logger.warning(f"Failed to publish progress: {e}")


def _create_progress_callback(
    backtest_id: str,
    start_pct: float = 40.0,
    end_pct: float = 90.0,
) -> Callable[[int, int, datetime], None]:
    """Create a progress callback for the backtest engine.

    Args:
        backtest_id: UUID of the backtest.
        start_pct: Progress percentage when simulation starts.
        end_pct: Progress percentage when simulation ends.

    Returns:
        Callback function for engine progress reporting.
    """
    import time

    start_time = time.monotonic()
    last_report_time = start_time
    last_report_pct = 0.0

    def callback(current_bar: int, total_bars: int, current_date: datetime) -> None:
        nonlocal last_report_time, last_report_pct

        if total_bars <= 0:
            return

        # Calculate progress percentage
        sim_progress = current_bar / total_bars
        progress = start_pct + (sim_progress * (end_pct - start_pct))

        # Rate limit: only report every 0.5 seconds or on 5% jumps
        now = time.monotonic()
        if progress - last_report_pct < 5.0 and now - last_report_time < 0.5:
            return

        last_report_time = now
        last_report_pct = progress

        # Calculate ETA
        elapsed = now - start_time
        if elapsed > 0.1 and current_bar > 0:
            items_per_second = current_bar / elapsed
            remaining = total_bars - current_bar
            eta_seconds = int(remaining / items_per_second) if items_per_second > 0 else None
        else:
            eta_seconds = None

        # Format message
        date_str = current_date.strftime("%Y-%m-%d")
        message = f"Processing {date_str} ({current_bar}/{total_bars})"

        _publish_progress(backtest_id, progress, message, eta_seconds)

    return callback


async def _run_backtest_async(
    backtest_id: str,
    tenant_id: str,
) -> dict[str, str | float | int]:
    """Execute a backtest asynchronously."""
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Get backtest
        stmt = select(Backtest).where(
            Backtest.id == UUID(backtest_id),
            Backtest.tenant_id == UUID(tenant_id),
        )
        result = await db.execute(stmt)
        backtest = result.scalar_one_or_none()

        if not backtest:
            raise ValueError(f"Backtest {backtest_id} not found")

        if backtest.status not in (BACKTEST_STATUS_PENDING, BACKTEST_STATUS_RUNNING):
            raise ValueError(f"Backtest is {backtest.status}, cannot run")

        # Update status to running
        _publish_progress(backtest_id, 0, "Starting backtest")
        backtest.status = BACKTEST_STATUS_RUNNING
        backtest.started_at = datetime.now(UTC)
        await db.commit()

        try:
            # Get strategy version
            _publish_progress(backtest_id, 10, "Loading strategy")
            stmt = select(StrategyVersion).where(
                StrategyVersion.strategy_id == backtest.strategy_id,
                StrategyVersion.version == backtest.strategy_version,
            )
            result = await db.execute(stmt)
            strategy_ver = result.scalar_one_or_none()

            if not strategy_ver:
                raise ValueError("Strategy version not found")

            config_sexpr = strategy_ver.config_sexpr
            if not config_sexpr:
                raise ValueError("Strategy has no S-expression config")

            # Create strategy function
            strategy_fn, _min_bars = create_strategy_function(config_sexpr)
            _publish_progress(backtest_id, 20, "Strategy compiled")

            # Fetch historical bars
            _publish_progress(backtest_id, 30, "Fetching market data")
            market_data_client = GRPCMarketDataClient()
            bars = await market_data_client.fetch_bars(
                symbols=backtest.symbols,
                timeframe=strategy_ver.timeframe or "1D",
                start_date=backtest.start_date,
                end_date=backtest.end_date,
            )

            if not bars:
                raise ValueError("No market data available for specified period")

            _publish_progress(backtest_id, 40, "Running simulation")

            # Run backtest with progress callback
            config = BacktestConfig(
                initial_capital=float(backtest.initial_capital),
                commission_rate=float(backtest.config.get("commission", 0)),
                slippage_rate=float(backtest.config.get("slippage", 0)),
            )
            bt_engine = BacktestEngine(config)

            # Create progress callback for bar-by-bar updates (40% to 90%)
            progress_callback = _create_progress_callback(backtest_id, 40.0, 90.0)

            # Cast bars dict to expected type (structure is compatible)
            from src.engine.backtester import BarData

            typed_bars: dict[str, list[BarData]] = cast(dict[str, list[BarData]], bars)
            bt_result = bt_engine.run(
                bars=typed_bars,
                strategy_fn=strategy_fn,
                start_date=datetime.combine(backtest.start_date, datetime.min.time()),
                end_date=datetime.combine(backtest.end_date, datetime.max.time()),
                progress_callback=progress_callback,
            )

            _publish_progress(backtest_id, 90, "Calculating metrics")

            # Save results
            backtest_result = DBBacktestResult(
                backtest_id=backtest.id,
                total_return=Decimal(str(bt_result.total_return)),
                annual_return=Decimal(str(bt_result.annual_return)),
                sharpe_ratio=Decimal(str(bt_result.sharpe_ratio)),
                sortino_ratio=(
                    Decimal(str(bt_result.sortino_ratio)) if bt_result.sortino_ratio else None
                ),
                max_drawdown=Decimal(str(bt_result.max_drawdown)),
                max_drawdown_duration=bt_result.max_drawdown_duration,
                win_rate=Decimal(str(bt_result.win_rate)),
                profit_factor=(
                    Decimal(str(bt_result.profit_factor)) if bt_result.profit_factor else None
                ),
                total_trades=len(bt_result.trades),
                winning_trades=len([t for t in bt_result.trades if t.pnl > 0]),
                losing_trades=len([t for t in bt_result.trades if t.pnl <= 0]),
                avg_trade_return=Decimal(
                    str(
                        sum(t.pnl_percent for t in bt_result.trades) / len(bt_result.trades)
                        if bt_result.trades
                        else 0
                    )
                ),
                final_equity=Decimal(str(bt_result.final_equity)),
                exposure_time=Decimal(str(bt_result.exposure_time)),
                equity_curve=[
                    {"date": ec[0].isoformat(), "equity": ec[1]} for ec in bt_result.equity_curve
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
                    for t in bt_result.trades
                ],
                daily_returns=bt_result.daily_returns,
                monthly_returns=bt_result.monthly_returns,
            )
            db.add(backtest_result)

            # Update backtest status
            backtest.status = BACKTEST_STATUS_COMPLETED
            backtest.completed_at = datetime.now(UTC)
            await db.commit()

            _publish_progress(backtest_id, 100, "Completed")

            return {
                "status": "completed",
                "backtest_id": backtest_id,
                "total_return": float(bt_result.total_return),
                "total_trades": len(bt_result.trades),
            }

        except MarketDataError as e:
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = f"Market data error: {e}"
            backtest.completed_at = datetime.now(UTC)
            await db.commit()
            _publish_progress(backtest_id, 100, f"Failed: {e}")
            raise

        except Exception as e:
            backtest.status = BACKTEST_STATUS_FAILED
            backtest.error_message = str(e)
            backtest.completed_at = datetime.now(UTC)
            await db.commit()
            _publish_progress(backtest_id, 100, f"Failed: {e}")
            raise

    await engine.dispose()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(MarketDataError,),
    retry_backoff=True,
)
def run_backtest_task(self: Task, backtest_id: str, tenant_id: str) -> dict[str, str | float | int]:
    """Execute a backtest as a Celery task.

    Args:
        backtest_id: UUID of the backtest to run
        tenant_id: UUID of the tenant

    Returns:
        Dictionary with status and results
    """
    logger.info(f"Starting backtest task: {backtest_id}")

    try:
        # Run the async function
        result = asyncio.run(_run_backtest_async(backtest_id, tenant_id))
        logger.info(f"Backtest completed: {backtest_id}")
        return result
    except Exception as e:
        logger.error(f"Backtest failed: {backtest_id} - {e}")
        raise


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def run_symbol_chunk(
    self: Task,
    backtest_id: str,
    tenant_id: str,
    symbols: list[str],
    config_sexpr: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
    commission: float,
    slippage: float,
) -> dict[str, object]:
    """Run backtest for a chunk of symbols (for parallel execution).

    Args:
        backtest_id: UUID of parent backtest
        tenant_id: UUID of tenant
        symbols: Symbols to process in this chunk
        config_sexpr: Strategy S-expression
        timeframe: Bar timeframe
        start_date: ISO date string
        end_date: ISO date string
        initial_capital: Capital allocated to this chunk
        commission: Commission rate
        slippage: Slippage rate

    Returns:
        Dictionary with chunk results
    """
    import asyncio
    from datetime import datetime as dt

    from src.engine.backtester import BacktestConfig, BacktestEngine
    from src.engine.strategy_adapter import create_strategy_function
    from src.services.backtest_service import GRPCMarketDataClient

    logger.info(f"Running symbol chunk for {backtest_id}: {symbols}")

    async def run_chunk() -> dict[str, object]:
        market_data_client = GRPCMarketDataClient()

        # Fetch bars for this chunk
        bars = await market_data_client.fetch_bars(
            symbols=symbols,
            timeframe=timeframe,
            start_date=dt.fromisoformat(start_date).date(),
            end_date=dt.fromisoformat(end_date).date(),
        )

        if not bars:
            return {
                "status": "no_data",
                "symbols": symbols,
                "trades": [],
                "equity_curve": [],
                "final_equity": initial_capital,
            }

        # Create strategy
        strategy_fn, _ = create_strategy_function(config_sexpr)

        # Run backtest
        config = BacktestConfig(
            initial_capital=initial_capital,
            commission_rate=commission,
            slippage_rate=slippage,
        )
        engine = BacktestEngine(config)

        # Cast bars to expected type (structure is compatible)
        from typing import cast

        from src.engine.backtester import BarData

        typed_bars: dict[str, list[BarData]] = cast(dict[str, list[BarData]], bars)
        result = engine.run(
            bars=typed_bars,
            strategy_fn=strategy_fn,
            start_date=dt.fromisoformat(start_date),
            end_date=dt.fromisoformat(end_date).replace(hour=23, minute=59, second=59),
        )

        return {
            "status": "completed",
            "symbols": symbols,
            "trades": [
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
            "equity_curve": [
                {"date": ec[0].isoformat(), "equity": ec[1]} for ec in result.equity_curve
            ],
            "final_equity": result.final_equity,
            "total_return": result.total_return,
            "daily_returns": result.daily_returns,
        }

    try:
        return asyncio.run(run_chunk())
    except Exception as e:
        logger.error(f"Symbol chunk failed: {symbols} - {e}")
        raise


@shared_task(bind=True)
def merge_results(
    self: Task, results: list[dict[str, object]], backtest_id: str, tenant_id: str
) -> dict[str, object]:
    """Merge results from parallel symbol chunks.

    Combines trades, equity curves, and metrics from multiple chunk results.

    Args:
        results: List of chunk result dictionaries
        backtest_id: UUID of parent backtest
        tenant_id: UUID of tenant

    Returns:
        Merged result dictionary
    """
    import asyncio
    from decimal import Decimal

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from llamatrade_db.models.backtest import Backtest, BacktestResult

    logger.info(f"Merging {len(results)} chunk results for {backtest_id}")

    # Helper for safe float conversion
    def safe_float(val: object, default: float = 0.0) -> float:
        """Safely convert object to float."""
        if val is None:
            return default
        try:
            return float(val)  # type: ignore[arg-type]
        except TypeError, ValueError:
            return default

    # Combine all trades
    all_trades: list[dict[str, object]] = []
    for r in results:
        if r.get("status") == "completed":
            trades = cast(list[dict[str, object]], r.get("trades", []))
            all_trades.extend(trades)

    # Combine equity curves (sum across chunks by date)
    equity_by_date: dict[str, float] = {}
    for r in results:
        equity_curve = cast(list[dict[str, object]], r.get("equity_curve", []))
        for ec_dict in equity_curve:
            date_key = str(ec_dict.get("date", ""))
            if date_key not in equity_by_date:
                equity_by_date[date_key] = 0
            equity_by_date[date_key] += safe_float(ec_dict.get("equity", 0))

    sorted_dates = sorted(equity_by_date.keys())
    combined_equity_curve: list[dict[str, str | float]] = [
        {"date": d, "equity": equity_by_date[d]} for d in sorted_dates
    ]

    # Calculate combined metrics
    initial_capital: float = sum(safe_float(r.get("initial_capital", 0)) for r in results)
    if initial_capital == 0:
        # Estimate from first equity value
        if combined_equity_curve:
            first_equity = combined_equity_curve[0]["equity"]
            initial_capital = float(first_equity)
        else:
            initial_capital = 100000  # Default fallback

    final_equity: float = sum(safe_float(r.get("final_equity", 0)) for r in results)
    total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else 0

    # Combine daily returns (weighted average would be more accurate, but simple average works)
    all_daily_returns: list[float] = []
    for r in results:
        raw_returns = r.get("daily_returns", [])
        daily_returns: list[float] = cast(list[float], raw_returns) if raw_returns else []
        all_daily_returns.extend(daily_returns)

    # Save to database
    async def save_merged_results() -> None:
        engine = create_async_engine(DATABASE_URL)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as db:
            # Get backtest
            stmt = select(Backtest).where(
                Backtest.id == UUID(backtest_id),
                Backtest.tenant_id == UUID(tenant_id),
            )
            result = await db.execute(stmt)
            backtest = result.scalar_one_or_none()

            if not backtest:
                raise ValueError(f"Backtest {backtest_id} not found")

            # Calculate additional metrics
            wins = [t for t in all_trades if safe_float(t.get("pnl", 0)) > 0]
            losses = [t for t in all_trades if safe_float(t.get("pnl", 0)) <= 0]
            win_rate = len(wins) / len(all_trades) if all_trades else 0

            total_wins = sum(safe_float(t.get("pnl", 0)) for t in wins)
            total_losses = abs(sum(safe_float(t.get("pnl", 0)) for t in losses))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            # Metrics requiring equity curve
            import numpy as np

            equities = (
                np.array([ec["equity"] for ec in combined_equity_curve])
                if combined_equity_curve
                else np.array([])
            )

            if len(equities) > 1:
                daily_returns_arr = np.diff(equities) / equities[:-1]
                sharpe_ratio = (
                    float(np.sqrt(252) * np.mean(daily_returns_arr) / np.std(daily_returns_arr))
                    if np.std(daily_returns_arr) > 0
                    else 0
                )

                # Max drawdown
                peak = np.maximum.accumulate(equities)
                drawdown = (peak - equities) / peak
                max_drawdown = float(np.max(drawdown))

                # Max drawdown duration
                max_dd_duration = 0
                current_duration = 0
                for dd in drawdown:
                    if dd > 0:
                        current_duration += 1
                        max_dd_duration = max(max_dd_duration, current_duration)
                    else:
                        current_duration = 0

                sortino_denom = np.std(daily_returns_arr[daily_returns_arr < 0])
                sortino_ratio = (
                    float(np.sqrt(252) * np.mean(daily_returns_arr) / sortino_denom)
                    if sortino_denom > 0
                    else 0
                )
            else:
                sharpe_ratio = 0
                sortino_ratio = 0
                max_drawdown = 0
                max_dd_duration = 0

            # Annual return
            num_days = len(equities)
            annual_return = (
                ((1 + total_return) ** (252 / max(num_days, 1))) - 1 if num_days > 0 else 0
            )

            # Save result
            backtest_result = BacktestResult(
                backtest_id=backtest.id,
                total_return=Decimal(str(total_return)),
                annual_return=Decimal(str(annual_return)),
                sharpe_ratio=Decimal(str(sharpe_ratio)),
                sortino_ratio=Decimal(str(sortino_ratio)),
                max_drawdown=Decimal(str(max_drawdown)),
                max_drawdown_duration=max_dd_duration,
                win_rate=Decimal(str(win_rate)),
                profit_factor=Decimal(str(profit_factor)),
                total_trades=len(all_trades),
                winning_trades=len(wins),
                losing_trades=len(losses),
                avg_trade_return=Decimal(
                    str(
                        sum(safe_float(t.get("pnl_percent", 0)) for t in all_trades)
                        / len(all_trades)
                        if all_trades
                        else 0
                    )
                ),
                final_equity=Decimal(str(final_equity)),
                exposure_time=Decimal("0"),  # Would need tracking across chunks
                equity_curve=combined_equity_curve,
                trades=all_trades,
                daily_returns=all_daily_returns,
                monthly_returns={},  # Could compute from equity curve
            )
            db.add(backtest_result)

            backtest.status = BACKTEST_STATUS_COMPLETED
            backtest.completed_at = datetime.now(UTC)
            await db.commit()

        await engine.dispose()
        _publish_progress(backtest_id, 100, "Completed")

    try:
        asyncio.run(save_merged_results())
        return {
            "status": "completed",
            "backtest_id": backtest_id,
            "total_trades": len(all_trades),
            "final_equity": final_equity,
            "total_return": total_return,
        }
    except Exception as e:
        logger.error(f"Merge failed: {backtest_id} - {e}")
        raise


def queue_parallel_backtest(
    backtest_id: str,
    tenant_id: str,
    symbols: list[str],
    config_sexpr: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
    commission: float,
    slippage: float,
    chunk_size: int = 25,
) -> str:
    """Queue a backtest with parallel symbol processing.

    Splits symbols into chunks and processes them in parallel using Celery groups.

    Args:
        backtest_id: UUID of backtest
        tenant_id: UUID of tenant
        symbols: List of all symbols
        config_sexpr: Strategy S-expression
        timeframe: Bar timeframe
        start_date: ISO date string
        end_date: ISO date string
        initial_capital: Total starting capital
        commission: Commission rate
        slippage: Slippage rate
        chunk_size: Number of symbols per chunk

    Returns:
        Celery group task ID
    """
    from celery import chord  # type: ignore[import-untyped]
    from celery.canvas import Signature  # type: ignore[import-untyped]

    # Calculate capital per chunk (proportional to symbol count)
    num_symbols = len(symbols)
    chunks = [symbols[i : i + chunk_size] for i in range(0, num_symbols, chunk_size)]

    chunk_tasks: list[Signature] = []
    for chunk_symbols in chunks:
        # Allocate capital proportionally
        chunk_capital = initial_capital * len(chunk_symbols) / num_symbols

        task = run_symbol_chunk.s(  # type: ignore[attr-defined]
            backtest_id=backtest_id,
            tenant_id=tenant_id,
            symbols=chunk_symbols,
            config_sexpr=config_sexpr,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=chunk_capital,
            commission=commission,
            slippage=slippage,
        )
        chunk_tasks.append(task)  # type: ignore[arg-type]

    # Use chord to run chunks in parallel, then merge
    callback: Signature = merge_results.s(backtest_id, tenant_id)  # type: ignore[attr-defined]
    job = chord(chunk_tasks, callback)
    result = job.apply_async()  # type: ignore[union-attr]

    logger.info(f"Queued parallel backtest {backtest_id} with {len(chunks)} chunks")
    return str(result.id)  # type: ignore[union-attr]
