"""Tests for the get_portfolio_performance tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_proto.generated import common_pb2, portfolio_pb2

from src.tools.base import ToolContext
from src.tools.portfolio_tools import GetPortfolioPerformanceTool

pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


def _client_class(get_performance: AsyncMock) -> MagicMock:
    """A patchable PortfolioServiceClient class whose instance uses get_performance."""
    client = MagicMock()
    client.get_performance = get_performance
    return MagicMock(return_value=client)


def _metrics_response() -> MagicMock:
    metrics = portfolio_pb2.PerformanceMetrics(
        total_return=common_pb2.Decimal(value="12.5"),
        ytd_return=common_pb2.Decimal(value="8.0"),
        mtd_return=common_pb2.Decimal(value="1.2"),
        wtd_return=common_pb2.Decimal(value="0.3"),
        volatility=common_pb2.Decimal(value="0.18"),
        sharpe_ratio=common_pb2.Decimal(value="1.4"),
        max_drawdown=common_pb2.Decimal(value="-5.5"),
        beta=common_pb2.Decimal(value="0.95"),
        benchmark_return=common_pb2.Decimal(value="10.0"),
        alpha=common_pb2.Decimal(value="2.5"),
        total_positions=7,
    )
    return MagicMock(metrics=metrics)


async def test_returns_full_metrics(ctx: ToolContext) -> None:
    """A live portfolio surfaces every metric field, decoded from proto Decimals."""
    call = AsyncMock(return_value=_metrics_response())
    with patch(
        "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient",
        _client_class(call),
    ):
        result = await GetPortfolioPerformanceTool().execute({"period": "3m"}, ctx)

    assert result.success is True
    assert result.data is not None
    assert result.data["period"] == "3m"
    assert result.data["total_return"] == "12.5"
    assert result.data["sharpe_ratio"] == "1.4"
    assert result.data["max_drawdown"] == "-5.5"
    assert result.data["alpha"] == "2.5"
    assert result.data["total_positions"] == 7


async def test_sends_tenant_context_and_time_range(ctx: ToolContext) -> None:
    """The request carries the caller's identity and a positive start/end window."""
    call = AsyncMock(return_value=_metrics_response())
    with patch(
        "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient",
        _client_class(call),
    ):
        await GetPortfolioPerformanceTool().execute({"period": "1y"}, ctx)

    request = call.call_args.args[0]
    assert request.context.tenant_id == str(ctx.tenant_id)
    assert request.context.user_id == str(ctx.user_id)
    # ~365d window, both endpoints set so the servicer buckets it (not the default).
    assert request.time_range.start.seconds > 0
    assert request.time_range.end.seconds > request.time_range.start.seconds


async def test_defaults_period_to_1m(ctx: ToolContext) -> None:
    """No period argument falls back to 1m rather than erroring."""
    call = AsyncMock(return_value=_metrics_response())
    with patch(
        "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient",
        _client_class(call),
    ):
        result = await GetPortfolioPerformanceTool().execute({}, ctx)

    assert result.success is True
    assert result.data is not None
    assert result.data["period"] == "1m"


async def test_ytd_uses_year_start(ctx: ToolContext) -> None:
    """A ytd request anchors the window to Jan 1 of the current year."""
    from datetime import UTC, datetime

    call = AsyncMock(return_value=_metrics_response())
    with patch(
        "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient",
        _client_class(call),
    ):
        await GetPortfolioPerformanceTool().execute({"period": "ytd"}, ctx)

    request = call.call_args.args[0]
    year_start = int(datetime(datetime.now(UTC).year, 1, 1, tzinfo=UTC).timestamp())
    assert request.time_range.start.seconds == year_start


async def test_reports_failure_honestly(ctx: ToolContext) -> None:
    """A service error surfaces success=False with the reason, not a masked success."""
    call = AsyncMock(side_effect=RuntimeError("portfolio down"))
    with patch(
        "llamatrade_proto.generated.portfolio_connect.PortfolioServiceClient",
        _client_class(call),
    ):
        result = await GetPortfolioPerformanceTool().execute({"period": "1m"}, ctx)

    assert result.success is False
    assert result.error is not None
    assert "portfolio down" in result.error
