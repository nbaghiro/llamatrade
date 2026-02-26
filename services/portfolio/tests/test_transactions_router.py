"""Tests for transactions router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import AsyncClient
from llamatrade_db import get_db
from src.main import app
from src.models import TransactionResponse, TransactionType
from src.services.transaction_service import TransactionService, get_transaction_service

TEST_TRANSACTION_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def mock_transaction_service() -> AsyncMock:
    """Create a mock transaction service."""
    service = AsyncMock(spec=TransactionService)
    return service


async def test_list_transactions_success(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test listing transactions returns correct data."""
    now = datetime.now(UTC)
    mock_transaction_service.list_transactions.return_value = (
        [
            TransactionResponse(
                id=TEST_TRANSACTION_ID,
                type=TransactionType.BUY,
                symbol="AAPL",
                qty=100.0,
                price=150.0,
                amount=15000.0,
                commission=0.0,
                description="Buy 100 AAPL",
                executed_at=now,
            ),
        ],
        1,  # total count
    )

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["symbol"] == "AAPL"
        assert data["items"][0]["type"] == "buy"
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_empty(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test listing transactions when none exist returns empty list."""
    mock_transaction_service.list_transactions.return_value = ([], 0)

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_with_type_filter(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test listing transactions with type filter."""
    mock_transaction_service.list_transactions.return_value = ([], 0)

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions?type=buy")
        assert response.status_code == 200

        # Verify filter was passed to service
        call_args = mock_transaction_service.list_transactions.call_args
        assert call_args.kwargs["type"] == TransactionType.BUY
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_with_symbol_filter(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test listing transactions with symbol filter."""
    mock_transaction_service.list_transactions.return_value = ([], 0)

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions?symbol=aapl")
        assert response.status_code == 200

        # Verify symbol was uppercased
        call_args = mock_transaction_service.list_transactions.call_args
        assert call_args.kwargs["symbol"] == "AAPL"
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_pagination(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test listing transactions with pagination."""
    mock_transaction_service.list_transactions.return_value = ([], 0)

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions?page=2&page_size=50")
        assert response.status_code == 200

        # Verify pagination was passed to service
        call_args = mock_transaction_service.list_transactions.call_args
        assert call_args.kwargs["page"] == 2
        assert call_args.kwargs["page_size"] == 50
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_invalid_page(
    authenticated_client: AsyncClient,
    mock_db: AsyncMock,
):
    """Test listing transactions with invalid page returns 422."""
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions?page=0")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_invalid_page_size(
    authenticated_client: AsyncClient,
    mock_db: AsyncMock,
):
    """Test listing transactions with invalid page_size returns 422."""
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get("/transactions?page_size=101")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_get_transaction_success(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting a specific transaction returns correct data."""
    now = datetime.now(UTC)
    mock_transaction_service.get_transaction.return_value = TransactionResponse(
        id=TEST_TRANSACTION_ID,
        type=TransactionType.BUY,
        symbol="AAPL",
        qty=100.0,
        price=150.0,
        amount=15000.0,
        commission=0.0,
        description="Buy 100 AAPL",
        executed_at=now,
    )

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get(f"/transactions/{TEST_TRANSACTION_ID}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(TEST_TRANSACTION_ID)
        assert data["symbol"] == "AAPL"
    finally:
        app.dependency_overrides.clear()


async def test_get_transaction_not_found(
    authenticated_client: AsyncClient,
    mock_transaction_service: AsyncMock,
    mock_db: AsyncMock,
):
    """Test getting a non-existent transaction returns 404."""
    mock_transaction_service.get_transaction.return_value = None

    app.dependency_overrides[get_transaction_service] = lambda: mock_transaction_service
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        response = await authenticated_client.get(f"/transactions/{TEST_TRANSACTION_ID}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


async def test_list_transactions_unauthorized(client: AsyncClient):
    """Test listing transactions without auth returns 401."""
    response = await client.get("/transactions")
    assert response.status_code == 401
