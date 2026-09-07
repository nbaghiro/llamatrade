"""FastAPI lifespan: RLS verification, rehydration loop wiring, lease release.

Drives ``src.main.lifespan`` directly with the infrastructure seams patched:
the RLS enforcement check, the recovery module's rehydration loop and lease
release, and the DB pool teardown. Asserts the startup ordering (fail-closed
RLS first), the stop-event/cancellation shutdown of the rehydration task, and
that a rehydration wiring failure degrades startup instead of blocking it.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.main as main_module
import src.recovery as recovery_module
from src.main import app, lifespan
from src.runner.runner import RunnerManager


class _LoopProbe:
    """Recording stand-in for ``rehydration_loop`` (runs until cancelled/stopped)."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False
        self.stop_event: asyncio.Event | None = None
        self.manager: RunnerManager | None = None

    async def __call__(self, manager: RunnerManager, stop_event: asyncio.Event) -> None:
        self.manager = manager
        self.stop_event = stop_event
        self.started.set()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.fixture
def seams(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        "verify_rls": AsyncMock(),
        "release_leases": AsyncMock(),
        "close_db": AsyncMock(),
    }
    monkeypatch.setattr(main_module, "verify_rls_enforcement", mocks["verify_rls"])
    monkeypatch.setattr(recovery_module, "release_all_leases", mocks["release_leases"])
    monkeypatch.setattr(main_module, "close_db", mocks["close_db"])
    return mocks


class TestLifespan:
    async def test_startup_verifies_rls_starts_rehydration_and_shuts_down_cleanly(
        self, seams: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
    ):
        probe = _LoopProbe()
        monkeypatch.setattr(recovery_module, "rehydration_loop", probe)

        async with lifespan(app):
            seams["verify_rls"].assert_awaited_once()
            await asyncio.wait_for(probe.started.wait(), timeout=2.0)
            assert isinstance(probe.manager, RunnerManager)
            seams["release_leases"].assert_not_awaited()

        assert probe.stop_event is not None and probe.stop_event.is_set()
        seams["release_leases"].assert_awaited_once()
        seams["close_db"].assert_awaited_once()

    async def test_rls_failure_blocks_startup(
        self, seams: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
    ):
        seams["verify_rls"].side_effect = RuntimeError("role bypasses RLS")
        probe = _LoopProbe()
        monkeypatch.setattr(recovery_module, "rehydration_loop", probe)

        with pytest.raises(RuntimeError, match="role bypasses RLS"):
            async with lifespan(app):
                pytest.fail("lifespan must not yield when RLS verification fails")

        assert not probe.started.is_set()

    async def test_rehydration_wiring_failure_degrades_startup_but_does_not_block(
        self, seams: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
    ):
        broken_loop = MagicMock(side_effect=TypeError("bad wiring"))
        monkeypatch.setattr(recovery_module, "rehydration_loop", broken_loop)

        async with lifespan(app):
            broken_loop.assert_called_once()

        seams["release_leases"].assert_awaited_once()
        seams["close_db"].assert_awaited_once()

    async def test_lease_release_failure_is_contained_and_pool_still_closes(
        self, seams: dict[str, AsyncMock], monkeypatch: pytest.MonkeyPatch
    ):
        seams["release_leases"].side_effect = RuntimeError("db already gone")
        probe = _LoopProbe()
        monkeypatch.setattr(recovery_module, "rehydration_loop", probe)

        async with lifespan(app):
            await asyncio.wait_for(probe.started.wait(), timeout=2.0)

        seams["close_db"].assert_awaited_once()
