"""Pure interval arithmetic over half-open time ranges ``[start, end)``.

Kept free of any DB/IO so the gap math is unit-testable in isolation. The
repository derives the *covered* intervals from stored bars and uses
:func:`subtract` to decide which sub-ranges still need fetching from upstream.

Half-open semantics: an interval ``(s, e)`` includes ``s`` and excludes ``e``;
``s == e`` is empty. Two intervals that merely touch (``a.end == b.start``) are
treated as contiguous and coalesced — there is no gap between them.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

# Half-open [start, end). start < end for any non-empty interval.
Interval = tuple[datetime, datetime]


def merge(intervals: Sequence[Interval]) -> list[Interval]:
    """Coalesce overlapping/adjacent intervals into a sorted, disjoint list.

    Empty intervals (``start >= end``) are dropped. Touching intervals are
    merged (half-open semantics), so the result has a real gap between any two
    consecutive entries.
    """
    items = sorted((s, e) for s, e in intervals if s < e)
    if not items:
        return []

    merged: list[Interval] = [items[0]]
    for start, end in items[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:  # overlap or touch -> extend
            if end > last_end:
                merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged


def subtract(whole: Interval, covered: Sequence[Interval]) -> list[Interval]:
    """Return the parts of ``whole`` not covered by ``covered``.

    The result is the ordered list of gaps within ``whole``; an empty list
    means ``whole`` is fully covered. ``covered`` need not be sorted or
    disjoint — it is normalized internally.
    """
    whole_start, whole_end = whole
    if whole_start >= whole_end:
        return []

    gaps: list[Interval] = []
    cursor = whole_start
    for cov_start, cov_end in merge(covered):
        if cov_end <= cursor:
            continue  # entirely before the cursor
        if cov_start >= whole_end:
            break  # past the window; nothing more can overlap
        if cov_start > cursor:
            gaps.append((cursor, min(cov_start, whole_end)))
        cursor = max(cursor, cov_end)
        if cursor >= whole_end:
            break
    if cursor < whole_end:
        gaps.append((cursor, whole_end))
    return gaps


def total_seconds(intervals: Sequence[Interval]) -> float:
    """Total covered duration in seconds (after merging). Useful for metrics."""
    return sum((e - s).total_seconds() for s, e in merge(intervals))
