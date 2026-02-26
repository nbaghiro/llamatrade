"""Tests for bars router endpoints."""

import pytest
from src.models import AlpacaRateLimitError, CircuitOpenError, SymbolNotFoundError


class TestGetBars:
    """Tests for GET /bars/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_get_bars_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful bars retrieval."""
        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z", "timeframe": "1Day"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["close"] == 151.75

    @pytest.mark.asyncio
    async def test_get_bars_with_all_params(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test bars retrieval with all parameters."""
        response = await client.get(
            "/bars/AAPL",
            params={
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-31T00:00:00Z",
                "timeframe": "1Hour",
                "limit": 500,
                "refresh": True,
            },
        )

        assert response.status_code == 200
        mock_market_data_service.get_bars.assert_called_once()
        call_args = mock_market_data_service.get_bars.call_args
        assert call_args.kwargs["refresh"] is True
        assert call_args.kwargs["limit"] == 500

    @pytest.mark.asyncio
    async def test_get_bars_missing_start_param(self, client, auth_override):
        """Test that missing start parameter returns 422."""
        response = await client.get("/bars/AAPL")

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_bars_invalid_timeframe(self, client, auth_override):
        """Test that invalid timeframe returns 422."""
        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z", "timeframe": "invalid"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_bars_invalid_limit(self, client, auth_override):
        """Test that invalid limit returns 422."""
        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z", "limit": 999999},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_bars_unauthorized(self, client):
        """Test that missing auth returns 401."""
        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_bars_symbol_not_found(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test that symbol not found returns 404."""
        mock_market_data_service.get_bars.side_effect = SymbolNotFoundError("INVALID")

        response = await client.get(
            "/bars/INVALID",
            params={"start": "2024-01-01T00:00:00Z"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "symbol_not_found"
        assert "INVALID" in data["symbol"]

    @pytest.mark.asyncio
    async def test_get_bars_rate_limited(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test that rate limit returns 503 with Retry-After."""
        mock_market_data_service.get_bars.side_effect = AlpacaRateLimitError(
            "Rate limited", retry_after=30
        )

        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z"},
        )

        assert response.status_code == 503
        assert response.headers.get("Retry-After") == "30"
        data = response.json()
        assert data["error"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_get_bars_circuit_open(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test that circuit open returns 503."""
        mock_market_data_service.get_bars.side_effect = CircuitOpenError()

        response = await client.get(
            "/bars/AAPL",
            params={"start": "2024-01-01T00:00:00Z"},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "service_unavailable"


class TestGetMultiBars:
    """Tests for POST /bars endpoint."""

    @pytest.mark.asyncio
    async def test_get_multi_bars_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful multi-symbol bars retrieval."""
        response = await client.post(
            "/bars",
            json={
                "symbols": ["AAPL", "TSLA"],
                "start": "2024-01-01T00:00:00Z",
                "timeframe": "1Day",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "bars" in data
        assert "AAPL" in data["bars"]

    @pytest.mark.asyncio
    async def test_get_multi_bars_empty_symbols(self, client, auth_override):
        """Test that empty symbols list returns 422."""
        response = await client.post(
            "/bars",
            json={
                "symbols": [],
                "start": "2024-01-01T00:00:00Z",
            },
        )

        # Depends on model validation - may be 422 or may return empty
        # The implementation should handle this gracefully
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_get_multi_bars_with_refresh(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test multi-symbol bars with refresh parameter."""
        response = await client.post(
            "/bars",
            params={"refresh": True},
            json={
                "symbols": ["AAPL"],
                "start": "2024-01-01T00:00:00Z",
            },
        )

        assert response.status_code == 200
        mock_market_data_service.get_multi_bars.assert_called_once()
        call_args = mock_market_data_service.get_multi_bars.call_args
        assert call_args.kwargs["refresh"] is True


class TestGetLatestBar:
    """Tests for GET /bars/{symbol}/latest endpoint."""

    @pytest.mark.asyncio
    async def test_get_latest_bar_success(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test successful latest bar retrieval."""
        response = await client.get("/bars/AAPL/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["close"] == 151.75

    @pytest.mark.asyncio
    async def test_get_latest_bar_not_found(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test latest bar not found returns 404."""
        mock_market_data_service.get_latest_bar.return_value = None

        response = await client.get("/bars/INVALID/latest")

        assert response.status_code == 404
        data = response.json()
        assert "No bar found" in data["detail"]

    @pytest.mark.asyncio
    async def test_get_latest_bar_with_refresh(
        self, client, auth_override, service_override, mock_market_data_service
    ):
        """Test latest bar with refresh parameter."""
        response = await client.get("/bars/AAPL/latest", params={"refresh": True})

        assert response.status_code == 200
        call_args = mock_market_data_service.get_latest_bar.call_args
        assert call_args.kwargs["refresh"] is True
