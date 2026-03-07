"""Tests for models module."""

from datetime import UTC, datetime

from llamatrade_alpaca import (
    Bar,
    Quote,
    Snapshot,
    Timeframe,
    Trade,
    parse_bar,
    parse_quote,
    parse_snapshot,
    parse_timestamp,
    parse_trade,
)


class TestTimeframe:
    """Tests for Timeframe enum."""

    def test_minute_values(self) -> None:
        """Test minute timeframe values."""
        assert Timeframe.MINUTE_1 == "1Min"
        assert Timeframe.MINUTE_5 == "5Min"
        assert Timeframe.MINUTE_15 == "15Min"
        assert Timeframe.MINUTE_30 == "30Min"

    def test_hour_values(self) -> None:
        """Test hour timeframe values."""
        assert Timeframe.HOUR_1 == "1Hour"
        assert Timeframe.HOUR_4 == "4Hour"

    def test_day_week_values(self) -> None:
        """Test day and week timeframe values."""
        assert Timeframe.DAY_1 == "1Day"
        assert Timeframe.WEEK_1 == "1Week"


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_z_suffix(self) -> None:
        """Test parsing timestamp with Z suffix."""
        ts = parse_timestamp("2024-01-15T09:30:00Z")
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15
        assert ts.hour == 9
        assert ts.minute == 30
        assert ts.tzinfo is not None

    def test_parse_with_offset(self) -> None:
        """Test parsing timestamp with offset."""
        ts = parse_timestamp("2024-01-15T09:30:00+00:00")
        assert ts.tzinfo is not None


class TestParseBar:
    """Tests for parse_bar function."""

    def test_parse_complete_bar(self) -> None:
        """Test parsing bar with all fields."""
        data = {
            "t": "2024-01-15T09:30:00Z",
            "o": 150.25,
            "h": 151.50,
            "l": 149.75,
            "c": 151.00,
            "v": 1000000,
            "vw": 150.50,
            "n": 5000,
        }
        bar = parse_bar(data)

        assert isinstance(bar, Bar)
        assert bar.open == 150.25
        assert bar.high == 151.50
        assert bar.low == 149.75
        assert bar.close == 151.00
        assert bar.volume == 1000000
        assert bar.vwap == 150.50
        assert bar.trade_count == 5000

    def test_parse_bar_optional_fields(self) -> None:
        """Test parsing bar without optional fields."""
        data = {
            "t": "2024-01-15T09:30:00Z",
            "o": 150.25,
            "h": 151.50,
            "l": 149.75,
            "c": 151.00,
            "v": 1000000,
        }
        bar = parse_bar(data)

        assert bar.vwap is None
        assert bar.trade_count is None


class TestParseQuote:
    """Tests for parse_quote function."""

    def test_parse_quote(self) -> None:
        """Test parsing quote."""
        data = {
            "t": "2024-01-15T09:30:00Z",
            "bp": 150.00,
            "bs": 100,
            "ap": 150.10,
            "as": 200,
        }
        quote = parse_quote(data, "AAPL")

        assert isinstance(quote, Quote)
        assert quote.symbol == "AAPL"
        assert quote.bid_price == 150.00
        assert quote.bid_size == 100
        assert quote.ask_price == 150.10
        assert quote.ask_size == 200


class TestParseTrade:
    """Tests for parse_trade function."""

    def test_parse_trade_with_exchange(self) -> None:
        """Test parsing trade with exchange."""
        data = {
            "t": "2024-01-15T09:30:00Z",
            "p": 150.50,
            "s": 100,
            "x": "NYSE",
        }
        trade = parse_trade(data, "AAPL")

        assert isinstance(trade, Trade)
        assert trade.symbol == "AAPL"
        assert trade.price == 150.50
        assert trade.size == 100
        assert trade.exchange == "NYSE"

    def test_parse_trade_without_exchange(self) -> None:
        """Test parsing trade without exchange."""
        data = {
            "t": "2024-01-15T09:30:00Z",
            "p": 150.50,
            "s": 100,
        }
        trade = parse_trade(data, "AAPL")

        assert trade.exchange is None


class TestParseSnapshot:
    """Tests for parse_snapshot function."""

    def test_parse_complete_snapshot(self) -> None:
        """Test parsing snapshot with all data."""
        data = {
            "latestTrade": {
                "t": "2024-01-15T09:30:00Z",
                "p": 150.50,
                "s": 100,
                "x": "NYSE",
            },
            "latestQuote": {
                "t": "2024-01-15T09:30:00Z",
                "bp": 150.00,
                "bs": 100,
                "ap": 150.10,
                "as": 200,
            },
            "minuteBar": {
                "t": "2024-01-15T09:30:00Z",
                "o": 150.25,
                "h": 151.50,
                "l": 149.75,
                "c": 151.00,
                "v": 1000000,
            },
            "dailyBar": {
                "t": "2024-01-15T00:00:00Z",
                "o": 149.00,
                "h": 152.00,
                "l": 148.50,
                "c": 151.00,
                "v": 50000000,
            },
            "prevDailyBar": {
                "t": "2024-01-14T00:00:00Z",
                "o": 148.00,
                "h": 150.00,
                "l": 147.50,
                "c": 149.00,
                "v": 45000000,
            },
        }
        snapshot = parse_snapshot(data, "AAPL")

        assert isinstance(snapshot, Snapshot)
        assert snapshot.symbol == "AAPL"
        assert snapshot.latest_trade is not None
        assert snapshot.latest_quote is not None
        assert snapshot.minute_bar is not None
        assert snapshot.daily_bar is not None
        assert snapshot.prev_daily_bar is not None

    def test_parse_partial_snapshot(self) -> None:
        """Test parsing snapshot with missing data."""
        data = {
            "latestQuote": {
                "t": "2024-01-15T09:30:00Z",
                "bp": 150.00,
                "bs": 100,
                "ap": 150.10,
                "as": 200,
            },
        }
        snapshot = parse_snapshot(data, "AAPL")

        assert snapshot.symbol == "AAPL"
        assert snapshot.latest_trade is None
        assert snapshot.latest_quote is not None
        assert snapshot.minute_bar is None
        assert snapshot.daily_bar is None
        assert snapshot.prev_daily_bar is None


class TestModels:
    """Tests for Pydantic models."""

    def test_bar_model(self) -> None:
        """Test Bar model creation."""
        bar = Bar(
            timestamp=datetime.now(tz=UTC),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000,
        )
        assert bar.open == 100.0
        assert bar.vwap is None

    def test_quote_model(self) -> None:
        """Test Quote model creation."""
        quote = Quote(
            symbol="AAPL",
            bid_price=100.0,
            bid_size=100,
            ask_price=100.10,
            ask_size=200,
            timestamp=datetime.now(tz=UTC),
        )
        assert quote.symbol == "AAPL"

    def test_trade_model(self) -> None:
        """Test Trade model creation."""
        trade = Trade(
            symbol="AAPL",
            price=100.50,
            size=100,
            timestamp=datetime.now(tz=UTC),
        )
        assert trade.exchange is None

    def test_snapshot_model(self) -> None:
        """Test Snapshot model creation."""
        snapshot = Snapshot(symbol="AAPL")
        assert snapshot.latest_trade is None
        assert snapshot.latest_quote is None
