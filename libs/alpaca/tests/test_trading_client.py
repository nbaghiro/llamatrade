"""Tests for TradingClient."""

import pytest
import respx
from httpx import Response

from llamatrade_alpaca import (
    Account,
    MarketClock,
    Order,
    OrderNotFoundError,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionNotFoundError,
    TimeInForce,
    TradingClient,
)


@pytest.fixture
def trading_client() -> TradingClient:
    """Create a TradingClient for testing."""
    return TradingClient(
        api_key="test_key",
        api_secret="test_secret",
        paper=True,
    )


class TestTradingClientInit:
    """Tests for TradingClient initialization."""

    def test_init_with_credentials(self) -> None:
        """Test client initialization with explicit credentials."""
        client = TradingClient(
            api_key="my_key",
            api_secret="my_secret",
            paper=True,
        )
        assert client.paper is True

    def test_init_live_mode(self) -> None:
        """Test client initialization in live mode."""
        client = TradingClient(
            api_key="my_key",
            api_secret="my_secret",
            paper=False,
        )
        assert client.paper is False


class TestGetAccount:
    """Tests for get_account method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_account_success(self, trading_client: TradingClient) -> None:
        """Test successful account retrieval."""
        respx.get("https://paper-api.alpaca.markets/v2/account").mock(
            return_value=Response(
                200,
                json={
                    "id": "account-123",
                    "account_number": "ABC123",
                    "status": "ACTIVE",
                    "currency": "USD",
                    "cash": "10000.00",
                    "portfolio_value": "50000.00",
                    "buying_power": "20000.00",
                    "equity": "45000.00",
                },
            )
        )

        account = await trading_client.get_account()

        assert isinstance(account, Account)
        assert account.id == "account-123"
        assert account.status == "ACTIVE"
        assert account.cash == 10000.0

        await trading_client.close()


class TestSubmitOrder:
    """Tests for submit_order method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_submit_market_order(self, trading_client: TradingClient) -> None:
        """Test submitting a market order."""
        respx.post("https://paper-api.alpaca.markets/v2/orders").mock(
            return_value=Response(
                200,
                json={
                    "id": "order-123",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "10",
                    "type": "market",
                    "status": "new",
                    "time_in_force": "day",
                    "created_at": "2024-01-15T09:30:00Z",
                },
            )
        )

        order = await trading_client.submit_order(
            symbol="AAPL",
            qty=10,
            side="buy",
            order_type="market",
        )

        assert isinstance(order, Order)
        assert order.id == "order-123"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET

        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_submit_limit_order(self, trading_client: TradingClient) -> None:
        """Test submitting a limit order."""
        respx.post("https://paper-api.alpaca.markets/v2/orders").mock(
            return_value=Response(
                200,
                json={
                    "id": "order-456",
                    "symbol": "MSFT",
                    "side": "sell",
                    "qty": "5",
                    "type": "limit",
                    "status": "new",
                    "time_in_force": "gtc",
                    "limit_price": "350.00",
                    "created_at": "2024-01-15T09:30:00Z",
                },
            )
        )

        order = await trading_client.submit_order(
            symbol="MSFT",
            qty=5,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            limit_price=350.00,
        )

        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 350.00

        await trading_client.close()


class TestGetOrder:
    """Tests for get_order method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_order_success(self, trading_client: TradingClient) -> None:
        """Test getting an order by ID."""
        respx.get("https://paper-api.alpaca.markets/v2/orders/order-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "order-123",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": "10",
                    "type": "market",
                    "status": "filled",
                    "time_in_force": "day",
                    "filled_qty": "10",
                    "filled_avg_price": "150.00",
                    "created_at": "2024-01-15T09:30:00Z",
                },
            )
        )

        order = await trading_client.get_order("order-123")

        assert order is not None
        assert order.status == OrderStatus.FILLED

        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_order_not_found(self, trading_client: TradingClient) -> None:
        """Test getting a non-existent order."""
        respx.get("https://paper-api.alpaca.markets/v2/orders/nonexistent").mock(
            return_value=Response(404, json={"message": "Order not found"})
        )

        order = await trading_client.get_order("nonexistent")

        assert order is None

        await trading_client.close()


class TestCancelOrder:
    """Tests for cancel_order method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_cancel_order_success(self, trading_client: TradingClient) -> None:
        """Test cancelling an order."""
        respx.delete("https://paper-api.alpaca.markets/v2/orders/order-123").mock(
            return_value=Response(204)
        )

        # Should not raise
        await trading_client.cancel_order("order-123")

        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_cancel_order_not_found(self, trading_client: TradingClient) -> None:
        """Test cancelling a non-existent order."""
        respx.delete("https://paper-api.alpaca.markets/v2/orders/nonexistent").mock(
            return_value=Response(404, json={"message": "Order not found"})
        )

        with pytest.raises(OrderNotFoundError):
            await trading_client.cancel_order("nonexistent")

        await trading_client.close()


class TestGetPositions:
    """Tests for position methods."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_positions(self, trading_client: TradingClient) -> None:
        """Test getting all positions."""
        respx.get("https://paper-api.alpaca.markets/v2/positions").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "symbol": "AAPL",
                        "qty": "100",
                        "side": "long",
                        "avg_entry_price": "150.00",
                        "market_value": "15500.00",
                        "cost_basis": "15000.00",
                        "unrealized_pl": "500.00",
                        "unrealized_plpc": "0.0333",
                        "current_price": "155.00",
                    }
                ],
            )
        )

        positions = await trading_client.get_positions()

        assert len(positions) == 1
        assert isinstance(positions[0], Position)
        assert positions[0].symbol == "AAPL"

        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_position_by_symbol(self, trading_client: TradingClient) -> None:
        """Test getting a specific position."""
        respx.get("https://paper-api.alpaca.markets/v2/positions/AAPL").mock(
            return_value=Response(
                200,
                json={
                    "symbol": "AAPL",
                    "qty": "100",
                    "side": "long",
                    "avg_entry_price": "150.00",
                    "market_value": "15500.00",
                    "cost_basis": "15000.00",
                    "unrealized_pl": "500.00",
                    "unrealized_plpc": "0.0333",
                    "current_price": "155.00",
                },
            )
        )

        position = await trading_client.get_position("AAPL")

        assert position is not None
        assert position.symbol == "AAPL"

        await trading_client.close()


class TestClosePosition:
    """Tests for close_position method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_close_position_success(self, trading_client: TradingClient) -> None:
        """Test closing a position."""
        respx.delete("https://paper-api.alpaca.markets/v2/positions/AAPL").mock(
            return_value=Response(
                200,
                json={
                    "id": "order-close-123",
                    "symbol": "AAPL",
                    "side": "sell",
                    "qty": "100",
                    "type": "market",
                    "status": "new",
                    "time_in_force": "day",
                    "created_at": "2024-01-15T09:30:00Z",
                },
            )
        )

        order = await trading_client.close_position("AAPL")

        assert isinstance(order, Order)
        assert order.symbol == "AAPL"

        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_close_position_not_found(self, trading_client: TradingClient) -> None:
        """Test closing a non-existent position."""
        respx.delete("https://paper-api.alpaca.markets/v2/positions/NONEXISTENT").mock(
            return_value=Response(404, json={"message": "Position not found"})
        )

        with pytest.raises(PositionNotFoundError):
            await trading_client.close_position("NONEXISTENT")

        await trading_client.close()


class TestGetClock:
    """Tests for get_clock method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_clock(self, trading_client: TradingClient) -> None:
        """Test getting market clock."""
        respx.get("https://paper-api.alpaca.markets/v2/clock").mock(
            return_value=Response(
                200,
                json={
                    "timestamp": "2024-01-15T14:30:00Z",
                    "is_open": True,
                    "next_open": "2024-01-16T14:30:00Z",
                    "next_close": "2024-01-15T21:00:00Z",
                },
            )
        )

        clock = await trading_client.get_clock()

        assert isinstance(clock, MarketClock)
        assert clock.is_open is True

        await trading_client.close()
