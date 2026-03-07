"""Tests for trading models."""

from datetime import UTC, datetime

from llamatrade_alpaca import (
    Account,
    MarketClock,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    TimeInForce,
    parse_account,
    parse_clock,
    parse_order,
    parse_position,
)


class TestOrderEnums:
    """Tests for order enums."""

    def test_order_side_values(self) -> None:
        """Test OrderSide enum values."""
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"

    def test_order_type_values(self) -> None:
        """Test OrderType enum values."""
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"
        assert OrderType.STOP == "stop"
        assert OrderType.STOP_LIMIT == "stop_limit"

    def test_order_status_values(self) -> None:
        """Test OrderStatus enum values."""
        assert OrderStatus.NEW == "new"
        assert OrderStatus.FILLED == "filled"
        assert OrderStatus.CANCELED == "canceled"
        assert OrderStatus.PARTIALLY_FILLED == "partially_filled"

    def test_time_in_force_values(self) -> None:
        """Test TimeInForce enum values."""
        assert TimeInForce.DAY == "day"
        assert TimeInForce.GTC == "gtc"
        assert TimeInForce.IOC == "ioc"


class TestParseOrder:
    """Tests for parse_order function."""

    def test_parse_complete_order(self) -> None:
        """Test parsing order with all fields."""
        data = {
            "id": "abc123",
            "client_order_id": "client-456",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "filled_qty": "5",
            "type": "limit",
            "status": "partially_filled",
            "time_in_force": "day",
            "limit_price": "150.00",
            "stop_price": None,
            "filled_avg_price": "149.50",
            "created_at": "2024-01-15T09:30:00Z",
            "submitted_at": "2024-01-15T09:30:01Z",
            "filled_at": None,
            "extended_hours": True,
        }
        order = parse_order(data)

        assert isinstance(order, Order)
        assert order.id == "abc123"
        assert order.client_order_id == "client-456"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.qty == 10.0
        assert order.filled_qty == 5.0
        assert order.order_type == OrderType.LIMIT
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.time_in_force == TimeInForce.DAY
        assert order.limit_price == 150.00
        assert order.filled_avg_price == 149.50
        assert order.extended_hours is True

    def test_parse_market_order(self) -> None:
        """Test parsing market order."""
        data = {
            "id": "xyz789",
            "symbol": "MSFT",
            "side": "sell",
            "qty": "100",
            "type": "market",
            "status": "filled",
            "time_in_force": "gtc",
            "created_at": "2024-01-15T09:30:00Z",
            "filled_at": "2024-01-15T09:30:05Z",
            "filled_qty": "100",
            "filled_avg_price": "350.25",
        }
        order = parse_order(data)

        assert order.order_type == OrderType.MARKET
        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.SELL


class TestParsePosition:
    """Tests for parse_position function."""

    def test_parse_long_position(self) -> None:
        """Test parsing long position."""
        data = {
            "symbol": "AAPL",
            "qty": "100",
            "side": "long",
            "avg_entry_price": "150.00",
            "market_value": "15500.00",
            "cost_basis": "15000.00",
            "unrealized_pl": "500.00",
            "unrealized_plpc": "0.0333",
            "current_price": "155.00",
            "lastday_price": "152.00",
            "change_today": "0.0197",
        }
        position = parse_position(data)

        assert isinstance(position, Position)
        assert position.symbol == "AAPL"
        assert position.qty == 100.0
        assert position.side == PositionSide.LONG
        assert position.avg_entry_price == 150.00
        assert position.market_value == 15500.00
        assert position.unrealized_pl == 500.00

    def test_parse_short_position(self) -> None:
        """Test parsing short position."""
        data = {
            "symbol": "GME",
            "qty": "-50",
            "side": "short",
            "avg_entry_price": "20.00",
            "market_value": "900.00",
            "cost_basis": "1000.00",
            "unrealized_pl": "100.00",
            "unrealized_plpc": "0.1",
            "current_price": "18.00",
        }
        position = parse_position(data)

        assert position.side == PositionSide.SHORT


class TestParseAccount:
    """Tests for parse_account function."""

    def test_parse_account(self) -> None:
        """Test parsing account data."""
        data = {
            "id": "account-123",
            "account_number": "ABC123456",
            "status": "ACTIVE",
            "currency": "USD",
            "cash": "10000.00",
            "portfolio_value": "50000.00",
            "buying_power": "20000.00",
            "equity": "45000.00",
            "last_equity": "44000.00",
            "long_market_value": "35000.00",
            "short_market_value": "0.00",
            "initial_margin": "5000.00",
            "maintenance_margin": "2500.00",
            "daytrade_count": "2",
            "pattern_day_trader": False,
            "trading_blocked": False,
        }
        account = parse_account(data)

        assert isinstance(account, Account)
        assert account.id == "account-123"
        assert account.account_number == "ABC123456"
        assert account.status == "ACTIVE"
        assert account.cash == 10000.00
        assert account.buying_power == 20000.00
        assert account.daytrade_count == 2


class TestParseClock:
    """Tests for parse_clock function."""

    def test_parse_clock(self) -> None:
        """Test parsing market clock data."""
        data = {
            "timestamp": "2024-01-15T14:30:00Z",
            "is_open": True,
            "next_open": "2024-01-16T14:30:00Z",
            "next_close": "2024-01-15T21:00:00Z",
        }
        clock = parse_clock(data)

        assert isinstance(clock, MarketClock)
        assert clock.is_open is True
        assert clock.timestamp.year == 2024

    def test_parse_clock_closed(self) -> None:
        """Test parsing market clock when closed."""
        data = {
            "timestamp": "2024-01-15T22:00:00Z",
            "is_open": False,
            "next_open": "2024-01-16T14:30:00Z",
            "next_close": "2024-01-16T21:00:00Z",
        }
        clock = parse_clock(data)

        assert clock.is_open is False


class TestModels:
    """Tests for model creation."""

    def test_order_model(self) -> None:
        """Test Order model creation."""
        order = Order(
            id="test-123",
            symbol="AAPL",
            side=OrderSide.BUY,
            qty=10.0,
            order_type=OrderType.MARKET,
            status=OrderStatus.NEW,
            time_in_force=TimeInForce.DAY,
            created_at=datetime.now(tz=UTC),
        )
        assert order.id == "test-123"
        assert order.filled_qty == 0

    def test_position_model(self) -> None:
        """Test Position model creation."""
        position = Position(
            symbol="AAPL",
            qty=100.0,
            side=PositionSide.LONG,
            avg_entry_price=150.0,
            market_value=15500.0,
            cost_basis=15000.0,
            unrealized_pl=500.0,
            unrealized_plpc=0.0333,
            current_price=155.0,
        )
        assert position.symbol == "AAPL"

    def test_account_model(self) -> None:
        """Test Account model creation."""
        account = Account(
            id="acc-123",
            account_number="ABC123",
            status="ACTIVE",
            cash=10000.0,
            portfolio_value=50000.0,
            buying_power=20000.0,
            equity=45000.0,
        )
        assert account.status == "ACTIVE"

    def test_market_clock_model(self) -> None:
        """Test MarketClock model creation."""
        now = datetime.now(tz=UTC)
        clock = MarketClock(
            timestamp=now,
            is_open=True,
            next_open=now,
            next_close=now,
        )
        assert clock.is_open is True
