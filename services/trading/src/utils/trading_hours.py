"""Trading hours utility for market session management.

This module provides utilities for checking market hours and handling
trading sessions with proper timezone and holiday support.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

logger = logging.getLogger(__name__)

# US Eastern timezone
ET = ZoneInfo("America/New_York")

# Standard US market hours
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended hours
PRE_MARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


@dataclass(frozen=True)
class TradingHoursConfig:
    """Configuration for trading hours checker.

    Attributes:
        exchange: Exchange code (e.g., "XNYS" for NYSE).
        allow_premarket: Whether to allow trading during pre-market hours.
        allow_afterhours: Whether to allow trading during after-hours.
        premarket_open: Pre-market open time (ET).
        regular_open: Regular market open time (ET).
        regular_close: Regular market close time (ET).
        afterhours_close: After-hours close time (ET).
    """

    exchange: str = "XNYS"  # NYSE
    allow_premarket: bool = False
    allow_afterhours: bool = False
    premarket_open: time = PRE_MARKET_OPEN
    regular_open: time = MARKET_OPEN
    regular_close: time = MARKET_CLOSE
    afterhours_close: time = AFTER_HOURS_CLOSE


@dataclass
class MarketSession:
    """Information about the current or next market session.

    Attributes:
        session_type: Type of session ("regular", "premarket", "afterhours", "closed").
        is_open: Whether trading is allowed in this session.
        session_open: When this session opened.
        session_close: When this session closes.
        next_regular_open: When the next regular session opens (if market is closed).
    """

    session_type: str
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    next_regular_open: datetime | None = None


class TradingHoursChecker:
    """Checks market hours and determines if trading is allowed.

    Uses exchange-calendars library for accurate holiday and special session
    handling. Supports regular, pre-market, and after-hours sessions.

    Usage:
        checker = TradingHoursChecker()

        # Check if market is open now
        if checker.is_market_open():
            # Execute trade
            pass

        # Check if a specific time is during market hours
        if checker.is_market_open(some_timestamp):
            # Process bar
            pass

        # Get next market open time
        next_open = checker.get_next_open()
    """

    def __init__(self, config: TradingHoursConfig | None = None):
        """Initialize the trading hours checker.

        Args:
            config: Trading hours configuration. Defaults to NYSE with
                regular hours only.
        """
        self.config = config or TradingHoursConfig()
        self._calendar = xcals.get_calendar(self.config.exchange)

    def is_market_open(
        self,
        timestamp: datetime | None = None,
        check_holidays: bool = True,
    ) -> bool:
        """Check if the market is open at a given time.

        Args:
            timestamp: Time to check. Defaults to current time.
            check_holidays: Whether to check for holidays. Set to False
                for faster checks when you know it's not a holiday.

        Returns:
            True if trading is allowed at the given time.
        """
        ts = timestamp or datetime.now(ET)

        # Ensure timestamp is in ET
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        else:
            ts = ts.astimezone(ET)

        # Check if it's a weekend
        if ts.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Check holidays using exchange calendar
        if check_holidays:
            ts_date = ts.date()
            if not self._calendar.is_session(ts_date):
                return False

        # Get the current time of day
        current_time = ts.time()

        # Check pre-market hours
        if self.config.allow_premarket:
            if self.config.premarket_open <= current_time < self.config.regular_open:
                return True

        # Check regular hours
        if self.config.regular_open <= current_time < self.config.regular_close:
            return True

        # Check after-hours
        if self.config.allow_afterhours:
            if self.config.regular_close <= current_time < self.config.afterhours_close:
                return True

        return False

    def get_session_info(self, timestamp: datetime | None = None) -> MarketSession:
        """Get detailed information about the current market session.

        Args:
            timestamp: Time to check. Defaults to current time.

        Returns:
            MarketSession with session details.
        """
        ts = timestamp or datetime.now(ET)

        # Ensure timestamp is in ET
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        else:
            ts = ts.astimezone(ET)

        ts_date = ts.date()
        current_time = ts.time()

        # Check if it's a trading day
        is_trading_day = self._calendar.is_session(ts_date)

        if not is_trading_day:
            next_open = self.get_next_open(ts)
            return MarketSession(
                session_type="closed",
                is_open=False,
                session_open=None,
                session_close=None,
                next_regular_open=next_open,
            )

        # Get session bounds
        premarket_open_dt = datetime.combine(ts_date, self.config.premarket_open, tzinfo=ET)
        regular_open_dt = datetime.combine(ts_date, self.config.regular_open, tzinfo=ET)
        regular_close_dt = datetime.combine(ts_date, self.config.regular_close, tzinfo=ET)
        afterhours_close_dt = datetime.combine(ts_date, self.config.afterhours_close, tzinfo=ET)

        # Determine session type
        if current_time < self.config.premarket_open:
            # Before pre-market
            return MarketSession(
                session_type="closed",
                is_open=False,
                session_open=None,
                session_close=None,
                next_regular_open=regular_open_dt,
            )
        elif current_time < self.config.regular_open:
            # Pre-market
            return MarketSession(
                session_type="premarket",
                is_open=self.config.allow_premarket,
                session_open=premarket_open_dt,
                session_close=regular_open_dt,
                next_regular_open=regular_open_dt,
            )
        elif current_time < self.config.regular_close:
            # Regular hours
            return MarketSession(
                session_type="regular",
                is_open=True,
                session_open=regular_open_dt,
                session_close=regular_close_dt,
            )
        elif current_time < self.config.afterhours_close:
            # After-hours
            next_open = self.get_next_open(ts + timedelta(days=1))
            return MarketSession(
                session_type="afterhours",
                is_open=self.config.allow_afterhours,
                session_open=regular_close_dt,
                session_close=afterhours_close_dt,
                next_regular_open=next_open,
            )
        else:
            # After after-hours
            next_open = self.get_next_open(ts + timedelta(days=1))
            return MarketSession(
                session_type="closed",
                is_open=False,
                session_open=None,
                session_close=None,
                next_regular_open=next_open,
            )

    def get_next_open(self, from_timestamp: datetime | None = None) -> datetime:
        """Get the next market open time.

        Args:
            from_timestamp: Start time for search. Defaults to current time.

        Returns:
            Next market open datetime in ET timezone.
        """
        ts = from_timestamp or datetime.now(ET)

        # Ensure timestamp is in ET
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        else:
            ts = ts.astimezone(ET)

        # Start searching from the given date
        search_date = ts.date()

        # If we're past market open today, start from tomorrow
        if ts.time() >= self.config.regular_open:
            search_date = search_date + timedelta(days=1)

        # Find the next valid trading session
        max_days = 10  # Safety limit (covers long holiday weekends)
        for _ in range(max_days):
            if self._calendar.is_session(search_date):
                # Found a trading day
                return datetime.combine(search_date, self.config.regular_open, tzinfo=ET)
            search_date = search_date + timedelta(days=1)

        # Fallback: shouldn't happen unless calendar is malformed
        logger.warning(f"Could not find next trading session within {max_days} days")
        return datetime.combine(search_date, self.config.regular_open, tzinfo=ET)

    def get_next_close(self, from_timestamp: datetime | None = None) -> datetime:
        """Get the next market close time.

        Args:
            from_timestamp: Start time for search. Defaults to current time.

        Returns:
            Next market close datetime in ET timezone.
        """
        ts = from_timestamp or datetime.now(ET)

        # Ensure timestamp is in ET
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        else:
            ts = ts.astimezone(ET)

        # Check if today is a trading day and we're before close
        if self._calendar.is_session(ts.date()) and ts.time() < self.config.regular_close:
            return datetime.combine(ts.date(), self.config.regular_close, tzinfo=ET)

        # Otherwise, find the next trading day
        next_open = self.get_next_open(ts)
        return datetime.combine(next_open.date(), self.config.regular_close, tzinfo=ET)

    def seconds_until_open(self, from_timestamp: datetime | None = None) -> float:
        """Get seconds until the next market open.

        Args:
            from_timestamp: Start time. Defaults to current time.

        Returns:
            Seconds until next market open. Returns 0 if market is open.
        """
        ts = from_timestamp or datetime.now(ET)

        if self.is_market_open(ts):
            return 0.0

        next_open = self.get_next_open(ts)
        return (next_open - ts).total_seconds()

    def seconds_until_close(self, from_timestamp: datetime | None = None) -> float | None:
        """Get seconds until the current session closes.

        Args:
            from_timestamp: Start time. Defaults to current time.

        Returns:
            Seconds until market close. Returns None if market is closed.
        """
        ts = from_timestamp or datetime.now(ET)

        if not self.is_market_open(ts):
            return None

        next_close = self.get_next_close(ts)
        return (next_close - ts).total_seconds()

    def is_early_close_day(self, check_date: datetime | None = None) -> bool:
        """Check if a given date is an early close day (e.g., day before holiday).

        Args:
            check_date: Date to check. Defaults to today.

        Returns:
            True if the market closes early on this day.
        """
        ts = check_date or datetime.now(ET)
        ts_date = ts.date()

        if not self._calendar.is_session(ts_date):
            return False

        # Check if the session has early close
        try:
            session = self._calendar.session_open_close(ts_date)
            close_time = session[1].time()
            return close_time < self.config.regular_close
        except Exception:
            return False


# Singleton instance for default usage
_default_checker: TradingHoursChecker | None = None


def get_trading_hours_checker(
    config: TradingHoursConfig | None = None,
) -> TradingHoursChecker:
    """Get a trading hours checker instance.

    Args:
        config: Optional configuration. If provided, creates a new instance.
            If None, returns a shared singleton with default config.

    Returns:
        TradingHoursChecker instance.
    """
    global _default_checker

    if config is not None:
        return TradingHoursChecker(config)

    if _default_checker is None:
        _default_checker = TradingHoursChecker()

    return _default_checker
