"""Tests for trading hours utility."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.utils.trading_hours import (
    ET,
    TradingHoursChecker,
    TradingHoursConfig,
    get_trading_hours_checker,
)


@pytest.fixture
def checker() -> TradingHoursChecker:
    """Create default trading hours checker."""
    return TradingHoursChecker()


@pytest.fixture
def extended_hours_checker() -> TradingHoursChecker:
    """Create checker with extended hours enabled."""
    config = TradingHoursConfig(
        allow_premarket=True,
        allow_afterhours=True,
    )
    return TradingHoursChecker(config)


class TestIsMarketOpen:
    """Tests for is_market_open method."""

    def test_regular_hours_open(self, checker: TradingHoursChecker) -> None:
        """Test that regular trading hours are recognized as open."""
        # Use a known trading day (Monday, non-holiday)
        # January 6, 2025 is a Monday
        trading_day = datetime(2025, 1, 6, 10, 30, tzinfo=ET)
        assert checker.is_market_open(trading_day) is True

    def test_regular_hours_market_open_boundary(self, checker: TradingHoursChecker) -> None:
        """Test exact market open time."""
        # 9:30 AM ET on a trading day
        trading_day = datetime(2025, 1, 6, 9, 30, tzinfo=ET)
        assert checker.is_market_open(trading_day) is True

    def test_regular_hours_before_open(self, checker: TradingHoursChecker) -> None:
        """Test that time before market open is closed."""
        # 9:29 AM ET on a trading day
        trading_day = datetime(2025, 1, 6, 9, 29, tzinfo=ET)
        assert checker.is_market_open(trading_day) is False

    def test_regular_hours_at_close(self, checker: TradingHoursChecker) -> None:
        """Test exact market close time (should be closed)."""
        # 4:00 PM ET on a trading day
        trading_day = datetime(2025, 1, 6, 16, 0, tzinfo=ET)
        assert checker.is_market_open(trading_day) is False

    def test_regular_hours_just_before_close(self, checker: TradingHoursChecker) -> None:
        """Test one minute before market close."""
        # 3:59 PM ET on a trading day
        trading_day = datetime(2025, 1, 6, 15, 59, tzinfo=ET)
        assert checker.is_market_open(trading_day) is True

    def test_weekend_saturday(self, checker: TradingHoursChecker) -> None:
        """Test that Saturday is closed."""
        # January 4, 2025 is a Saturday
        saturday = datetime(2025, 1, 4, 12, 0, tzinfo=ET)
        assert checker.is_market_open(saturday) is False

    def test_weekend_sunday(self, checker: TradingHoursChecker) -> None:
        """Test that Sunday is closed."""
        # January 5, 2025 is a Sunday
        sunday = datetime(2025, 1, 5, 12, 0, tzinfo=ET)
        assert checker.is_market_open(sunday) is False

    def test_premarket_without_extended_hours(self, checker: TradingHoursChecker) -> None:
        """Test that pre-market is closed by default."""
        # 8:00 AM ET on a trading day (pre-market)
        trading_day = datetime(2025, 1, 6, 8, 0, tzinfo=ET)
        assert checker.is_market_open(trading_day) is False

    def test_premarket_with_extended_hours(
        self, extended_hours_checker: TradingHoursChecker
    ) -> None:
        """Test that pre-market is open when enabled."""
        # 8:00 AM ET on a trading day (pre-market)
        trading_day = datetime(2025, 1, 6, 8, 0, tzinfo=ET)
        assert extended_hours_checker.is_market_open(trading_day) is True

    def test_afterhours_without_extended_hours(self, checker: TradingHoursChecker) -> None:
        """Test that after-hours is closed by default."""
        # 5:00 PM ET on a trading day (after-hours)
        trading_day = datetime(2025, 1, 6, 17, 0, tzinfo=ET)
        assert checker.is_market_open(trading_day) is False

    def test_afterhours_with_extended_hours(
        self, extended_hours_checker: TradingHoursChecker
    ) -> None:
        """Test that after-hours is open when enabled."""
        # 5:00 PM ET on a trading day (after-hours)
        trading_day = datetime(2025, 1, 6, 17, 0, tzinfo=ET)
        assert extended_hours_checker.is_market_open(trading_day) is True

    def test_timezone_conversion_utc(self, checker: TradingHoursChecker) -> None:
        """Test that UTC timestamps are properly converted."""
        # 2:30 PM UTC = 9:30 AM ET (market open)
        utc_time = datetime(2025, 1, 6, 14, 30, tzinfo=ZoneInfo("UTC"))
        assert checker.is_market_open(utc_time) is True

    def test_timezone_conversion_pacific(self, checker: TradingHoursChecker) -> None:
        """Test that Pacific timestamps are properly converted."""
        # 6:30 AM PT = 9:30 AM ET (market open)
        pacific_time = datetime(2025, 1, 6, 6, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
        assert checker.is_market_open(pacific_time) is True


class TestGetNextOpen:
    """Tests for get_next_open method."""

    def test_get_next_open_during_trading_day(self, checker: TradingHoursChecker) -> None:
        """Test getting next open when already open (returns tomorrow)."""
        # During trading hours
        trading_day = datetime(2025, 1, 6, 12, 0, tzinfo=ET)
        next_open = checker.get_next_open(trading_day)

        # Should return next trading day at 9:30 AM
        assert next_open.date() > trading_day.date()
        assert next_open.time() == time(9, 30)

    def test_get_next_open_before_market_open(self, checker: TradingHoursChecker) -> None:
        """Test getting next open before market opens today."""
        # Before market opens
        trading_day = datetime(2025, 1, 6, 8, 0, tzinfo=ET)
        next_open = checker.get_next_open(trading_day)

        # Should return today at 9:30 AM
        assert next_open.date() == trading_day.date()
        assert next_open.time() == time(9, 30)

    def test_get_next_open_on_weekend(self, checker: TradingHoursChecker) -> None:
        """Test getting next open from a weekend."""
        # Saturday
        saturday = datetime(2025, 1, 4, 12, 0, tzinfo=ET)
        next_open = checker.get_next_open(saturday)

        # Should return Monday at 9:30 AM
        assert next_open.weekday() == 0  # Monday
        assert next_open.time() == time(9, 30)


class TestGetNextClose:
    """Tests for get_next_close method."""

    def test_get_next_close_during_trading(self, checker: TradingHoursChecker) -> None:
        """Test getting next close during trading hours."""
        # During trading hours
        trading_day = datetime(2025, 1, 6, 12, 0, tzinfo=ET)
        next_close = checker.get_next_close(trading_day)

        # Should return today at 4:00 PM
        assert next_close.date() == trading_day.date()
        assert next_close.time() == time(16, 0)

    def test_get_next_close_after_close(self, checker: TradingHoursChecker) -> None:
        """Test getting next close after market closed."""
        # After market close
        trading_day = datetime(2025, 1, 6, 17, 0, tzinfo=ET)
        next_close = checker.get_next_close(trading_day)

        # Should return next trading day at 4:00 PM
        assert next_close.date() > trading_day.date()
        assert next_close.time() == time(16, 0)


class TestGetSessionInfo:
    """Tests for get_session_info method."""

    def test_session_info_regular_hours(self, checker: TradingHoursChecker) -> None:
        """Test session info during regular hours."""
        trading_day = datetime(2025, 1, 6, 12, 0, tzinfo=ET)
        session = checker.get_session_info(trading_day)

        assert session.session_type == "regular"
        assert session.is_open is True
        assert session.session_open is not None
        assert session.session_close is not None
        assert session.session_open.time() == time(9, 30)
        assert session.session_close.time() == time(16, 0)

    def test_session_info_premarket(self, extended_hours_checker: TradingHoursChecker) -> None:
        """Test session info during pre-market."""
        trading_day = datetime(2025, 1, 6, 8, 0, tzinfo=ET)
        session = extended_hours_checker.get_session_info(trading_day)

        assert session.session_type == "premarket"
        assert session.is_open is True  # Extended hours enabled

    def test_session_info_premarket_disabled(self, checker: TradingHoursChecker) -> None:
        """Test session info during pre-market when disabled."""
        trading_day = datetime(2025, 1, 6, 8, 0, tzinfo=ET)
        session = checker.get_session_info(trading_day)

        assert session.session_type == "premarket"
        assert session.is_open is False  # Extended hours disabled

    def test_session_info_afterhours(self, extended_hours_checker: TradingHoursChecker) -> None:
        """Test session info during after-hours."""
        trading_day = datetime(2025, 1, 6, 17, 0, tzinfo=ET)
        session = extended_hours_checker.get_session_info(trading_day)

        assert session.session_type == "afterhours"
        assert session.is_open is True  # Extended hours enabled

    def test_session_info_closed_weekend(self, checker: TradingHoursChecker) -> None:
        """Test session info on weekend."""
        saturday = datetime(2025, 1, 4, 12, 0, tzinfo=ET)
        session = checker.get_session_info(saturday)

        assert session.session_type == "closed"
        assert session.is_open is False
        assert session.next_regular_open is not None


class TestSecondsUntilOpenClose:
    """Tests for seconds_until_open and seconds_until_close methods."""

    def test_seconds_until_open_when_closed(self, checker: TradingHoursChecker) -> None:
        """Test seconds until open when market is closed."""
        # 9:00 AM ET (30 minutes before open)
        trading_day = datetime(2025, 1, 6, 9, 0, tzinfo=ET)
        seconds = checker.seconds_until_open(trading_day)

        # Should be 30 minutes = 1800 seconds
        assert seconds == pytest.approx(1800.0, abs=60)

    def test_seconds_until_open_when_open(self, checker: TradingHoursChecker) -> None:
        """Test seconds until open when market is open."""
        trading_day = datetime(2025, 1, 6, 12, 0, tzinfo=ET)
        seconds = checker.seconds_until_open(trading_day)

        assert seconds == 0.0

    def test_seconds_until_close_when_open(self, checker: TradingHoursChecker) -> None:
        """Test seconds until close when market is open."""
        # 3:00 PM ET (1 hour before close)
        trading_day = datetime(2025, 1, 6, 15, 0, tzinfo=ET)
        seconds = checker.seconds_until_close(trading_day)

        # Should be 1 hour = 3600 seconds
        assert seconds == pytest.approx(3600.0, abs=60)

    def test_seconds_until_close_when_closed(self, checker: TradingHoursChecker) -> None:
        """Test seconds until close when market is closed."""
        saturday = datetime(2025, 1, 4, 12, 0, tzinfo=ET)
        seconds = checker.seconds_until_close(saturday)

        assert seconds is None


class TestCustomConfig:
    """Tests for custom trading hours configuration."""

    def test_custom_regular_hours(self) -> None:
        """Test custom regular hours configuration."""
        config = TradingHoursConfig(
            regular_open=time(10, 0),
            regular_close=time(15, 0),
        )
        checker = TradingHoursChecker(config)

        # 10:30 AM should be open with custom hours
        trading_day = datetime(2025, 1, 6, 10, 30, tzinfo=ET)
        assert checker.is_market_open(trading_day) is True

        # 9:30 AM should be closed with custom hours
        early_morning = datetime(2025, 1, 6, 9, 30, tzinfo=ET)
        assert checker.is_market_open(early_morning) is False

    def test_custom_premarket_hours(self) -> None:
        """Test custom pre-market hours configuration."""
        config = TradingHoursConfig(
            allow_premarket=True,
            premarket_open=time(7, 0),  # Custom pre-market start
        )
        checker = TradingHoursChecker(config)

        # 7:30 AM should be open with custom pre-market
        trading_day = datetime(2025, 1, 6, 7, 30, tzinfo=ET)
        assert checker.is_market_open(trading_day) is True

        # 6:30 AM should be closed (before custom pre-market)
        too_early = datetime(2025, 1, 6, 6, 30, tzinfo=ET)
        assert checker.is_market_open(too_early) is False


class TestSingletonFactory:
    """Tests for get_trading_hours_checker factory function."""

    def test_returns_singleton_without_config(self) -> None:
        """Test that the same instance is returned without config."""
        checker1 = get_trading_hours_checker()
        checker2 = get_trading_hours_checker()

        assert checker1 is checker2

    def test_returns_new_instance_with_config(self) -> None:
        """Test that a new instance is returned with config."""
        default = get_trading_hours_checker()
        custom = get_trading_hours_checker(TradingHoursConfig(allow_premarket=True))

        assert default is not custom
        assert default.config.allow_premarket is False
        assert custom.config.allow_premarket is True
