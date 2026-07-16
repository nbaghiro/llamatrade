"""Unit tests for the server-side NYSE market calendar."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.market_calendar import (
    MarketState,
    early_close_days,
    market_holidays,
    market_status,
)

_ET = ZoneInfo("America/New_York")


def _et(year, month, day, hour, minute=0):
    """Build a UTC instant from an Eastern-Time wall clock."""
    return datetime(year, month, day, hour, minute, tzinfo=_ET).astimezone(UTC)


# === Holiday set ===


class TestHolidays:
    def test_2025_full_holidays(self):
        from datetime import date

        assert market_holidays(2025) == frozenset(
            {
                date(2025, 1, 1),  # New Year's Day
                date(2025, 1, 20),  # MLK Jr. Day
                date(2025, 2, 17),  # Washington's Birthday
                date(2025, 4, 18),  # Good Friday
                date(2025, 5, 26),  # Memorial Day
                date(2025, 6, 19),  # Juneteenth
                date(2025, 7, 4),  # Independence Day
                date(2025, 9, 1),  # Labor Day
                date(2025, 11, 27),  # Thanksgiving
                date(2025, 12, 25),  # Christmas
            }
        )

    def test_independence_day_saturday_observed_friday(self):
        from datetime import date

        # July 4, 2026 is a Saturday -> observed Friday July 3.
        assert date(2026, 7, 3) in market_holidays(2026)

    def test_juneteenth_absent_before_2022(self):
        from datetime import date

        assert date(2021, 6, 19) not in market_holidays(2021)
        assert date(2022, 6, 20) in market_holidays(2022)  # Jun 19 2022 is a Sunday

    def test_new_year_saturday_not_observed_on_friday(self):
        from datetime import date

        # Jan 1, 2028 is a Saturday: NYSE is NOT closed the preceding Friday.
        assert date(2027, 12, 31) not in market_holidays(2027)
        assert date(2028, 1, 1) not in market_holidays(2028)

    def test_early_close_days_2025(self):
        from datetime import date

        assert early_close_days(2025) == frozenset(
            {
                date(2025, 7, 3),  # day before Independence Day (Thu)
                date(2025, 11, 28),  # Black Friday
                date(2025, 12, 24),  # Christmas Eve
            }
        )


# === Status transitions ===


class TestMarketStatus:
    def test_regular_hours_open(self):
        result = market_status(_et(2026, 7, 15, 10, 0))  # Wednesday 10:00 ET
        assert result.state is MarketState.OPEN
        assert result.next_close == _et(2026, 7, 15, 16, 0)
        assert result.next_open == _et(2026, 7, 16, 9, 30)  # next session's open

    def test_pre_market(self):
        result = market_status(_et(2026, 7, 15, 8, 0))
        assert result.state is MarketState.PRE_MARKET
        assert result.next_open == _et(2026, 7, 15, 9, 30)
        assert result.next_close == _et(2026, 7, 15, 16, 0)

    def test_before_pre_market_is_closed(self):
        result = market_status(_et(2026, 7, 15, 3, 0))
        assert result.state is MarketState.CLOSED

    def test_after_hours(self):
        result = market_status(_et(2026, 7, 15, 17, 0))
        assert result.state is MarketState.AFTER_HOURS
        assert result.next_open == _et(2026, 7, 16, 9, 30)

    def test_late_night_closed(self):
        result = market_status(_et(2026, 7, 15, 21, 0))
        assert result.state is MarketState.CLOSED

    def test_weekend_closed_rolls_to_monday(self):
        result = market_status(_et(2026, 7, 18, 12, 0))  # Saturday
        assert result.state is MarketState.CLOSED
        assert result.next_open == _et(2026, 7, 20, 9, 30)  # Monday

    def test_holiday_closed(self):
        result = market_status(_et(2026, 12, 25, 11, 0))  # Christmas (Friday)
        assert result.state is MarketState.CLOSED
        assert result.next_open == _et(2026, 12, 28, 9, 30)  # Monday

    def test_early_close_half_day_open(self):
        # July 3, 2025 (Thu) closes at 13:00 ET.
        result = market_status(_et(2025, 7, 3, 12, 0))
        assert result.state is MarketState.OPEN
        assert result.next_close == _et(2025, 7, 3, 13, 0)

    def test_early_close_after_hours(self):
        result = market_status(_et(2025, 7, 3, 14, 0))
        assert result.state is MarketState.AFTER_HOURS

    def test_dst_offsets(self):
        # Summer sessions are UTC-4, winter sessions UTC-5.
        summer = market_status(_et(2026, 7, 15, 10, 0))
        winter = market_status(_et(2026, 1, 15, 10, 0))
        assert summer.next_close.hour == 20  # 16:00 EDT -> 20:00 UTC
        assert winter.next_close.hour == 21  # 16:00 EST -> 21:00 UTC

    def test_next_open_is_timezone_aware_utc(self):
        result = market_status(_et(2026, 7, 18, 12, 0))
        assert result.next_open.tzinfo is UTC
        assert result.next_close.tzinfo is UTC


@pytest.mark.parametrize(
    "instant",
    [
        _et(2026, 1, 1, 12, 0),  # New Year's Day
        _et(2026, 7, 4, 12, 0),  # Independence Day (Saturday)
        _et(2026, 11, 26, 12, 0),  # Thanksgiving
    ],
)
def test_known_holidays_report_closed(instant):
    assert market_status(instant).state is MarketState.CLOSED
