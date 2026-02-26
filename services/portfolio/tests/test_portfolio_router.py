"""Tests for portfolio router endpoints."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import AsyncClient
from llamatrade_db import get_db
from src.clients.market_data import get_market_data_client
from src.main import app
from src.models import PortfolioSummary, PositionResponse
from src.services.portfolio_service import PortfolioService, get_portfolio_service


@pytest.fixture
def mock_portfolio_service() -> AsyncMock:
    """Create a mock portfolio service."""
    service = AsyncMock(spec=PortfolioService)
    return service


async def test_get_portfolio_summary_success(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
    tenant_id: UUID,
):
    """Test getting portfolio summary returns correct data."""
    from datetime import UTC, datetime

    # Setup mock response
    mock_portfolio_service.get_summary.return_value = PortfolioSummary(
        total_equity=100000.0,
        cash=50000.0,
        market_value=50000.0,
        total_unrealized_pnl=500.0,
        total_realized_pnl=1000.0,
        day_pnl=200.0,
        day_pnl_percent=0.2,
        total_pnl_percent=1.5,
        positions_count=2,
        updated_at=datetime.now(UTC),
    )

    # Override dependencies
    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        response = await authenticated_client.get("/portfolio/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["total_equity"] == 100000.0
        assert data["cash"] == 50000.0
        assert data["market_value"] == 50000.0
        assert data["positions_count"] == 2
    finally:
        app.dependency_overrides.clear()


async def test_get_portfolio_summary_unauthorized(client: AsyncClient):
    """Test getting portfolio summary without auth returns 401."""
    response = await client.get("/portfolio/summary")
    assert response.status_code == 401


async def test_list_positions_success(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
):
    """Test listing positions returns correct data."""
    # Setup mock response
    mock_portfolio_service.list_positions.return_value = [
        PositionResponse(
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=14500.0,
            market_value=15000.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.45,
            current_price=150.0,
            avg_entry_price=145.0,
        ),
    ]

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        response = await authenticated_client.get("/portfolio/positions")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "AAPL"
        assert data[0]["qty"] == 100.0
        assert data[0]["unrealized_pnl"] == 500.0
    finally:
        app.dependency_overrides.clear()


async def test_list_positions_empty(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
):
    """Test listing positions when none exist returns empty list."""
    mock_portfolio_service.list_positions.return_value = []

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        response = await authenticated_client.get("/portfolio/positions")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_get_position_success(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
):
    """Test getting a specific position returns correct data."""
    mock_portfolio_service.get_position.return_value = PositionResponse(
        symbol="AAPL",
        qty=100.0,
        side="long",
        cost_basis=14500.0,
        market_value=15000.0,
        unrealized_pnl=500.0,
        unrealized_pnl_percent=3.45,
        current_price=150.0,
        avg_entry_price=145.0,
    )

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        response = await authenticated_client.get("/portfolio/positions/AAPL")
        assert response.status_code == 200

        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["qty"] == 100.0
    finally:
        app.dependency_overrides.clear()


async def test_get_position_not_found(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
):
    """Test getting a non-existent position returns 404."""
    mock_portfolio_service.get_position.return_value = None

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        response = await authenticated_client.get("/portfolio/positions/UNKNOWN")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


async def test_get_position_symbol_case_insensitive(
    authenticated_client: AsyncClient,
    mock_portfolio_service: AsyncMock,
    mock_db: AsyncMock,
    mock_market_data_client: AsyncMock,
):
    """Test symbol lookup is case-insensitive (converts to uppercase)."""
    mock_portfolio_service.get_position.return_value = PositionResponse(
        symbol="AAPL",
        qty=100.0,
        side="long",
        cost_basis=14500.0,
        market_value=15000.0,
        unrealized_pnl=500.0,
        unrealized_pnl_percent=3.45,
        current_price=150.0,
        avg_entry_price=145.0,
    )

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_market_data_client] = lambda: mock_market_data_client

    try:
        # Request with lowercase
        response = await authenticated_client.get("/portfolio/positions/aapl")
        assert response.status_code == 200

        # Verify service was called with uppercase
        mock_portfolio_service.get_position.assert_called_once()
        call_args = mock_portfolio_service.get_position.call_args
        assert call_args.kwargs["symbol"] == "AAPL"
    finally:
        app.dependency_overrides.clear()
