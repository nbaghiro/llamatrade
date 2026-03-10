"""Tests for performance service."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import numpy as np
import pytest
from numpy.typing import NDArray

from src.services.performance_service import PerformanceService

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def performance_service(mock_db: AsyncMock) -> PerformanceService:
    """Create performance service with mocked dependencies."""
    return PerformanceService(db=mock_db)


async def test_get_metrics_no_data(
    performance_service: PerformanceService,
    mock_db: AsyncMock,
) -> None:
    """Test get_metrics returns zeros when no history exists."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    metrics = await performance_service.get_metrics(TEST_TENANT_ID, "1M")

    assert metrics.period == "1M"
    assert metrics.total_return == 0.0
    assert metrics.sharpe_ratio == 0.0
    assert metrics.max_drawdown == 0.0


async def test_get_metrics_with_data(
    performance_service: PerformanceService,
    mock_db: AsyncMock,
    sample_portfolio_history: list[MagicMock],
) -> None:
    """Test get_metrics calculates correctly with history data."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_portfolio_history
    mock_db.execute.return_value = mock_result

    metrics = await performance_service.get_metrics(TEST_TENANT_ID, "1M")

    assert metrics.period == "1M"
    assert metrics.total_return > 0  # Should have positive return
    assert metrics.volatility >= 0


async def test_get_equity_curve_empty(
    performance_service: PerformanceService,
    mock_db: AsyncMock,
) -> None:
    """Test get_equity_curve returns empty list when no history."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    curve = await performance_service.get_equity_curve(TEST_TENANT_ID, None, None)

    assert curve == []


async def test_get_equity_curve_with_data(
    performance_service: PerformanceService,
    mock_db: AsyncMock,
    sample_portfolio_history: list[MagicMock],
) -> None:
    """Test get_equity_curve returns equity points."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_portfolio_history
    mock_db.execute.return_value = mock_result

    curve = await performance_service.get_equity_curve(TEST_TENANT_ID, None, None)

    assert len(curve) == len(sample_portfolio_history)
    assert curve[0].equity == float(sample_portfolio_history[0].equity)


async def test_get_daily_returns_empty(
    performance_service: PerformanceService,
    mock_db: AsyncMock,
) -> None:
    """Test get_daily_returns returns empty list when no history."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    returns = await performance_service.get_daily_returns(TEST_TENANT_ID, "1M")

    assert returns == []


def test_get_period_dates_1d() -> None:
    """Test period date calculation for 1D."""
    service = PerformanceService(db=MagicMock())
    today = date.today()

    start, end = service._get_period_dates("1D")

    assert end == today
    assert start == today - timedelta(days=1)


def test_get_period_dates_1w() -> None:
    """Test period date calculation for 1W."""
    service = PerformanceService(db=MagicMock())
    today = date.today()

    start, end = service._get_period_dates("1W")

    assert end == today
    assert start == today - timedelta(weeks=1)


def test_get_period_dates_1m() -> None:
    """Test period date calculation for 1M."""
    service = PerformanceService(db=MagicMock())
    today = date.today()

    start, end = service._get_period_dates("1M")

    assert end == today
    assert start == today - timedelta(days=30)


def test_get_period_dates_ytd() -> None:
    """Test period date calculation for YTD."""
    service = PerformanceService(db=MagicMock())
    today = date.today()

    start, end = service._get_period_dates("YTD")

    assert end == today
    assert start == date(today.year, 1, 1)


def test_get_period_dates_all() -> None:
    """Test period date calculation for ALL."""
    service = PerformanceService(db=MagicMock())
    today = date.today()

    start, end = service._get_period_dates("ALL")

    assert end == today
    assert start == date(2000, 1, 1)


def test_calc_sharpe_ratio_positive() -> None:
    """Test Sharpe ratio calculation with positive returns."""
    service = PerformanceService(db=MagicMock())
    daily_returns: NDArray[np.float64] = np.array([0.01, 0.02, -0.005, 0.015, 0.008])

    sharpe = service._calc_sharpe_ratio(daily_returns, risk_free_rate=0.02)

    assert sharpe > 0


def test_calc_sharpe_ratio_empty() -> None:
    """Test Sharpe ratio with empty returns."""
    service = PerformanceService(db=MagicMock())
    daily_returns: NDArray[np.float64] = np.array([])

    sharpe = service._calc_sharpe_ratio(daily_returns)

    assert sharpe == 0.0


def test_calc_sharpe_ratio_zero_std() -> None:
    """Test Sharpe ratio with zero standard deviation."""
    service = PerformanceService(db=MagicMock())
    daily_returns: NDArray[np.float64] = np.array([0.01, 0.01, 0.01])

    sharpe = service._calc_sharpe_ratio(daily_returns)

    assert sharpe == 0.0


def test_calc_sortino_ratio_positive() -> None:
    """Test Sortino ratio calculation."""
    service = PerformanceService(db=MagicMock())
    daily_returns: NDArray[np.float64] = np.array([0.01, 0.02, -0.005, 0.015, -0.01])

    sortino = service._calc_sortino_ratio(daily_returns)

    assert sortino != 0.0  # Should have some value


def test_calc_sortino_ratio_no_negative_returns() -> None:
    """Test Sortino ratio with no negative returns."""
    service = PerformanceService(db=MagicMock())
    daily_returns: NDArray[np.float64] = np.array([0.01, 0.02, 0.015])

    sortino = service._calc_sortino_ratio(daily_returns)

    assert sortino == 0.0


def test_calc_max_drawdown() -> None:
    """Test max drawdown calculation."""
    service = PerformanceService(db=MagicMock())
    # Equity goes 100 -> 110 -> 90 -> 100
    # Max drawdown should be (110 - 90) / 110 = 18.18%
    equities: NDArray[np.float64] = np.array([100.0, 110.0, 90.0, 100.0])

    max_dd = service._calc_max_drawdown(equities)

    assert abs(max_dd - 18.18) < 0.1  # Allow small rounding error


def test_calc_max_drawdown_no_drawdown() -> None:
    """Test max drawdown with monotonically increasing equity."""
    service = PerformanceService(db=MagicMock())
    equities: NDArray[np.float64] = np.array([100.0, 110.0, 120.0, 130.0])

    max_dd = service._calc_max_drawdown(equities)

    assert max_dd == 0.0


def test_calc_max_drawdown_empty() -> None:
    """Test max drawdown with empty array."""
    service = PerformanceService(db=MagicMock())
    equities: NDArray[np.float64] = np.array([])

    max_dd = service._calc_max_drawdown(equities)

    assert max_dd == 0.0
