"""Tests for backtest service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from src.models import BacktestStatus
from src.services.backtest_service import BacktestService

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_BACKTEST_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def mock_strategy():
    """Create a mock strategy object."""
    strategy = MagicMock()
    strategy.id = TEST_STRATEGY_ID
    strategy.tenant_id = TEST_TENANT_ID
    strategy.current_version = 1
    return strategy


@pytest.fixture
def mock_strategy_version():
    """Create a mock strategy version object."""
    version = MagicMock()
    version.id = uuid4()
    version.strategy_id = TEST_STRATEGY_ID
    version.version = 1
    version.config_sexpr = """(strategy
        :name "Test"
        :symbols ["AAPL"]
        :timeframe "1D"
        :entry (> (sma close 10) (sma close 20))
        :exit (< (sma close 10) (sma close 20))
        :position-size 10)"""
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
    backtest.status = "pending"
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
        assert result.status == BacktestStatus.PENDING
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
            status=BacktestStatus.PENDING,
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
        mock_backtest.status = "pending"
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is True
        assert mock_backtest.status == "cancelled"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_running_backtest(self, mock_db, mock_backtest):
        """Test cancelling a running backtest."""
        mock_backtest.status = "running"
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.cancel_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is True
        assert mock_backtest.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_backtest_fails(self, mock_db, mock_backtest):
        """Test that completed backtests cannot be cancelled."""
        mock_backtest.status = "completed"
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
        mock_backtest.status = "failed"
        mock_backtest.error_message = "Previous error"
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_backtest)
        )

        service = BacktestService(mock_db)
        result = await service.retry_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert result is not None
        assert mock_backtest.status == "pending"
        assert mock_backtest.error_message is None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_retry_non_failed_backtest_raises(self, mock_db, mock_backtest):
        """Test that retrying non-failed backtest raises error."""
        mock_backtest.status = "completed"
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
        mock_backtest.status = "completed"
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
        mock_backtest.status = "pending"

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
            await service.run_backtest(TEST_BACKTEST_ID, TEST_TENANT_ID)

        assert "No market data" in str(exc_info.value)
        assert mock_backtest.status == "failed"


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
