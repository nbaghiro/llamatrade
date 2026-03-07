"""Tests for llamatrade_proto.clients.backtest module."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.auth import TenantContext
from llamatrade_proto.clients.backtest import (
    BacktestClient,
    BacktestConfig,
    BacktestMetrics,
    BacktestProgressUpdate,
    BacktestResults,
    BacktestRun,
    BacktestStatus,
    BacktestTrade,
    EquityPoint,
)


class TestBacktestStatus:
    """Tests for BacktestStatus enum."""

    def test_backtest_status_values(self) -> None:
        """Test BacktestStatus enum values."""
        assert BacktestStatus.PENDING.value == "pending"
        assert BacktestStatus.RUNNING.value == "running"
        assert BacktestStatus.COMPLETED.value == "completed"
        assert BacktestStatus.FAILED.value == "failed"
        assert BacktestStatus.CANCELLED.value == "cancelled"

    def test_backtest_status_count(self) -> None:
        """Test BacktestStatus has expected number of values."""
        assert len(BacktestStatus) == 5


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass."""

    def test_create_config_minimal(self) -> None:
        """Test creating BacktestConfig with required fields."""
        config = BacktestConfig(
            strategy_id="strat-123",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            initial_capital=Decimal("100000"),
            symbols=["AAPL", "GOOGL"],
        )

        assert config.strategy_id == "strat-123"
        assert config.start_date == datetime(2023, 1, 1)
        assert config.end_date == datetime(2024, 1, 1)
        assert config.initial_capital == Decimal("100000")
        assert config.symbols == ["AAPL", "GOOGL"]
        # Check defaults
        assert config.strategy_version == 1
        assert config.commission == Decimal("0")
        assert config.slippage_percent == Decimal("0")
        assert config.allow_shorting is False
        assert config.max_position_size == Decimal("1.0")
        assert config.timeframe == "1D"
        assert config.use_adjusted_prices is True
        assert config.parameters == {}

    def test_create_config_full(self) -> None:
        """Test creating BacktestConfig with all fields."""
        config = BacktestConfig(
            strategy_id="strat-456",
            start_date=datetime(2023, 6, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=Decimal("50000"),
            symbols=["TSLA"],
            strategy_version=3,
            commission=Decimal("0.001"),
            slippage_percent=Decimal("0.0005"),
            allow_shorting=True,
            max_position_size=Decimal("0.25"),
            timeframe="1H",
            use_adjusted_prices=False,
            parameters={"rsi_period": "14", "rsi_threshold": "30"},
        )

        assert config.strategy_version == 3
        assert config.commission == Decimal("0.001")
        assert config.allow_shorting is True
        assert config.timeframe == "1H"
        assert config.parameters["rsi_period"] == "14"


class TestBacktestMetrics:
    """Tests for BacktestMetrics dataclass."""

    def test_create_metrics(self) -> None:
        """Test creating BacktestMetrics."""
        metrics = BacktestMetrics(
            total_return=Decimal("0.25"),
            annualized_return=Decimal("0.30"),
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            max_drawdown=Decimal("-0.15"),
            max_drawdown_duration_days=Decimal("45"),
            volatility=Decimal("0.20"),
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=Decimal("0.60"),
            average_win=Decimal("500"),
            average_loss=Decimal("-300"),
            profit_factor=Decimal("2.5"),
            expectancy=Decimal("150"),
            starting_capital=Decimal("100000"),
            ending_capital=Decimal("125000"),
            total_commission=Decimal("500"),
        )

        assert metrics.total_return == Decimal("0.25")
        assert metrics.sharpe_ratio == Decimal("1.5")
        assert metrics.total_trades == 100
        assert metrics.win_rate == Decimal("0.60")
        assert metrics.benchmark_return is None
        assert metrics.alpha is None
        assert metrics.beta is None

    def test_create_metrics_with_benchmark(self) -> None:
        """Test creating BacktestMetrics with benchmark data."""
        metrics = BacktestMetrics(
            total_return=Decimal("0.25"),
            annualized_return=Decimal("0.30"),
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            max_drawdown=Decimal("-0.15"),
            max_drawdown_duration_days=Decimal("45"),
            volatility=Decimal("0.20"),
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=Decimal("0.60"),
            average_win=Decimal("500"),
            average_loss=Decimal("-300"),
            profit_factor=Decimal("2.5"),
            expectancy=Decimal("150"),
            starting_capital=Decimal("100000"),
            ending_capital=Decimal("125000"),
            total_commission=Decimal("500"),
            benchmark_return=Decimal("0.15"),
            alpha=Decimal("0.10"),
            beta=Decimal("0.85"),
        )

        assert metrics.benchmark_return == Decimal("0.15")
        assert metrics.alpha == Decimal("0.10")
        assert metrics.beta == Decimal("0.85")


class TestEquityPoint:
    """Tests for EquityPoint dataclass."""

    def test_create_equity_point(self) -> None:
        """Test creating EquityPoint."""
        point = EquityPoint(
            timestamp=datetime(2024, 1, 15, 16, 0, 0),
            equity=Decimal("105000"),
            cash=Decimal("50000"),
            positions_value=Decimal("55000"),
            daily_return=Decimal("0.005"),
            drawdown=Decimal("-0.02"),
        )

        assert point.timestamp == datetime(2024, 1, 15, 16, 0, 0)
        assert point.equity == Decimal("105000")
        assert point.cash == Decimal("50000")
        assert point.positions_value == Decimal("55000")
        assert point.daily_return == Decimal("0.005")
        assert point.drawdown == Decimal("-0.02")


class TestBacktestTrade:
    """Tests for BacktestTrade dataclass."""

    def test_create_backtest_trade_long(self) -> None:
        """Test creating a long BacktestTrade."""
        trade = BacktestTrade(
            symbol="AAPL",
            side="buy",
            quantity=Decimal("100"),
            entry_price=Decimal("150.00"),
            exit_price=Decimal("160.00"),
            entry_time=datetime(2024, 1, 10, 10, 0, 0),
            exit_time=datetime(2024, 1, 15, 14, 0, 0),
            pnl=Decimal("1000.00"),
            pnl_percent=Decimal("6.67"),
            commission=Decimal("5.00"),
            holding_period_bars=5,
            entry_reason="RSI oversold",
            exit_reason="Take profit",
        )

        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.pnl == Decimal("1000.00")
        assert trade.entry_reason == "RSI oversold"

    def test_create_backtest_trade_short(self) -> None:
        """Test creating a short BacktestTrade."""
        trade = BacktestTrade(
            symbol="TSLA",
            side="sell",
            quantity=Decimal("50"),
            entry_price=Decimal("200.00"),
            exit_price=Decimal("180.00"),
            entry_time=datetime(2024, 1, 5, 10, 0, 0),
            exit_time=datetime(2024, 1, 8, 14, 0, 0),
            pnl=Decimal("1000.00"),
            pnl_percent=Decimal("10.00"),
            commission=Decimal("3.00"),
            holding_period_bars=3,
            entry_reason="Bearish signal",
            exit_reason="Stop loss",
        )

        assert trade.side == "sell"


class TestBacktestResults:
    """Tests for BacktestResults dataclass."""

    def test_create_results(self) -> None:
        """Test creating BacktestResults."""
        metrics = BacktestMetrics(
            total_return=Decimal("0.25"),
            annualized_return=Decimal("0.30"),
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            max_drawdown=Decimal("-0.15"),
            max_drawdown_duration_days=Decimal("45"),
            volatility=Decimal("0.20"),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=Decimal("0.60"),
            average_win=Decimal("500"),
            average_loss=Decimal("-300"),
            profit_factor=Decimal("2.5"),
            expectancy=Decimal("150"),
            starting_capital=Decimal("100000"),
            ending_capital=Decimal("125000"),
            total_commission=Decimal("50"),
        )

        equity_curve = [
            EquityPoint(
                timestamp=datetime(2024, 1, 15),
                equity=Decimal("100000"),
                cash=Decimal("100000"),
                positions_value=Decimal("0"),
                daily_return=Decimal("0"),
                drawdown=Decimal("0"),
            )
        ]

        trades: list[BacktestTrade] = []

        results = BacktestResults(
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            monthly_returns={"2024-01": 0.05},
        )

        assert results.metrics is metrics
        assert len(results.equity_curve) == 1
        assert len(results.trades) == 0
        assert results.monthly_returns["2024-01"] == 0.05


class TestBacktestRun:
    """Tests for BacktestRun dataclass."""

    def test_create_run_pending(self) -> None:
        """Test creating pending BacktestRun."""
        config = BacktestConfig(
            strategy_id="strat-123",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            initial_capital=Decimal("100000"),
            symbols=["AAPL"],
        )

        run = BacktestRun(
            id="backtest-123",
            tenant_id="tenant-456",
            strategy_id="strat-123",
            strategy_version=1,
            config=config,
            status=BacktestStatus.PENDING,
            status_message=None,
            progress_percent=0,
            current_date=None,
            results=None,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            started_at=None,
            completed_at=None,
        )

        assert run.id == "backtest-123"
        assert run.status == BacktestStatus.PENDING
        assert run.progress_percent == 0
        assert run.results is None


class TestBacktestProgressUpdate:
    """Tests for BacktestProgressUpdate dataclass."""

    def test_create_progress_update(self) -> None:
        """Test creating BacktestProgressUpdate."""
        update = BacktestProgressUpdate(
            backtest_id="backtest-123",
            status=BacktestStatus.RUNNING,
            progress_percent=50,
            current_date="2023-06-15",
            message="Processing June 2023",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            partial_metrics=None,
        )

        assert update.backtest_id == "backtest-123"
        assert update.status == BacktestStatus.RUNNING
        assert update.progress_percent == 50
        assert update.current_date == "2023-06-15"
        assert update.partial_metrics is None


class TestBacktestClientInit:
    """Tests for BacktestClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test BacktestClient initialization with defaults."""
        client = BacktestClient()

        assert client._target == "backtest:8830"
        assert client._secure is False
        assert client._stub is None

    def test_init_with_custom_target(self) -> None:
        """Test BacktestClient initialization with custom target."""
        client = BacktestClient("localhost:9000")

        assert client._target == "localhost:9000"

    def test_init_with_secure(self) -> None:
        """Test BacktestClient initialization with secure=True."""
        client = BacktestClient(secure=True)

        assert client._secure is True


class TestBacktestClientStub:
    """Tests for BacktestClient stub property."""

    def test_stub_raises_on_missing_generated_code(self) -> None:
        """Test stub raises RuntimeError when generated code is missing."""
        client = BacktestClient()

        with patch("grpc.aio.insecure_channel"):
            with patch.dict("sys.modules", {"llamatrade_proto.generated": None}):
                with pytest.raises((RuntimeError, ImportError)):
                    _ = client.stub


class TestBacktestClientRunBacktest:
    """Tests for BacktestClient.run_backtest method."""

    @pytest.mark.asyncio
    async def test_run_backtest_success(self) -> None:
        """Test run_backtest returns BacktestRun."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        config = BacktestConfig(
            strategy_id="strat-123",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            initial_capital=Decimal("100000"),
            symbols=["AAPL"],
        )

        # Create mock proto backtest
        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_backtest = MagicMock()
        mock_backtest.id = "backtest-123"
        mock_backtest.tenant_id = "tenant-123"
        mock_backtest.strategy_id = "strat-123"
        mock_backtest.strategy_version = 1
        mock_backtest.status = 1  # PENDING
        mock_backtest.status_message = ""
        mock_backtest.progress_percent = 0
        mock_backtest.current_date = ""
        mock_backtest.created_at = mock_created_at
        mock_backtest.HasField = lambda field: field in ["created_at"]

        mock_response = MagicMock()
        mock_response.backtest = mock_backtest

        mock_stub = MagicMock()
        mock_stub.RunBacktest = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()
        mock_backtest_pb2.BACKTEST_STATUS_PENDING = 1
        mock_backtest_pb2.BACKTEST_STATUS_RUNNING = 2
        mock_backtest_pb2.BACKTEST_STATUS_COMPLETED = 3
        mock_backtest_pb2.BACKTEST_STATUS_FAILED = 4
        mock_backtest_pb2.BACKTEST_STATUS_CANCELLED = 5

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.run_backtest(ctx, config)

        mock_stub.RunBacktest.assert_called_once()
        assert result.id == "backtest-123"
        assert result.strategy_id == "strat-123"


class TestBacktestClientGetBacktest:
    """Tests for BacktestClient.get_backtest method."""

    @pytest.mark.asyncio
    async def test_get_backtest_success(self) -> None:
        """Test get_backtest returns BacktestRun."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_backtest = MagicMock()
        mock_backtest.id = "backtest-123"
        mock_backtest.tenant_id = "tenant-123"
        mock_backtest.strategy_id = "strat-123"
        mock_backtest.strategy_version = 1
        mock_backtest.status = 3  # COMPLETED
        mock_backtest.status_message = "Completed successfully"
        mock_backtest.progress_percent = 100
        mock_backtest.current_date = "2024-01-01"
        mock_backtest.created_at = mock_created_at
        mock_backtest.HasField = lambda field: field in ["created_at"]

        mock_response = MagicMock()
        mock_response.backtest = mock_backtest

        mock_stub = MagicMock()
        mock_stub.GetBacktest = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()
        mock_backtest_pb2.BACKTEST_STATUS_COMPLETED = 3

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.get_backtest(ctx, "backtest-123")

        mock_stub.GetBacktest.assert_called_once()
        assert result.id == "backtest-123"
        assert result.progress_percent == 100


class TestBacktestClientListBacktests:
    """Tests for BacktestClient.list_backtests method."""

    @pytest.mark.asyncio
    async def test_list_backtests_success(self) -> None:
        """Test list_backtests returns list of BacktestRun."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_backtest = MagicMock()
        mock_backtest.id = "backtest-123"
        mock_backtest.tenant_id = "tenant-123"
        mock_backtest.strategy_id = "strat-123"
        mock_backtest.strategy_version = 1
        mock_backtest.status = 1
        mock_backtest.status_message = ""
        mock_backtest.progress_percent = 0
        mock_backtest.current_date = ""
        mock_backtest.created_at = mock_created_at
        mock_backtest.HasField = lambda field: field in ["created_at"]

        mock_response = MagicMock()
        mock_response.backtests = [mock_backtest]

        mock_stub = MagicMock()
        mock_stub.ListBacktests = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()
        mock_backtest_pb2.BACKTEST_STATUS_PENDING = 1

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.list_backtests(ctx)

        mock_stub.ListBacktests.assert_called_once()
        assert len(result) == 1
        assert result[0].id == "backtest-123"

    @pytest.mark.asyncio
    async def test_list_backtests_empty(self) -> None:
        """Test list_backtests returns empty list."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_response = MagicMock()
        mock_response.backtests = []

        mock_stub = MagicMock()
        mock_stub.ListBacktests = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.list_backtests(ctx)

        assert result == []


class TestBacktestClientCancelBacktest:
    """Tests for BacktestClient.cancel_backtest method."""

    @pytest.mark.asyncio
    async def test_cancel_backtest_success(self) -> None:
        """Test cancel_backtest returns cancelled BacktestRun."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_backtest = MagicMock()
        mock_backtest.id = "backtest-123"
        mock_backtest.tenant_id = "tenant-123"
        mock_backtest.strategy_id = "strat-123"
        mock_backtest.strategy_version = 1
        mock_backtest.status = 5  # CANCELLED
        mock_backtest.status_message = "Cancelled by user"
        mock_backtest.progress_percent = 50
        mock_backtest.current_date = "2023-06-15"
        mock_backtest.created_at = mock_created_at
        mock_backtest.HasField = lambda field: field in ["created_at"]

        mock_response = MagicMock()
        mock_response.backtest = mock_backtest

        mock_stub = MagicMock()
        mock_stub.CancelBacktest = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()
        mock_backtest_pb2.BACKTEST_STATUS_CANCELLED = 5

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.cancel_backtest(ctx, "backtest-123")

        mock_stub.CancelBacktest.assert_called_once()
        assert result.id == "backtest-123"
        assert result.status_message == "Cancelled by user"


class TestBacktestClientCompareBacktests:
    """Tests for BacktestClient.compare_backtests method."""

    @pytest.mark.asyncio
    async def test_compare_backtests_success(self) -> None:
        """Test compare_backtests returns list of BacktestRun."""
        client = BacktestClient()
        ctx = TenantContext("tenant-123", "user-456", ["trader"])

        mock_created_at = MagicMock()
        mock_created_at.seconds = 1705320000

        mock_backtest1 = MagicMock()
        mock_backtest1.id = "backtest-123"
        mock_backtest1.tenant_id = "tenant-123"
        mock_backtest1.strategy_id = "strat-123"
        mock_backtest1.strategy_version = 1
        mock_backtest1.status = 3
        mock_backtest1.status_message = ""
        mock_backtest1.progress_percent = 100
        mock_backtest1.current_date = ""
        mock_backtest1.created_at = mock_created_at
        mock_backtest1.HasField = lambda field: field in ["created_at"]

        mock_backtest2 = MagicMock()
        mock_backtest2.id = "backtest-456"
        mock_backtest2.tenant_id = "tenant-123"
        mock_backtest2.strategy_id = "strat-123"
        mock_backtest2.strategy_version = 2
        mock_backtest2.status = 3
        mock_backtest2.status_message = ""
        mock_backtest2.progress_percent = 100
        mock_backtest2.current_date = ""
        mock_backtest2.created_at = mock_created_at
        mock_backtest2.HasField = lambda field: field in ["created_at"]

        mock_response = MagicMock()
        mock_response.backtests = [mock_backtest1, mock_backtest2]

        mock_stub = MagicMock()
        mock_stub.CompareBacktests = AsyncMock(return_value=mock_response)
        client._stub = mock_stub

        mock_backtest_pb2 = MagicMock()
        mock_backtest_pb2.BACKTEST_STATUS_COMPLETED = 3

        with patch.dict(
            "sys.modules",
            {
                "llamatrade_proto.generated": MagicMock(),
                "llamatrade_proto.generated.backtest_pb2": mock_backtest_pb2,
                "llamatrade_proto.generated.common_pb2": MagicMock(),
            },
        ):
            result = await client.compare_backtests(ctx, ["backtest-123", "backtest-456"])

        mock_stub.CompareBacktests.assert_called_once()
        assert len(result) == 2
        assert result[0].id == "backtest-123"
        assert result[1].id == "backtest-456"
