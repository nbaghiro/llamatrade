"""Tests for trading service routers."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import (
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionResponse,
    SessionResponse,
    SessionStatus,
    TradingMode,
)

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_ORDER_ID = UUID("55555555-5555-5555-5555-555555555555")


@pytest.fixture
def mock_tenant_context():
    """Create mock tenant context."""
    return TenantContext(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_USER_ID,
        email="test@example.com",
        roles=["user"],
    )


@pytest.fixture
def auth_override(mock_tenant_context):
    """Override auth dependency."""
    app.dependency_overrides[require_auth] = lambda: mock_tenant_context
    yield
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Ensure dependency overrides are cleaned up."""
    yield
    app.dependency_overrides.clear()


class TestOrdersRouter:
    """Tests for orders router."""

    async def test_submit_order_success(self, client, auth_override):
        """Test submitting an order successfully."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.submit_order = AsyncMock(
            return_value=OrderResponse(
                id=TEST_ORDER_ID,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=10.0,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.post(
            f"/orders?session_id={TEST_SESSION_ID}",
            json={
                "symbol": "AAPL",
                "side": "buy",
                "order_type": "market",
                "qty": 10,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["side"] == "buy"

    async def test_submit_order_validation_error(self, client, auth_override):
        """Test order submission with validation error."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.submit_order = AsyncMock(side_effect=ValueError("Invalid order"))
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.post(
            f"/orders?session_id={TEST_SESSION_ID}",
            json={
                "symbol": "AAPL",
                "side": "buy",
                "order_type": "market",
                "qty": 10,
            },
        )

        assert response.status_code == 400
        assert "Invalid order" in response.json()["detail"]

    async def test_list_orders(self, client, auth_override):
        """Test listing orders."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.list_orders = AsyncMock(
            return_value=(
                [
                    OrderResponse(
                        id=TEST_ORDER_ID,
                        alpaca_order_id="alpaca-123",
                        symbol="AAPL",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        qty=10.0,
                        status=OrderStatus.FILLED,
                        submitted_at=datetime.now(UTC),
                    )
                ],
                1,
            )
        )
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.get("/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["symbol"] == "AAPL"

    async def test_list_orders_with_filters(self, client, auth_override):
        """Test listing orders with filters."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.list_orders = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.get(
            f"/orders?session_id={TEST_SESSION_ID}&status=filled&page=2&page_size=50"
        )

        assert response.status_code == 200
        mock_executor.list_orders.assert_called_once()
        call_kwargs = mock_executor.list_orders.call_args[1]
        assert call_kwargs["session_id"] == TEST_SESSION_ID
        assert call_kwargs["status"] == OrderStatus.FILLED
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 50

    async def test_get_order_success(self, client, auth_override):
        """Test getting a specific order."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.get_order = AsyncMock(
            return_value=OrderResponse(
                id=TEST_ORDER_ID,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=10.0,
                status=OrderStatus.FILLED,
                submitted_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.get(f"/orders/{TEST_ORDER_ID}")

        assert response.status_code == 200
        assert response.json()["id"] == str(TEST_ORDER_ID)

    async def test_get_order_not_found(self, client, auth_override):
        """Test getting a non-existent order."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.get_order = AsyncMock(return_value=None)
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.get(f"/orders/{TEST_ORDER_ID}")

        assert response.status_code == 404

    async def test_sync_order_status(self, client, auth_override):
        """Test syncing order status."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.sync_order_status = AsyncMock(
            return_value=OrderResponse(
                id=TEST_ORDER_ID,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                qty=10.0,
                status=OrderStatus.FILLED,
                submitted_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.post(f"/orders/{TEST_ORDER_ID}/sync")

        assert response.status_code == 200
        assert response.json()["status"] == "filled"

    async def test_sync_order_not_found(self, client, auth_override):
        """Test syncing non-existent order."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.sync_order_status = AsyncMock(return_value=None)
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.post(f"/orders/{TEST_ORDER_ID}/sync")

        assert response.status_code == 404

    async def test_cancel_order_success(self, client, auth_override):
        """Test canceling an order."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.cancel_order = AsyncMock(return_value=True)
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.delete(f"/orders/{TEST_ORDER_ID}")

        assert response.status_code == 204

    async def test_cancel_order_failure(self, client, auth_override):
        """Test cancel order failure."""
        from src.executor.order_executor import get_order_executor

        mock_executor = AsyncMock()
        mock_executor.cancel_order = AsyncMock(return_value=False)
        app.dependency_overrides[get_order_executor] = lambda: mock_executor

        response = await client.delete(f"/orders/{TEST_ORDER_ID}")

        assert response.status_code == 400


class TestPositionsRouter:
    """Tests for positions router."""

    async def test_list_positions_from_alpaca(self, client, auth_override):
        """Test listing positions from Alpaca."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.get_positions = AsyncMock(
            return_value=[
                PositionResponse(
                    symbol="AAPL",
                    qty=10.0,
                    side="long",
                    cost_basis=1500.0,
                    market_value=1600.0,
                    unrealized_pnl=100.0,
                    unrealized_pnl_percent=6.67,
                    current_price=160.0,
                )
            ]
        )
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.get("/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "AAPL"

    async def test_list_positions_from_session(self, client, auth_override):
        """Test listing positions from session."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_position_service = AsyncMock()
        mock_position_service.list_open_positions = AsyncMock(
            return_value=[
                PositionResponse(
                    symbol="AAPL",
                    qty=10.0,
                    side="long",
                    cost_basis=1500.0,
                    market_value=1600.0,
                    unrealized_pnl=100.0,
                    unrealized_pnl_percent=6.67,
                    current_price=160.0,
                )
            ]
        )
        app.dependency_overrides[get_position_service] = lambda: mock_position_service
        app.dependency_overrides[get_alpaca_trading_client] = lambda: AsyncMock()

        response = await client.get(f"/positions?session_id={TEST_SESSION_ID}")

        assert response.status_code == 200
        mock_position_service.list_open_positions.assert_called_once()

    async def test_get_position_from_alpaca(self, client, auth_override):
        """Test getting a position from Alpaca."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.get_position = AsyncMock(
            return_value=PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=1500.0,
                market_value=1600.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=6.67,
                current_price=160.0,
            )
        )
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.get("/positions/AAPL")

        assert response.status_code == 200
        assert response.json()["symbol"] == "AAPL"

    async def test_get_position_from_session(self, client, auth_override):
        """Test getting a position from session."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_position_service = AsyncMock()
        mock_position_service.get_position = AsyncMock(
            return_value=PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=1500.0,
                market_value=1600.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=6.67,
                current_price=160.0,
            )
        )
        app.dependency_overrides[get_position_service] = lambda: mock_position_service
        app.dependency_overrides[get_alpaca_trading_client] = lambda: AsyncMock()

        response = await client.get(f"/positions/AAPL?session_id={TEST_SESSION_ID}")

        assert response.status_code == 200

    async def test_get_position_not_found(self, client, auth_override):
        """Test getting a non-existent position."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.get_position = AsyncMock(return_value=None)
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.get("/positions/INVALID")

        assert response.status_code == 404

    async def test_close_position_success(self, client, auth_override):
        """Test closing a position."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.close_position = AsyncMock(return_value=True)
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.delete("/positions/AAPL")

        assert response.status_code == 204

    async def test_close_position_failure(self, client, auth_override):
        """Test close position failure."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.close_position = AsyncMock(return_value=False)
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.delete("/positions/AAPL")

        assert response.status_code == 400

    async def test_close_position_with_session(self, client, auth_override):
        """Test closing a position with session tracking."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_alpaca = AsyncMock()
        mock_alpaca.close_position = AsyncMock(return_value=True)

        mock_position_service = AsyncMock()
        mock_position_service.close_position = AsyncMock()

        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca
        app.dependency_overrides[get_position_service] = lambda: mock_position_service

        # Provide exit_price directly to avoid market data lookup
        response = await client.delete(
            f"/positions/AAPL?session_id={TEST_SESSION_ID}&exit_price=155.0"
        )

        assert response.status_code == 204
        mock_position_service.close_position.assert_called_once()

    async def test_close_all_positions(self, client, auth_override):
        """Test closing all positions."""
        from src.alpaca_client import get_alpaca_trading_client

        mock_alpaca = AsyncMock()
        mock_alpaca.close_all_positions = AsyncMock(return_value=True)
        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca

        response = await client.delete("/positions")

        assert response.status_code == 204

    async def test_sync_position(self, client, auth_override):
        """Test syncing a position."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_position_service = AsyncMock()
        mock_position_service.update_prices = AsyncMock(return_value=1)
        mock_position_service.get_position = AsyncMock(
            return_value=PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=1500.0,
                market_value=1600.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=6.67,
                current_price=160.0,
            )
        )
        app.dependency_overrides[get_position_service] = lambda: mock_position_service
        app.dependency_overrides[get_alpaca_trading_client] = lambda: AsyncMock()

        response = await client.post(f"/positions/AAPL/sync?session_id={TEST_SESSION_ID}")

        assert response.status_code == 200

    async def test_sync_position_no_positions(self, client, auth_override):
        """Test syncing when no positions exist."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_position_service = AsyncMock()
        mock_position_service.update_prices = AsyncMock(return_value=0)
        app.dependency_overrides[get_position_service] = lambda: mock_position_service
        app.dependency_overrides[get_alpaca_trading_client] = lambda: AsyncMock()

        response = await client.post(f"/positions/AAPL/sync?session_id={TEST_SESSION_ID}")

        assert response.status_code == 404

    async def test_sync_position_not_found_after_update(self, client, auth_override):
        """Test syncing when position not found after update."""
        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_position_service = AsyncMock()
        mock_position_service.update_prices = AsyncMock(return_value=1)
        mock_position_service.get_position = AsyncMock(return_value=None)
        app.dependency_overrides[get_position_service] = lambda: mock_position_service
        app.dependency_overrides[get_alpaca_trading_client] = lambda: AsyncMock()

        response = await client.post(f"/positions/AAPL/sync?session_id={TEST_SESSION_ID}")

        assert response.status_code == 404

    async def test_close_position_with_session_no_exit_price(self, client, auth_override):
        """Test closing position with session but no exit price (fetches from market data)."""

        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_alpaca = AsyncMock()
        mock_alpaca.close_position = AsyncMock(return_value=True)

        mock_position_service = AsyncMock()
        mock_position_service.close_position = AsyncMock()

        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca
        app.dependency_overrides[get_position_service] = lambda: mock_position_service

        # Mock the market data client import
        mock_market_data = MagicMock()
        mock_market_data.get_latest_price = AsyncMock(return_value=155.0)

        with patch(
            "src.clients.market_data.get_market_data_client",
            return_value=mock_market_data,
        ):
            response = await client.delete(f"/positions/AAPL?session_id={TEST_SESSION_ID}")

        assert response.status_code == 204
        mock_position_service.close_position.assert_called_once()

    async def test_close_all_positions_with_session(self, client, auth_override):
        """Test closing all positions with session tracking."""

        from src.alpaca_client import get_alpaca_trading_client
        from src.services.position_service import get_position_service

        mock_alpaca = AsyncMock()
        mock_alpaca.close_all_positions = AsyncMock(return_value=True)

        mock_position_service = AsyncMock()
        mock_position_service.list_open_positions = AsyncMock(
            return_value=[
                PositionResponse(
                    symbol="AAPL",
                    qty=10.0,
                    side="long",
                    cost_basis=1500.0,
                    market_value=1600.0,
                    unrealized_pnl=100.0,
                    unrealized_pnl_percent=6.67,
                    current_price=160.0,
                ),
                PositionResponse(
                    symbol="GOOGL",
                    qty=5.0,
                    side="long",
                    cost_basis=750.0,
                    market_value=800.0,
                    unrealized_pnl=50.0,
                    unrealized_pnl_percent=6.67,
                    current_price=160.0,
                ),
            ]
        )
        mock_position_service.close_position = AsyncMock()

        app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_alpaca
        app.dependency_overrides[get_position_service] = lambda: mock_position_service

        # Mock the market data client
        mock_market_data = MagicMock()
        mock_market_data.get_latest_price = AsyncMock(return_value=155.0)

        with patch(
            "src.clients.market_data.get_market_data_client",
            return_value=mock_market_data,
        ):
            response = await client.delete(f"/positions?session_id={TEST_SESSION_ID}")

        assert response.status_code == 204
        assert mock_position_service.close_position.call_count == 2


class TestSessionsRouter:
    """Tests for sessions router."""

    async def test_list_sessions(self, client, auth_override):
        """Test listing trading sessions."""
        from src.services.session_service import get_session_service

        mock_service = AsyncMock()
        mock_service.list_sessions = AsyncMock(return_value=([], 0))
        app.dependency_overrides[get_session_service] = lambda: mock_service

        response = await client.get("/sessions")

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_create_session(self, client, auth_override):
        """Test creating a trading session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.start_session = AsyncMock(
            return_value=SessionResponse(
                id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
                mode=TradingMode.PAPER,
                status=SessionStatus.ACTIVE,
                started_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(
            "/sessions",
            json={
                "name": "Test Session",
                "strategy_id": "33333333-3333-3333-3333-333333333333",
                "strategy_version": 1,
                "credentials_id": "66666666-6666-6666-6666-666666666666",
                "mode": "paper",
                "symbols": ["AAPL"],
                "config": {},
            },
        )

        assert response.status_code == 201

    async def test_get_session(self, client, auth_override):
        """Test getting a session."""
        from src.services.session_service import get_session_service

        mock_service = AsyncMock()
        mock_service.get_session = AsyncMock(
            return_value=SessionResponse(
                id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
                mode=TradingMode.PAPER,
                status=SessionStatus.ACTIVE,
                started_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_session_service] = lambda: mock_service

        response = await client.get(f"/sessions/{TEST_SESSION_ID}")

        assert response.status_code == 200

    async def test_get_session_not_found(self, client, auth_override):
        """Test getting non-existent session."""
        from src.services.session_service import get_session_service

        mock_service = AsyncMock()
        mock_service.get_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_session_service] = lambda: mock_service

        response = await client.get(f"/sessions/{TEST_SESSION_ID}")

        assert response.status_code == 404

    async def test_stop_session(self, client, auth_override):
        """Test stopping a session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.stop_session = AsyncMock(
            return_value=SessionResponse(
                id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
                mode=TradingMode.PAPER,
                status=SessionStatus.STOPPED,
                started_at=datetime.now(UTC),
                stopped_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/stop")

        assert response.status_code == 200

    async def test_stop_session_not_found(self, client, auth_override):
        """Test stopping non-existent session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.stop_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/stop")

        assert response.status_code == 404

    async def test_pause_session(self, client, auth_override):
        """Test pausing a session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.pause_session = AsyncMock(
            return_value=SessionResponse(
                id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
                mode=TradingMode.PAPER,
                status=SessionStatus.PAUSED,
                started_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    async def test_pause_session_not_found(self, client, auth_override):
        """Test pausing non-existent session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.pause_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/pause")

        assert response.status_code == 404

    async def test_pause_session_error(self, client, auth_override):
        """Test pausing session with error."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.pause_session = AsyncMock(side_effect=ValueError("Cannot pause"))
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/pause")

        assert response.status_code == 400

    async def test_resume_session(self, client, auth_override):
        """Test resuming a session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.resume_session = AsyncMock(
            return_value=SessionResponse(
                id=TEST_SESSION_ID,
                tenant_id=TEST_TENANT_ID,
                strategy_id=UUID("33333333-3333-3333-3333-333333333333"),
                mode=TradingMode.PAPER,
                status=SessionStatus.ACTIVE,
                started_at=datetime.now(UTC),
            )
        )
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/resume")

        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_resume_session_not_found(self, client, auth_override):
        """Test resuming non-existent session."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.resume_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/resume")

        assert response.status_code == 404

    async def test_resume_session_error(self, client, auth_override):
        """Test resuming session with error."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.resume_session = AsyncMock(side_effect=ValueError("Cannot resume"))
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(f"/sessions/{TEST_SESSION_ID}/resume")

        assert response.status_code == 400

    async def test_create_session_error(self, client, auth_override):
        """Test creating session with error."""
        from src.services.live_session_service import get_live_session_service

        mock_service = AsyncMock()
        mock_service.start_session = AsyncMock(side_effect=ValueError("Invalid strategy"))
        app.dependency_overrides[get_live_session_service] = lambda: mock_service

        response = await client.post(
            "/sessions",
            json={
                "name": "Test Session",
                "strategy_id": "33333333-3333-3333-3333-333333333333",
                "strategy_version": 1,
                "credentials_id": "66666666-6666-6666-6666-666666666666",
                "mode": "paper",
                "symbols": ["AAPL"],
                "config": {},
            },
        )

        assert response.status_code == 400
