"""Backtest service - manages backtest runs with database persistence."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.market_data import MarketDataClient, MarketDataError
from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.strategy_adapter import create_strategy_function
from src.models import (
    BacktestMetrics,
    BacktestResponse,
    BacktestResultResponse,
    BacktestStatus,
    EquityPoint,
    TradeRecord,
)

# Feature flag for async execution
USE_CELERY = os.getenv("BACKTEST_USE_CELERY", "false").lower() == "true"


class BacktestService:
    """Service for managing backtest runs."""

    def __init__(
        self,
        db: AsyncSession,
        market_data_client: MarketDataClient | None = None,
    ):
        self.db = db
        self.market_data_client = market_data_client or MarketDataClient()

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
    ) -> BacktestResponse:
        """Create a new backtest job."""
        if end_date <= start_date:
            raise ValueError("End date must be after start date")

        # Verify strategy exists and belongs to tenant
        strategy = await self._get_strategy(tenant_id, strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

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

        backtest = Backtest(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            strategy_version=version,
            name=name,
            status="pending",
            config={
                "commission": commission,
                "slippage": slippage,
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
        status: BacktestStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BacktestResponse], int]:
        """List backtests for tenant."""
        stmt = select(Backtest).where(Backtest.tenant_id == tenant_id)

        if strategy_id:
            stmt = stmt.where(Backtest.strategy_id == strategy_id)
        if status:
            stmt = stmt.where(Backtest.status == status.value)

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
    ) -> BacktestResultResponse:
        """Execute a pending backtest."""
        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != "pending":
            raise ValueError(f"Backtest is {backtest.status}, cannot run")

        # Update status to running
        backtest.status = "running"
        backtest.started_at = datetime.now(UTC)
        await self.db.commit()

        try:
            # Get strategy version
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
            strategy_fn, min_bars = create_strategy_function(config_sexpr)

            # Fetch historical bars
            bars = await self.market_data_client.fetch_bars(
                symbols=backtest.symbols,
                timeframe=strategy_ver.timeframe or "1D",
                start_date=backtest.start_date,
                end_date=backtest.end_date,
            )

            if not bars:
                raise ValueError("No market data available for specified period")

            # Run backtest
            config = BacktestConfig(
                initial_capital=float(backtest.initial_capital),
                commission_rate=backtest.config.get("commission", 0),
                slippage_rate=backtest.config.get("slippage", 0),
            )
            engine = BacktestEngine(config)

            result = engine.run(
                bars=bars,
                strategy_fn=strategy_fn,
                start_date=datetime.combine(backtest.start_date, datetime.min.time()),
                end_date=datetime.combine(backtest.end_date, datetime.max.time()),
            )

            # Save results
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
            )
            self.db.add(backtest_result)

            # Update backtest status
            backtest.status = "completed"
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(backtest_result)

            return self._to_result_response(backtest, backtest_result)

        except MarketDataError as e:
            backtest.status = "failed"
            backtest.error_message = f"Market data error: {e}"
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise ValueError(str(e)) from e

        except Exception as e:
            backtest.status = "failed"
            backtest.error_message = str(e)
            backtest.completed_at = datetime.now(UTC)
            await self.db.commit()
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

        if backtest.status not in ("pending", "running"):
            return False

        backtest.status = "cancelled"
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

        if backtest.status != "failed":
            raise ValueError("Only failed backtests can be retried")

        backtest.status = "pending"
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
        from src.workers.celery_tasks import run_backtest_task

        backtest = await self._get_backtest_by_id(tenant_id, backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status != "pending":
            raise ValueError(f"Backtest is {backtest.status}, cannot queue")

        # Queue the task
        task = run_backtest_task.delay(str(backtest_id), str(tenant_id))
        return str(task.id)

    async def get_task_status(self, task_id: str) -> dict:
        """Get the status of a Celery task.

        Returns:
            Dictionary with task status and result
        """
        from src.celery_app import celery_app

        result = celery_app.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
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
        return BacktestResponse(
            id=b.id,
            tenant_id=b.tenant_id,
            strategy_id=b.strategy_id,
            strategy_version=b.strategy_version,
            start_date=datetime.combine(b.start_date, datetime.min.time()),
            end_date=datetime.combine(b.end_date, datetime.min.time()),
            initial_capital=float(b.initial_capital),
            status=BacktestStatus(b.status),
            progress=100.0 if b.status == "completed" else 0.0,
            error_message=b.error_message,
            created_at=b.created_at,
            started_at=b.started_at,
            completed_at=b.completed_at,
        )

    def _to_result_response(self, b: Backtest, r: BacktestResult) -> BacktestResultResponse:
        """Convert backtest result to response."""
        # Build equity curve
        equity_curve: list[EquityPoint] = []
        if r.equity_curve:
            prev_equity = float(b.initial_capital)
            peak = prev_equity
            for point in r.equity_curve:
                equity = point.get("equity", 0)
                peak = max(peak, equity)
                drawdown = peak - equity
                drawdown_pct = (drawdown / peak) if peak > 0 else 0

                equity_curve.append(
                    EquityPoint(
                        date=datetime.fromisoformat(point["date"]),
                        equity=equity,
                        drawdown=drawdown,
                        drawdown_percent=drawdown_pct * 100,
                    )
                )
                prev_equity = equity

        # Build trades
        trades: list[TradeRecord] = []
        if r.trades:
            for t in r.trades:
                trades.append(
                    TradeRecord(
                        entry_date=datetime.fromisoformat(t["entry_date"]),
                        exit_date=datetime.fromisoformat(t["exit_date"])
                        if t.get("exit_date")
                        else None,
                        symbol=t["symbol"],
                        side=t["side"],
                        entry_price=t["entry_price"],
                        exit_price=t.get("exit_price"),
                        quantity=t["quantity"],
                        pnl=t.get("pnl", 0),
                        pnl_percent=t.get("pnl_percent", 0),
                        commission=t.get("commission", 0),
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
        holding_periods = []
        for t in trades:
            if t.exit_date:
                delta = t.exit_date - t.entry_date
                holding_periods.append(delta.days)
        avg_holding = sum(holding_periods) / len(holding_periods) if holding_periods else 0

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
        )

        return BacktestResultResponse(
            id=r.id,
            backtest_id=b.id,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=r.monthly_returns or {},
            created_at=r.created_at,
        )


async def get_backtest_service(
    db: AsyncSession = Depends(get_db),
) -> BacktestService:
    """Dependency to get backtest service."""
    return BacktestService(db)
