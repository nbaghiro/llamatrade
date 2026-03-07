"""Tests for position service."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from llamatrade_proto.generated.trading_pb2 import (
    POSITION_SIDE_LONG,
    POSITION_SIDE_SHORT,
)

from src.services.position_service import PositionService

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_market_data():
    """Create mock market data client."""
    client = AsyncMock()
    client.get_latest_price = AsyncMock(return_value=155.0)
    client.get_prices = AsyncMock(return_value={"AAPL": 155.0, "GOOGL": 142.0})
    return client


@pytest.fixture
def mock_position():
    """Create mock position ORM object."""
    pos = MagicMock()
    pos.id = UUID("77777777-7777-7777-7777-777777777777")
    pos.tenant_id = TEST_TENANT_ID
    pos.session_id = TEST_SESSION_ID
    pos.symbol = "AAPL"
    pos.side = POSITION_SIDE_LONG
    pos.qty = Decimal("100")
    pos.avg_entry_price = Decimal("150.00")
    pos.current_price = Decimal("155.00")
    pos.market_value = Decimal("15500.00")
    pos.cost_basis = Decimal("15000.00")
    pos.unrealized_pl = Decimal("500.00")
    pos.unrealized_plpc = Decimal("0.0333")
    pos.realized_pl = Decimal("0")
    pos.is_open = True
    pos.opened_at = datetime.now(UTC)
    pos.closed_at = None
    return pos


class TestPositionService:
    """Test suite for PositionService."""

    async def test_open_position_success(self, mock_db, mock_market_data):
        """Test opening a new position."""
        mock_db.refresh = AsyncMock()
        service = PositionService(db=mock_db, market_data=mock_market_data)

        await service.open_position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            side="long",
            qty=100.0,
            entry_price=150.0,
        )

        # Verify db.add was called
        assert mock_db.add.called
        assert mock_db.commit.called

    async def test_open_position_normalizes_symbol(self, mock_db, mock_market_data):
        """Test that symbol is normalized to uppercase."""
        mock_db.refresh = AsyncMock()
        service = PositionService(db=mock_db, market_data=mock_market_data)

        await service.open_position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="aapl",  # lowercase
            side="long",
            qty=100.0,
            entry_price=150.0,
        )

        # Check that the added position has uppercase symbol
        added_position = mock_db.add.call_args[0][0]
        assert added_position.symbol == "AAPL"

    async def test_close_position_calculates_pnl_long(self, mock_db, mock_position):
        """Test closing a long position calculates correct P&L."""
        # Setup mock to return the position
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_position
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        await service.close_position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            exit_price=160.0,  # Profit: (160 - 150) * 100 = 1000
        )

        assert mock_position.is_open is False
        assert float(mock_position.realized_pl) == 1000.0  # (160 - 150) * 100

    async def test_close_position_calculates_pnl_short(self, mock_db):
        """Test closing a short position calculates correct P&L."""
        # Create short position mock
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.side = POSITION_SIDE_SHORT
        mock_position.qty = Decimal("100")
        mock_position.avg_entry_price = Decimal("150.00")
        mock_position.cost_basis = Decimal("15000.00")
        mock_position.is_open = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_position
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        await service.close_position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            exit_price=140.0,  # Profit: (150 - 140) * 100 = 1000 (short)
        )

        assert float(mock_position.realized_pl) == 1000.0  # (150 - 140) * 100

    async def test_close_position_not_found(self, mock_db):
        """Test closing non-existent position returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        response = await service.close_position(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            symbol="AAPL",
            exit_price=160.0,
        )

        assert response is None

    async def test_get_session_pnl(self, mock_db):
        """Test calculating session P&L."""
        # Mock results for realized and unrealized P&L queries
        realized_result = MagicMock()
        realized_result.scalar.return_value = Decimal("1500.00")

        unrealized_result = MagicMock()
        unrealized_result.scalar.return_value = Decimal("500.00")

        mock_db.execute = AsyncMock(side_effect=[realized_result, unrealized_result])

        service = PositionService(db=mock_db)

        realized, unrealized = await service.get_session_pnl(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert realized == 1500.0
        assert unrealized == 500.0

    async def test_get_session_pnl_empty(self, mock_db):
        """Test session P&L with no positions."""
        # Mock results returning None (no positions)
        realized_result = MagicMock()
        realized_result.scalar.return_value = None

        unrealized_result = MagicMock()
        unrealized_result.scalar.return_value = None

        mock_db.execute = AsyncMock(side_effect=[realized_result, unrealized_result])

        service = PositionService(db=mock_db)

        realized, unrealized = await service.get_session_pnl(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert realized == 0.0
        assert unrealized == 0.0

    async def test_count_trades(self, mock_db):
        """Test counting completed trades."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15

        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        count = await service.count_trades(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert count == 15

    async def test_update_prices_with_market_data(self, mock_db, mock_market_data, mock_position):
        """Test updating position prices from market data."""
        # Setup mock to return list of positions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_position]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db, market_data=mock_market_data)

        updated = await service.update_prices(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert updated == 1
        assert mock_market_data.get_prices.called

    async def test_update_prices_with_provided_prices(self, mock_db, mock_position):
        """Test updating position prices with provided prices."""
        # Setup mock to return list of positions
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_position]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        updated = await service.update_prices(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
            prices={"AAPL": 160.0},
        )

        assert updated == 1
        # Verify position was updated
        assert mock_position.current_price == Decimal("160.0")

    async def test_update_prices_no_positions(self, mock_db, mock_market_data):
        """Test updating prices when no positions exist."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db, market_data=mock_market_data)

        updated = await service.update_prices(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert updated == 0

    async def test_list_open_positions(self, mock_db, mock_position):
        """Test listing open positions."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_position]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PositionService(db=mock_db)

        positions = await service.list_open_positions(
            tenant_id=TEST_TENANT_ID,
            session_id=TEST_SESSION_ID,
        )

        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

    async def test_response_conversion(self, mock_db, mock_position):
        """Test position to response conversion."""
        service = PositionService(db=mock_db)
        response = service._to_response(mock_position)

        assert response.symbol == "AAPL"
        assert response.qty == 100.0
        assert response.side == "long"
        assert response.cost_basis == 15000.0
        assert response.market_value == 15500.0
        assert response.unrealized_pnl == 500.0
        # unrealized_plpc is multiplied by 100 in response
        assert response.unrealized_pnl_percent == pytest.approx(3.33, rel=0.01)
