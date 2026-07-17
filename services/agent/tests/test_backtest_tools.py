"""Tests for the run_backtest tool (the confirmation-gated action)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.tools.backtest_tools import RunBacktestTool
from src.tools.base import ToolContext


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


def _client_class(run_backtest: AsyncMock) -> MagicMock:
    """A patchable BacktestServiceClient class whose instance uses run_backtest."""
    client = MagicMock()
    client.run_backtest = run_backtest
    return MagicMock(return_value=client)


def test_run_backtest_is_confirmation_gated() -> None:
    assert RunBacktestTool().requires_confirmation is True


@pytest.mark.asyncio
async def test_submits_complete_config(ctx: ToolContext) -> None:
    """A saved strategy submits a job with a fully-populated window + capital —
    the empty Decimal the old tool sent crashed the service."""
    run = AsyncMock(return_value=MagicMock(backtest=MagicMock(id="bt-1")))
    with patch(
        "llamatrade_proto.generated.backtest_connect.BacktestServiceClient", _client_class(run)
    ):
        result = await RunBacktestTool().execute(
            {"strategy_id": "s1", "initial_capital": 50000}, ctx
        )

    assert result.success is True
    assert result.data is not None
    assert result.data["backtest_id"] == "bt-1"

    request = run.await_args.args[0]
    assert request.config.strategy_id == "s1"
    assert request.config.start_date.seconds > 0
    assert request.config.end_date.seconds > request.config.start_date.seconds
    assert request.config.initial_capital.value == "50000.0"


@pytest.mark.asyncio
async def test_defaults_window_and_capital(ctx: ToolContext) -> None:
    """Unspecified dates/capital fall back to last ~3y and $100k."""
    run = AsyncMock(return_value=MagicMock(backtest=MagicMock(id="bt-2")))
    with patch(
        "llamatrade_proto.generated.backtest_connect.BacktestServiceClient", _client_class(run)
    ):
        result = await RunBacktestTool().execute({"strategy_id": "s1"}, ctx)

    assert result.success is True
    request = run.await_args.args[0]
    assert request.config.initial_capital.value == "100000.0"
    # ~3 years between defaults.
    span_days = (request.config.end_date.seconds - request.config.start_date.seconds) / 86400
    assert 1000 < span_days < 1150


@pytest.mark.asyncio
async def test_draft_asks_to_save_first(ctx: ToolContext) -> None:
    """A draft (dsl_code only) can't be backtested — the engine runs saved ids."""
    result = await RunBacktestTool().execute({"dsl_code": '(strategy "S")'}, ctx)
    assert result.success is False
    assert "save" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_missing_strategy_id(ctx: ToolContext) -> None:
    result = await RunBacktestTool().execute({}, ctx)
    assert result.success is False
    assert "strategy_id" in (result.error or "")


@pytest.mark.asyncio
async def test_reports_failure_honestly(ctx: ToolContext) -> None:
    """A backend failure returns success=False — NOT masked as success."""
    run = AsyncMock(side_effect=RuntimeError("service down"))
    with patch(
        "llamatrade_proto.generated.backtest_connect.BacktestServiceClient", _client_class(run)
    ):
        result = await RunBacktestTool().execute({"strategy_id": "s1"}, ctx)

    assert result.success is False
    assert "backtest" in (result.error or "").lower()
