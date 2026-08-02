"""Tests for the single rebalance clock."""

from datetime import date, timedelta

from llamatrade_runtime.rebalance import should_rebalance


def test_first_evaluation_always_rebalances():
    assert should_rebalance(date(2024, 1, 2), None, "daily") is True
    assert should_rebalance(date(2024, 1, 2), None, "monthly") is True
    assert should_rebalance(date(2024, 1, 2), None, None) is True


def test_same_day_never_rebalances():
    d = date(2024, 1, 2)
    assert should_rebalance(d, d, "daily") is False
    assert should_rebalance(d, d, "monthly") is False


def test_daily():
    assert should_rebalance(date(2024, 1, 3), date(2024, 1, 2), "daily") is True


def test_weekly_fires_on_first_trading_day_of_each_iso_week():
    # Same ISO week -> no rebalance; a new ISO week -> rebalance, regardless of weekday.
    monday = date(2024, 1, 8)  # ISO week 2
    tuesday = date(2024, 1, 9)  # same ISO week 2
    next_monday = date(2024, 1, 15)  # ISO week 3
    assert should_rebalance(tuesday, monday, "weekly") is False
    assert should_rebalance(next_monday, monday, "weekly") is True
    assert should_rebalance(next_monday, tuesday, "weekly") is True


def test_weekly_fires_in_a_holiday_monday_week():
    # 2024-01-15 is MLK Day (market closed); the first trading day of ISO week 3 is Tue 16th.
    last = date(2024, 1, 12)  # Fri, ISO week 2
    holiday_week_first_session = date(2024, 1, 16)  # Tue, ISO week 3
    assert should_rebalance(holiday_week_first_session, last, "weekly") is True


def test_weekly_fires_once_per_iso_week_over_2024_including_holiday_mondays():
    # NYSE full-day closures in 2024 (four fall on a Monday: MLK, Presidents', Memorial, Labor).
    holidays = {
        date(2024, 1, 1),
        date(2024, 1, 15),
        date(2024, 2, 19),
        date(2024, 3, 29),
        date(2024, 5, 27),
        date(2024, 6, 19),
        date(2024, 7, 4),
        date(2024, 9, 2),
        date(2024, 11, 28),
        date(2024, 12, 25),
    }
    sessions: list[date] = []
    day = date(2024, 1, 1)
    while day.year == 2024:
        if day.weekday() < 5 and day not in holidays:
            sessions.append(day)
        day += timedelta(days=1)

    last: date | None = None
    fired: list[date] = []
    for session in sessions:
        if should_rebalance(session, last, "weekly"):
            fired.append(session)
            last = session

    weeks_with_sessions = {s.isocalendar()[:2] for s in sessions}
    first_session_of_week: dict[tuple[int, int], date] = {}
    for s in sessions:
        first_session_of_week.setdefault(s.isocalendar()[:2], s)

    # Exactly one rebalance per ISO week that has a trading day, on that week's first session.
    assert fired == [first_session_of_week[w] for w in sorted(weeks_with_sessions)]
    # The MLK week (Mon 2024-01-15 closed) still fires, on Tue 2024-01-16.
    assert date(2024, 1, 16) in fired


def test_monthly():
    assert should_rebalance(date(2024, 2, 1), date(2024, 1, 31), "monthly") is True
    assert should_rebalance(date(2024, 1, 31), date(2024, 1, 2), "monthly") is False


def test_quarterly():
    assert should_rebalance(date(2024, 4, 1), date(2024, 3, 31), "quarterly") is True
    assert should_rebalance(date(2024, 3, 31), date(2024, 1, 2), "quarterly") is False


def test_annually():
    assert should_rebalance(date(2025, 1, 1), date(2024, 12, 31), "annually") is True
    assert should_rebalance(date(2024, 12, 31), date(2024, 1, 2), "annually") is False


def test_none_frequency_defaults_to_daily():
    assert should_rebalance(date(2024, 1, 3), date(2024, 1, 2), None) is True
