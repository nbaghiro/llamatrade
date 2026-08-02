"""Tests for TradingClient."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import Response

from llamatrade_alpaca import (
    Account,
    AuthenticationError,
    CircuitOpenError,
    CorporateActionDateType,
    CorporateActionType,
    InvalidRequestError,
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


class TestGetAsset:
    """Tests for get_asset method (asset tradability lookup)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_asset_tradable(self, trading_client: TradingClient) -> None:
        respx.get("https://paper-api.alpaca.markets/v2/assets/AAPL").mock(
            return_value=Response(
                200,
                json={
                    "id": "asset-1",
                    "class": "us_equity",
                    "exchange": "NASDAQ",
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "status": "active",
                    "tradable": True,
                    "fractionable": True,
                },
            )
        )

        asset = await trading_client.get_asset("AAPL")

        assert asset is not None
        assert asset.symbol == "AAPL"
        assert asset.tradable is True
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_asset_not_tradable(self, trading_client: TradingClient) -> None:
        respx.get("https://paper-api.alpaca.markets/v2/assets/XYZ").mock(
            return_value=Response(
                200,
                json={
                    "id": "asset-2",
                    "class": "us_equity",
                    "exchange": "OTC",
                    "symbol": "XYZ",
                    "name": "Delisted Co",
                    "status": "inactive",
                    "tradable": False,
                },
            )
        )

        asset = await trading_client.get_asset("XYZ")

        assert asset is not None
        assert asset.tradable is False
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_asset_unknown_returns_none(self, trading_client: TradingClient) -> None:
        respx.get("https://paper-api.alpaca.markets/v2/assets/NOPE").mock(
            return_value=Response(404, json={"message": "asset not found"})
        )

        assert await trading_client.get_asset("NOPE") is None
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_assets_returns_all(self, trading_client: TradingClient) -> None:
        respx.get("https://paper-api.alpaca.markets/v2/assets").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "a1",
                        "class": "us_equity",
                        "exchange": "ARCA",
                        "symbol": "SPY",
                        "name": "SPDR S&P 500",
                        "status": "active",
                        "tradable": True,
                        "fractionable": True,
                    },
                    {
                        "id": "a2",
                        "class": "us_equity",
                        "exchange": "NASDAQ",
                        "symbol": "QQQ",
                        "name": "Invesco QQQ",
                        "status": "active",
                        "tradable": True,
                        "fractionable": True,
                    },
                ],
            )
        )

        assets = await trading_client.list_assets()

        assert {a.symbol for a in assets} == {"SPY", "QQQ"}
        assert all(a.tradable for a in assets)
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
            qty=Decimal("10"),
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
            qty=Decimal("5"),
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            limit_price=Decimal("350.00"),
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


_CLOCK_JSON = {
    "timestamp": "2024-01-15T14:30:00Z",
    "is_open": True,
    "next_open": "2024-01-16T14:30:00Z",
    "next_close": "2024-01-15T21:00:00Z",
}
_CLOCK_URL = "https://paper-api.alpaca.markets/v2/clock"


class TestGetClockErrors:
    """Error mapping and retry/circuit behavior for get_clock."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_error_maps_and_does_not_retry(self, trading_client: TradingClient) -> None:
        route = respx.get(_CLOCK_URL).mock(
            return_value=Response(401, json={"message": "unauthorized"})
        )

        with pytest.raises(AuthenticationError):
            await trading_client.get_clock()

        assert route.call_count == 1
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_request_maps_and_does_not_retry(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_CLOCK_URL).mock(return_value=Response(400, json={"message": "bad"}))

        with pytest.raises(InvalidRequestError):
            await trading_client.get_clock()

        assert route.call_count == 1
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_retried_then_recovers(self, trading_client: TradingClient) -> None:
        route = respx.get(_CLOCK_URL)
        route.side_effect = [
            Response(500, json={"message": "boom"}),
            Response(502, json={"message": "boom"}),
            Response(200, json=_CLOCK_JSON),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            clock = await trading_client.get_clock()

        assert clock.is_open is True
        assert route.call_count == 3
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_persistent_server_errors_open_circuit(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_CLOCK_URL).mock(return_value=Response(500, json={"message": "down"}))

        # Trading breaker threshold is 3: three real attempts, then the circuit
        # opens and the final retry surfaces CircuitOpenError.
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(CircuitOpenError):
                await trading_client.get_clock()

        assert route.call_count == 3
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error_retried_then_recovers(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_CLOCK_URL)
        route.side_effect = [
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            Response(200, json=_CLOCK_JSON),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            clock = await trading_client.get_clock()

        assert isinstance(clock, MarketClock)
        assert route.call_count == 3
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_malformed_response_raises_without_retry(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_CLOCK_URL).mock(return_value=Response(200, json={}))

        with pytest.raises(KeyError):
            await trading_client.get_clock()

        assert route.call_count == 1
        await trading_client.close()


_ANNOUNCEMENTS_URL = "https://paper-api.alpaca.markets/v2/corporate_actions/announcements"


class TestGetCorporateAnnouncements:
    """Tests for get_corporate_announcements."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_parsed_announcements(self, trading_client: TradingClient) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": "ann-1",
                        "corporate_action_id": "F1",
                        "ca_type": "dividend",
                        "ca_sub_type": "cash",
                        "initiating_symbol": "AAPL",
                        "target_symbol": "AAPL",
                        "ex_date": "2024-02-09",
                        "payable_date": "2024-02-15",
                        "cash": "0.24",
                    },
                    {
                        "id": "ann-2",
                        "corporate_action_id": "S1",
                        "ca_type": "split",
                        "ca_sub_type": "stock_split",
                        "initiating_symbol": "NVDA",
                        "target_symbol": "NVDA",
                        "ex_date": "2024-06-10",
                        "old_rate": "1",
                        "new_rate": "10",
                    },
                ],
            )
        )

        announcements = await trading_client.get_corporate_announcements(
            since=date(2024, 4, 1), until=date(2024, 6, 30)
        )

        assert [a.id for a in announcements] == ["ann-1", "ann-2"]
        assert announcements[0].ca_type == CorporateActionType.DIVIDEND
        assert announcements[0].cash == Decimal("0.24")
        assert announcements[1].new_rate == Decimal("10")
        assert route.call_count == 1
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_window_and_filter_params(self, trading_client: TradingClient) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL).mock(return_value=Response(200, json=[]))

        await trading_client.get_corporate_announcements(
            since=date(2024, 1, 1),
            until=date(2024, 1, 31),
            ca_types=[CorporateActionType.DIVIDEND, CorporateActionType.SPLIT],
            symbol="aapl",
            date_type=CorporateActionDateType.PAYABLE_DATE,
        )

        params = route.calls[0].request.url.params
        assert params["ca_types"] == "dividend,split"
        assert params["since"] == "2024-01-01"
        assert params["until"] == "2024-01-31"
        assert params["symbol"] == "AAPL"
        assert params["date_type"] == "payable_date"
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_defaults_to_all_types_and_omits_optional_filters(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL).mock(return_value=Response(200, json=[]))

        assert (
            await trading_client.get_corporate_announcements(
                since=date(2024, 1, 1), until=date(2024, 1, 2)
            )
            == []
        )

        params = route.calls[0].request.url.params
        assert params["ca_types"] == "dividend,merger,spinoff,split"
        assert "symbol" not in params
        assert "date_type" not in params
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_window_over_90_days_rejected_without_call(
        self, trading_client: TradingClient
    ) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL).mock(return_value=Response(200, json=[]))

        with pytest.raises(InvalidRequestError):
            await trading_client.get_corporate_announcements(
                since=date(2024, 1, 1), until=date(2024, 5, 1)
            )

        assert route.call_count == 0
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_inverted_window_rejected(self, trading_client: TradingClient) -> None:
        with pytest.raises(InvalidRequestError):
            await trading_client.get_corporate_announcements(
                since=date(2024, 2, 1), until=date(2024, 1, 1)
            )
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_ca_types_rejected(self, trading_client: TradingClient) -> None:
        with pytest.raises(InvalidRequestError):
            await trading_client.get_corporate_announcements(
                since=date(2024, 1, 1), until=date(2024, 1, 2), ca_types=[]
            )
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_retried_then_recovers(self, trading_client: TradingClient) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL)
        route.side_effect = [
            Response(500, json={"message": "boom"}),
            Response(200, json=[]),
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            assert (
                await trading_client.get_corporate_announcements(
                    since=date(2024, 1, 1), until=date(2024, 1, 2)
                )
                == []
            )

        assert route.call_count == 2
        await trading_client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_error_maps_and_does_not_retry(self, trading_client: TradingClient) -> None:
        route = respx.get(_ANNOUNCEMENTS_URL).mock(
            return_value=Response(401, json={"message": "unauthorized"})
        )

        with pytest.raises(AuthenticationError):
            await trading_client.get_corporate_announcements(
                since=date(2024, 1, 1), until=date(2024, 1, 2)
            )

        assert route.call_count == 1
        await trading_client.close()
