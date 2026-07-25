"""Tests for the dataset materialization layer (spec, store, prepare + coalescing + gap-fill)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest

from src.dataset.prepare import _find_gaps, _merge_dedup, prepare_dataset
from src.dataset.spec import DatasetSpec
from src.dataset.store import LocalDatasetStore
from src.engine.bars import BarData


def _bar(ts: datetime, close: float = 100.0) -> BarData:
    return BarData(timestamp=ts, open=close, high=close, low=close, close=close, volume=1000)


def _series(days: int, start: datetime | None = None) -> list[BarData]:
    anchor = start or datetime(2024, 1, 1, tzinfo=UTC)
    return [_bar(anchor + timedelta(days=i)) for i in range(days)]


def _daterange(s: date, e: date) -> Iterator[date]:
    d = s
    while d <= e:
        yield d
        d += timedelta(days=1)


class TestDatasetSpec:
    def test_hash_is_order_case_and_dupe_invariant(self) -> None:
        a = DatasetSpec.create(["SPY", "QQQ", "spy"], "1D", date(2024, 1, 1), date(2025, 1, 1))
        b = DatasetSpec.create(["qqq", "SPY"], "1D", date(2024, 1, 1), date(2025, 1, 1))
        assert a.symbols == ("QQQ", "SPY")
        assert a.dataset_hash == b.dataset_hash

    def test_distinct_specs_have_distinct_hashes(self) -> None:
        base = DatasetSpec.create(["SPY"], "1D", date(2024, 1, 1), date(2025, 1, 1))
        assert (
            base.dataset_hash
            != DatasetSpec.create(["SPY"], "1D", date(2024, 1, 2), date(2025, 1, 1)).dataset_hash
        )
        assert (
            base.dataset_hash
            != DatasetSpec.create(["SPY"], "1H", date(2024, 1, 1), date(2025, 1, 1)).dataset_hash
        )

    def test_object_key_partitions_by_timeframe(self) -> None:
        spec = DatasetSpec.create(["SPY"], "1D", date(2024, 1, 1), date(2025, 1, 1))
        assert spec.object_key == f"1D/{spec.dataset_hash}.parquet"


class TestLocalDatasetStore:
    def test_round_trip_preserves_bars(self, tmp_path: object) -> None:
        store = LocalDatasetStore(str(tmp_path))
        spec = DatasetSpec.create(["SPY", "QQQ"], "1D", date(2024, 1, 1), date(2024, 1, 5))
        bars = {"SPY": _series(5), "QQQ": _series(5)}
        assert not store.exists(spec)
        store.write(spec, bars)
        assert store.exists(spec)
        back = store.read(spec)
        assert set(back) == {"SPY", "QQQ"}
        assert back["SPY"] == bars["SPY"]
        assert isinstance(back["SPY"][0]["volume"], int)


class TestGapDetection:
    def test_find_gaps_flags_interior_hole(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        series = [_bar(start), _bar(start + timedelta(days=1)), _bar(start + timedelta(days=15))]
        gaps = _find_gaps(series, threshold_days=6)
        assert gaps == [(date(2024, 1, 3), date(2024, 1, 15))]

    def test_find_gaps_ignores_normal_weekend(self) -> None:
        start = datetime(2024, 1, 5, tzinfo=UTC)  # Fri
        series = [_bar(start), _bar(start + timedelta(days=3))]  # Fri -> Mon
        assert _find_gaps(series, threshold_days=6) == []

    def test_merge_dedup_keeps_existing_and_sorts(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        existing = [_bar(start, 100.0), _bar(start + timedelta(days=2), 102.0)]
        patch = [_bar(start + timedelta(days=1), 101.0), _bar(start + timedelta(days=2), 999.0)]
        merged = _merge_dedup(existing, patch)
        assert [b["timestamp"] for b in merged] == [
            start,
            start + timedelta(days=1),
            start + timedelta(days=2),
        ]
        assert merged[2]["close"] == 102.0  # existing wins on conflict


class _FakeStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, list[BarData]]] = {}

    def exists(self, spec: DatasetSpec) -> bool:
        return spec.dataset_hash in self._data

    def read(self, spec: DatasetSpec) -> dict[str, list[BarData]]:
        return self._data[spec.dataset_hash]

    def write(self, spec: DatasetSpec, bars: dict[str, list[BarData]]) -> None:
        self._data[spec.dataset_hash] = bars


class _FakeRedis:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def set(
        self, name: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and name in self._keys:
            return None
        self._keys[name] = value
        return True

    async def delete(self, *names: str) -> int:
        removed = 0
        for name in names:
            if self._keys.pop(name, None) is not None:
                removed += 1
        return removed


_SPEC = DatasetSpec.create(["SPY"], "1D", date(2024, 1, 1), date(2024, 1, 5))


class TestPrepareDataset:
    @pytest.mark.asyncio
    async def test_warm_hit_skips_fetch(self) -> None:
        store, redis = _FakeStore(), _FakeRedis()
        store.write(_SPEC, {"SPY": _series(5)})
        calls = 0

        async def fetch(symbols: list[str], tf: str, s: date, e: date) -> dict[str, list[BarData]]:
            nonlocal calls
            calls += 1
            return {}

        out = await prepare_dataset(_SPEC, fetch, store, redis)
        assert calls == 0
        assert out["SPY"]

    @pytest.mark.asyncio
    async def test_materialize_fetches_and_caches(self) -> None:
        store, redis = _FakeStore(), _FakeRedis()
        calls = 0

        async def fetch(symbols: list[str], tf: str, s: date, e: date) -> dict[str, list[BarData]]:
            nonlocal calls
            calls += 1
            return {"SPY": _series(5)}

        out = await prepare_dataset(_SPEC, fetch, store, redis)
        assert calls == 1
        assert store.exists(_SPEC)
        assert out["SPY"]

    @pytest.mark.asyncio
    async def test_coalesced_waiter_reads_snapshot_without_fetching(self) -> None:
        import asyncio

        store, redis = _FakeStore(), _FakeRedis()
        # Simulate another worker already holding the lock.
        await redis.set(f"backtest:dataset:lock:{_SPEC.dataset_hash}", "1", nx=True, ex=300)

        async def producer() -> None:
            await asyncio.sleep(0.6)
            store.write(_SPEC, {"SPY": _series(5)})

        fetch_calls = 0

        async def fetch(symbols: list[str], tf: str, s: date, e: date) -> dict[str, list[BarData]]:
            nonlocal fetch_calls
            fetch_calls += 1
            return {}

        task = asyncio.create_task(producer())
        out = await prepare_dataset(_SPEC, fetch, store, redis, wait_timeout=5.0)
        await task
        assert fetch_calls == 0
        assert out["SPY"]

    @pytest.mark.asyncio
    async def test_waiter_falls_back_when_producer_never_publishes(self) -> None:
        store, redis = _FakeStore(), _FakeRedis()
        await redis.set(f"backtest:dataset:lock:{_SPEC.dataset_hash}", "1", nx=True, ex=300)
        calls = 0

        async def fetch(symbols: list[str], tf: str, s: date, e: date) -> dict[str, list[BarData]]:
            nonlocal calls
            calls += 1
            return {"SPY": _series(5)}

        out = await prepare_dataset(_SPEC, fetch, store, redis, wait_timeout=1.0)
        assert calls == 1  # fell back to materializing itself
        assert out["SPY"]

    @pytest.mark.asyncio
    async def test_interior_gap_is_backfilled(self) -> None:
        store, redis = _FakeStore(), _FakeRedis()
        spec = DatasetSpec.create(["SPY"], "1D", date(2024, 1, 1), date(2024, 1, 31))
        anchor = datetime(2024, 1, 1, tzinfo=UTC)
        holey = {
            "SPY": [_bar(anchor + timedelta(days=i)) for i in (0, 1, 2)]
            + [_bar(anchor + timedelta(days=i)) for i in (14, 15, 16)]
        }
        calls: list[tuple[date, date]] = []

        async def fetch(symbols: list[str], tf: str, s: date, e: date) -> dict[str, list[BarData]]:
            calls.append((s, e))
            if len(calls) == 1:
                return holey
            filled = [
                _bar(datetime.combine(d, datetime.min.time(), tzinfo=UTC)) for d in _daterange(s, e)
            ]
            return {"SPY": filled}

        out = await prepare_dataset(spec, fetch, store, redis)
        assert len(calls) >= 2  # a targeted interior re-fetch happened
        filled_dates = {b["timestamp"].date() for b in out["SPY"]}
        assert date(2024, 1, 8) in filled_dates  # a previously-missing interior day is present
