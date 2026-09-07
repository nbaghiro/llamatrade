"""Unit tests for interior-gap detection and gap-repair failure isolation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from tests.fakes import FakeMarketDataClient
from tests.test_metrics import _exposition, _sample

from src.ingest.backfill import BackfillController
from src.ingest.gaps import GapRepairer, find_interior_gaps
from src.store.models import BarRow
from src.store.repository import BarStore

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


class MemoryStore:
    """Whole-window-missing store: every repair fetches one full-window gap."""

    def __init__(self, fail_symbols: set[str] | None = None) -> None:
        self.upserted: dict[str, int] = {}
        self.fail_symbols = fail_symbols or set()

    async def select_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[BarRow]:
        if symbol in self.fail_symbols:
            raise RuntimeError(f"injected select failure for {symbol}")
        return []

    async def missing_ranges(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        return [(start, end)]

    async def upsert_bars(self, rows: list[BarRow], timeframe: str) -> int:
        for row in rows:
            self.upserted[row.symbol] = self.upserted.get(row.symbol, 0) + 1
        return len(rows)


_FAILURES_TOTAL = "llamatrade_marketdata_ingest_gap_repair_failures_total"


def _repairer(store: MemoryStore, alpaca: FakeMarketDataClient) -> GapRepairer:
    controller = BackfillController(
        cast(BarStore, store), alpaca, timeframes=("1Min",), lookback_for={"1Min": 0.01}
    )
    return GapRepairer(
        controller,
        step=STEP,
        max_gap=MAX_GAP,
        recent_lookback_days=0.01,  # ~14 min window
    )


class TestRepairFailureIsolation:
    async def test_one_failing_symbol_does_not_abort_the_pass(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = MemoryStore()
        alpaca = FakeMarketDataClient(fail_symbols={"BAD"})
        repairer = _repairer(store, alpaca)
        before = _sample(_exposition(), _FAILURES_TOTAL) or 0.0

        with caplog.at_level(logging.ERROR, logger="src.ingest.gaps"):
            written = await repairer.repair(["AAPL", "BAD", "MSFT"], "1Min", _t(20))

        assert written > 0
        assert set(store.upserted) == {"AAPL", "MSFT"}  # BAD skipped, others repaired
        assert _sample(_exposition(), _FAILURES_TOTAL) == before + 1.0
        assert "Gap repair failed for BAD 1Min" in caplog.text

    async def test_store_read_failure_is_isolated_too(self) -> None:
        store = MemoryStore(fail_symbols={"AAPL"})
        repairer = _repairer(store, FakeMarketDataClient())
        before = _sample(_exposition(), _FAILURES_TOTAL) or 0.0

        written = await repairer.repair(["AAPL", "MSFT"], "1Min", _t(20))

        assert written > 0
        assert set(store.upserted) == {"MSFT"}
        assert _sample(_exposition(), _FAILURES_TOTAL) == before + 1.0

    async def test_clean_pass_counts_no_failures(self) -> None:
        store = MemoryStore()
        repairer = _repairer(store, FakeMarketDataClient())
        before = _sample(_exposition(), _FAILURES_TOTAL) or 0.0

        written = await repairer.repair(["AAPL", "MSFT"], "1Min", _t(20))

        assert written > 0
        assert set(store.upserted) == {"AAPL", "MSFT"}
        assert (_sample(_exposition(), _FAILURES_TOTAL) or 0.0) == before
