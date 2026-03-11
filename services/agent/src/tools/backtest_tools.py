"""Backtest-related tools for the agent.

These tools interact with the Backtest service to retrieve and analyze
historical performance data for strategies.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class GetBacktestResultsTool(BaseTool):
    """Get backtest results for a strategy."""

    @property
    def name(self) -> str:
        return "get_backtest_results"

    @property
    def description(self) -> str:
        return (
            "Get backtest results for a strategy including performance metrics, "
            "equity curve summary, and trade statistics. Use this to inform "
            "optimization suggestions or explain strategy performance."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of the strategy",
                },
                "backtest_id": {
                    "type": "string",
                    "description": "UUID of specific backtest (optional, defaults to latest)",
                },
            },
            "required": ["strategy_id"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_backtest_results tool."""
        strategy_id = arguments.get("strategy_id")
        backtest_id = arguments.get("backtest_id")

        if not strategy_id:
            return ToolResult(success=False, error="strategy_id is required")

        try:
            from llamatrade_proto.generated import backtest_pb2, common_pb2
            from llamatrade_proto.generated.backtest_connect import BacktestServiceClient

            from src.tools.clients import BACKTEST_SERVICE_URL, tenant_headers

            client = BacktestServiceClient(BACKTEST_SERVICE_URL)

            # If we have a specific backtest_id, get it directly
            if backtest_id:
                request = backtest_pb2.GetBacktestRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(context.tenant_id),
                        user_id=str(context.user_id),
                    ),
                    backtest_id=backtest_id,
                )

                response = await client.get_backtest(
                    request,
                    headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
                )
                backtest = response.backtest
            else:
                # List backtests for the strategy and get the most recent
                list_request = backtest_pb2.ListBacktestsRequest(
                    context=common_pb2.TenantContext(
                        tenant_id=str(context.tenant_id),
                        user_id=str(context.user_id),
                    ),
                    strategy_id=strategy_id,
                    pagination=common_pb2.PaginationRequest(
                        page=1,
                        page_size=1,
                    ),
                )

                list_response = await client.list_backtests(
                    list_request,
                    headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
                )

                if not list_response.backtests:
                    return ToolResult(
                        success=True,
                        data={
                            "note": "No backtests found for this strategy.",
                            "strategy_id": strategy_id,
                        },
                    )

                backtest = list_response.backtests[0]

            # Extract results from backtest
            results = backtest.results
            metrics = results.metrics if results else None

            data: dict[str, Any] = {
                "backtest_id": backtest.id,
                "strategy_id": backtest.strategy_id,
                "status": _backtest_status_to_string(backtest.status),
            }

            if backtest.config:
                data["initial_capital"] = str(backtest.config.initial_capital)

            if results:
                data["final_equity"] = str(metrics.ending_capital) if metrics else None
                data["benchmark_symbol"] = results.benchmark_symbol

            if metrics:
                data["metrics"] = {
                    "total_return": str(metrics.total_return),
                    "annualized_return": str(metrics.annualized_return),
                    "sharpe_ratio": str(metrics.sharpe_ratio),
                    "sortino_ratio": str(metrics.sortino_ratio),
                    "max_drawdown": str(metrics.max_drawdown),
                    "volatility": str(metrics.volatility),
                    "total_trades": metrics.total_trades,
                    "winning_trades": metrics.winning_trades,
                    "losing_trades": metrics.losing_trades,
                    "win_rate": str(metrics.win_rate),
                    "profit_factor": str(metrics.profit_factor),
                    "benchmark_return": str(metrics.benchmark_return),
                    "alpha": str(metrics.alpha),
                    "beta": str(metrics.beta),
                }

            return ToolResult(success=True, data=data)
        except Exception as e:
            logger.warning("Backtest service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "note": "Backtest service is currently unavailable.",
                    "strategy_id": strategy_id,
                },
            )


class ListBacktestsTool(BaseTool):
    """List backtests for a strategy."""

    @property
    def name(self) -> str:
        return "list_backtests"

    @property
    def description(self) -> str:
        return (
            "List all backtests for a strategy. Use this to see the history "
            "of backtest runs and compare different configurations."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of the strategy",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum backtests to return (default: 10)",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["strategy_id"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the list_backtests tool."""
        strategy_id = arguments.get("strategy_id")
        limit = arguments.get("limit", 10)

        if not strategy_id:
            return ToolResult(success=False, error="strategy_id is required")

        try:
            from llamatrade_proto.generated import backtest_pb2, common_pb2
            from llamatrade_proto.generated.backtest_connect import BacktestServiceClient

            from src.tools.clients import BACKTEST_SERVICE_URL, tenant_headers

            client = BacktestServiceClient(BACKTEST_SERVICE_URL)

            request = backtest_pb2.ListBacktestsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                strategy_id=strategy_id,
                pagination=common_pb2.PaginationRequest(
                    page=1,
                    page_size=limit,
                ),
            )

            response = await client.list_backtests(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            backtests = []
            for bt in response.backtests:
                bt_data: dict[str, Any] = {
                    "id": bt.id,
                    "status": _backtest_status_to_string(bt.status),
                }

                if bt.config:
                    bt_data["initial_capital"] = str(bt.config.initial_capital)

                if bt.results and bt.results.metrics:
                    metrics = bt.results.metrics
                    bt_data["total_return"] = str(metrics.total_return)
                    bt_data["sharpe_ratio"] = str(metrics.sharpe_ratio)
                    bt_data["max_drawdown"] = str(metrics.max_drawdown)

                if bt.created_at:
                    bt_data["created_at"] = bt.created_at.seconds

                backtests.append(bt_data)

            return ToolResult(
                success=True,
                data={
                    "backtests": backtests,
                    "count": len(backtests),
                },
            )
        except Exception as e:
            logger.warning("Backtest service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "note": "Backtest service is currently unavailable.",
                    "backtests": [],
                    "count": 0,
                },
            )


class RunBacktestTool(BaseTool):
    """Run a backtest on a strategy."""

    @property
    def name(self) -> str:
        return "run_backtest"

    @property
    def description(self) -> str:
        return (
            "Run a backtest on a strategy. Use this when the user wants to "
            "see historical performance of a strategy or pending strategy."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of existing strategy to backtest",
                },
                "dsl_code": {
                    "type": "string",
                    "description": "DSL code to backtest (for pending/new strategies)",
                },
                "start_date": {
                    "type": "string",
                    "description": "Backtest start date (YYYY-MM-DD)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Backtest end date (YYYY-MM-DD)",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Starting capital (default: 100000)",
                    "minimum": 1000,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the run_backtest tool."""
        strategy_id = arguments.get("strategy_id")
        dsl_code = arguments.get("dsl_code")

        if not strategy_id and not dsl_code:
            return ToolResult(
                success=False,
                error="Either strategy_id or dsl_code is required",
            )

        try:
            from llamatrade_proto.generated import backtest_pb2, common_pb2
            from llamatrade_proto.generated.backtest_connect import BacktestServiceClient

            from src.tools.clients import BACKTEST_SERVICE_URL, tenant_headers

            client = BacktestServiceClient(BACKTEST_SERVICE_URL)

            # Build backtest config
            config = backtest_pb2.BacktestConfig(
                strategy_id=strategy_id or "",
            )

            # Note: For DSL code backtesting, the service would need to handle
            # the dsl_code separately. This may require a different endpoint
            # or field on the config. For now, we only support strategy_id.

            request = backtest_pb2.RunBacktestRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                config=config,
            )

            response = await client.run_backtest(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            return ToolResult(
                success=True,
                data={
                    "backtest_id": response.backtest.id,
                    "status": "submitted",
                    "message": "Backtest submitted successfully. Results will be available shortly.",
                },
            )
        except Exception as e:
            logger.warning("Backtest service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "note": "Backtest service is currently unavailable. Unable to run backtest.",
                },
            )


def _backtest_status_to_string(status: int) -> str:
    """Convert backtest status enum to string."""
    from llamatrade_proto.generated import backtest_pb2

    status_map: dict[int, str] = {
        int(backtest_pb2.BACKTEST_STATUS_UNSPECIFIED): "unknown",
        int(backtest_pb2.BACKTEST_STATUS_PENDING): "pending",
        int(backtest_pb2.BACKTEST_STATUS_RUNNING): "running",
        int(backtest_pb2.BACKTEST_STATUS_COMPLETED): "completed",
        int(backtest_pb2.BACKTEST_STATUS_FAILED): "failed",
        int(backtest_pb2.BACKTEST_STATUS_CANCELLED): "cancelled",
    }
    return status_map.get(status, "unknown")
