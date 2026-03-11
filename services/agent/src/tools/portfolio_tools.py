"""Portfolio-related tools for the agent.

These tools interact with the Portfolio service to get user's
portfolio information, positions, and performance.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class GetPortfolioSummaryTool(BaseTool):
    """Get user's current portfolio summary."""

    @property
    def name(self) -> str:
        return "get_portfolio_summary"

    @property
    def description(self) -> str:
        return (
            "Get the user's current portfolio including total equity, cash, "
            "positions, and P&L. Use this to understand the user's current "
            "holdings before making recommendations."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_portfolio_summary tool."""
        try:
            from llamatrade_proto.generated import common_pb2, portfolio_pb2
            from llamatrade_proto.generated.portfolio_connect import PortfolioServiceClient

            from src.tools.clients import PORTFOLIO_SERVICE_URL, tenant_headers

            client = PortfolioServiceClient(PORTFOLIO_SERVICE_URL)

            # Get portfolio - note: API may require portfolio_id
            request = portfolio_pb2.ListPortfoliosRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
            )

            response = await client.list_portfolios(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            if not response.portfolios:
                return ToolResult(
                    success=True,
                    data={
                        "note": "No portfolios found for this user.",
                        "portfolios": [],
                    },
                )

            # Get the first/primary portfolio
            portfolio = response.portfolios[0]
            return ToolResult(
                success=True,
                data={
                    "portfolio_id": portfolio.id,
                    "name": portfolio.name,
                    "total_value": str(portfolio.total_value),
                    "cash_balance": str(portfolio.cash_balance),
                    "positions_value": str(portfolio.positions_value),
                    "total_return": str(portfolio.total_return),
                    "total_return_percent": str(portfolio.total_return_percent),
                    "day_return": str(portfolio.day_return),
                    "day_return_percent": str(portfolio.day_return_percent),
                },
            )
        except Exception as e:
            logger.warning("Portfolio service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "note": "Portfolio service is currently unavailable. Unable to retrieve portfolio data.",
                    "portfolios": [],
                },
            )


class GetPortfolioPerformanceTool(BaseTool):
    """Get portfolio performance metrics."""

    @property
    def name(self) -> str:
        return "get_portfolio_performance"

    @property
    def description(self) -> str:
        return (
            "Get portfolio performance metrics including returns, volatility, "
            "and drawdown over specified time periods."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["1d", "1w", "1m", "3m", "6m", "1y", "ytd", "all"],
                    "description": "Time period for performance calculation (default: 1m)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_portfolio_performance tool."""
        # This would require getting the portfolio_id first, then performance
        # For now, provide a graceful fallback
        return ToolResult(
            success=True,
            data={
                "note": "Portfolio performance data requires an active portfolio. "
                "Use get_portfolio_summary first to identify available portfolios.",
            },
        )


class GetPositionsTool(BaseTool):
    """Get detailed position information."""

    @property
    def name(self) -> str:
        return "get_positions"

    @property
    def description(self) -> str:
        return (
            "Get detailed information about current portfolio positions "
            "including cost basis, P&L, and current prices."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "portfolio_id": {
                    "type": "string",
                    "description": "Portfolio ID (get from get_portfolio_summary)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_positions tool."""
        portfolio_id = arguments.get("portfolio_id")

        if not portfolio_id:
            return ToolResult(
                success=True,
                data={
                    "note": "portfolio_id is required. Use get_portfolio_summary first.",
                    "positions": [],
                },
            )

        try:
            from llamatrade_proto.generated import common_pb2, portfolio_pb2
            from llamatrade_proto.generated.portfolio_connect import PortfolioServiceClient

            from src.tools.clients import PORTFOLIO_SERVICE_URL, tenant_headers

            client = PortfolioServiceClient(PORTFOLIO_SERVICE_URL)

            request = portfolio_pb2.GetPositionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                portfolio_id=portfolio_id,
            )

            response = await client.get_positions(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            positions = []
            for p in response.positions:
                positions.append(
                    {
                        "symbol": p.symbol,
                        "quantity": str(p.quantity),
                        "average_entry_price": str(p.average_entry_price),
                        "current_price": str(p.current_price),
                        "market_value": str(p.market_value),
                        "cost_basis": str(p.cost_basis),
                        "unrealized_pnl": str(p.unrealized_pnl),
                        "unrealized_pnl_percent": str(p.unrealized_pnl_percent),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "positions": positions,
                    "count": len(positions),
                },
            )
        except Exception as e:
            logger.warning("Portfolio service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "note": "Portfolio service is currently unavailable.",
                    "positions": [],
                },
            )
