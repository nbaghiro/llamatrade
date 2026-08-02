"""Unit tests for the ingest supervisor entrypoint (src/ingest/main.py)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable

import pytest
from httpx import ASGITransport, AsyncClient

from llamatrade_telemetry import init_telemetry

from src.ingest import main as ingest_main
from src.ingest.universe import IngestUniverse

_REAL_SLEEP = asyncio.sleep


async def _wait_until(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not condition():
            await _REAL_SLEEP(0.005)

    await asyncio.wait_for(poll(), timeout=timeout)


class TestPeriodic:
    async def test_swallows_bad_iteration_and_keeps_looping(self) -> None:
        stop = asyncio.Event()
        calls = 0

        async def flaky() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("bad iteration")
            if calls >= 3:
                stop.set()

        await asyncio.wait_for(
            ingest_main._periodic("test", flaky, interval_s=0.01, stop=stop), timeout=2.0
        )
        assert calls >= 3

    async def test_does_not_run_when_stop_already_set(self) -> None:
        stop = asyncio.Event()
        stop.set()
        calls = 0

        async def fn() -> None:
            nonlocal calls
            calls += 1

        await asyncio.wait_for(
            ingest_main._periodic("test", fn, interval_s=60.0, stop=stop), timeout=1.0
        )
        assert calls == 0

    async def test_long_interval_wait_is_interrupted_by_stop(self) -> None:
        stop = asyncio.Event()
        ran = asyncio.Event()

        async def fn() -> None:
            ran.set()

        task = asyncio.create_task(ingest_main._periodic("test", fn, interval_s=60.0, stop=stop))
        await asyncio.wait_for(ran.wait(), timeout=1.0)
        stop.set()
        await asyncio.wait_for(task, timeout=1.0)


class FakeStream:
    """Scripted stand-in for MarketDataStreamClient."""

    def __init__(self, run_forever: bool) -> None:
        self.subscribed: list[list[str]] = []
        self.unsubscribed: list[list[str]] = []
        self.run_calls = 0
        self._run_forever = run_forever

    async def subscribe(self, bars: list[str]) -> bool:
        self.subscribed.append(list(bars))
        return True

    async def unsubscribe(self, bars: list[str]) -> bool:
        self.unsubscribed.append(list(bars))
        return True

    async def run(self) -> None:
        self.run_calls += 1
        if self._run_forever:
            await asyncio.Event().wait()


class FakeIngestor:
    def __init__(self) -> None:
        self.attached: list[object] = []
        self.flush_started = asyncio.Event()

    def attach(self, stream: object) -> None:
        self.attached.append(stream)

    async def run_flush_loop(self, *, stop_event: asyncio.Event) -> None:
        self.flush_started.set()
        await stop_event.wait()


class FakeController:
    def __init__(self) -> None:
        self.runs: list[list[str]] = []
        self.fail_for: str | None = None

    async def run(self, universe: list[str], now: object) -> None:
        self.runs.append(list(universe))
        if self.fail_for is not None and self.fail_for in universe:
            raise RuntimeError(f"backfill failed for {self.fail_for}")


class FakeRepairer:
    async def repair(self, universe: list[str], timeframe: str, now: object) -> None:
        return None


class FakeRefresher:
    async def refresh(self, universe: list[str], now: object) -> None:
        return None


class FakeBus:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeSymbolSource:
    """Live-session symbols the supervisor's universe derives from (no DB)."""

    def __init__(self) -> None:
        self.symbols: frozenset[str] = frozenset()

    async def __call__(self) -> frozenset[str]:
        return self.symbols


class FakeAdminServer:
    """Stand-in for the uvicorn admin server (no port binding)."""

    def __init__(self) -> None:
        self.should_exit = False
        self.serving = asyncio.Event()

    async def serve(self) -> None:
        self.serving.set()
        while not self.should_exit:
            await _REAL_SLEEP(0.005)


class SupervisorHarness:
    """Patches every collaborator of run() and captures its internal stop event."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, streams: list[FakeStream | None]) -> None:
        self.streams = streams
        self.init_calls = 0
        self.close_stream_calls = 0
        self.close_all_calls = 0
        self.close_engine_calls = 0
        self.stop_events: list[asyncio.Event] = []
        self.controller = FakeController()
        self.ingestor = FakeIngestor()
        self.bus = FakeBus()
        self.live_symbols = FakeSymbolSource()
        self.admin_server = FakeAdminServer()
        self.telemetry_apps: list[object] = []

        def fake_universe(baseline: Iterable[str]) -> IngestUniverse:
            return IngestUniverse(baseline, source=self.live_symbols)

        async def fake_init() -> FakeStream | None:
            self.init_calls += 1
            return self.streams[min(self.init_calls, len(self.streams)) - 1]

        async def fake_close_stream() -> None:
            self.close_stream_calls += 1

        async def fake_close_all() -> None:
            self.close_all_calls += 1

        async def fake_close_engine() -> None:
            self.close_engine_calls += 1

        async def fake_get_client() -> object:
            return object()

        async def fast_sleep(delay: float) -> None:
            await _REAL_SLEEP(0)

        def fake_init_telemetry(app: object, *, service: str, version: str) -> None:
            self.telemetry_apps.append(app)

        mp = monkeypatch
        mp.setattr(ingest_main, "init_telemetry", fake_init_telemetry)
        mp.setattr(ingest_main, "_build_admin_server", lambda app: self.admin_server)
        mp.setattr(ingest_main, "get_universe", lambda: ["AAPL"])
        mp.setattr(ingest_main, "IngestUniverse", fake_universe)
        mp.setattr(ingest_main, "BarStore", lambda: object())
        mp.setattr(ingest_main, "get_market_data_client_async", fake_get_client)
        mp.setattr(ingest_main, "get_default_transport", lambda: object())
        mp.setattr(ingest_main, "EventBus", lambda transport: self.bus)
        mp.setattr(ingest_main, "BackfillController", lambda *a, **k: self.controller)
        mp.setattr(ingest_main, "GapRepairer", lambda *a, **k: FakeRepairer())
        mp.setattr(ingest_main, "CorporateActionRefresher", lambda *a, **k: FakeRefresher())
        mp.setattr(ingest_main, "BarIngestor", lambda *a, **k: self.ingestor)
        mp.setattr(ingest_main, "init_market_data_stream", fake_init)
        mp.setattr(ingest_main, "close_market_data_stream", fake_close_stream)
        mp.setattr(ingest_main, "close_all_clients", fake_close_all)
        mp.setattr(ingest_main, "close_engine", fake_close_engine)
        mp.setattr(ingest_main, "_install_signal_handlers", self.stop_events.append)
        # Collapses the supervisor's 15s restart delay; nothing else sleeps.
        mp.setattr(asyncio, "sleep", fast_sleep)

    def stop(self) -> None:
        self.stop_events[0].set()


class TestSuperviseStream:
    async def test_reinitializes_fresh_stream_and_resubscribes_after_run_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream1 = FakeStream(run_forever=False)  # run() returns: reconnects exhausted
        stream2 = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream1, stream2])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream2.subscribed))

        assert stream1.run_calls == 1
        assert harness.init_calls == 2  # initial + re-init after exhaustion
        assert harness.close_stream_calls >= 1  # dead stream torn down first
        assert harness.ingestor.attached == [stream1, stream2]
        assert stream1.subscribed == [["AAPL"]]
        assert stream2.subscribed == [["AAPL"]]

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

    async def test_shutdown_cancels_tasks_and_closes_resources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: harness.ingestor.flush_started.is_set())
        assert stream.run_calls == 1

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

        # The blocked stream/flush tasks were cancelled and every resource closed.
        assert harness.close_stream_calls == 1
        assert harness.close_all_calls == 1
        assert harness.close_engine_calls == 1
        assert harness.bus.closed is True
        assert harness.controller.runs and harness.controller.runs[0] == ["AAPL"]

    async def test_stream_unavailable_still_runs_maintenance_and_shuts_down(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = SupervisorHarness(monkeypatch, streams=[None])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: len(harness.controller.runs) >= 2)  # initial + periodic

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

        assert harness.ingestor.attached == []
        assert harness.close_all_calls == 1
        assert harness.bus.closed is True


class TestDerivedUniverse:
    async def test_live_session_symbols_join_the_initial_backfill_and_subscription(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])
        harness.live_symbols.symbols = frozenset({"TSLA"})

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream.subscribed))

        assert stream.subscribed == [["AAPL", "TSLA"]]
        assert harness.controller.runs[0] == ["AAPL", "TSLA"]

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

    async def test_refresh_loop_subscribes_new_symbols_and_drops_stopped_ones(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S", "0.01")
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream.subscribed))
        assert stream.subscribed == [["AAPL"]]

        harness.live_symbols.symbols = frozenset({"TSLA"})
        await _wait_until(lambda: len(stream.subscribed) >= 2)
        assert stream.subscribed[1] == ["TSLA"]

        harness.live_symbols.symbols = frozenset()
        await _wait_until(lambda: bool(stream.unsubscribed))
        assert stream.unsubscribed == [["TSLA"]]  # the configured baseline stays

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

    async def test_a_symbol_added_by_a_refresh_is_backfilled_immediately(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A new symbol streams at once but has no history until the next daily
        pass, so the refresh that added it schedules a catch-up backfill."""
        monkeypatch.setenv("MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S", "0.01")
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream.subscribed))

        harness.live_symbols.symbols = frozenset({"TSLA"})
        # Only the targeted pass backfills TSLA on its own; every scheduled pass
        # carries the whole universe.
        await _wait_until(lambda: ["TSLA"] in harness.controller.runs)

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)

    async def test_a_failing_catch_up_backfill_keeps_refreshes_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One unfetchable symbol must not stop the universe-refresh loop."""
        monkeypatch.setenv("MARKET_DATA_UNIVERSE_REFRESH_INTERVAL_S", "0.01")
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])
        harness.controller.fail_for = "BADSYM"

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream.subscribed))

        harness.live_symbols.symbols = frozenset({"BADSYM"})
        await _wait_until(lambda: ["BADSYM"] in harness.controller.runs)

        harness.live_symbols.symbols = frozenset({"BADSYM", "TSLA"})
        await _wait_until(lambda: ["TSLA"] in harness.controller.runs)

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)


class TestAdminServer:
    async def test_starts_with_telemetry_and_stops_gracefully(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: harness.admin_server.serving.is_set())
        # init_telemetry received the admin app so /metrics + middleware are wired.
        assert len(harness.telemetry_apps) == 1
        assert harness.telemetry_apps[0] is not None

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)
        assert harness.admin_server.should_exit is True

    async def test_reconnect_hook_installed_on_initial_and_reestablished_streams(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stream1 = FakeStream(run_forever=False)  # run() returns: reconnects exhausted
        stream2 = FakeStream(run_forever=True)
        harness = SupervisorHarness(monkeypatch, streams=[stream1, stream2])

        run_task = asyncio.create_task(ingest_main.run())
        await _wait_until(lambda: bool(stream2.subscribed))

        assert getattr(stream1, "_on_reconnect") is ingest_main.record_stream_reconnect
        assert getattr(stream2, "_on_reconnect") is ingest_main.record_stream_reconnect

        harness.stop()
        await asyncio.wait_for(run_task, timeout=2.0)


class TestAdminApp:
    async def test_serves_metrics_and_healthy_health(self) -> None:
        app = ingest_main._build_admin_app(lambda: True)
        init_telemetry(app, service=ingest_main.SERVICE_NAME, version="test")
        # Instruments are lazy; record one so the exposition carries a real series.
        ingest_main.record_stream_reconnect()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            metrics_resp = await client.get("/metrics")
            assert metrics_resp.status_code == 200
            assert "llamatrade_marketdata_stream_reconnects" in metrics_resp.text

            health_resp = await client.get("/health")
            assert health_resp.status_code == 200
            body = health_resp.json()
            assert body["status"] == "healthy"
            assert body["service"] == "market-data-ingest"
            assert body["checks"]["ingest_loops"]["healthy"] is True

    async def test_health_unhealthy_when_ingest_loops_dead(self) -> None:
        app = ingest_main._build_admin_app(lambda: False)
        init_telemetry(app, service=ingest_main.SERVICE_NAME, version="test")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "unhealthy"
            assert body["checks"]["ingest_loops"]["healthy"] is False
