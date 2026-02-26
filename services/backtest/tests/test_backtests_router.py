"""Tests for backtests router - API integration tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.models import BacktestResponse, BacktestStatus
from src.services.backtest_service import get_backtest_service

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_BACKTEST_ID = UUID("44444444-4444-4444-4444-444444444444")


def create_mock_auth():
    """Create a mock auth dependency."""
    return MagicMock(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="test@example.com",
        roles=["user"],
    )


@pytest.fixture
def sample_backtest_response():
    """Sample backtest response."""
    return BacktestResponse(
        id=TEST_BACKTEST_ID,
        tenant_id=TEST_TENANT_ID,
        strategy_id=TEST_STRATEGY_ID,
        strategy_version=1,
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
        end_date=datetime(2024, 6, 30, tzinfo=UTC),
        initial_capital=100000.0,
        status=BacktestStatus.PENDING,
        progress=0.0,
        error_message=None,
        created_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
    )


class TestCreateBacktest:
    """Tests for POST /backtests endpoint."""

    @pytest.mark.asyncio
    async def test_create_backtest_success(self, sample_backtest_response):
        """Test successful backtest creation."""
        mock_service = AsyncMock()
        mock_service.create_backtest.return_value = sample_backtest_response

        # Override dependencies
        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/backtests",
                    json={
                        "strategy_id": str(TEST_STRATEGY_ID),
                        "name": "Test Backtest",
                        "start_date": "2024-01-01T00:00:00Z",
                        "end_date": "2024-06-30T00:00:00Z",
                        "initial_capital": 100000,
                        "symbols": ["AAPL"],
                        "commission": 0.001,
                        "slippage": 0.001,
                    },
                )

                assert response.status_code == 201
                data = response.json()
                assert data["id"] == str(TEST_BACKTEST_ID)
                assert data["status"] == "pending"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_backtest_validation_error(self):
        """Test backtest creation with invalid data."""
        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/backtests",
                    json={
                        "strategy_id": "not-a-uuid",
                        "start_date": "2024-01-01T00:00:00Z",
                        "end_date": "2024-06-30T00:00:00Z",
                    },
                )

                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_backtest_service_error(self):
        """Test backtest creation when service raises error."""
        mock_service = AsyncMock()
        mock_service.create_backtest.side_effect = ValueError("Strategy not found")

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/backtests",
                    json={
                        "strategy_id": str(TEST_STRATEGY_ID),
                        "start_date": "2024-01-01T00:00:00Z",
                        "end_date": "2024-06-30T00:00:00Z",
                    },
                )

                assert response.status_code == 400
                assert "Strategy not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


class TestListBacktests:
    """Tests for GET /backtests endpoint."""

    @pytest.mark.asyncio
    async def test_list_backtests_success(self, sample_backtest_response):
        """Test successful backtest listing."""
        mock_service = AsyncMock()
        mock_service.list_backtests.return_value = ([sample_backtest_response], 1)

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/backtests")

                assert response.status_code == 200
                data = response.json()
                assert data["total"] == 1
                assert len(data["items"]) == 1
                assert data["items"][0]["id"] == str(TEST_BACKTEST_ID)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_backtests_with_filters(self, sample_backtest_response):
        """Test listing with query parameters."""
        mock_service = AsyncMock()
        mock_service.list_backtests.return_value = ([sample_backtest_response], 1)

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/backtests",
                    params={
                        "strategy_id": str(TEST_STRATEGY_ID),
                        "status": "pending",
                        "page": 1,
                        "page_size": 10,
                    },
                )

                assert response.status_code == 200
                # Verify service was called with correct params
                mock_service.list_backtests.assert_called_once()
        finally:
            app.dependency_overrides.clear()


class TestGetBacktest:
    """Tests for GET /backtests/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_backtest_success(self, sample_backtest_response):
        """Test successful backtest retrieval."""
        mock_service = AsyncMock()
        mock_service.get_backtest.return_value = sample_backtest_response

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/backtests/{TEST_BACKTEST_ID}")

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(TEST_BACKTEST_ID)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_backtest_not_found(self):
        """Test backtest not found returns 404."""
        mock_service = AsyncMock()
        mock_service.get_backtest.return_value = None

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/backtests/{TEST_BACKTEST_ID}")

                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestGetBacktestResults:
    """Tests for GET /backtests/{id}/results endpoint."""

    @pytest.mark.asyncio
    async def test_get_results_not_found(self):
        """Test results not found returns 404."""
        mock_service = AsyncMock()
        mock_service.get_results.return_value = None

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/backtests/{TEST_BACKTEST_ID}/results")

                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestCancelBacktest:
    """Tests for DELETE /backtests/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_backtest_success(self):
        """Test successful backtest cancellation."""
        mock_service = AsyncMock()
        mock_service.cancel_backtest.return_value = True

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/backtests/{TEST_BACKTEST_ID}")

                assert response.status_code == 204
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_cancel_backtest_not_cancellable(self):
        """Test cancelling non-cancellable backtest returns 400."""
        mock_service = AsyncMock()
        mock_service.cancel_backtest.return_value = False

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/backtests/{TEST_BACKTEST_ID}")

                assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()


class TestRetryBacktest:
    """Tests for POST /backtests/{id}/retry endpoint."""

    @pytest.mark.asyncio
    async def test_retry_backtest_success(self, sample_backtest_response):
        """Test successful backtest retry."""
        mock_service = AsyncMock()
        mock_service.retry_backtest.return_value = sample_backtest_response

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/backtests/{TEST_BACKTEST_ID}/retry")

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(TEST_BACKTEST_ID)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_retry_backtest_not_found(self):
        """Test retrying non-existent backtest returns 404."""
        mock_service = AsyncMock()
        mock_service.retry_backtest.return_value = None

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/backtests/{TEST_BACKTEST_ID}/retry")

                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_retry_non_failed_backtest(self):
        """Test retrying non-failed backtest returns 400."""
        mock_service = AsyncMock()
        mock_service.retry_backtest.side_effect = ValueError("Only failed backtests can be retried")

        from llamatrade_common.middleware import require_auth

        app.dependency_overrides[require_auth] = create_mock_auth
        app.dependency_overrides[get_backtest_service] = lambda: mock_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(f"/backtests/{TEST_BACKTEST_ID}/retry")

                assert response.status_code == 400
                assert "Only failed" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
