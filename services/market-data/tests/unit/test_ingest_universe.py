"""Unit tests for the derived ingest universe (no DB, no stream)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from llamatrade_telemetry import get_metrics

from src.ingest import universe as universe_module
from src.ingest.universe import IngestUniverse, UniverseChange, normalize_symbols


class FakeStream:
    """Records the bar subscribe/unsubscribe calls the reconciler makes."""

    def __init__(self, *, subscribe_result: bool = True, raises: bool = False) -> None:
        self.subscribed: list[list[str]] = []
        self.unsubscribed: list[list[str]] = []
        self._subscribe_result = subscribe_result
        self._raises = raises

    async def subscribe(self, *, bars: list[str]) -> bool:
        if self._raises:
            raise ConnectionError("socket closed")
        self.subscribed.append(list(bars))
        return self._subscribe_result

    async def unsubscribe(self, *, bars: list[str]) -> bool:
        self.unsubscribed.append(list(bars))
        return True


class FakeSource:
    """Stands in for the live-session query; ``symbols`` is rewritten per test."""

    def __init__(self, *symbols: str) -> None:
        self.symbols = frozenset(symbols)
        self.fails = False

    async def __call__(self) -> frozenset[str]:
        if self.fails:
            raise RuntimeError("database unreachable")
        return self.symbols


def _counter(reason: str) -> float:
    """Current value of the refresh-failure counter for ``reason`` (0 if unset)."""
    name = "llamatrade_marketdata_ingest_universe_refresh_failures_total"
    for line in get_metrics().decode().splitlines():
        if line.startswith(name) and f'reason="{reason}"' in line:
            return float(line.rpartition(" ")[2])
    return 0.0


def _gauge(kind: str) -> float | None:
    """Current value of the universe-size gauge for ``kind``, or None if unset."""
    name = "llamatrade_marketdata_ingest_universe_symbols"
    for line in get_metrics().decode().splitlines():
        if line.startswith(name) and f'kind="{kind}"' in line:
            return float(line.rpartition(" ")[2])
    return None


class TestNormalizeSymbols:
    def test_trims_uppercases_and_dedupes_keeping_order(self) -> None:
        assert normalize_symbols([" aapl", "MSFT", "aapl", "", "  ", "tsla"]) == (
            "AAPL",
            "MSFT",
            "TSLA",
        )


class TestBaseline:
    def test_starts_at_the_normalized_baseline(self) -> None:
        universe = IngestUniverse([" spy ", "qqq", "SPY"], source=FakeSource())

        assert universe.baseline == ("SPY", "QQQ")
        assert universe.symbols == ("SPY", "QQQ")


class TestRefresh:
    async def test_adds_live_symbols_after_the_baseline(self) -> None:
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA", "NVDA"))

        assert await universe.refresh() == UniverseChange(added=("NVDA", "TSLA"))
        assert universe.symbols == ("SPY", "NVDA", "TSLA")

    async def test_subscribes_only_the_added_symbols(self) -> None:
        stream = FakeStream()
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA"))
        universe.attach(stream)

        await universe.refresh()

        assert stream.subscribed == [["TSLA"]]
        assert stream.unsubscribed == []

    async def test_unchanged_universe_touches_the_stream_once(self) -> None:
        stream = FakeStream()
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA"))
        universe.attach(stream)

        await universe.refresh()
        assert await universe.refresh() == UniverseChange()

        assert stream.subscribed == [["TSLA"]]

    async def test_live_symbol_already_in_the_baseline_is_not_resubscribed(self) -> None:
        stream = FakeStream()
        universe = IngestUniverse(["SPY"], source=FakeSource("SPY"))
        universe.attach(stream)

        assert await universe.refresh() == UniverseChange()
        assert universe.symbols == ("SPY",)
        assert stream.subscribed == []

    async def test_symbols_are_normalized_from_the_source(self) -> None:
        universe = IngestUniverse([], source=FakeSource(" tsla "))

        await universe.refresh()

        assert universe.symbols == ("TSLA",)

    async def test_updates_the_set_with_no_stream_attached(self) -> None:
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA"))

        assert await universe.refresh() == UniverseChange(added=("TSLA",))
        assert universe.symbols == ("SPY", "TSLA")

    async def test_detached_stream_still_advances_the_set(self) -> None:
        stream = FakeStream()
        source = FakeSource("TSLA")
        universe = IngestUniverse(["SPY"], source=source)
        universe.attach(stream)
        await universe.refresh()

        universe.attach(None)
        source.symbols = frozenset({"TSLA", "NVDA"})
        assert await universe.refresh() == UniverseChange(added=("NVDA",))
        assert universe.symbols == ("SPY", "NVDA", "TSLA")
        assert stream.subscribed == [["TSLA"]]


class TestRemoval:
    async def test_symbol_leaves_when_its_session_stops(self) -> None:
        stream = FakeStream()
        source = FakeSource("TSLA", "NVDA")
        universe = IngestUniverse(["SPY"], source=source)
        universe.attach(stream)
        await universe.refresh()

        source.symbols = frozenset({"TSLA"})
        assert await universe.refresh() == UniverseChange(removed=("NVDA",))
        assert universe.symbols == ("SPY", "TSLA")
        assert stream.unsubscribed == [["NVDA"]]

    async def test_baseline_survives_every_session_stopping(self) -> None:
        stream = FakeStream()
        source = FakeSource("SPY", "TSLA")
        universe = IngestUniverse(["SPY", "QQQ"], source=source)
        universe.attach(stream)
        await universe.refresh()

        source.symbols = frozenset()
        await universe.refresh()

        assert universe.symbols == ("SPY", "QQQ")
        assert stream.unsubscribed == [["TSLA"]]

    async def test_add_and_remove_in_one_refresh(self) -> None:
        stream = FakeStream()
        source = FakeSource("TSLA")
        universe = IngestUniverse(["SPY"], source=source)
        universe.attach(stream)
        await universe.refresh()

        source.symbols = frozenset({"NVDA"})
        assert await universe.refresh() == UniverseChange(added=("NVDA",), removed=("TSLA",))
        assert stream.subscribed == [["TSLA"], ["NVDA"]]
        assert stream.unsubscribed == [["TSLA"]]


class TestQueryFailureFallback:
    async def test_keeps_the_current_set_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        stream = FakeStream()
        source = FakeSource("TSLA")
        universe = IngestUniverse(["SPY"], source=source)
        universe.attach(stream)
        await universe.refresh()

        source.fails = True
        before = _counter("query")
        with caplog.at_level(logging.WARNING, logger="src.ingest.universe"):
            assert await universe.refresh() == UniverseChange()

        assert universe.symbols == ("SPY", "TSLA")
        assert stream.subscribed == [["TSLA"]]
        assert stream.unsubscribed == []
        assert _counter("query") == before + 1
        assert "Live-session symbol read failed" in caplog.text

    async def test_first_refresh_failure_leaves_the_baseline(self) -> None:
        source = FakeSource()
        source.fails = True
        universe = IngestUniverse(["SPY", "QQQ"], source=source)

        assert await universe.refresh() == UniverseChange()
        assert universe.symbols == ("SPY", "QQQ")

    async def test_stalled_read_times_out_and_keeps_the_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def hang() -> frozenset[str]:
            await asyncio.Event().wait()
            return frozenset()

        monkeypatch.setattr(universe_module, "REFRESH_TIMEOUT_S", 0.01)
        universe = IngestUniverse(["SPY"], source=hang)

        before = _counter("query")
        assert await universe.refresh() == UniverseChange()

        assert universe.symbols == ("SPY",)
        assert _counter("query") == before + 1


class TestSubscribeFailure:
    async def test_refused_subscribe_keeps_the_set_for_the_next_pass(self) -> None:
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA"))
        universe.attach(FakeStream(subscribe_result=False))

        before = _counter("subscribe")
        assert await universe.refresh() == UniverseChange()

        assert universe.symbols == ("SPY",)
        assert _counter("subscribe") == before + 1

        universe.attach(FakeStream())
        assert await universe.refresh() == UniverseChange(added=("TSLA",))

    async def test_raising_stream_is_contained(self) -> None:
        universe = IngestUniverse(["SPY"], source=FakeSource("TSLA"))
        universe.attach(FakeStream(raises=True))

        before = _counter("subscribe")
        assert await universe.refresh() == UniverseChange()

        assert universe.symbols == ("SPY",)
        assert _counter("subscribe") == before + 1

    async def test_removal_is_not_applied_when_the_subscribe_failed(self) -> None:
        source = FakeSource("TSLA")
        universe = IngestUniverse(["SPY"], source=source)
        universe.attach(FakeStream())
        await universe.refresh()

        failing = FakeStream(subscribe_result=False)
        universe.attach(failing)
        source.symbols = frozenset({"NVDA"})
        assert await universe.refresh() == UniverseChange()

        assert failing.unsubscribed == []
        assert universe.symbols == ("SPY", "TSLA")


class TestMetrics:
    async def test_gauge_tracks_baseline_live_and_total(self) -> None:
        universe = IngestUniverse(["SPY", "QQQ"], source=FakeSource("TSLA", "NVDA"))

        await universe.refresh()

        assert _gauge("baseline") == 2
        assert _gauge("live") == 2
        assert _gauge("total") == 4
