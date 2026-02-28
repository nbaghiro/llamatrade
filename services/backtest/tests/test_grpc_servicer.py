"""Tests for backtest gRPC servicer methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import grpc.aio
import pytest
from src.models import BacktestResponse, BacktestStatus

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_BACKTEST_ID = UUID("44444444-4444-4444-4444-444444444444")

pytestmark = pytest.mark.asyncio


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self) -> None:
        self.code = None
        self.details = None
        self._cancelled = False

    async def abort(self, code, details: str) -> None:
        """Mock abort that raises an exception."""
        self.code = code
        self.details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    def cancelled(self) -> bool:
        return self._cancelled


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def backtest_servicer():
    """Create a backtest servicer instance."""
    from src.grpc.servicer import BacktestServicer

    return BacktestServicer()


def make_mock_backtest(
    id: UUID = TEST_BACKTEST_ID,
    tenant_id: UUID = TEST_TENANT_ID,
    strategy_id: UUID = TEST_STRATEGY_ID,
    strategy_version: int = 1,
    status: BacktestStatus = BacktestStatus.PENDING,
    progress: float = 0.0,
    initial_capital: float = 100000.0,
    error_message: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> BacktestResponse:
    """Create a mock backtest response object."""
    return BacktestResponse(
        id=id,
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        status=status,
        progress=progress,
        initial_capital=initial_capital,
        error_message=error_message,
        start_date=start_date or datetime(2024, 1, 1, tzinfo=UTC),
        end_date=end_date or datetime(2024, 6, 30, tzinfo=UTC),
        created_at=created_at or datetime.now(UTC),
        started_at=started_at,
        completed_at=completed_at,
    )


class MockAsyncContextManager:
    """Mock async context manager for database sessions."""

    def __init__(self, service_mock):
        self.service_mock = service_mock

    async def __aenter__(self):
        return self.service_mock

    async def __aexit__(self, *args):
        pass


class TestRunBacktest:
    """Tests for RunBacktest gRPC method."""

    async def test_run_backtest_success(self, backtest_servicer, grpc_context):
        """Test successfully running a backtest."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtest = make_mock_backtest()

        # Mock the database session and service
        mock_service = MagicMock()
        mock_service.create_backtest = AsyncMock(return_value=mock_backtest)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.RunBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    config=backtest_pb2.BacktestConfig(
                        strategy_id=str(TEST_STRATEGY_ID),
                        strategy_version=1,
                        start_date=common_pb2.Timestamp(
                            seconds=int(datetime(2024, 1, 1).timestamp())
                        ),
                        end_date=common_pb2.Timestamp(
                            seconds=int(datetime(2024, 6, 30).timestamp())
                        ),
                        initial_capital=common_pb2.Decimal(value="100000"),
                    ),
                )

                response = await backtest_servicer.RunBacktest(request, grpc_context)

                assert response.backtest.id == str(TEST_BACKTEST_ID)
                assert response.backtest.status == backtest_pb2.BACKTEST_STATUS_PENDING

    async def test_run_backtest_invalid_argument(self, backtest_servicer, grpc_context):
        """Test running backtest with invalid arguments."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service.create_backtest = AsyncMock(side_effect=ValueError("Invalid strategy"))

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.RunBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    config=backtest_pb2.BacktestConfig(
                        strategy_id="invalid",
                        start_date=common_pb2.Timestamp(seconds=0),
                        end_date=common_pb2.Timestamp(seconds=0),
                        initial_capital=common_pb2.Decimal(value="100000"),
                    ),
                )

                with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                    await backtest_servicer.RunBacktest(request, grpc_context)

                assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestGetBacktest:
    """Tests for GetBacktest gRPC method."""

    async def test_get_backtest_success(self, backtest_servicer, grpc_context):
        """Test getting a backtest by ID."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtest = make_mock_backtest()

        mock_service = MagicMock()
        mock_service.get_backtest = AsyncMock(return_value=mock_backtest)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.GetBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(TEST_BACKTEST_ID),
                )

                response = await backtest_servicer.GetBacktest(request, grpc_context)

                assert response.backtest.id == str(TEST_BACKTEST_ID)
                mock_service.get_backtest.assert_called_once()

    async def test_get_backtest_not_found(self, backtest_servicer, grpc_context):
        """Test getting a nonexistent backtest returns NOT_FOUND."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_service = MagicMock()
        mock_service.get_backtest = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.GetBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(uuid4()),
                )

                with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                    await backtest_servicer.GetBacktest(request, grpc_context)

                assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestListBacktests:
    """Tests for ListBacktests gRPC method."""

    async def test_list_backtests_empty(self, backtest_servicer, grpc_context):
        """Test listing backtests returns empty list when none exist."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_service = MagicMock()
        mock_service.list_backtests = AsyncMock(return_value=([], 0))

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.ListBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                )

                response = await backtest_servicer.ListBacktests(request, grpc_context)

                assert len(response.backtests) == 0
                assert response.pagination.total_items == 0

    async def test_list_backtests_with_data(self, backtest_servicer, grpc_context):
        """Test listing backtests with data."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtests = [
            make_mock_backtest(id=uuid4()),
            make_mock_backtest(id=uuid4(), status=BacktestStatus.COMPLETED),
        ]

        mock_service = MagicMock()
        mock_service.list_backtests = AsyncMock(return_value=(mock_backtests, 2))

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.ListBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                )

                response = await backtest_servicer.ListBacktests(request, grpc_context)

                assert len(response.backtests) == 2
                assert response.pagination.total_items == 2

    async def test_list_backtests_filter_by_strategy(self, backtest_servicer, grpc_context):
        """Test filtering backtests by strategy ID."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtests = [make_mock_backtest()]

        mock_service = MagicMock()
        mock_service.list_backtests = AsyncMock(return_value=(mock_backtests, 1))

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.ListBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    strategy_id=str(TEST_STRATEGY_ID),
                )

                response = await backtest_servicer.ListBacktests(request, grpc_context)

                assert len(response.backtests) == 1
                # Verify the service was called with strategy_id
                mock_service.list_backtests.assert_called_once()

    async def test_list_backtests_filter_by_status(self, backtest_servicer, grpc_context):
        """Test filtering backtests by status."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtests = [make_mock_backtest(status=BacktestStatus.COMPLETED)]

        mock_service = MagicMock()
        mock_service.list_backtests = AsyncMock(return_value=(mock_backtests, 1))

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.ListBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    statuses=[backtest_pb2.BACKTEST_STATUS_COMPLETED],
                )

                response = await backtest_servicer.ListBacktests(request, grpc_context)

                assert len(response.backtests) == 1
                assert response.backtests[0].status == backtest_pb2.BACKTEST_STATUS_COMPLETED


class TestCancelBacktest:
    """Tests for CancelBacktest gRPC method."""

    async def test_cancel_backtest_success(self, backtest_servicer, grpc_context):
        """Test successfully cancelling a backtest."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtest = make_mock_backtest(status=BacktestStatus.CANCELLED)

        mock_service = MagicMock()
        mock_service.cancel_backtest = AsyncMock(return_value=True)
        mock_service.get_backtest = AsyncMock(return_value=mock_backtest)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.CancelBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(TEST_BACKTEST_ID),
                )

                response = await backtest_servicer.CancelBacktest(request, grpc_context)

                assert response.backtest.status == backtest_pb2.BACKTEST_STATUS_CANCELLED
                mock_service.cancel_backtest.assert_called_once()

    async def test_cancel_backtest_failed_precondition(self, backtest_servicer, grpc_context):
        """Test cancelling a backtest that cannot be cancelled."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_service = MagicMock()
        mock_service.cancel_backtest = AsyncMock(return_value=False)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.CancelBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(TEST_BACKTEST_ID),
                )

                with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                    await backtest_servicer.CancelBacktest(request, grpc_context)

                assert exc_info.value.code() == grpc.StatusCode.FAILED_PRECONDITION


class TestCompareBacktests:
    """Tests for CompareBacktests gRPC method."""

    async def test_compare_backtests_success(self, backtest_servicer, grpc_context):
        """Test comparing multiple backtests."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        backtest_id_1 = uuid4()
        backtest_id_2 = uuid4()
        mock_backtests = [
            make_mock_backtest(id=backtest_id_1, status=BacktestStatus.COMPLETED),
            make_mock_backtest(id=backtest_id_2, status=BacktestStatus.COMPLETED),
        ]

        mock_service = MagicMock()
        mock_service.get_backtest = AsyncMock(side_effect=mock_backtests)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.CompareBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_ids=[str(backtest_id_1), str(backtest_id_2)],
                )

                response = await backtest_servicer.CompareBacktests(request, grpc_context)

                assert len(response.backtests) == 2

    async def test_compare_backtests_partial_not_found(self, backtest_servicer, grpc_context):
        """Test comparing backtests when some are not found."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        backtest_id_1 = uuid4()
        backtest_id_2 = uuid4()
        mock_backtest = make_mock_backtest(id=backtest_id_1, status=BacktestStatus.COMPLETED)

        mock_service = MagicMock()
        # First call returns backtest, second returns None
        mock_service.get_backtest = AsyncMock(side_effect=[mock_backtest, None])

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.CompareBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_ids=[str(backtest_id_1), str(backtest_id_2)],
                )

                response = await backtest_servicer.CompareBacktests(request, grpc_context)

                # Should only return the found backtest
                assert len(response.backtests) == 1


class TestStreamBacktestProgress:
    """Tests for StreamBacktestProgress gRPC method."""

    async def test_stream_progress_backtest_not_found(self, backtest_servicer, grpc_context):
        """Test streaming progress for nonexistent backtest returns NOT_FOUND."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_service = MagicMock()
        mock_service.get_backtest = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.StreamBacktestProgressRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(uuid4()),
                )

                with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                    async for _ in backtest_servicer.StreamBacktestProgress(request, grpc_context):
                        pass

                assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    async def test_stream_progress_completed_backtest(self, backtest_servicer, grpc_context):
        """Test streaming progress for already completed backtest returns immediately."""
        from llamatrade.v1 import backtest_pb2, common_pb2

        mock_backtest = make_mock_backtest(status=BacktestStatus.COMPLETED, progress=100.0)

        mock_service = MagicMock()
        mock_service.get_backtest = AsyncMock(return_value=mock_backtest)

        mock_db = MagicMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with patch.object(backtest_servicer, "_get_db", new=AsyncMock(return_value=mock_db)):
            with patch("src.grpc.servicer.BacktestService", return_value=mock_service):
                request = backtest_pb2.StreamBacktestProgressRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(TEST_TENANT_ID),
                        user_id=str(TEST_USER_ID),
                    ),
                    backtest_id=str(TEST_BACKTEST_ID),
                )

                updates = []
                async for update in backtest_servicer.StreamBacktestProgress(request, grpc_context):
                    updates.append(update)

                # Should get one initial status update then stop
                assert len(updates) == 1
                assert updates[0].status == backtest_pb2.BACKTEST_STATUS_COMPLETED
