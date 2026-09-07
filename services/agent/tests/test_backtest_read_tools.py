"""The copilot's two backtest read tools.

``test_backtest_tools.py`` covers only ``RunBacktestTool``, the confirmation-gated
action, so the tools the assistant actually reaches for when a user asks "how did
that do?" had no coverage: fetching one run's metrics and listing a strategy's
history. Both talk to the backtest service and shape the payload the model reads,
so a wrong field name or a swallowed failure becomes a confidently wrong answer.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_proto.generated import backtest_pb2

from src.tools.backtest_tools import GetBacktestResultsTool, ListBacktestsTool
from src.tools.base import ToolContext

CLIENT = "llamatrade_proto.generated.backtest_connect.BacktestServiceClient"


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


def _client(**methods: AsyncMock) -> MagicMock:
    """A patchable client class whose instance exposes the given async methods."""
    instance = MagicMock()
    for name, method in methods.items():
        setattr(instance, name, method)
    return MagicMock(return_value=instance)


def _metrics(**over: Any) -> MagicMock:
    defaults = dict(
        ending_capital="12000",
        total_return="0.2",
        annualized_return="0.1",
        sharpe_ratio="1.5",
        sortino_ratio="2.0",
        max_drawdown="-0.08",
        volatility="0.13",
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate="0.6",
        profit_factor="1.8",
        benchmark_return="0.05",
        alpha="0.03",
        beta="0.9",
    )
    return MagicMock(**{**defaults, **over})


def _backtest(**over: Any) -> MagicMock:
    defaults = dict(
        id="bt-1",
        strategy_id="s1",
        status=backtest_pb2.BACKTEST_STATUS_COMPLETED,
        config=MagicMock(initial_capital="10000"),
        results=MagicMock(metrics=_metrics(), benchmark_symbol="SPY"),
        created_at=MagicMock(seconds=1700),
    )
    return MagicMock(**{**defaults, **over})


class TestGetBacktestResults:
    async def test_requires_a_strategy_id(self, ctx: ToolContext) -> None:
        result = await GetBacktestResultsTool().execute({}, ctx)

        assert result.success is False
        assert result.error is not None and "strategy_id" in result.error

    async def test_fetches_a_named_backtest_directly(self, ctx: ToolContext) -> None:
        get = AsyncMock(return_value=MagicMock(backtest=_backtest()))
        list_ = AsyncMock()
        with patch(CLIENT, _client(get_backtest=get, list_backtests=list_)):
            result = await GetBacktestResultsTool().execute(
                {"strategy_id": "s1", "backtest_id": "bt-1"}, ctx
            )

        assert result.success is True
        list_.assert_not_awaited()
        assert get.await_args.args[0].backtest_id == "bt-1"
        assert result.data is not None
        assert result.data["backtest_id"] == "bt-1"
        assert result.data["status"] == "completed"

    async def test_falls_back_to_the_most_recent_run(self, ctx: ToolContext) -> None:
        list_ = AsyncMock(return_value=MagicMock(backtests=[_backtest(id="bt-latest")]))
        with patch(CLIENT, _client(get_backtest=AsyncMock(), list_backtests=list_)):
            result = await GetBacktestResultsTool().execute({"strategy_id": "s1"}, ctx)

        assert result.data is not None
        assert result.data["backtest_id"] == "bt-latest"
        # Only the newest run is needed, so the page must be bounded to one.
        request = list_.await_args.args[0]
        assert request.strategy_id == "s1"
        assert request.pagination.page_size == 1

    async def test_says_so_when_a_strategy_has_never_been_backtested(
        self, ctx: ToolContext
    ) -> None:
        list_ = AsyncMock(return_value=MagicMock(backtests=[]))
        with patch(CLIENT, _client(get_backtest=AsyncMock(), list_backtests=list_)):
            result = await GetBacktestResultsTool().execute({"strategy_id": "s1"}, ctx)

        # A truthful empty answer, not a failure the model would apologise for.
        assert result.success is True
        assert result.data is not None
        assert "No backtests" in result.data["note"]

    async def test_reports_every_metric_the_model_quotes(self, ctx: ToolContext) -> None:
        get = AsyncMock(return_value=MagicMock(backtest=_backtest()))
        with patch(CLIENT, _client(get_backtest=get, list_backtests=AsyncMock())):
            result = await GetBacktestResultsTool().execute(
                {"strategy_id": "s1", "backtest_id": "bt-1"}, ctx
            )

        assert result.data is not None
        metrics = result.data["metrics"]
        assert metrics["sharpe_ratio"] == "1.5"
        assert metrics["max_drawdown"] == "-0.08"
        assert metrics["total_trades"] == 10
        assert metrics["win_rate"] == "0.6"
        assert result.data["final_equity"] == "12000"
        assert result.data["benchmark_symbol"] == "SPY"
        assert result.data["initial_capital"] == "10000"

    async def test_omits_metrics_for_a_run_with_no_results(self, ctx: ToolContext) -> None:
        get = AsyncMock(return_value=MagicMock(backtest=_backtest(results=None)))
        with patch(CLIENT, _client(get_backtest=get, list_backtests=AsyncMock())):
            result = await GetBacktestResultsTool().execute(
                {"strategy_id": "s1", "backtest_id": "bt-1"}, ctx
            )

        assert result.success is True
        assert result.data is not None
        assert "metrics" not in result.data
        assert "final_equity" not in result.data

    async def test_a_service_outage_is_reported_not_answered_around(self, ctx: ToolContext) -> None:
        get = AsyncMock(side_effect=RuntimeError("connection refused"))
        with patch(CLIENT, _client(get_backtest=get, list_backtests=AsyncMock())):
            result = await GetBacktestResultsTool().execute(
                {"strategy_id": "s1", "backtest_id": "bt-1"}, ctx
            )

        assert result.success is False
        assert result.error is not None and "unavailable" in result.error
        assert result.data == {"strategy_id": "s1"}


class TestListBacktests:
    async def test_summarizes_each_run(self, ctx: ToolContext) -> None:
        list_ = AsyncMock(return_value=MagicMock(backtests=[_backtest(id="a"), _backtest(id="b")]))
        with patch(CLIENT, _client(list_backtests=list_)):
            result = await ListBacktestsTool().execute({"strategy_id": "s1"}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["count"] == 2
        first = result.data["backtests"][0]
        assert first["id"] == "a"
        assert first["status"] == "completed"
        assert first["total_return"] == "0.2"
        assert first["sharpe_ratio"] == "1.5"
        assert first["created_at"] == 1700

    async def test_a_pending_run_carries_no_metrics(self, ctx: ToolContext) -> None:
        pending = _backtest(id="p", status=backtest_pb2.BACKTEST_STATUS_RUNNING, results=None)
        with patch(
            CLIENT, _client(list_backtests=AsyncMock(return_value=MagicMock(backtests=[pending])))
        ):
            result = await ListBacktestsTool().execute({"strategy_id": "s1"}, ctx)

        assert result.data is not None
        row = result.data["backtests"][0]
        assert row["status"] == "running"
        assert "total_return" not in row

    async def test_an_empty_history_is_a_successful_empty_list(self, ctx: ToolContext) -> None:
        with patch(CLIENT, _client(list_backtests=AsyncMock(return_value=MagicMock(backtests=[])))):
            result = await ListBacktestsTool().execute({"strategy_id": "s1"}, ctx)

        assert result.success is True
        assert result.data == {"backtests": [], "count": 0}

    async def test_a_service_outage_is_reported(self, ctx: ToolContext) -> None:
        with patch(CLIENT, _client(list_backtests=AsyncMock(side_effect=RuntimeError("down")))):
            result = await ListBacktestsTool().execute({"strategy_id": "s1"}, ctx)

        assert result.success is False
        assert result.error is not None and "unavailable" in result.error
