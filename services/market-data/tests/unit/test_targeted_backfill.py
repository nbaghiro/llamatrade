"""Unit tests for the catch-up backfill of newly added universe symbols."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import cast

import pytest

from llamatrade_telemetry import get_metrics

from src.ingest.backfill import BackfillController, TargetedBackfill

_NOW = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)


def _counter(outcome: str) -> float:
    """Current value of the targeted-backfill counter for ``outcome`` (0 if unset)."""
    name = "llamatrade_marketdata_ingest_targeted_backfills_total"
    for line in get_metrics().decode().splitlines():
        if line.startswith(name) and f'outcome="{outcome}"' in line:
            return float(line.rpartition(" ")[2])
    return 0.0


class FakeController:
    """Records the symbol sets a pass was asked to backfill."""

    def __init__(self, *, fails: bool = False) -> None:
        self.runs: list[list[str]] = []
        self.gate: asyncio.Event | None = None
        self.fails = fails

    async def run(self, symbols: list[str], now: datetime) -> dict[str, int]:
        self.runs.append(list(symbols))
        if self.gate is not None:
            await self.gate.wait()
        if self.fails:
            raise RuntimeError("Alpaca is down")
        return dict.fromkeys(symbols, 0)


def _targeted(controller: FakeController) -> TargetedBackfill:
    return TargetedBackfill(cast(BackfillController, controller), lambda: _NOW)


async def _settle(targeted: TargetedBackfill) -> None:
    """Let the scheduled pass (and its follow-up) finish."""
    task = targeted._task
    if task is not None:
        await asyncio.wait_for(task, timeout=2.0)


class TestSchedule:
    async def test_added_symbol_is_backfilled_once(self) -> None:
        controller = FakeController()
        targeted = _targeted(controller)
        before = _counter("ok")

        targeted.schedule(("TSLA",))
        await _settle(targeted)

        assert controller.runs == [["TSLA"]]
        assert _counter("ok") == before + 1

    async def test_nothing_added_schedules_no_pass(self) -> None:
        controller = FakeController()
        targeted = _targeted(controller)

        targeted.schedule(())
        await asyncio.sleep(0)

        assert controller.runs == []
        assert targeted._task is None

    async def test_repeated_schedule_does_not_refetch_a_done_symbol(self) -> None:
        controller = FakeController()
        targeted = _targeted(controller)

        targeted.schedule(("TSLA",))
        await _settle(targeted)
        targeted.schedule(("NVDA",))
        await _settle(targeted)

        assert controller.runs == [["TSLA"], ["NVDA"]]

    async def test_symbols_added_during_a_pass_join_the_next_one(self) -> None:
        controller = FakeController()
        controller.gate = asyncio.Event()
        targeted = _targeted(controller)

        targeted.schedule(("TSLA",))
        await asyncio.sleep(0)  # let the pass start and block on the gate
        targeted.schedule(("NVDA", "AMD"))
        controller.gate.set()
        await _settle(targeted)

        assert controller.runs == [["TSLA"], ["AMD", "NVDA"]]

    async def test_passes_the_current_time_to_the_controller(self) -> None:
        stamps: list[datetime] = []

        class StampingController(FakeController):
            async def run(self, symbols: list[str], now: datetime) -> dict[str, int]:
                stamps.append(now)
                return await super().run(symbols, now)

        controller = StampingController()
        targeted = _targeted(controller)

        targeted.schedule(("TSLA",))
        await _settle(targeted)

        assert stamps == [_NOW]


class TestFailureIsolation:
    async def test_failed_pass_is_counted_and_contained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        controller = FakeController(fails=True)
        targeted = _targeted(controller)
        before = _counter("error")

        with caplog.at_level(logging.ERROR, logger="src.ingest.backfill"):
            targeted.schedule(("BADSYM",))
            await _settle(targeted)

        assert _counter("error") == before + 1
        assert "Targeted backfill failed" in caplog.text
        assert targeted._task is not None and targeted._task.exception() is None

    async def test_a_failed_pass_does_not_block_the_next_refresh(self) -> None:
        controller = FakeController(fails=True)
        targeted = _targeted(controller)

        targeted.schedule(("BADSYM",))
        await _settle(targeted)
        controller.fails = False
        targeted.schedule(("TSLA",))
        await _settle(targeted)

        assert controller.runs == [["BADSYM"], ["TSLA"]]


class TestClose:
    async def test_cancels_an_in_flight_pass(self) -> None:
        controller = FakeController()
        controller.gate = asyncio.Event()
        targeted = _targeted(controller)

        targeted.schedule(("TSLA",))
        await asyncio.sleep(0)
        await targeted.aclose()

        assert targeted._task is None

    async def test_close_without_a_pass_is_a_no_op(self) -> None:
        targeted = _targeted(FakeController())
        await targeted.aclose()
        assert targeted._task is None
