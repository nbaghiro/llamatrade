"""Dataset materialization — the warm-ahead / shared-snapshot layer for backtests.

Before a sim runs, `prepare_dataset` guarantees complete, gap-free bar coverage (via the
market-data service) and writes a content-addressed, immutable snapshot. Concurrent runs over
overlapping assets coalesce onto one snapshot + one fetch, and the sim reads pure warm data —
never Alpaca directly.
"""

from src.dataset.prepare import Fetcher, RedisLike, prepare_dataset
from src.dataset.spec import DatasetSpec
from src.dataset.store import (
    DatasetStore,
    InMemoryDatasetStore,
    LocalDatasetStore,
    get_dataset_store,
)

__all__ = [
    "DatasetSpec",
    "DatasetStore",
    "Fetcher",
    "InMemoryDatasetStore",
    "LocalDatasetStore",
    "RedisLike",
    "get_dataset_store",
    "prepare_dataset",
]
