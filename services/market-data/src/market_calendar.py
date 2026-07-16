"""Server-side US equity (NYSE/Nasdaq) market calendar.

Computes market open/closed state plus the next open/close purely from the
calendar — no external API. Used as the source of truth for ``GetMarketStatus``
when Alpaca credentials are absent, and as a graceful fallback when the Alpaca
clock endpoint is unavailable.

Covers regular NYSE sessions (09:30-16:00 ET), the pre-market (04:00-09:30 ET)
and after-hours (16:00-20:00 ET) windows, weekends, the standard full-day US
market holidays, and the standard 13:00 ET early-close half days. All arithmetic
is done in America/New_York so DST is handled by ``zoneinfo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import IntEnum
from functools import lru_cache
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# Session boundaries in Eastern Time.
_PRE_MARKET_OPEN = time(4, 0)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)
_AFTER_HOURS_END = time(20, 0)

# Weekday constants (Monday=0 .. Sunday=6).
_SATURDAY = 5
_SUNDAY = 6


class MarketState(IntEnum):
    """Calendar-derived market state.

    Values intentionally mirror ``market_data_pb2.MarketStatus`` so the mapping
    to proto is unambiguous, but the servicer maps explicitly (see ``_CAL_TO_PROTO``).
    """

    OPEN = 1
    CLOSED = 2
    PRE_MARKET = 3
    AFTER_HOURS = 4


@dataclass(frozen=True)
class MarketCalendarStatus:
    """Result of a calendar status lookup. Timestamps are timezone-aware UTC."""

    state: MarketState
    next_open: datetime
    next_close: datetime


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the ``n``-th ``weekday`` (Mon=0) of ``month`` (1-indexed)."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last ``weekday`` (Mon=0) of ``month``."""
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observed(holiday: date) -> date:
    """Apply the standard Sat->Fri / Sun->Mon observance shift."""
    if holiday.weekday() == _SATURDAY:
        return holiday - timedelta(days=1)
    if holiday.weekday() == _SUNDAY:
        return holiday + timedelta(days=1)
    return holiday


def _new_year_observed(year: int) -> date | None:
    """New Year's Day observance.

    Per NYSE rules the exchange is NOT closed the preceding Friday when Jan 1
    falls on a Saturday; a Sunday shifts observance to Monday.
    """
    day = date(year, 1, 1)
    if day.weekday() == _SATURDAY:
        return None
    if day.weekday() == _SUNDAY:
        return day + timedelta(days=1)
    return day


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    m = (a + 11 * h + 22 * ((32 + 2 * e + 2 * i - h - k) % 7)) // 451
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=32)
def market_holidays(year: int) -> frozenset[date]:
    """Full-day NYSE market holidays observed in ``year``."""
    holidays: set[date] = set()
    new_year = _new_year_observed(year)
    if new_year is not None:
        holidays.add(new_year)
    holidays.add(_nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
    holidays.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday
    holidays.add(_easter(year) - timedelta(days=2))  # Good Friday
    holidays.add(_last_weekday(year, 5, 0))  # Memorial Day
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))  # Juneteenth
    holidays.add(_observed(date(year, 7, 4)))  # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))  # Labor Day
    holidays.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
    holidays.add(_observed(date(year, 12, 25)))  # Christmas
    return frozenset(holidays)


@lru_cache(maxsize=32)
def early_close_days(year: int) -> frozenset[date]:
    """Half sessions that close at 13:00 ET (holidays excluded)."""
    candidates: set[date] = set()
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    candidates.add(thanksgiving + timedelta(days=1))  # Black Friday
    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < _SATURDAY:
        candidates.add(christmas_eve)
    july_3 = date(year, 7, 3)
    july_4 = date(year, 7, 4)
    if july_3.weekday() < _SATURDAY and july_4.weekday() < _SATURDAY:
        candidates.add(july_3)  # only when the 4th is a real weekday holiday
    return frozenset(candidates - market_holidays(year))


def _is_trading_day(day: date) -> bool:
    return day.weekday() < _SATURDAY and day not in market_holidays(day.year)


def _session_close_time(day: date) -> time:
    return _EARLY_CLOSE if day in early_close_days(day.year) else _REGULAR_CLOSE


def _session_bounds(day: date) -> tuple[datetime, datetime] | None:
    """Regular-session (open, close) in ET for ``day``, or None if closed."""
    if not _is_trading_day(day):
        return None
    open_dt = datetime.combine(day, _REGULAR_OPEN, tzinfo=_ET)
    close_dt = datetime.combine(day, _session_close_time(day), tzinfo=_ET)
    return open_dt, close_dt


def _next_session(start: date) -> tuple[datetime, datetime]:
    """(open, close) in ET of the first trading day on or after ``start``."""
    day = start
    for _ in range(14):  # max realistic gap is a holiday-extended long weekend
        bounds = _session_bounds(day)
        if bounds is not None:
            return bounds
        day += timedelta(days=1)
    raise RuntimeError(f"No trading day found within 14 days of {start}")


def market_status(now: datetime) -> MarketCalendarStatus:
    """Compute market state and next open/close for the instant ``now`` (UTC)."""
    eastern = now.astimezone(_ET)
    today = eastern.date()
    todays = _session_bounds(today)

    if todays is not None:
        open_dt, close_dt = todays
        pre_dt = datetime.combine(today, _PRE_MARKET_OPEN, tzinfo=_ET)
        after_dt = datetime.combine(today, _AFTER_HOURS_END, tzinfo=_ET)

        if eastern < open_dt:
            state = MarketState.PRE_MARKET if eastern >= pre_dt else MarketState.CLOSED
            next_open, next_close = open_dt, close_dt
        elif eastern < close_dt:
            state = MarketState.OPEN
            next_open = _next_session(today + timedelta(days=1))[0]
            next_close = close_dt
        elif eastern < after_dt:
            state = MarketState.AFTER_HOURS
            next_open, next_close = _next_session(today + timedelta(days=1))
        else:
            state = MarketState.CLOSED
            next_open, next_close = _next_session(today + timedelta(days=1))
    else:
        state = MarketState.CLOSED
        next_open, next_close = _next_session(today + timedelta(days=1))

    return MarketCalendarStatus(
        state=state,
        next_open=next_open.astimezone(UTC),
        next_close=next_close.astimezone(UTC),
    )
