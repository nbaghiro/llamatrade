"""Tests for usage endpoints."""

from httpx import AsyncClient

from tests.conftest import make_auth_header


class TestGetUsageSummary:
    """Tests for GET /usage/summary."""

    async def test_get_usage_summary_requires_auth(self, client: AsyncClient) -> None:
        """Test that getting usage summary requires authentication."""
        response = await client.get("/usage/summary")

        assert response.status_code == 401

    async def test_get_usage_summary_success(self, client: AsyncClient) -> None:
        """Test successful usage summary retrieval."""
        headers = make_auth_header()
        response = await client.get("/usage/summary", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "backtests_count" in data
        assert "backtests_limit" in data
        assert "live_strategies_count" in data
        assert "api_calls_count" in data
        assert "period_start" in data
        assert "period_end" in data


class TestGetUsageHistory:
    """Tests for GET /usage/history."""

    async def test_get_usage_history_requires_auth(self, client: AsyncClient) -> None:
        """Test that getting usage history requires authentication."""
        response = await client.get("/usage/history")

        assert response.status_code == 401

    async def test_get_usage_history_success(self, client: AsyncClient) -> None:
        """Test successful usage history retrieval."""
        headers = make_auth_header()
        response = await client.get("/usage/history", headers=headers)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_usage_history_with_months_param(self, client: AsyncClient) -> None:
        """Test usage history with months parameter."""
        headers = make_auth_header()
        response = await client.get("/usage/history?months=6", headers=headers)

        assert response.status_code == 200
        assert isinstance(response.json(), list)
