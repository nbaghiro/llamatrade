"""Tests for llamatrade_proto.timestamps conversion helpers."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from llamatrade_proto.timestamps import (
    date_from_proto_timestamp,
    date_to_proto_timestamp,
    from_proto_timestamp,
    to_proto_timestamp,
)


class TestToProtoTimestamp:
    def test_encodes_utc_datetime(self) -> None:
        dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        ts = to_proto_timestamp(dt)
        assert ts.seconds == int(dt.timestamp())
        assert ts.nanos == 0

    def test_preserves_microseconds_as_nanos(self) -> None:
        dt = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=UTC)
        ts = to_proto_timestamp(dt)
        assert ts.nanos == 123456 * 1000

    def test_non_utc_aware_datetime_encodes_same_instant(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        dt_east = datetime(2024, 1, 15, 7, 30, 45, tzinfo=eastern)
        dt_utc = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        assert to_proto_timestamp(dt_east).seconds == to_proto_timestamp(dt_utc).seconds

    def test_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            to_proto_timestamp(datetime(2024, 1, 15, 12, 30, 45))


class TestFromProtoTimestamp:
    def test_returns_utc_aware_datetime(self) -> None:
        dt = datetime(2024, 6, 1, 9, 0, 0, tzinfo=UTC)
        decoded = from_proto_timestamp(to_proto_timestamp(dt))
        assert decoded.tzinfo is UTC
        assert decoded == dt

    def test_round_trip_with_microseconds(self) -> None:
        dt = datetime(2024, 6, 1, 9, 0, 0, 654321, tzinfo=UTC)
        assert from_proto_timestamp(to_proto_timestamp(dt)) == dt

    def test_round_trip_from_non_utc_zone_normalizes_to_utc(self) -> None:
        eastern = timezone(timedelta(hours=-5))
        dt_east = datetime(2024, 1, 15, 7, 30, 45, tzinfo=eastern)
        decoded = from_proto_timestamp(to_proto_timestamp(dt_east))
        assert decoded == dt_east
        assert decoded.tzinfo is UTC


class TestDateVariants:
    def test_date_encodes_utc_midnight(self) -> None:
        ts = date_to_proto_timestamp(date(2024, 3, 10))
        decoded = from_proto_timestamp(ts)
        assert decoded == datetime(2024, 3, 10, 0, 0, 0, tzinfo=UTC)

    def test_date_round_trip(self) -> None:
        d = date(2023, 12, 31)
        assert date_from_proto_timestamp(date_to_proto_timestamp(d)) == d

    def test_date_from_timestamp_uses_utc_calendar_day(self) -> None:
        # 23:30 UTC on 2024-03-10 is still 2024-03-10 in UTC.
        ts = to_proto_timestamp(datetime(2024, 3, 10, 23, 30, tzinfo=UTC))
        assert date_from_proto_timestamp(ts) == date(2024, 3, 10)
