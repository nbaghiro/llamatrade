"""Dataset janitor: stale snapshots evict by age; fresh files survive."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from src.dataset.spec import DatasetSpec
from src.dataset.store import LocalDatasetStore
from src.engine.bars import BarData


def _spec(symbol: str) -> DatasetSpec:
    return DatasetSpec.create(
        symbols=[symbol],
        fetch_start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 6, 1, tzinfo=UTC),
        timeframe="1D",
    )


def _bar() -> BarData:
    return BarData(
        timestamp=datetime(2026, 1, 2, tzinfo=UTC),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=1,
    )


def test_evict_stale_removes_only_old_snapshots(tmp_path: Path) -> None:
    store = LocalDatasetStore(str(tmp_path))
    old_spec, new_spec = _spec("AAA"), _spec("BBB")
    store.write(old_spec, {"AAA": [_bar()]})
    store.write(new_spec, {"BBB": [_bar()]})

    old_path = store._path(old_spec)
    stale_time = time.time() - 8 * 24 * 3600
    os.utime(old_path, (stale_time, stale_time))

    removed = store.evict_stale(max_age_seconds=7 * 24 * 3600)

    assert removed == 1
    assert not store.exists(old_spec)
    assert store.exists(new_spec)


def test_evict_on_missing_root_is_noop(tmp_path: Path) -> None:
    store = LocalDatasetStore(str(tmp_path / "never-created"))
    assert store.evict_stale(max_age_seconds=1) == 0


def test_evict_cleans_stale_tmp_files_without_counting_them(tmp_path: Path) -> None:
    """Orphaned .parquet.tmp files (crashed writes) are swept but not counted as snapshots."""
    store = LocalDatasetStore(str(tmp_path))
    store.write(_spec("AAA"), {"AAA": [_bar()]})

    stale_tmp = tmp_path / "1D" / "orphan.parquet.tmp"
    stale_tmp.write_bytes(b"partial write")
    fresh_tmp = tmp_path / "1D" / "inflight.parquet.tmp"
    fresh_tmp.write_bytes(b"partial write")

    stale_time = time.time() - 8 * 24 * 3600
    os.utime(stale_tmp, (stale_time, stale_time))

    removed = store.evict_stale(max_age_seconds=7 * 24 * 3600)

    assert removed == 0
    assert not stale_tmp.exists()
    assert fresh_tmp.exists()
    assert store.exists(_spec("AAA"))
