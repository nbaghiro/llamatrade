"""Unit tests for pure interval/gap arithmetic (no DB, no IO)."""

from datetime import UTC, datetime, timedelta

from src.store.intervals import merge, subtract, total_seconds


def _t(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


class TestMerge:
    def test_empty(self) -> None:
        assert merge([]) == []

    def test_drops_empty_intervals(self) -> None:
        assert merge([(_t(2), _t(2)), (_t(3), _t(1))]) == []

    def test_single(self) -> None:
        assert merge([(_t(1), _t(3))]) == [(_t(1), _t(3))]

    def test_disjoint_sorted(self) -> None:
        assert merge([(_t(5), _t(6)), (_t(1), _t(2))]) == [(_t(1), _t(2)), (_t(5), _t(6))]

    def test_overlapping_coalesced(self) -> None:
        assert merge([(_t(1), _t(4)), (_t(3), _t(6))]) == [(_t(1), _t(6))]

    def test_touching_coalesced(self) -> None:
        # half-open: [1,3) and [3,5) are contiguous -> one interval
        assert merge([(_t(1), _t(3)), (_t(3), _t(5))]) == [(_t(1), _t(5))]

    def test_nested_interval_absorbed(self) -> None:
        assert merge([(_t(1), _t(10)), (_t(3), _t(4))]) == [(_t(1), _t(10))]


class TestSubtract:
    def test_no_coverage_returns_whole(self) -> None:
        assert subtract((_t(1), _t(5)), []) == [(_t(1), _t(5))]

    def test_full_coverage_returns_empty(self) -> None:
        assert subtract((_t(1), _t(5)), [(_t(1), _t(5))]) == []

    def test_over_coverage_returns_empty(self) -> None:
        assert subtract((_t(2), _t(4)), [(_t(1), _t(9))]) == []

    def test_interior_gap(self) -> None:
        # covered the edges, missing the middle
        gaps = subtract((_t(1), _t(10)), [(_t(1), _t(3)), (_t(7), _t(10))])
        assert gaps == [(_t(3), _t(7))]

    def test_leading_gap(self) -> None:
        assert subtract((_t(1), _t(10)), [(_t(4), _t(10))]) == [(_t(1), _t(4))]

    def test_trailing_gap(self) -> None:
        assert subtract((_t(1), _t(10)), [(_t(1), _t(6))]) == [(_t(6), _t(10))]

    def test_multiple_holes(self) -> None:
        gaps = subtract(
            (_t(1), _t(12)),
            [(_t(2), _t(3)), (_t(5), _t(6)), (_t(9), _t(10))],
        )
        assert gaps == [(_t(1), _t(2)), (_t(3), _t(5)), (_t(6), _t(9)), (_t(10), _t(12))]

    def test_coverage_outside_window_ignored(self) -> None:
        gaps = subtract((_t(5), _t(8)), [(_t(1), _t(3)), (_t(9), _t(12))])
        assert gaps == [(_t(5), _t(8))]

    def test_empty_window(self) -> None:
        assert subtract((_t(5), _t(5)), [(_t(1), _t(9))]) == []

    def test_unsorted_overlapping_coverage(self) -> None:
        gaps = subtract((_t(1), _t(10)), [(_t(7), _t(9)), (_t(2), _t(4)), (_t(3), _t(5))])
        assert gaps == [(_t(1), _t(2)), (_t(5), _t(7)), (_t(9), _t(10))]


class TestTotalSeconds:
    def test_merges_before_summing(self) -> None:
        one_day = timedelta(days=1).total_seconds()
        # overlapping intervals counted once
        assert total_seconds([(_t(1), _t(3)), (_t(2), _t(4))]) == 3 * one_day

    def test_empty(self) -> None:
        assert total_seconds([]) == 0
