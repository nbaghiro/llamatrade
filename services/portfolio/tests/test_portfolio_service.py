"""Tests for portfolio service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.services.portfolio_service import PortfolioService

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def portfolio_service(mock_db: AsyncMock, mock_market_data_client: AsyncMock) -> PortfolioService:
    """Create portfolio service with mocked dependencies."""
    return PortfolioService(db=mock_db, market_data=mock_market_data_client)


@pytest.fixture
def portfolio_service_no_market_data(mock_db: AsyncMock) -> PortfolioService:
    """Create portfolio service without market data client."""
    return PortfolioService(db=mock_db, market_data=None)


async def test_get_summary_no_data(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
):
    """Test get_summary returns default when no summary exists."""
    # Mock empty result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    summary = await portfolio_service.get_summary(TEST_TENANT_ID)

    assert summary.total_equity == 0.0
    assert summary.cash == 0.0
    assert summary.positions_count == 0


async def test_get_summary_with_data(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
    mock_market_data_client: AsyncMock,
):
    """Test get_summary returns correct data when summary exists."""
    # Mock result with data
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    summary = await portfolio_service.get_summary(TEST_TENANT_ID)

    assert summary.total_equity == 100000.0
    assert summary.cash == 50000.0
    assert summary.positions_count == 2


async def test_list_positions_empty(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
):
    """Test list_positions returns empty list when no summary exists."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    positions = await portfolio_service.list_positions(TEST_TENANT_ID)

    assert positions == []


async def test_list_positions_with_data(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
    mock_market_data_client: AsyncMock,
):
    """Test list_positions returns enriched position data."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    positions = await portfolio_service.list_positions(TEST_TENANT_ID)

    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert positions[0].current_price == 150.0  # From mock market data
    # P&L should be calculated: (150 - 145) * 100 = 500
    assert positions[0].unrealized_pnl == 500.0


async def test_list_positions_without_market_data(
    portfolio_service_no_market_data: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
):
    """Test list_positions uses stored price when market data unavailable."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    positions = await portfolio_service_no_market_data.list_positions(TEST_TENANT_ID)

    assert len(positions) == 2
    # Should use stored current_price from positions data
    assert positions[0].current_price == 150.0


async def test_get_position_found(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
    mock_market_data_client: AsyncMock,
):
    """Test get_position returns correct position."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    position = await portfolio_service.get_position(TEST_TENANT_ID, "AAPL")

    assert position is not None
    assert position.symbol == "AAPL"


async def test_get_position_not_found(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
    mock_market_data_client: AsyncMock,
):
    """Test get_position returns None when symbol not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    position = await portfolio_service.get_position(TEST_TENANT_ID, "UNKNOWN")

    assert position is None


async def test_get_position_case_insensitive(
    portfolio_service: PortfolioService,
    mock_db: AsyncMock,
    sample_portfolio_summary: MagicMock,
    mock_market_data_client: AsyncMock,
):
    """Test get_position handles case-insensitive symbol lookup."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_portfolio_summary
    mock_db.execute.return_value = mock_result

    # Request with lowercase
    position = await portfolio_service.get_position(TEST_TENANT_ID, "aapl")

    # Should still find AAPL
    assert position is not None
    assert position.symbol == "AAPL"


def test_calculate_unrealized_pnl_long_profit():
    """Test P&L calculation for profitable long position."""
    service = PortfolioService(db=MagicMock(), market_data=None)

    pnl = service._calculate_unrealized_pnl(
        side="long",
        qty=100,
        entry_price=100.0,
        current_price=110.0,
    )

    assert pnl == 1000.0  # (110 - 100) * 100


def test_calculate_unrealized_pnl_long_loss():
    """Test P&L calculation for losing long position."""
    service = PortfolioService(db=MagicMock(), market_data=None)

    pnl = service._calculate_unrealized_pnl(
        side="long",
        qty=100,
        entry_price=100.0,
        current_price=90.0,
    )

    assert pnl == -1000.0  # (90 - 100) * 100


def test_calculate_unrealized_pnl_short_profit():
    """Test P&L calculation for profitable short position."""
    service = PortfolioService(db=MagicMock(), market_data=None)

    pnl = service._calculate_unrealized_pnl(
        side="short",
        qty=100,
        entry_price=100.0,
        current_price=90.0,
    )

    assert pnl == 1000.0  # (100 - 90) * 100


def test_calculate_unrealized_pnl_short_loss():
    """Test P&L calculation for losing short position."""
    service = PortfolioService(db=MagicMock(), market_data=None)

    pnl = service._calculate_unrealized_pnl(
        side="short",
        qty=100,
        entry_price=100.0,
        current_price=110.0,
    )

    assert pnl == -1000.0  # (100 - 110) * 100
