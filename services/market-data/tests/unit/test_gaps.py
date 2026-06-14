"""Unit tests for interior-gap detection (pure, no DB)."""

from datetime import UTC, datetime, timedelta

from src.ingest.gaps import find_interior_gaps

STEP = timedelta(minutes=1)
MAX_GAP = timedelta(hours=4)


def _t(minute: int) -> datetime:
    return datetime(2026, 1, 5, 14, 0, tzinfo=UTC) + timedelta(minutes=minute)


def test_contiguous_no_gaps() -> None:
    times = [_t(0), _t(1), _t(2), _t(3)]
    assert find_interior_gaps(times, STEP, MAX_GAP) == []


def test_single_interior_hole() -> None:
    # missing minutes 2,3 -> hole [_t(2), _t(4))
    times = [_t(0), _t(1), _t(4), _t(5)]
    assert find_interior_gaps(times, STEP, MAX_GAP) == [(_t(2), _t(4))]


def test_multiple_holes() -> None:
    times = [_t(0), _t(3), _t(4), _t(8)]
    assert find_interior_gaps(times, STEP, MAX_GAP) == [(_t(1), _t(3)), (_t(5), _t(8))]


def test_session_boundary_excluded() -> None:
    # An overnight-sized gap (> max_gap) is a session boundary, not a hole.
    times = [_t(0), _t(0) + timedelta(hours=18)]
    assert find_interior_gaps(times, STEP, MAX_GAP) == []


def test_empty_and_single() -> None:
    assert find_interior_gaps([], STEP, MAX_GAP) == []
    assert find_interior_gaps([_t(0)], STEP, MAX_GAP) == []
