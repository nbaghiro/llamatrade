"""Backtest gRPC client."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from llamatrade_grpc.clients.auth import TenantContext
from llamatrade_grpc.clients.base import BaseGRPCClient

if TYPE_CHECKING:
    from llamatrade.v1 import backtest_pb2, backtest_pb2_grpc

logger = logging.getLogger(__name__)


class BacktestStatus(Enum):
    """Backtest status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BacktestConfig:
    """Backtest configuration."""

    strategy_id: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    symbols: list[str]
    strategy_version: int = 1
    commission: Decimal = Decimal("0")
    slippage_percent: Decimal = Decimal("0")
    allow_shorting: bool = False
    max_position_size: Decimal = Decimal("1.0")
    timeframe: str = "1D"
    use_adjusted_prices: bool = True
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class BacktestMetrics:
    """Backtest performance metrics."""

    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    max_drawdown: Decimal
    max_drawdown_duration_days: Decimal
    volatility: Decimal
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Decimal
    expectancy: Decimal
    starting_capital: Decimal
    ending_capital: Decimal
    total_commission: Decimal
    benchmark_return: Decimal | None = None
    alpha: Decimal | None = None
    beta: Decimal | None = None


@dataclass
class EquityPoint:
    """Equity curve point."""

    timestamp: datetime
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    daily_return: Decimal
    drawdown: Decimal


@dataclass
class BacktestTrade:
    """Backtest trade record."""

    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    pnl_percent: Decimal
    commission: Decimal
    holding_period_bars: int
    entry_reason: str
    exit_reason: str


@dataclass
class BacktestResults:
    """Backtest results."""

    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[BacktestTrade]
    monthly_returns: dict[str, float]


@dataclass
class BacktestRun:
    """Backtest run."""

    id: str
    tenant_id: str
    strategy_id: str
    strategy_version: int
    config: BacktestConfig
    status: BacktestStatus
    status_message: str | None
    progress_percent: int
    current_date: str | None
    results: BacktestResults | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass
class BacktestProgressUpdate:
    """Backtest progress update."""

    backtest_id: str
    status: BacktestStatus
    progress_percent: int
    current_date: str | None
    message: str | None
    timestamp: datetime
    partial_metrics: BacktestMetrics | None


class BacktestClient(BaseGRPCClient):
    """Client for the Backtest gRPC service.

    Example:
        async with BacktestClient("backtest:8830") as client:
            # Run a backtest
            config = BacktestConfig(
                strategy_id="strat-123",
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 1, 1),
                initial_capital=Decimal("100000"),
                symbols=["AAPL", "GOOGL"],
            )
            run = await client.run_backtest(context, config)

            # Stream progress updates
            async for update in client.stream_progress(context, run.id):
                print(f"Progress: {update.progress_percent}%")
    """

    def __init__(
        self,
        target: str = "backtest:8830",
        *,
        secure: bool = False,
        credentials: object | None = None,
        interceptors: list[object] | None = None,
        options: list[tuple[str, str | int | bool]] | None = None,
    ) -> None:
        """Initialize the Backtest client.

        Args:
            target: The gRPC server address
            secure: Whether to use TLS
            credentials: Optional channel credentials
            interceptors: Optional client interceptors
            options: Optional channel options
        """
        super().__init__(
            target,
            secure=secure,
            credentials=credentials,  # type: ignore[arg-type]
            interceptors=interceptors,  # type: ignore[arg-type]
            options=options,
        )
        self._stub: backtest_pb2_grpc.BacktestServiceStub | None = None

    @property
    def stub(self) -> backtest_pb2_grpc.BacktestServiceStub:
        """Get the gRPC stub (lazy initialization)."""
        if self._stub is None:
            try:
                from llamatrade.v1 import backtest_pb2_grpc

                self._stub = backtest_pb2_grpc.BacktestServiceStub(self.channel)
            except ImportError:
                raise RuntimeError(
                    "Generated gRPC code not found. Run 'make generate' in libs/proto"
                )
        return self._stub

    async def run_backtest(
        self,
        context: TenantContext,
        config: BacktestConfig,
    ) -> BacktestRun:
        """Run a new backtest.

        Args:
            context: Tenant context
            config: Backtest configuration

        Returns:
            The created BacktestRun
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        proto_config = backtest_pb2.BacktestConfig(
            strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            start_date=common_pb2.Timestamp(seconds=int(config.start_date.timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(config.end_date.timestamp())),
            initial_capital=common_pb2.Decimal(value=str(config.initial_capital)),
            symbols=config.symbols,
            commission=common_pb2.Decimal(value=str(config.commission)),
            slippage_percent=common_pb2.Decimal(value=str(config.slippage_percent)),
            allow_shorting=config.allow_shorting,
            max_position_size=common_pb2.Decimal(value=str(config.max_position_size)),
            timeframe=config.timeframe,
            use_adjusted_prices=config.use_adjusted_prices,
            parameters=config.parameters,
        )

        request = backtest_pb2.RunBacktestRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            config=proto_config,
        )

        response = await self.stub.RunBacktest(request)
        return self._proto_to_backtest_run(response.backtest)

    async def get_backtest(
        self,
        context: TenantContext,
        backtest_id: str,
    ) -> BacktestRun:
        """Get a backtest by ID.

        Args:
            context: Tenant context
            backtest_id: The backtest ID

        Returns:
            The BacktestRun
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        request = backtest_pb2.GetBacktestRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            backtest_id=backtest_id,
        )

        response = await self.stub.GetBacktest(request)
        return self._proto_to_backtest_run(response.backtest)

    async def list_backtests(
        self,
        context: TenantContext,
        strategy_id: str | None = None,
        statuses: list[BacktestStatus] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BacktestRun]:
        """List backtests.

        Args:
            context: Tenant context
            strategy_id: Optional filter by strategy
            statuses: Optional filter by status
            page: Page number
            page_size: Page size

        Returns:
            List of BacktestRun objects
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        status_map = {
            BacktestStatus.PENDING: backtest_pb2.BACKTEST_STATUS_PENDING,
            BacktestStatus.RUNNING: backtest_pb2.BACKTEST_STATUS_RUNNING,
            BacktestStatus.COMPLETED: backtest_pb2.BACKTEST_STATUS_COMPLETED,
            BacktestStatus.FAILED: backtest_pb2.BACKTEST_STATUS_FAILED,
            BacktestStatus.CANCELLED: backtest_pb2.BACKTEST_STATUS_CANCELLED,
        }

        request = backtest_pb2.ListBacktestsRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            pagination=common_pb2.PaginationRequest(page=page, page_size=page_size),
        )

        if strategy_id:
            request.strategy_id = strategy_id
        if statuses:
            request.statuses.extend([status_map[s] for s in statuses])

        response = await self.stub.ListBacktests(request)
        return [self._proto_to_backtest_run(bt) for bt in response.backtests]

    async def cancel_backtest(
        self,
        context: TenantContext,
        backtest_id: str,
    ) -> BacktestRun:
        """Cancel a running backtest.

        Args:
            context: Tenant context
            backtest_id: The backtest ID

        Returns:
            The cancelled BacktestRun
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        request = backtest_pb2.CancelBacktestRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            backtest_id=backtest_id,
        )

        response = await self.stub.CancelBacktest(request)
        return self._proto_to_backtest_run(response.backtest)

    async def stream_progress(
        self,
        context: TenantContext,
        backtest_id: str,
    ) -> AsyncIterator[BacktestProgressUpdate]:
        """Stream backtest progress updates.

        Args:
            context: Tenant context
            backtest_id: The backtest ID

        Yields:
            BacktestProgressUpdate events
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        request = backtest_pb2.StreamBacktestProgressRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            backtest_id=backtest_id,
        )

        async for update in self.stub.StreamBacktestProgress(request):
            yield self._proto_to_progress_update(update)

    async def compare_backtests(
        self,
        context: TenantContext,
        backtest_ids: list[str],
    ) -> list[BacktestRun]:
        """Compare multiple backtests.

        Args:
            context: Tenant context
            backtest_ids: List of backtest IDs to compare

        Returns:
            List of BacktestRun objects for comparison
        """
        from llamatrade.v1 import backtest_pb2, common_pb2

        request = backtest_pb2.CompareBacktestsRequest(
            context=common_pb2.TenantContext(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                roles=context.roles,
            ),
            backtest_ids=backtest_ids,
        )

        response = await self.stub.CompareBacktests(request)
        return [self._proto_to_backtest_run(bt) for bt in response.backtests]

    def _proto_to_backtest_run(self, proto: backtest_pb2.BacktestRun) -> BacktestRun:
        """Convert protobuf BacktestRun to dataclass."""
        from llamatrade.v1 import backtest_pb2

        status_map = {
            backtest_pb2.BACKTEST_STATUS_PENDING: BacktestStatus.PENDING,
            backtest_pb2.BACKTEST_STATUS_RUNNING: BacktestStatus.RUNNING,
            backtest_pb2.BACKTEST_STATUS_COMPLETED: BacktestStatus.COMPLETED,
            backtest_pb2.BACKTEST_STATUS_FAILED: BacktestStatus.FAILED,
            backtest_pb2.BACKTEST_STATUS_CANCELLED: BacktestStatus.CANCELLED,
        }

        config = self._proto_to_config(proto.config) if proto.HasField("config") else None
        results = self._proto_to_results(proto.results) if proto.HasField("results") else None

        return BacktestRun(
            id=proto.id,
            tenant_id=proto.tenant_id,
            strategy_id=proto.strategy_id,
            strategy_version=proto.strategy_version,
            config=config,  # type: ignore[arg-type]
            status=status_map.get(proto.status, BacktestStatus.PENDING),
            status_message=proto.status_message if proto.status_message else None,
            progress_percent=proto.progress_percent,
            current_date=proto.current_date if proto.current_date else None,
            results=results,
            created_at=datetime.fromtimestamp(proto.created_at.seconds),
            started_at=(
                datetime.fromtimestamp(proto.started_at.seconds)
                if proto.HasField("started_at")
                else None
            ),
            completed_at=(
                datetime.fromtimestamp(proto.completed_at.seconds)
                if proto.HasField("completed_at")
                else None
            ),
        )

    def _proto_to_config(self, proto: backtest_pb2.BacktestConfig) -> BacktestConfig:
        """Convert protobuf BacktestConfig to dataclass."""
        return BacktestConfig(
            strategy_id=proto.strategy_id,
            strategy_version=proto.strategy_version,
            start_date=datetime.fromtimestamp(proto.start_date.seconds),
            end_date=datetime.fromtimestamp(proto.end_date.seconds),
            initial_capital=Decimal(proto.initial_capital.value),
            symbols=list(proto.symbols),
            commission=Decimal(proto.commission.value)
            if proto.HasField("commission")
            else Decimal("0"),
            slippage_percent=Decimal(proto.slippage_percent.value)
            if proto.HasField("slippage_percent")
            else Decimal("0"),
            allow_shorting=proto.allow_shorting,
            max_position_size=Decimal(proto.max_position_size.value)
            if proto.HasField("max_position_size")
            else Decimal("1.0"),
            timeframe=proto.timeframe,
            use_adjusted_prices=proto.use_adjusted_prices,
            parameters=dict(proto.parameters),
        )

    def _proto_to_results(self, proto: backtest_pb2.BacktestResults) -> BacktestResults:
        """Convert protobuf BacktestResults to dataclass."""
        metrics = self._proto_to_metrics(proto.metrics)
        equity_curve = [self._proto_to_equity_point(ep) for ep in proto.equity_curve]
        trades = [self._proto_to_trade(t) for t in proto.trades]

        return BacktestResults(
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns=dict(proto.monthly_returns),
        )

    def _proto_to_metrics(self, proto: backtest_pb2.BacktestMetrics) -> BacktestMetrics:
        """Convert protobuf BacktestMetrics to dataclass."""
        return BacktestMetrics(
            total_return=Decimal(proto.total_return.value)
            if proto.HasField("total_return")
            else Decimal("0"),
            annualized_return=Decimal(proto.annualized_return.value)
            if proto.HasField("annualized_return")
            else Decimal("0"),
            sharpe_ratio=Decimal(proto.sharpe_ratio.value)
            if proto.HasField("sharpe_ratio")
            else Decimal("0"),
            sortino_ratio=Decimal(proto.sortino_ratio.value)
            if proto.HasField("sortino_ratio")
            else Decimal("0"),
            max_drawdown=Decimal(proto.max_drawdown.value)
            if proto.HasField("max_drawdown")
            else Decimal("0"),
            max_drawdown_duration_days=Decimal(proto.max_drawdown_duration_days.value)
            if proto.HasField("max_drawdown_duration_days")
            else Decimal("0"),
            volatility=Decimal(proto.volatility.value)
            if proto.HasField("volatility")
            else Decimal("0"),
            total_trades=proto.total_trades,
            winning_trades=proto.winning_trades,
            losing_trades=proto.losing_trades,
            win_rate=Decimal(proto.win_rate.value) if proto.HasField("win_rate") else Decimal("0"),
            average_win=Decimal(proto.average_win.value)
            if proto.HasField("average_win")
            else Decimal("0"),
            average_loss=Decimal(proto.average_loss.value)
            if proto.HasField("average_loss")
            else Decimal("0"),
            profit_factor=Decimal(proto.profit_factor.value)
            if proto.HasField("profit_factor")
            else Decimal("0"),
            expectancy=Decimal(proto.expectancy.value)
            if proto.HasField("expectancy")
            else Decimal("0"),
            starting_capital=Decimal(proto.starting_capital.value)
            if proto.HasField("starting_capital")
            else Decimal("0"),
            ending_capital=Decimal(proto.ending_capital.value)
            if proto.HasField("ending_capital")
            else Decimal("0"),
            total_commission=Decimal(proto.total_commission.value)
            if proto.HasField("total_commission")
            else Decimal("0"),
            benchmark_return=Decimal(proto.benchmark_return.value)
            if proto.HasField("benchmark_return")
            else None,
            alpha=Decimal(proto.alpha.value) if proto.HasField("alpha") else None,
            beta=Decimal(proto.beta.value) if proto.HasField("beta") else None,
        )

    def _proto_to_equity_point(self, proto: backtest_pb2.EquityPoint) -> EquityPoint:
        """Convert protobuf EquityPoint to dataclass."""
        return EquityPoint(
            timestamp=datetime.fromtimestamp(proto.timestamp.seconds),
            equity=Decimal(proto.equity.value) if proto.HasField("equity") else Decimal("0"),
            cash=Decimal(proto.cash.value) if proto.HasField("cash") else Decimal("0"),
            positions_value=Decimal(proto.positions_value.value)
            if proto.HasField("positions_value")
            else Decimal("0"),
            daily_return=Decimal(proto.daily_return.value)
            if proto.HasField("daily_return")
            else Decimal("0"),
            drawdown=Decimal(proto.drawdown.value) if proto.HasField("drawdown") else Decimal("0"),
        )

    def _proto_to_trade(self, proto: backtest_pb2.BacktestTrade) -> BacktestTrade:
        """Convert protobuf BacktestTrade to dataclass."""
        from llamatrade.v1 import trading_pb2

        side = "buy" if proto.side == trading_pb2.ORDER_SIDE_BUY else "sell"

        return BacktestTrade(
            symbol=proto.symbol,
            side=side,
            quantity=Decimal(proto.quantity.value) if proto.HasField("quantity") else Decimal("0"),
            entry_price=Decimal(proto.entry_price.value)
            if proto.HasField("entry_price")
            else Decimal("0"),
            exit_price=Decimal(proto.exit_price.value)
            if proto.HasField("exit_price")
            else Decimal("0"),
            entry_time=datetime.fromtimestamp(proto.entry_time.seconds),
            exit_time=datetime.fromtimestamp(proto.exit_time.seconds),
            pnl=Decimal(proto.pnl.value) if proto.HasField("pnl") else Decimal("0"),
            pnl_percent=Decimal(proto.pnl_percent.value)
            if proto.HasField("pnl_percent")
            else Decimal("0"),
            commission=Decimal(proto.commission.value)
            if proto.HasField("commission")
            else Decimal("0"),
            holding_period_bars=proto.holding_period_bars,
            entry_reason=proto.entry_reason,
            exit_reason=proto.exit_reason,
        )

    def _proto_to_progress_update(
        self,
        proto: backtest_pb2.BacktestProgressUpdate,
    ) -> BacktestProgressUpdate:
        """Convert protobuf BacktestProgressUpdate to dataclass."""
        from llamatrade.v1 import backtest_pb2

        status_map = {
            backtest_pb2.BACKTEST_STATUS_PENDING: BacktestStatus.PENDING,
            backtest_pb2.BACKTEST_STATUS_RUNNING: BacktestStatus.RUNNING,
            backtest_pb2.BACKTEST_STATUS_COMPLETED: BacktestStatus.COMPLETED,
            backtest_pb2.BACKTEST_STATUS_FAILED: BacktestStatus.FAILED,
            backtest_pb2.BACKTEST_STATUS_CANCELLED: BacktestStatus.CANCELLED,
        }

        partial_metrics = None
        if proto.HasField("partial_metrics"):
            partial_metrics = self._proto_to_metrics(proto.partial_metrics)

        return BacktestProgressUpdate(
            backtest_id=proto.backtest_id,
            status=status_map.get(proto.status, BacktestStatus.PENDING),
            progress_percent=proto.progress_percent,
            current_date=proto.current_date if proto.current_date else None,
            message=proto.message if proto.message else None,
            timestamp=datetime.fromtimestamp(proto.timestamp.seconds),
            partial_metrics=partial_metrics,
        )
