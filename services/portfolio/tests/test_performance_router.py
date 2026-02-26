"""Tests for performance router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from llamatrade_db import get_db
from src.main import app
from src.models import EquityPoint, PerformanceMetrics
from src.services.performance_service import PerformanceService, get_performance_service


@pytest.fixture
def mock_performance_service() -> AsyncMock:
    """Create a mock performance service."""
    service = AsyncMock(spec=PerformanceService)
    return service


async def test_get_performance_metrics_success(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting performance metrics returns correct data."""
    mock_performance_service.get_metrics.return_value = PerformanceMetrics(
        period="1M",
        total_return=1500.0,
        total_return_percent=1.5,
        annualized_return=18.0,
        volatility=15.0,
        sharpe_ratio=1.2,
        sortino_ratio=1.8,
        max_drawdown=5.0,
        win_rate=55.0,
        profit_factor=1.5,
        best_day=2.5,
        worst_day=-1.5,
        avg_daily_return=0.05,
    )

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/performance/metrics?period=1M")
        assert response.status_code == 200

        data = response.json()
        assert data["period"] == "1M"
        assert data["total_return"] == 1500.0
        assert data["sharpe_ratio"] == 1.2
        assert data["max_drawdown"] == 5.0
    finally:
        app.dependency_overrides.clear()


async def test_get_performance_metrics_default_period(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting metrics with default period."""
    mock_performance_service.get_metrics.return_value = PerformanceMetrics(
        period="1M",
        total_return=0.0,
        total_return_percent=0.0,
        annualized_return=0.0,
        volatility=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        best_day=0.0,
        worst_day=0.0,
        avg_daily_return=0.0,
    )

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        # Request without period parameter
        response = await authenticated_client.get("/performance/metrics")
        assert response.status_code == 200

        # Verify default period was used
        call_args = mock_performance_service.get_metrics.call_args
        assert call_args.kwargs["period"] == "1M"
    finally:
        app.dependency_overrides.clear()


async def test_get_performance_metrics_all_periods(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test all valid period values are accepted."""
    mock_performance_service.get_metrics.return_value = PerformanceMetrics(
        period="1D",
        total_return=0.0,
        total_return_percent=0.0,
        annualized_return=0.0,
        volatility=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        best_day=0.0,
        worst_day=0.0,
        avg_daily_return=0.0,
    )

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        valid_periods = ["1D", "1W", "1M", "3M", "6M", "1Y", "YTD", "ALL"]
        for period in valid_periods:
            response = await authenticated_client.get(f"/performance/metrics?period={period}")
            assert response.status_code == 200, f"Period {period} should be valid"
    finally:
        app.dependency_overrides.clear()


async def test_get_performance_metrics_invalid_period(
    authenticated_client: AsyncClient,
    mock_db: AsyncMock,
):
    """Test invalid period value returns 422."""
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/performance/metrics?period=INVALID")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_get_equity_curve_success(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting equity curve returns correct data."""
    now = datetime.now(UTC)
    mock_performance_service.get_equity_curve.return_value = [
        EquityPoint(
            timestamp=now,
            equity=100000.0,
            cash=50000.0,
            market_value=50000.0,
        ),
    ]

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/performance/equity-curve")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["equity"] == 100000.0
    finally:
        app.dependency_overrides.clear()


async def test_get_equity_curve_with_date_range(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting equity curve with date range filter."""
    mock_performance_service.get_equity_curve.return_value = []

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get(
            "/performance/equity-curve?start_date=2024-01-01T00:00:00Z&end_date=2024-12-31T23:59:59Z"
        )
        assert response.status_code == 200

        # Verify dates were passed to service
        call_args = mock_performance_service.get_equity_curve.call_args
        assert call_args.kwargs["start_date"] is not None
        assert call_args.kwargs["end_date"] is not None
    finally:
        app.dependency_overrides.clear()


async def test_get_daily_returns_success(
    authenticated_client: AsyncClient,
    mock_performance_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting daily returns returns correct data."""
    now = datetime.now(UTC)
    mock_performance_service.get_daily_returns.return_value = [
        {"date": now, "return": 0.5, "cumulative_return": 1.5},
    ]

    app.dependency_overrides[get_performance_service] = lambda: mock_performance_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/performance/daily-returns?period=1M")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["return"] == 0.5
    finally:
        app.dependency_overrides.clear()


async def test_get_metrics_unauthorized(client: AsyncClient):
    """Test getting metrics without auth returns 401."""
    response = await client.get("/performance/metrics")
    assert response.status_code == 401
