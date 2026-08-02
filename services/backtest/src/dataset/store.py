"""Dataset snapshot store — persists a materialized bar dataset as columnar Parquet.

A dataset (``dict[str, list[BarData]]``) is stored as one Parquet table keyed by the
``DatasetSpec`` hash. Writes are atomic (temp file + rename) so a concurrent reader — or a
coalescing waiter — never observes a partial snapshot. `LocalDatasetStore` covers dev and
single-node; a bucket-backed store sits behind the same `DatasetStore` seam.
"""

import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq

from src.dataset.spec import DatasetSpec
from src.engine.bars import BarData

_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
    ]
)

_NUMERIC_FIELDS = ("open", "high", "low", "close")


def _bars_to_table(bars: dict[str, list[BarData]]) -> pa.Table:
    """Flatten multi-symbol bars into one columnar table, symbol- then time-ordered.

    ``BarData`` is a TypedDict, so its non-optional fields are a static claim, not a
    runtime guarantee — market-data serves nullable columns. A missing price is
    corrupt input and fails loudly; a missing volume is sparsity and reads as zero.
    """
    cols: dict[str, list[object]] = {name: [] for name in _SCHEMA.names}
    for symbol in sorted(bars):
        for b in bars[symbol]:
            raw = cast(Mapping[str, object], b)
            cols["symbol"].append(symbol)
            cols["timestamp"].append(b["timestamp"])
            for field in _NUMERIC_FIELDS:
                price = raw.get(field)
                if price is None:
                    raise ValueError(
                        f"{symbol} bar at {b['timestamp']} has no {field}; "
                        "refusing to build a backtest dataset from incomplete prices"
                    )
                cols[field].append(float(cast(float, price)))
            volume = raw.get("volume")
            cols["volume"].append(int(cast(float, volume)) if volume is not None else 0)
    return pa.table(cols, schema=_SCHEMA)


def _table_to_bars(table: pa.Table) -> dict[str, list[BarData]]:
    """Regroup a stored table back into per-symbol bar lists (order preserved)."""
    data = table.to_pydict()
    result: dict[str, list[BarData]] = {}
    for i in range(table.num_rows):
        result.setdefault(data["symbol"][i], []).append(
            BarData(
                timestamp=data["timestamp"][i],
                open=data["open"][i],
                high=data["high"][i],
                low=data["low"][i],
                close=data["close"][i],
                volume=data["volume"][i],
            )
        )
    return result


class DatasetStore(Protocol):
    """Persists and retrieves materialized bar datasets by their content hash."""

    def exists(self, spec: DatasetSpec) -> bool: ...

    def read(self, spec: DatasetSpec) -> dict[str, list[BarData]]: ...

    def write(self, spec: DatasetSpec, bars: dict[str, list[BarData]]) -> None: ...


class LocalDatasetStore:
    """On-disk Parquet snapshots under a root directory (dev / single-node)."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, spec: DatasetSpec) -> Path:
        return self._root / spec.object_key

    def exists(self, spec: DatasetSpec) -> bool:
        return self._path(spec).exists()

    def read(self, spec: DatasetSpec) -> dict[str, list[BarData]]:
        return _table_to_bars(pq.read_table(self._path(spec)))

    def write(self, spec: DatasetSpec, bars: dict[str, list[BarData]]) -> None:
        path = self._path(spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic publish: write a temp file in the same dir, then rename over the target so a
        # concurrent reader/coalescing waiter only ever sees a complete snapshot.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
        os.close(fd)
        try:
            pq.write_table(_bars_to_table(bars), tmp, compression="zstd")
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def evict_stale(self, max_age_seconds: float) -> int:
        """Delete snapshots untouched for ``max_age_seconds``; returns the count removed.

        A raced reader falls back to a rebuild on miss, so eviction can never
        produce a wrong result, only a refetch.
        """
        cutoff = time.time() - max_age_seconds
        removed = 0
        if not self._root.exists():
            return removed
        for path in self._root.rglob("*.parquet"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        for tmp in self._root.rglob("*.parquet.tmp"):
            try:
                if tmp.stat().st_mtime < cutoff:
                    tmp.unlink(missing_ok=True)
            except OSError:
                continue
        return removed


class InMemoryDatasetStore:
    """Ephemeral in-process snapshots — the default when no persistent location is configured.

    Gives warm-hit reuse within one process (and test isolation, since each instance is fresh),
    but no cross-worker sharing — set ``BACKTEST_DATASET_DIR`` for that.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, list[BarData]]] = {}

    def exists(self, spec: DatasetSpec) -> bool:
        return spec.dataset_hash in self._data

    def read(self, spec: DatasetSpec) -> dict[str, list[BarData]]:
        return self._data[spec.dataset_hash]

    def write(self, spec: DatasetSpec, bars: dict[str, list[BarData]]) -> None:
        self._data[spec.dataset_hash] = bars


def get_dataset_store() -> DatasetStore:
    """Select the snapshot store from the environment.

    ``BACKTEST_DATASET_DIR`` → on-disk Parquet (persistent, cross-worker when shared); unset → an
    ephemeral in-memory store (dev / tests).
    """
    root = os.getenv("BACKTEST_DATASET_DIR")
    if root:
        return LocalDatasetStore(root)
    return InMemoryDatasetStore()
