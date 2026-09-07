"""The copilot's account-summary and positions tools.

``test_portfolio_tools.py`` covers only ``GetPortfolioPerformanceTool``, so the
two tools the assistant reaches for first, "what is my account worth?" and "what
do I hold?", had no coverage. Both shape the payload the model quotes back, and
both answer a service outage with ``success=True`` plus a note, so a wrong field
or a lost note turns an outage into a confidently wrong balance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.tools.base import ToolContext
from src.tools.portfolio_tools import GetPortfolioSummaryTool, GetPositionsTool

CLIENT = "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient"


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


def _client(**methods: AsyncMock) -> MagicMock:
    instance = MagicMock()
    for name, method in methods.items():
        setattr(instance, name, method)
    return MagicMock(return_value=instance)


def _portfolio(**over: Any) -> MagicMock:
    defaults = dict(
        id="p1",
        name="Main",
        total_value="10000",
        cash_balance="2500",
        positions_value="7500",
        total_return="500",
        total_return_percent="5.0",
        day_return="25",
        day_return_percent="0.25",
    )
    return MagicMock(**{**defaults, **over})


def _position(**over: Any) -> MagicMock:
    defaults = dict(
        symbol="AAPL",
        quantity="10",
        average_entry_price="100",
        current_price="120",
        market_value="1200",
        cost_basis="1000",
        unrealized_pnl="200",
        unrealized_pnl_percent="20",
    )
    return MagicMock(**{**defaults, **over})


class TestGetPortfolioSummary:
    async def test_reports_the_primary_portfolio(self, ctx: ToolContext) -> None:
        list_ = AsyncMock(return_value=MagicMock(portfolios=[_portfolio(), _portfolio(id="p2")]))
        with patch(CLIENT, _client(list_portfolios=list_)):
            result = await GetPortfolioSummaryTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["portfolio_id"] == "p1"
        assert result.data["total_value"] == "10000"
        assert result.data["cash_balance"] == "2500"
        assert result.data["day_return_percent"] == "0.25"

    async def test_threads_the_caller_identity(self, ctx: ToolContext) -> None:
        list_ = AsyncMock(return_value=MagicMock(portfolios=[_portfolio()]))
        with patch(CLIENT, _client(list_portfolios=list_)):
            await GetPortfolioSummaryTool().execute({}, ctx)

        request = list_.await_args.args[0]
        assert request.context.tenant_id == str(ctx.tenant_id)
        assert request.context.user_id == str(ctx.user_id)

    async def test_a_user_with_no_portfolio_gets_a_truthful_note(self, ctx: ToolContext) -> None:
        with patch(
            CLIENT, _client(list_portfolios=AsyncMock(return_value=MagicMock(portfolios=[])))
        ):
            result = await GetPortfolioSummaryTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["portfolios"] == []
        assert "No portfolios" in result.data["note"]

    async def test_an_outage_is_surfaced_as_a_note_never_as_a_balance(
        self, ctx: ToolContext
    ) -> None:
        """The tool answers success on failure, so the note is the only signal."""
        with patch(CLIENT, _client(list_portfolios=AsyncMock(side_effect=RuntimeError("down")))):
            result = await GetPortfolioSummaryTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert "unavailable" in result.data["note"]
        # Nothing that could be read as a real figure may appear.
        assert "total_value" not in result.data
        assert result.data["portfolios"] == []


class TestGetPositions:
    async def test_asks_for_the_portfolio_id_first(self, ctx: ToolContext) -> None:
        result = await GetPositionsTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["positions"] == []
        assert "get_portfolio_summary" in result.data["note"]

    async def test_lists_holdings_with_their_marks(self, ctx: ToolContext) -> None:
        get = AsyncMock(return_value=MagicMock(positions=[_position(), _position(symbol="MSFT")]))
        with patch(CLIENT, _client(get_positions=get)):
            result = await GetPositionsTool().execute({"portfolio_id": "p1"}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["count"] == 2
        first = result.data["positions"][0]
        assert first["symbol"] == "AAPL"
        assert first["quantity"] == "10"
        assert first["market_value"] == "1200"
        assert first["unrealized_pnl"] == "200"
        assert get.await_args.args[0].portfolio_id == "p1"

    async def test_a_flat_portfolio_is_an_empty_list(self, ctx: ToolContext) -> None:
        with patch(CLIENT, _client(get_positions=AsyncMock(return_value=MagicMock(positions=[])))):
            result = await GetPositionsTool().execute({"portfolio_id": "p1"}, ctx)

        assert result.success is True
        assert result.data == {"positions": [], "count": 0}

    async def test_an_outage_reports_no_holdings_rather_than_inventing_them(
        self, ctx: ToolContext
    ) -> None:
        with patch(CLIENT, _client(get_positions=AsyncMock(side_effect=RuntimeError("down")))):
            result = await GetPositionsTool().execute({"portfolio_id": "p1"}, ctx)

        assert result.data is not None
        assert result.data["positions"] == []
        assert "note" in result.data
