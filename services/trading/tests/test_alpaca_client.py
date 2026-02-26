"""Tests for Alpaca Trading API client."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from src.alpaca_client import AlpacaTradingClient, get_alpaca_trading_client

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


def create_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx Response."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    return mock_response


@pytest.fixture
def mock_httpx_client():
    """Mock httpx async client."""
    return AsyncMock(spec=httpx.AsyncClient)


class TestAlpacaTradingClientInit:
    """Tests for AlpacaTradingClient initialization."""

    def test_init_paper_mode(self):
        """Test initialization in paper trading mode."""
        with patch("httpx.AsyncClient") as mock_client:
            AlpacaTradingClient(
                api_key="test-key",
                api_secret="test-secret",
                paper=True,
            )
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["base_url"] == AlpacaTradingClient.PAPER_URL
            assert call_kwargs["headers"]["APCA-API-KEY-ID"] == "test-key"
            assert call_kwargs["headers"]["APCA-API-SECRET-KEY"] == "test-secret"

    def test_init_live_mode(self):
        """Test initialization in live trading mode."""
        with patch("httpx.AsyncClient") as mock_client:
            AlpacaTradingClient(
                api_key="test-key",
                api_secret="test-secret",
                paper=False,
            )
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["base_url"] == AlpacaTradingClient.LIVE_URL

    def test_init_from_env(self):
        """Test initialization from environment variables."""
        with patch.dict(
            "os.environ",
            {"ALPACA_API_KEY": "env-key", "ALPACA_API_SECRET": "env-secret"},
        ):
            with patch("httpx.AsyncClient") as mock_client:
                AlpacaTradingClient()
                call_kwargs = mock_client.call_args[1]
                assert call_kwargs["headers"]["APCA-API-KEY-ID"] == "env-key"
                assert call_kwargs["headers"]["APCA-API-SECRET-KEY"] == "env-secret"


class TestAlpacaTradingClientMethods:
    """Tests for AlpacaTradingClient API methods."""

    async def test_close(self, mock_httpx_client):
        """Test closing the client."""
        mock_httpx_client.aclose = AsyncMock()

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            await client.close()

        mock_httpx_client.aclose.assert_called_once()

    async def test_get_account_success(self, mock_httpx_client):
        """Test successful account fetch."""
        account_data = {
            "id": "test-account",
            "account_number": "123456789",
            "status": "ACTIVE",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "buying_power": "200000.00",
            "equity": "100000.00",
            "currency": "USD",
        }
        mock_response = create_mock_response(account_data)
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_account()

        assert result["id"] == "test-account"
        assert result["status"] == "ACTIVE"
        mock_httpx_client.get.assert_called_once_with("/account")

    async def test_submit_order_market(self, mock_httpx_client):
        """Test submitting a market order."""
        order_response = {
            "id": "order-123",
            "client_order_id": "client-123",
            "symbol": "AAPL",
            "qty": "10",
            "side": "buy",
            "type": "market",
            "status": "accepted",
        }
        mock_response = create_mock_response(order_response)
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.submit_order(
                symbol="AAPL",
                qty=10,
                side="buy",
                order_type="market",
            )

        assert result["id"] == "order-123"
        assert result["status"] == "accepted"
        mock_httpx_client.post.assert_called_once_with(
            "/orders",
            json={
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
        )

    async def test_submit_order_limit(self, mock_httpx_client):
        """Test submitting a limit order."""
        order_response = {"id": "order-123", "type": "limit", "status": "accepted"}
        mock_response = create_mock_response(order_response)
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            await client.submit_order(
                symbol="AAPL",
                qty=10,
                side="buy",
                order_type="limit",
                limit_price=150.00,
            )

        call_args = mock_httpx_client.post.call_args
        assert call_args[1]["json"]["limit_price"] == "150.0"

    async def test_submit_order_stop(self, mock_httpx_client):
        """Test submitting a stop order."""
        order_response = {"id": "order-123", "type": "stop", "status": "accepted"}
        mock_response = create_mock_response(order_response)
        mock_httpx_client.post = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            await client.submit_order(
                symbol="AAPL",
                qty=10,
                side="sell",
                order_type="stop",
                stop_price=145.00,
            )

        call_args = mock_httpx_client.post.call_args
        assert call_args[1]["json"]["stop_price"] == "145.0"

    async def test_get_order_success(self, mock_httpx_client):
        """Test fetching an order."""
        order_data = {
            "id": "order-123",
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "150.50",
        }
        mock_response = create_mock_response(order_data)
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_order("order-123")

        assert result is not None
        assert result["id"] == "order-123"
        assert result["status"] == "filled"

    async def test_get_order_not_found(self, mock_httpx_client):
        """Test fetching a non-existent order."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_order("nonexistent")

        assert result is None

    async def test_get_order_error_raises(self, mock_httpx_client):
        """Test that non-404 errors are raised."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_order("order-123")

    async def test_cancel_order_success(self, mock_httpx_client):
        """Test canceling an order."""
        mock_response = create_mock_response({}, status_code=204)
        mock_httpx_client.delete = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.cancel_order("order-123")

        assert result is True
        mock_httpx_client.delete.assert_called_once_with("/orders/order-123")

    async def test_cancel_order_failure(self, mock_httpx_client):
        """Test cancel order failure."""
        mock_httpx_client.delete = AsyncMock(
            side_effect=httpx.HTTPStatusError("Error", request=MagicMock(), response=MagicMock())
        )

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.cancel_order("order-123")

        assert result is False

    async def test_get_positions(self, mock_httpx_client):
        """Test getting all positions."""
        positions_data = [
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "long",
                "cost_basis": "1500.00",
                "market_value": "1550.00",
                "unrealized_pl": "50.00",
                "unrealized_plpc": "0.0333",
                "current_price": "155.00",
            },
            {
                "symbol": "GOOGL",
                "qty": "5",
                "side": "long",
                "cost_basis": "700.00",
                "market_value": "750.00",
                "unrealized_pl": "50.00",
                "unrealized_plpc": "0.0714",
                "current_price": "150.00",
            },
        ]
        mock_response = create_mock_response(positions_data)
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_positions(TEST_TENANT_ID)

        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[0].qty == 10.0
        assert result[0].unrealized_pnl == 50.0
        assert result[0].unrealized_pnl_percent == pytest.approx(3.33, rel=0.01)
        assert result[1].symbol == "GOOGL"

    async def test_get_position_success(self, mock_httpx_client):
        """Test getting a single position."""
        position_data = {
            "symbol": "AAPL",
            "qty": "10",
            "side": "long",
            "cost_basis": "1500.00",
            "market_value": "1550.00",
            "unrealized_pl": "50.00",
            "unrealized_plpc": "0.0333",
            "current_price": "155.00",
        }
        mock_response = create_mock_response(position_data)
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_position(TEST_TENANT_ID, "AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.qty == 10.0
        mock_httpx_client.get.assert_called_once_with("/positions/AAPL")

    async def test_get_position_not_found(self, mock_httpx_client):
        """Test getting a non-existent position."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.get_position(TEST_TENANT_ID, "INVALID")

        assert result is None

    async def test_get_position_error_raises(self, mock_httpx_client):
        """Test that non-404 errors are raised for position fetch."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_position(TEST_TENANT_ID, "AAPL")

    async def test_close_position_success(self, mock_httpx_client):
        """Test closing a position."""
        mock_response = create_mock_response({}, status_code=200)
        mock_httpx_client.delete = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.close_position(TEST_TENANT_ID, "AAPL")

        assert result is True
        mock_httpx_client.delete.assert_called_once_with("/positions/AAPL")

    async def test_close_position_204_success(self, mock_httpx_client):
        """Test closing a position with 204 response."""
        mock_response = create_mock_response({}, status_code=204)
        mock_httpx_client.delete = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.close_position(TEST_TENANT_ID, "AAPL")

        assert result is True

    async def test_close_position_failure(self, mock_httpx_client):
        """Test close position failure."""
        mock_httpx_client.delete = AsyncMock(
            side_effect=httpx.HTTPStatusError("Error", request=MagicMock(), response=MagicMock())
        )

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.close_position(TEST_TENANT_ID, "AAPL")

        assert result is False

    async def test_close_all_positions_success(self, mock_httpx_client):
        """Test closing all positions."""
        mock_response = create_mock_response({}, status_code=207)
        mock_httpx_client.delete = AsyncMock(return_value=mock_response)

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.close_all_positions(TEST_TENANT_ID)

        assert result is True
        mock_httpx_client.delete.assert_called_once_with("/positions")

    async def test_close_all_positions_failure(self, mock_httpx_client):
        """Test close all positions failure."""
        mock_httpx_client.delete = AsyncMock(
            side_effect=httpx.HTTPStatusError("Error", request=MagicMock(), response=MagicMock())
        )

        with patch.object(AlpacaTradingClient, "__init__", lambda self, **kwargs: None):
            client = AlpacaTradingClient()
            client._client = mock_httpx_client

            result = await client.close_all_positions(TEST_TENANT_ID)

        assert result is False


class TestGetAlpacaTradingClient:
    """Tests for singleton client accessor."""

    def test_creates_singleton(self):
        """Test that get_alpaca_trading_client creates a singleton."""
        import src.alpaca_client as module

        module._client = None

        with patch("httpx.AsyncClient"):
            client1 = get_alpaca_trading_client()
            client2 = get_alpaca_trading_client()

        assert client1 is client2
        module._client = None

    def test_returns_existing(self):
        """Test that existing client is returned."""
        import src.alpaca_client as module

        mock_client = MagicMock()
        module._client = mock_client

        result = get_alpaca_trading_client()

        assert result is mock_client
        module._client = None
