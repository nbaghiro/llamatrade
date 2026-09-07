"""Tests for src/main.py: bus-mode selection, the lifespan fork, and _check_kafka."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI

from src import main as service_main


class TestBarsFromBus:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_enable_bus_mode(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("MARKET_DATA_BARS_FROM_BUS", value)
        assert service_main._bars_from_bus() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "banana"])
    def test_falsy_values_stay_legacy(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("MARKET_DATA_BARS_FROM_BUS", value)
        assert service_main._bars_from_bus() is False

    def test_unset_stays_legacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MARKET_DATA_BARS_FROM_BUS", raising=False)
        assert service_main._bars_from_bus() is False


class _FakeKafkaTransport:
    def is_connected(self) -> bool:
        return True


class _FakeBridge:
    def __init__(self, running: bool) -> None:
        self.running = running


class TestCheckKafka:
    @pytest.fixture
    def probe_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> list[Callable[[], bool | Awaitable[bool]] | None]:
        """Stub the shared check_kafka probe, recording the is_alive argument."""
        calls: list[Callable[[], bool | Awaitable[bool]] | None] = []

        async def fake_check_kafka(
            bootstrap_servers: str | None = None,
            *,
            timeout: float = 2.0,
            is_alive: Callable[[], bool | Awaitable[bool]] | None = None,
            token_provider: object = None,
        ) -> bool:
            calls.append(is_alive)
            return True

        monkeypatch.setattr(service_main, "check_kafka", fake_check_kafka)
        return calls

    async def test_no_transport_falls_back_to_authenticated_probe(
        self, monkeypatch: pytest.MonkeyPatch, probe_calls: list[object]
    ) -> None:
        monkeypatch.setattr(service_main, "_kafka_transport", None)
        monkeypatch.setattr(service_main, "_bus_bridge", None)

        assert await service_main._check_kafka() is True
        assert probe_calls == [None]  # plain probe, no is_alive shortcut

    async def test_running_bridge_answers_healthy_without_probing(
        self, monkeypatch: pytest.MonkeyPatch, probe_calls: list[object]
    ) -> None:
        monkeypatch.setattr(service_main, "_kafka_transport", _FakeKafkaTransport())
        monkeypatch.setattr(service_main, "_bus_bridge", _FakeBridge(running=True))

        assert await service_main._check_kafka() is True
        assert probe_calls == []

    async def test_stopped_bridge_probes_via_transport_liveness(
        self, monkeypatch: pytest.MonkeyPatch, probe_calls: list[object]
    ) -> None:
        transport = _FakeKafkaTransport()
        monkeypatch.setattr(service_main, "_kafka_transport", transport)
        monkeypatch.setattr(service_main, "_bus_bridge", _FakeBridge(running=False))

        assert await service_main._check_kafka() is True
        assert probe_calls == [transport.is_connected]


class LifespanHarness:
    """Patches every lifespan collaborator in src.main and records the calls."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.rls_verified = False
        self.cache_inits = 0
        self.alpaca_inits = 0
        self.bridge_inits: list[tuple[object, object]] = []
        self.bus_bridges: list[object] = []
        self.buses: list[object] = []
        self.closed: list[str] = []
        harness = self

        async def verify_rls() -> None:
            harness.rls_verified = True

        async def init_cache() -> None:
            harness.cache_inits += 1
            return None

        async def init_alpaca() -> None:
            harness.alpaca_inits += 1
            return None

        async def init_bridge(stream: object, manager: object) -> object:
            harness.bridge_inits.append((stream, manager))
            return object()

        class FakeBusBridge:
            def __init__(self, bus: object, manager: object) -> None:
                self.started = False
                self.stopped = False
                harness.bus_bridges.append(self)

            async def start(self) -> None:
                self.started = True

            async def stop(self) -> None:
                self.stopped = True

        class FakeEventBus:
            def __init__(self, transport: object) -> None:
                self.closed = False
                harness.buses.append(self)

            async def close(self) -> None:
                self.closed = True

        def make_closer(name: str) -> Callable[[], Awaitable[None]]:
            async def closer() -> None:
                harness.closed.append(name)

            return closer

        mp = monkeypatch
        mp.setattr(service_main, "verify_rls_enforcement", verify_rls)
        mp.setattr(service_main, "init_cache", init_cache)
        mp.setattr(service_main, "init_market_data_stream", init_alpaca)
        mp.setattr(service_main, "init_stream_bridge", init_bridge)
        mp.setattr(service_main, "KafkaTransport", _FakeKafkaTransport)
        mp.setattr(service_main, "EventBus", FakeEventBus)
        mp.setattr(service_main, "BusBridge", FakeBusBridge)
        mp.setattr(service_main, "close_stream_bridge", make_closer("stream_bridge"))
        mp.setattr(service_main, "close_market_data_stream", make_closer("alpaca_stream"))
        mp.setattr(service_main, "close_all_clients", make_closer("clients"))
        mp.setattr(service_main, "close_cache", make_closer("cache"))
        mp.setattr(service_main, "close_db", make_closer("db"))
        mp.setattr(service_main, "_event_bus", None)
        mp.setattr(service_main, "_bus_bridge", None)
        mp.setattr(service_main, "_kafka_transport", None)
        mp.setattr(service_main, "_stream_connected", False)


class TestLifespanFork:
    async def test_bus_mode_starts_bridge_and_skips_alpaca(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MARKET_DATA_BARS_FROM_BUS", "1")
        harness = LifespanHarness(monkeypatch)
        app = FastAPI()

        async with service_main.lifespan(app):
            assert harness.rls_verified is True
            assert harness.cache_inits == 1
            assert harness.alpaca_inits == 0  # serving holds no Alpaca connection
            assert len(harness.bus_bridges) == 1
            assert getattr(harness.bus_bridges[0], "started") is True
            assert service_main._stream_connected is True
            assert app.routes  # Connect app mounted

        assert getattr(harness.bus_bridges[0], "stopped") is True
        assert getattr(harness.buses[0], "closed") is True
        assert service_main._kafka_transport is None

    async def test_legacy_mode_uses_alpaca_stream_bridge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MARKET_DATA_BARS_FROM_BUS", raising=False)
        harness = LifespanHarness(monkeypatch)
        sentinel_stream = object()

        async def init_alpaca_ok() -> object:
            harness.alpaca_inits += 1
            return sentinel_stream

        monkeypatch.setattr(service_main, "init_market_data_stream", init_alpaca_ok)

        async with service_main.lifespan(FastAPI()):
            assert harness.alpaca_inits == 1
            assert harness.bus_bridges == []  # no bus machinery in legacy mode
            assert len(harness.bridge_inits) == 1
            assert harness.bridge_inits[0][0] is sentinel_stream
            assert service_main._stream_connected is True

        assert "alpaca_stream" in harness.closed
        assert "cache" in harness.closed
        assert "db" in harness.closed

    async def test_legacy_mode_degrades_when_alpaca_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MARKET_DATA_BARS_FROM_BUS", raising=False)
        harness = LifespanHarness(monkeypatch)

        async with service_main.lifespan(FastAPI()):
            assert harness.alpaca_inits == 1
            assert harness.bridge_inits == []  # no bridge without a stream
            assert service_main._stream_connected is False
