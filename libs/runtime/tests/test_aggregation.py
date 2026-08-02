"""Golden tests for the forming-bar aggregator (period keying + OHLCV folding)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from llamatrade_runtime import Bar, FormingBarAggregator, daily_period_start, market_timezone

ET = ZoneInfo("America/New_York")


def _bar(ts: datetime, o: float, h: float, low: float, c: float, volume: int = 100) -> Bar:
    return Bar(timestamp=ts, open=o, high=h, low=low, close=c, volume=volume)


def _minute(day: datetime, index: int) -> datetime:
    """The ``index``-th minute of a regular session that opens at 09:30 ET."""
    return day.replace(hour=9, minute=30, tzinfo=ET) + timedelta(minutes=index)


class TestDailyPeriodStart:
    def test_returns_exchange_local_midnight(self) -> None:
        # 14:30Z on a summer day is 10:30 ET.
        ts = datetime(2025, 7, 15, 14, 30, tzinfo=UTC)
        assert daily_period_start(ts) == datetime(2025, 7, 15, tzinfo=ET)

    def test_summer_and_winter_days_both_key_to_local_midnight(self) -> None:
        """A fixed UTC offset would shift one of these by an hour across the DST change."""
        summer = daily_period_start(datetime(2025, 7, 15, 13, 30, tzinfo=UTC))
        winter = daily_period_start(datetime(2025, 1, 15, 14, 30, tzinfo=UTC))
        assert summer.utcoffset() == timedelta(hours=-4)
        assert winter.utcoffset() == timedelta(hours=-5)
        assert (summer.hour, summer.minute) == (0, 0)
        assert (winter.hour, winter.minute) == (0, 0)

    def test_after_hours_bar_past_utc_midnight_stays_in_the_same_session(self) -> None:
        """19:30 ET on Jan 2 is 00:30Z on Jan 3 — the UTC date would split the session."""
        ts = datetime(2025, 1, 3, 0, 30, tzinfo=UTC)
        assert daily_period_start(ts) == datetime(2025, 1, 2, tzinfo=ET)

    def test_spring_forward_day_keys_to_that_days_midnight(self) -> None:
        # 2025-03-09 is the spring-forward Sunday; the following session is 2025-03-10.
        ts = datetime(2025, 3, 10, 13, 30, tzinfo=UTC)
        period = daily_period_start(ts)
        assert period == datetime(2025, 3, 10, tzinfo=ET)
        assert period.utcoffset() == timedelta(hours=-4)  # already on EDT

    def test_naive_timestamp_is_read_as_utc(self) -> None:
        naive = datetime(2025, 7, 15, 14, 30)
        assert daily_period_start(naive) == daily_period_start(naive.replace(tzinfo=UTC))

    def test_explicit_timezone_overrides_the_market_default(self) -> None:
        ts = datetime(2025, 7, 15, 23, 30, tzinfo=UTC)
        assert daily_period_start(ts, UTC) == datetime(2025, 7, 15, tzinfo=UTC)
        assert daily_period_start(ts, ET) == datetime(2025, 7, 15, tzinfo=ET)

    def test_market_timezone_is_cached(self) -> None:
        assert market_timezone() is market_timezone()


class TestFormingBarAggregator:
    def test_first_bar_of_a_period_stamps_the_period_start(self) -> None:
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        forming = agg.update("SPY", _bar(_minute(day, 0), 100.0, 101.0, 99.0, 100.5))
        assert forming.timestamp == datetime(2025, 7, 15, tzinfo=ET)
        assert (forming.open, forming.high, forming.low, forming.close) == (
            100.0,
            101.0,
            99.0,
            100.5,
        )
        assert forming.volume == 100

    def test_folds_open_extrema_close_and_volume(self) -> None:
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        agg.update("SPY", _bar(_minute(day, 0), 100.0, 101.0, 99.5, 100.5, volume=10))
        agg.update("SPY", _bar(_minute(day, 1), 100.5, 103.0, 100.0, 102.0, volume=20))
        forming = agg.update("SPY", _bar(_minute(day, 2), 102.0, 102.5, 98.0, 98.5, volume=30))

        assert forming.open == 100.0  # first bar's open, never revised
        assert forming.high == 103.0  # running maximum
        assert forming.low == 98.0  # running minimum
        assert forming.close == 98.5  # latest bar's close
        assert forming.volume == 60  # summed

    def test_gaps_in_the_minute_stream_do_not_break_the_fold(self) -> None:
        """Missing minutes are simply absent from the fold; nothing is interpolated."""
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        agg.update("SPY", _bar(_minute(day, 0), 100.0, 100.0, 100.0, 100.0, volume=10))
        forming = agg.update("SPY", _bar(_minute(day, 240), 105.0, 106.0, 104.0, 105.5, volume=10))
        assert (forming.open, forming.high, forming.low, forming.close) == (
            100.0,
            106.0,
            100.0,
            105.5,
        )
        assert forming.volume == 20

    def test_new_period_starts_a_fresh_bar(self) -> None:
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        agg.update("SPY", _bar(_minute(day, 0), 100.0, 110.0, 90.0, 105.0, volume=10))
        next_day = datetime(2025, 7, 16)
        forming = agg.update("SPY", _bar(_minute(next_day, 0), 106.0, 107.0, 106.0, 106.5))

        assert forming.timestamp == datetime(2025, 7, 16, tzinfo=ET)
        assert (forming.open, forming.high, forming.low, forming.close) == (
            106.0,
            107.0,
            106.0,
            106.5,
        )
        assert forming.volume == 100  # not carried over from the previous period

    def test_after_hours_bar_extends_the_same_session(self) -> None:
        agg = FormingBarAggregator()
        agg.update(
            "SPY", _bar(datetime(2025, 1, 2, 14, 30, tzinfo=UTC), 100.0, 100.0, 100.0, 100.0)
        )
        forming = agg.update(
            "SPY", _bar(datetime(2025, 1, 3, 0, 30, tzinfo=UTC), 101.0, 102.0, 101.0, 101.5)
        )
        assert forming.timestamp == datetime(2025, 1, 2, tzinfo=ET)
        assert forming.open == 100.0 and forming.close == 101.5

    def test_symbols_are_independent(self) -> None:
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        agg.update("SPY", _bar(_minute(day, 0), 100.0, 100.0, 100.0, 100.0))
        agg.update("TLT", _bar(_minute(day, 0), 50.0, 50.0, 50.0, 50.0))
        agg.update("SPY", _bar(_minute(day, 1), 100.0, 120.0, 100.0, 118.0))

        spy = agg.current("SPY")
        tlt = agg.current("TLT")
        assert spy is not None and spy.high == 120.0
        assert tlt is not None and tlt.high == 50.0

    def test_current_is_none_before_any_bar(self) -> None:
        assert FormingBarAggregator().current("SPY") is None

    def test_reset_drops_forming_state(self) -> None:
        agg = FormingBarAggregator()
        day = datetime(2025, 7, 15)
        agg.update("SPY", _bar(_minute(day, 0), 100.0, 100.0, 100.0, 100.0, volume=10))
        agg.reset()
        assert agg.current("SPY") is None
        forming = agg.update("SPY", _bar(_minute(day, 1), 101.0, 101.0, 101.0, 101.0, volume=10))
        assert forming.open == 101.0 and forming.volume == 10


class TestSeeding:
    def test_seed_for_the_period_in_progress_is_extended(self) -> None:
        """A mid-day start adopts the preloaded partial bar instead of losing the morning."""
        day_start = datetime(2025, 7, 15, tzinfo=ET)
        seed = {"SPY": _bar(day_start, 100.0, 104.0, 99.0, 103.0, volume=5_000)}
        agg = FormingBarAggregator(seed=seed)

        forming = agg.update(
            "SPY", _bar(_minute(datetime(2025, 7, 15), 200), 103.0, 105.0, 102.0, 104.5, volume=100)
        )
        assert forming.open == 100.0  # from the preloaded morning
        assert forming.high == 105.0
        assert forming.low == 99.0
        assert forming.close == 104.5
        assert forming.volume == 5_100

    def test_seed_keeps_its_own_timestamp_so_history_stays_addressable(self) -> None:
        """Alpaca stamps daily bars at exchange midnight expressed in UTC — the same instant."""
        seed_ts = datetime(2025, 7, 15, 4, 0, tzinfo=UTC)  # 00:00 ET
        agg = FormingBarAggregator(seed={"SPY": _bar(seed_ts, 100.0, 100.0, 100.0, 100.0)})
        forming = agg.update(
            "SPY", _bar(_minute(datetime(2025, 7, 15), 5), 101.0, 101.0, 101.0, 101.0)
        )
        assert forming.timestamp == seed_ts
        assert forming.timestamp == datetime(2025, 7, 15, tzinfo=ET)  # equal instants

    def test_stale_seed_from_an_earlier_period_is_discarded(self) -> None:
        agg = FormingBarAggregator(
            seed={"SPY": _bar(datetime(2025, 7, 14, tzinfo=ET), 90.0, 95.0, 89.0, 94.0, volume=999)}
        )
        forming = agg.update(
            "SPY", _bar(_minute(datetime(2025, 7, 15), 0), 100.0, 100.0, 100.0, 100.0, volume=10)
        )
        assert forming.timestamp == datetime(2025, 7, 15, tzinfo=ET)
        assert forming.open == 100.0
        assert forming.volume == 10

    def test_custom_period_start_is_honoured(self) -> None:
        def hourly(ts: datetime) -> datetime:
            return ts.replace(minute=0, second=0, microsecond=0)

        agg = FormingBarAggregator(period_start=hourly)
        base = datetime(2025, 7, 15, 14, 0, tzinfo=UTC)
        agg.update("SPY", _bar(base, 100.0, 100.0, 100.0, 100.0))
        same_hour = agg.update(
            "SPY", _bar(base + timedelta(minutes=30), 100.0, 105.0, 100.0, 104.0)
        )
        assert same_hour.high == 105.0
        next_hour = agg.update("SPY", _bar(base + timedelta(hours=1), 104.0, 104.0, 104.0, 104.0))
        assert next_hour.timestamp == base + timedelta(hours=1)
        assert next_hour.high == 104.0
