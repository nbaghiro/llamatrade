"""Tests for backtest service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)

from src.services.backtest_service import BacktestService, warmup_padding_days

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_BACKTEST_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def mock_strategy():
    """Create a mock strategy object."""
    from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ACTIVE

    strategy = MagicMock()
    strategy.id = TEST_STRATEGY_ID
    strategy.tenant_id = TEST_TENANT_ID
    strategy.current_version = 1
    strategy.status = STRATEGY_STATUS_ACTIVE
    return strategy


@pytest.fixture
def mock_strategy_version():
    """Create a mock strategy version object."""
    version = MagicMock()
    version.id = uuid4()
    version.strategy_id = TEST_STRATEGY_ID
    version.version = 1
    # Use allocation-based DSL format expected by strategy_adapter
    version.config_sexpr = (
        '(strategy "Test" :benchmark SPY :rebalance daily (asset AAPL :weight 100))'
    )
    version.timeframe = "1D"
    version.symbols = ["AAPL"]
    return version


@pytest.fixture
def mock_backtest():
    """Create a mock backtest object."""
    backtest = MagicMock()
    backtest.id = TEST_BACKTEST_ID
    backtest.tenant_id = TEST_TENANT_ID
    backtest.strategy_id = TEST_STRATEGY_ID
    backtest.strategy_version = 1
    backtest.name = "Test Backtest"
    backtest.status = BACKTEST_STATUS_PENDING
    backtest.config = {"commission": 0.001, "slippage": 0.001}
    backtest.symbols = ["AAPL"]
    backtest.start_date = date(2024, 1, 1)
    backtest.end_date = date(2024, 6, 30)
    backtest.initial_capital = Decimal("100000")
    backtest.created_by = TEST_USER_ID
    backtest.created_at = datetime.now(UTC)
    backtest.started_at = None
    backtest.completed_at = None
    backtest.error_message = None
    return backtest


class TestBacktestServiceCreate:
    """Tests for create_backtest method."""

    @pytest.mark.asyncio
    async def test_create_backtest_success(self, mock_db, mock_strategy, mock_strategy_version):
        """Test successful backtest creation."""
        # Setup mocks
        mock_db.execute.side_effect = [
            # First call: _get_strategy
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            # Second call: _get_strategy_version
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        # Track what gets added to mock the refresh populating id/created_at
        added_backtest = None

        def capture_add(obj):
            nonlocal added_backtest
            added_backtest = obj
            # Simulate database populating fields
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        result = await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
        )

        assert result is not None
        assert result.strategy_id == TEST_STRATEGY_ID
        assert result.status == BACKTEST_STATUS_PENDING
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backtest_invalid_date_range(self, mock_db):
        """Test that end_date <= start_date raises error."""
        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 6, 30),
                end_date=date(2024, 1, 1),  # Before start
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
            )

        assert "End date must be after start date" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_backtest_strategy_not_found(self, mock_db):
        """Test that missing strategy raises error."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_backtest_version_not_found(self, mock_db, mock_strategy):
        """Test that missing strategy version raises error."""
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # Version not found
        ]

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=99,  # Non-existent version
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
            )

        assert "version" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_backtest_no_symbols(self, mock_db, mock_strategy):
        """Test that no symbols raises error."""
        mock_strategy_version = MagicMock()
        mock_strategy_version.symbols = []

        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=None,  # No symbols provided
                commission=0.001,
                slippage=0.001,
            )

        assert "No symbols" in str(exc_info.value)


class TestBacktestServiceGet:
    """Tests for get_backtest method."""

    @pytest.mark.asyncio
    async def test_get_backtest_success(self, mock_db, mock_backtest):
        """Test successful backtest retrieval."""
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.get_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is not None
        assert result.id == TEST_BACKTEST_ID
        assert result.strategy_id == TEST_STRATEGY_ID

    @pytest.mark.asyncio
    async def test_get_backtest_not_found(self, mock_db):
        """Test backtest not found returns None."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)
        result = await service.get_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_backtest_tenant_isolation(self, mock_db, mock_backtest):
        """Test that backtests are filtered by tenant."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)
        other_tenant = uuid4()
        result = await service.get_backtest(TEST_BACKTEST_ID, other_tenant)

        assert result is None


class TestBacktestServiceList:
    """Tests for list_backtests method."""

    @pytest.mark.asyncio
    async def test_list_backtests_success(self, mock_db, mock_backtest):
        """Test successful backtest listing."""
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=5)),  # Total count
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[mock_backtest]))
                )
            ),
        ]

        service = BacktestService(mock_db)
        backtests, total = await service.list_backtests(TEST_TENANT_ID)

        assert total == 5
        assert len(backtests) == 1
        assert backtests[0].id == TEST_BACKTEST_ID

    @pytest.mark.asyncio
    async def test_list_backtests_with_filters(self, mock_db, mock_backtest):
        """Test listing with status filter."""
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=1)),
            MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[mock_backtest]))
                )
            ),
        ]

        service = BacktestService(mock_db)
        backtests, total = await service.list_backtests(
            TEST_TENANT_ID,
            strategy_id=TEST_STRATEGY_ID,
            status=BACKTEST_STATUS_PENDING,
        )

        assert total == 1
        assert len(backtests) == 1

    @pytest.mark.asyncio
    async def test_list_backtests_pagination(self, mock_db):
        """Test pagination parameters."""
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=100)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]

        service = BacktestService(mock_db)
        _, total = await service.list_backtests(
            TEST_TENANT_ID,
            page=5,
            page_size=10,
        )

        assert total == 100


class TestBacktestServiceCancel:
    """Tests for cancel_backtest method."""

    @pytest.mark.asyncio
    async def test_cancel_pending_backtest(self, mock_db, mock_backtest):
        """Test cancelling a pending backtest."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is True
        assert mock_backtest.status == BACKTEST_STATUS_CANCELLED
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_running_backtest(self, mock_db, mock_backtest):
        """Test cancelling a running backtest."""
        mock_backtest.status = BACKTEST_STATUS_RUNNING
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is True
        assert mock_backtest.status == BACKTEST_STATUS_CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_backtest_fails(self, mock_db, mock_backtest):
        """Test that completed backtests cannot be cancelled."""
        mock_backtest.status = BACKTEST_STATUS_COMPLETED
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, mock_db):
        """Test cancelling non-existent backtest."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is False


class TestBacktestServiceRetry:
    """Tests for retry_backtest method."""

    @pytest.mark.asyncio
    async def test_retry_failed_backtest(self, mock_db, mock_backtest):
        """Test retrying a failed backtest."""
        mock_backtest.status = BACKTEST_STATUS_FAILED
        mock_backtest.error_message = "Previous error"
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.retry_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is not None
        assert mock_backtest.status == BACKTEST_STATUS_PENDING
        assert mock_backtest.error_message is None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_retry_non_failed_backtest_raises(self, mock_db, mock_backtest):
        """Test that retrying non-failed backtest raises error."""
        mock_backtest.status = BACKTEST_STATUS_COMPLETED
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.retry_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert "Only failed backtests" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_not_found(self, mock_db):
        """Test retrying non-existent backtest."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)
        result = await service.retry_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is None


class TestBacktestServiceRun:
    """Tests for run_backtest method."""

    @pytest.mark.asyncio
    async def test_run_backtest_not_pending_raises(self, mock_db, mock_backtest):
        """Test that running non-pending backtest raises error."""
        mock_backtest.status = BACKTEST_STATUS_COMPLETED
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert "cannot run" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_run_backtest_not_found_raises(self, mock_db):
        """Test that running non-existent backtest raises error."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_run_backtest_no_market_data(self, mock_db, mock_backtest, mock_strategy_version):
        """Test that missing market data raises error and sets failed status."""
        mock_backtest.status = BACKTEST_STATUS_PENDING

        # Setup mock returns
        mock_db.execute.side_effect = [
            # First call: get backtest
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            # Second call: get strategy version
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = {}  # No data

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(ValueError) as exc_info:
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert "No market data" in str(exc_info.value)
        assert mock_backtest.status == BACKTEST_STATUS_FAILED


class TestBacktestServiceResults:
    """Tests for get_results method."""

    @pytest.mark.asyncio
    async def test_get_results_not_found(self, mock_db, mock_backtest):
        """Test getting results for backtest with no results."""
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # No result
        ]

        service = BacktestService(mock_db)
        result = await service.get_results(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_results_backtest_not_found(self, mock_db):
        """Test getting results when backtest doesn't exist."""
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        service = BacktestService(mock_db)
        result = await service.get_results(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is None


class TestBacktestServiceTimeframe:
    """Tests for timeframe selection (Phase 1)."""

    @pytest.mark.asyncio
    async def test_create_backtest_with_timeframe(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test creating backtest with explicit timeframe."""
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        added_backtest = None

        def capture_add(obj):
            nonlocal added_backtest
            added_backtest = obj
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
            timeframe="1H",  # Explicit hourly timeframe
        )

        assert added_backtest is not None
        assert added_backtest.config["timeframe"] == "1H"

    @pytest.mark.asyncio
    async def test_create_backtest_invalid_timeframe(self, mock_db):
        """Test that invalid timeframe raises error."""
        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
                timeframe="invalid",
            )

        assert "Invalid timeframe" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_backtest_uses_strategy_timeframe(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test that strategy timeframe is used when not provided."""
        mock_strategy_version.timeframe = "4H"

        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        added_backtest = None

        def capture_add(obj):
            nonlocal added_backtest
            added_backtest = obj
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
            timeframe=None,  # No explicit timeframe
        )

        assert added_backtest is not None
        assert added_backtest.config["timeframe"] == "4H"


class TestBacktestServiceBenchmark:
    """Tests for benchmark configuration (Phase 2)."""

    @pytest.mark.asyncio
    async def test_create_backtest_with_benchmark(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test creating backtest with custom benchmark."""
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        added_backtest = None

        def capture_add(obj):
            nonlocal added_backtest
            added_backtest = obj
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
            benchmark_symbol="QQQ",
            include_benchmark=True,
        )

        assert added_backtest is not None
        assert added_backtest.config["benchmark_symbol"] == "QQQ"
        assert added_backtest.config["include_benchmark"] is True

    @pytest.mark.asyncio
    async def test_create_backtest_without_benchmark(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test creating backtest with benchmark disabled."""
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        added_backtest = None

        def capture_add(obj):
            nonlocal added_backtest
            added_backtest = obj
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
            include_benchmark=False,
        )

        assert added_backtest is not None
        assert added_backtest.config["include_benchmark"] is False


class TestWarmupPadding:
    """Tests for warm-up padding day calculation."""

    def test_zero_min_bars_needs_no_padding(self):
        assert warmup_padding_days("1D", 0) == 0

    def test_daily_padding_covers_lookback(self):
        """SMA-200 on daily bars needs at least 200 trading days of padding."""
        padding = warmup_padding_days("1D", 200)
        assert padding >= 200 * 1.5  # weekends/holidays buffer

    def test_weekly_padding_scales_by_week(self):
        assert warmup_padding_days("1W", 10) >= 10 * 5

    def test_intraday_padding_is_compact(self):
        """390 one-minute bars fit in a single trading day."""
        padding = warmup_padding_days("1Min", 390)
        assert padding <= 10

    def test_padding_monotonic_in_min_bars(self):
        assert warmup_padding_days("1D", 50) <= warmup_padding_days("1D", 200)


class TestFetchSymbolHandling:
    """Tests for symbol handling in the combined fetch (replaces N+1 validation)."""

    @pytest.mark.asyncio
    async def test_missing_strategy_symbol_fails_with_names(
        self, mock_db, mock_backtest, mock_strategy_version
    ):
        """Symbols with no data must fail the run, naming the symbols."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        # Fetch succeeds but returns no bars for AAPL
        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = {"AAPL": [], "SPY": [{"close": 400}]}

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(ValueError) as exc_info:
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert "AAPL" in str(exc_info.value)
        assert mock_backtest.status == BACKTEST_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_fetch_is_single_combined_call_with_padding(
        self, mock_db, mock_backtest, mock_strategy_version
    ):
        """One combined fetch, with the start date extended for warm-up."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = {}

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(ValueError):
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert mock_market_client.fetch_bars.call_count == 1
        call_kwargs = mock_market_client.fetch_bars.call_args.kwargs
        assert call_kwargs["start_date"] <= mock_backtest.start_date
        # Strategy symbols and benchmark are fetched together
        assert "AAPL" in call_kwargs["symbols"]
        assert "SPY" in call_kwargs["symbols"]

    @pytest.mark.asyncio
    async def test_corrupt_bars_fail_validation(
        self, mock_db, mock_backtest, mock_strategy_version
    ):
        """OHLC-inconsistent data must abort the run with a validation error."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        corrupt_bar = {
            "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
            "open": 100.0,
            "high": 90.0,  # high < open: invalid
            "low": 99.0,
            "close": 100.0,
            "volume": 1000,
        }
        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = {
            "AAPL": [corrupt_bar],
            "SPY": [corrupt_bar],
        }

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(ValueError, match="validation failed"):
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert mock_backtest.status == BACKTEST_STATUS_FAILED


class TestTimeframeMapping:
    """Tests for gRPC timeframe mapping."""

    @pytest.mark.asyncio
    async def test_unknown_timeframe_raises(self):
        """Unknown timeframes must raise, not silently map to daily."""
        from src.services.backtest_service import GRPCMarketDataClient, MarketDataError

        client = GRPCMarketDataClient("unused:1")

        with pytest.raises(MarketDataError, match="Unsupported timeframe"):
            await client.fetch_bars(
                symbols=["AAPL"],
                timeframe="2Min",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )


class TestBacktestServiceStrategyStatus:
    """Tests for strategy status enforcement."""

    @pytest.mark.asyncio
    async def test_create_backtest_rejects_draft_strategy(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test that DRAFT strategies cannot be backtested."""
        from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_DRAFT

        mock_strategy.status = STRATEGY_STATUS_DRAFT
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_strategy)
        )

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
            )

        assert "STRATEGY_STATUS_DRAFT" in str(exc_info.value)
        assert "ACTIVE or PAUSED" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_backtest_rejects_archived_strategy(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test that ARCHIVED strategies cannot be backtested."""
        from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ARCHIVED

        mock_strategy.status = STRATEGY_STATUS_ARCHIVED
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_strategy)
        )

        service = BacktestService(mock_db)

        with pytest.raises(ValueError) as exc_info:
            await service.create_backtest(
                tenant_id=TEST_TENANT_ID,
                user_id=TEST_USER_ID,
                strategy_id=TEST_STRATEGY_ID,
                strategy_version=None,
                name="Test Backtest",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=100000.0,
                symbols=["AAPL"],
                commission=0.001,
                slippage=0.001,
            )

        assert "STRATEGY_STATUS_ARCHIVED" in str(exc_info.value)
        assert "ACTIVE or PAUSED" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_backtest_allows_active_strategy(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test that ACTIVE strategies can be backtested."""
        from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ACTIVE

        mock_strategy.status = STRATEGY_STATUS_ACTIVE
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        def capture_add(obj):
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        result = await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
        )

        assert result is not None
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backtest_allows_paused_strategy(
        self, mock_db, mock_strategy, mock_strategy_version
    ):
        """Test that PAUSED strategies can be backtested."""
        from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_PAUSED

        mock_strategy.status = STRATEGY_STATUS_PAUSED
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        def capture_add(obj):
            obj.id = TEST_BACKTEST_ID
            obj.created_at = datetime.now(UTC)

        mock_db.add.side_effect = capture_add

        service = BacktestService(mock_db)

        result = await service.create_backtest(
            tenant_id=TEST_TENANT_ID,
            user_id=TEST_USER_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=None,
            name="Test Backtest",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            symbols=["AAPL"],
            commission=0.001,
            slippage=0.001,
        )

        assert result is not None
        mock_db.add.assert_called_once()


class TestZeroVsNullSemantics:
    """Zero is a value; NULL means unavailable (decision 7A)."""

    @staticmethod
    def _flat_bars(symbol_close: dict[str, float], days: int = 12) -> dict:
        out = {}
        for symbol, close in symbol_close.items():
            out[symbol] = [
                {
                    "timestamp": datetime(2024, 1, 1, 16, tzinfo=UTC)
                    + __import__("datetime").timedelta(days=i),
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1000,
                }
                for i in range(days)
            ]
        return out

    @pytest.mark.asyncio
    async def test_flat_benchmark_zero_return_stored_as_zero_not_null(
        self, mock_db, mock_backtest, mock_strategy_version
    ):
        """A 0.0 benchmark return (flat market) must persist as 0.0."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        saved = []
        mock_db.add.side_effect = saved.append

        async def fake_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = self._flat_bars({"AAPL": 150.0, "SPY": 400.0})

        service = BacktestService(mock_db, market_data_client=mock_market_client)
        response = await service.run_backtest(
            TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False
        )

        assert len(saved) == 1
        stored = saved[0]
        # Flat SPY → benchmark return is exactly 0.0 and must NOT be NULL
        assert stored.benchmark_return is not None
        assert float(stored.benchmark_return) == pytest.approx(0.0)
        # Availability is derived from is-not-None, so it must be True
        assert response.metrics.benchmark_data_available is True
        assert response.metrics.benchmark_return == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_stored_equity_curve_is_daily_within_window(
        self, mock_db, mock_backtest, mock_strategy_version
    ):
        """Persisted equity curve excludes warm-up days and is daily-resampled."""
        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_backtest.start_date = date(2024, 1, 5)
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        saved = []
        mock_db.add.side_effect = saved.append

        async def fake_refresh(obj):
            obj.id = uuid4()
            obj.created_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = self._flat_bars({"AAPL": 150.0, "SPY": 400.0})

        service = BacktestService(mock_db, market_data_client=mock_market_client)
        await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        stored = saved[0]
        curve_dates = [point["date"] for point in stored.equity_curve]
        assert curve_dates == sorted(curve_dates)
        # Bars start Jan 1 but the window starts Jan 5: warm-up days excluded
        assert all(d >= "2024-01-05" for d in curve_dates)
        # One point per day
        assert len({d[:10] for d in curve_dates}) == len(curve_dates)


class TestEquityCurveCap:
    """Storage backstop for pathological curve sizes."""

    def test_short_curve_unchanged(self):
        from src.services.backtest_service import _cap_equity_curve

        curve = [(datetime(2024, 1, 1, tzinfo=UTC), 100.0 + i) for i in range(100)]
        assert _cap_equity_curve(curve) == curve

    def test_long_curve_capped_and_keeps_last_point(self):
        from src.services.backtest_service import _MAX_STORED_EQUITY_POINTS, _cap_equity_curve

        n = _MAX_STORED_EQUITY_POINTS * 3 + 7
        curve = [
            (
                datetime(2024, 1, 1, tzinfo=UTC) + __import__("datetime").timedelta(minutes=i),
                float(i),
            )
            for i in range(n)
        ]
        capped = _cap_equity_curve(curve)
        assert len(capped) <= _MAX_STORED_EQUITY_POINTS + 1
        assert capped[0] == curve[0]
        assert capped[-1] == curve[-1]


class TestCancellationFlow:
    """Cooperative cancellation through the service layer."""

    @pytest.mark.asyncio
    async def test_cancelled_run_ends_cancelled_not_failed(
        self, mock_db, mock_backtest, mock_strategy_version, monkeypatch
    ):
        """A run aborted by the cancel flag must end CANCELLED, not FAILED."""
        from src.engine.backtester import BacktestCancelled

        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        bars = TestZeroVsNullSemantics._flat_bars({"AAPL": 150.0, "SPY": 400.0})
        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = bars

        # Cancel flag fires immediately
        monkeypatch.setattr(
            "src.services.backtest_service.CancellationFlag.make_should_abort",
            lambda self, backtest_id, check_interval=1.0: lambda: True,
        )

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(BacktestCancelled):
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert mock_backtest.status == BACKTEST_STATUS_CANCELLED
        assert mock_db.add.call_count == 0  # no result row persisted

    @pytest.mark.asyncio
    async def test_completed_run_does_not_clobber_cancelled_status(
        self, mock_db, mock_backtest, mock_strategy_version, monkeypatch
    ):
        """If the row turns CANCELLED while finishing, keep CANCELLED."""
        from src.engine.backtester import BacktestCancelled

        mock_backtest.status = BACKTEST_STATUS_PENDING
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_backtest)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=mock_strategy_version)),
        ]

        bars = TestZeroVsNullSemantics._flat_bars({"AAPL": 150.0, "SPY": 400.0})
        mock_market_client = AsyncMock()
        mock_market_client.fetch_bars.return_value = bars

        # Simulate a cancel landing mid-run: the pre-save refresh observes it
        async def refresh_sets_cancelled(obj):
            obj.status = BACKTEST_STATUS_CANCELLED

        mock_db.refresh = AsyncMock(side_effect=refresh_sets_cancelled)

        service = BacktestService(mock_db, market_data_client=mock_market_client)

        with pytest.raises(BacktestCancelled):
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID, publish_progress=False)

        assert mock_backtest.status == BACKTEST_STATUS_CANCELLED
        assert mock_db.add.call_count == 0  # result discarded

    @pytest.mark.asyncio
    async def test_cancel_backtest_sets_redis_flag(self, mock_db, mock_backtest, monkeypatch):
        """cancel_backtest must signal the worker via the cancellation flag."""
        mock_backtest.status = BACKTEST_STATUS_RUNNING
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        flagged: list[str] = []

        async def fake_request_cancel(self, backtest_id):
            flagged.append(backtest_id)

        monkeypatch.setattr(
            "src.services.backtest_service.CancellationFlag.request_cancel",
            fake_request_cancel,
        )

        service = BacktestService(mock_db, market_data_client=AsyncMock())
        cancelled = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert cancelled is True
        assert mock_backtest.status == BACKTEST_STATUS_CANCELLED
        assert flagged == [str(TEST_BACKTEST_ID)]


class TestParallelFetching:
    """Concurrent per-symbol fetching in GRPCMarketDataClient."""

    @staticmethod
    def _make_client_with_fake_grpc(fetch_fn):
        from src.services.backtest_service import GRPCMarketDataClient

        client = GRPCMarketDataClient("unused:1")
        fake_grpc = MagicMock()
        fake_grpc.get_historical_bars = fetch_fn
        client._client = fake_grpc
        return client

    @pytest.mark.asyncio
    async def test_symbols_fetched_concurrently_with_cap(self):
        """Fetches overlap (not sequential) but never exceed the semaphore cap."""
        import asyncio

        from src.services.backtest_service import MARKET_DATA_FETCH_CONCURRENCY

        active = 0
        max_active = 0

        async def slow_fetch(symbol, start, end, timeframe):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return []

        client = self._make_client_with_fake_grpc(slow_fetch)
        symbols = [f"SYM{i}" for i in range(20)]

        result = await client.fetch_bars(
            symbols=symbols,
            timeframe="1D",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert set(result) == set(symbols)
        assert max_active > 1, "fetches ran sequentially"
        assert max_active <= MARKET_DATA_FETCH_CONCURRENCY

    @pytest.mark.asyncio
    async def test_partial_failures_aggregate_symbol_names(self):
        """One failing symbol must produce an error naming it."""
        from src.services.backtest_service import MarketDataError

        async def flaky_fetch(symbol, start, end, timeframe):
            if symbol in ("BAD1", "BAD2"):
                raise RuntimeError(f"upstream error for {symbol}")
            return []

        client = self._make_client_with_fake_grpc(flaky_fetch)

        with pytest.raises(MarketDataError) as exc_info:
            await client.fetch_bars(
                symbols=["GOOD", "BAD1", "BAD2"],
                timeframe="1D",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
            )

        assert "BAD1" in str(exc_info.value)
        assert "BAD2" in str(exc_info.value)
