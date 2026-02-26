"""Tests for quotes router endpoints."""

import pytest
from src.models import AlpacaServerError, SymbolNotFoundError


class TestGetLatestQuote:
    """Tests for GET /quotes/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_get_latest_quote_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful quote retrieval."""
        response = await client.get("/quotes/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["bid_price"] == 151.50
        assert data["ask_price"] == 151.55

    @pytest.mark.asyncio
    async def test_get_latest_quote_not_found(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test quote not found returns 404."""
        mock_market_data_service.get_latest_quote.return_value = None

        response = await client.get("/quotes/INVALID")

        assert response.status_code == 404
        data = response.json()
        assert "No quote found" in data["detail"]

    @pytest.mark.asyncio
    async def test_get_latest_quote_with_refresh(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test quote retrieval with refresh parameter."""
        response = await client.get("/quotes/AAPL", params={"refresh": True})

        assert response.status_code == 200
        call_args = mock_market_data_service.get_latest_quote.call_args
        assert call_args.kwargs["refresh"] is True

    @pytest.mark.asyncio
    async def test_get_latest_quote_unauthorized(self, client):
        """Test that missing auth returns 401."""
        response = await client.get("/quotes/AAPL")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_latest_quote_symbol_not_found(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test that symbol not found from Alpaca returns 404."""
        mock_market_data_service.get_latest_quote.side_effect = SymbolNotFoundError("INVALID")

        response = await client.get("/quotes/INVALID")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "symbol_not_found"

    @pytest.mark.asyncio
    async def test_get_latest_quote_upstream_error(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test that upstream error returns 502."""
        mock_market_data_service.get_latest_quote.side_effect = AlpacaServerError("Internal error")

        response = await client.get("/quotes/AAPL")

        assert response.status_code == 502
        data = response.json()
        assert data["error"] == "upstream_error"


class TestGetSnapshot:
    """Tests for GET /quotes/{symbol}/snapshot endpoint."""

    @pytest.mark.asyncio
    async def test_get_snapshot_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful snapshot retrieval."""
        response = await client.get("/quotes/AAPL/snapshot")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "latest_trade" in data
        assert "latest_quote" in data
        assert "daily_bar" in data

    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test snapshot not found returns 404."""
        mock_market_data_service.get_snapshot.return_value = None

        response = await client.get("/quotes/INVALID/snapshot")

        assert response.status_code == 404
        data = response.json()
        assert "No snapshot found" in data["detail"]

    @pytest.mark.asyncio
    async def test_get_snapshot_with_refresh(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test snapshot retrieval with refresh parameter."""
        response = await client.get("/quotes/AAPL/snapshot", params={"refresh": True})

        assert response.status_code == 200
        call_args = mock_market_data_service.get_snapshot.call_args
        assert call_args.kwargs["refresh"] is True

    @pytest.mark.asyncio
    async def test_get_snapshot_includes_all_fields(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test snapshot includes all expected fields."""
        response = await client.get("/quotes/AAPL/snapshot")

        assert response.status_code == 200
        data = response.json()

        # Verify all snapshot fields are present
        assert "symbol" in data
        assert "latest_trade" in data
        assert "latest_quote" in data
        assert "minute_bar" in data
        assert "daily_bar" in data
        assert "prev_daily_bar" in data

        # Verify nested structures
        if data["latest_trade"]:
            assert "price" in data["latest_trade"]
            assert "size" in data["latest_trade"]

        if data["latest_quote"]:
            assert "bid_price" in data["latest_quote"]
            assert "ask_price" in data["latest_quote"]


class TestGetMultiSnapshots:
    """Tests for POST /quotes/snapshots endpoint."""

    @pytest.mark.asyncio
    async def test_get_multi_snapshots_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful multi-symbol snapshot retrieval."""
        response = await client.post(
            "/quotes/snapshots",
            json=["AAPL", "TSLA"],
        )

        assert response.status_code == 200
        data = response.json()
        assert "AAPL" in data
        assert "TSLA" in data

    @pytest.mark.asyncio
    async def test_get_multi_snapshots_partial_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test multi-symbol snapshot with some missing symbols."""
        # Mock returns only AAPL
        mock_market_data_service.get_multi_snapshots.return_value = {
            "AAPL": mock_market_data_service.get_multi_snapshots.return_value["AAPL"]
        }

        response = await client.post(
            "/quotes/snapshots",
            json=["AAPL", "NONEXISTENT"],
        )

        assert response.status_code == 200
        data = response.json()
        assert "AAPL" in data
        # NONEXISTENT may or may not be in response depending on Alpaca behavior

    @pytest.mark.asyncio
    async def test_get_multi_snapshots_with_refresh(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test multi-symbol snapshot with refresh parameter."""
        response = await client.post(
            "/quotes/snapshots",
            params={"refresh": True},
            json=["AAPL"],
        )

        assert response.status_code == 200
        call_args = mock_market_data_service.get_multi_snapshots.call_args
        assert call_args.kwargs["refresh"] is True

    @pytest.mark.asyncio
    async def test_get_multi_snapshots_unauthorized(self, client):
        """Test that missing auth returns 401."""
        response = await client.post(
            "/quotes/snapshots",
            json=["AAPL"],
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_multi_snapshots_empty_list(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test multi-symbol snapshot with empty list."""
        mock_market_data_service.get_multi_snapshots.return_value = {}

        response = await client.post(
            "/quotes/snapshots",
            json=[],
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {}
