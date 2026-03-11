"""Strategy-related tools for the agent.

These tools interact with the Strategy service to list, get, and manage
strategies and templates.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ListStrategiesTool(BaseTool):
    """List user's existing strategies."""

    @property
    def name(self) -> str:
        return "list_strategies"

    @property
    def description(self) -> str:
        return (
            "List the user's existing strategies with status, symbols, and performance summary. "
            "Use this to understand what strategies the user already has before making recommendations."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "active", "paused", "draft", "archived"],
                    "description": "Filter strategies by status (default: all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum strategies to return (default: 20)",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the list_strategies tool."""
        try:
            from llamatrade_proto.generated import common_pb2, strategy_pb2
            from llamatrade_proto.generated.strategy_connect import StrategyServiceClient

            from src.tools.clients import STRATEGY_SERVICE_URL, tenant_headers

            client = StrategyServiceClient(STRATEGY_SERVICE_URL)

            # Build status filter
            status_filter = arguments.get("status_filter", "all")
            limit = arguments.get("limit", 20)

            statuses = []
            if status_filter == "active":
                statuses = [strategy_pb2.STRATEGY_STATUS_ACTIVE]
            elif status_filter == "paused":
                statuses = [strategy_pb2.STRATEGY_STATUS_PAUSED]
            elif status_filter == "draft":
                statuses = [strategy_pb2.STRATEGY_STATUS_DRAFT]
            elif status_filter == "archived":
                statuses = [strategy_pb2.STRATEGY_STATUS_ARCHIVED]

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                statuses=statuses,
                pagination=common_pb2.PaginationRequest(
                    page=1,
                    page_size=limit,
                ),
            )

            response = await client.list_strategies(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            strategies = []
            for s in response.strategies:
                strategies.append(
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description or "",
                        "status": _status_to_string(s.status),
                        "symbols": list(s.symbols),
                        "dsl_code": s.dsl_code[:200] + "..."
                        if len(s.dsl_code) > 200
                        else s.dsl_code,
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "strategies": strategies,
                    "total_count": response.pagination.total_items,
                },
            )
        except Exception as e:
            logger.warning("Strategy service unavailable: %s", e)
            return ToolResult(
                success=True,
                data={
                    "strategies": [],
                    "total_count": 0,
                    "note": "Strategy service is currently unavailable. Please try again later.",
                },
            )


class GetStrategyTool(BaseTool):
    """Get full details of a specific strategy."""

    @property
    def name(self) -> str:
        return "get_strategy"

    @property
    def description(self) -> str:
        return (
            "Get full details of a specific strategy including the DSL code, "
            "performance metrics, and execution history. Use this to understand "
            "a strategy's logic before suggesting modifications."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of the strategy to retrieve",
                },
            },
            "required": ["strategy_id"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_strategy tool."""
        strategy_id = arguments.get("strategy_id")
        if not strategy_id:
            return ToolResult(success=False, error="strategy_id is required")

        try:
            from llamatrade_proto.generated import common_pb2, strategy_pb2
            from llamatrade_proto.generated.strategy_connect import StrategyServiceClient

            from src.tools.clients import STRATEGY_SERVICE_URL, tenant_headers

            client = StrategyServiceClient(STRATEGY_SERVICE_URL)

            request = strategy_pb2.GetStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                strategy_id=strategy_id,
            )

            response = await client.get_strategy(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            s = response.strategy
            return ToolResult(
                success=True,
                data={
                    "id": s.id,
                    "name": s.name,
                    "description": s.description or "",
                    "status": _status_to_string(s.status),
                    "symbols": list(s.symbols),
                    "dsl_code": s.dsl_code,
                    "version": s.version,
                },
            )
        except Exception as e:
            logger.warning("Strategy service unavailable: %s", e)
            return ToolResult(
                success=False,
                error=f"Could not retrieve strategy: {e}",
            )


class ListTemplatesTool(BaseTool):
    """Get pre-built strategy templates."""

    @property
    def name(self) -> str:
        return "list_templates"

    @property
    def description(self) -> str:
        return (
            "Get pre-built strategy templates. Use this to find examples or "
            "starting points for user requests. Templates provide well-tested "
            "strategy patterns that can be customized."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "buy-and-hold",
                        "tactical",
                        "factor",
                        "income",
                        "trend",
                        "mean-reversion",
                        "alternatives",
                    ],
                    "description": "Filter templates by category",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                    "description": "Filter by difficulty level",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the list_templates tool."""
        try:
            from llamatrade_proto.generated import strategy_pb2
            from llamatrade_proto.generated.strategy_connect import StrategyServiceClient

            from src.tools.clients import STRATEGY_SERVICE_URL, tenant_headers

            client = StrategyServiceClient(STRATEGY_SERVICE_URL)

            # Map category string to enum
            category = arguments.get("category")
            category_enum = strategy_pb2.TEMPLATE_CATEGORY_UNSPECIFIED
            if category == "buy-and-hold":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_BUY_AND_HOLD
            elif category == "tactical":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_TACTICAL
            elif category == "factor":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_FACTOR
            elif category == "income":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_INCOME
            elif category == "trend":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_TREND
            elif category == "mean-reversion":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_MEAN_REVERSION
            elif category == "alternatives":
                category_enum = strategy_pb2.TEMPLATE_CATEGORY_ALTERNATIVES

            # Map difficulty string to enum
            difficulty = arguments.get("difficulty")
            difficulty_enum = strategy_pb2.TEMPLATE_DIFFICULTY_UNSPECIFIED
            if difficulty == "beginner":
                difficulty_enum = strategy_pb2.TEMPLATE_DIFFICULTY_BEGINNER
            elif difficulty == "intermediate":
                difficulty_enum = strategy_pb2.TEMPLATE_DIFFICULTY_INTERMEDIATE
            elif difficulty == "advanced":
                difficulty_enum = strategy_pb2.TEMPLATE_DIFFICULTY_ADVANCED

            request = strategy_pb2.ListTemplatesRequest(
                category=category_enum,
                difficulty=difficulty_enum,
            )

            response = await client.list_templates(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            templates = []
            for t in response.templates:
                templates.append(
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description or "",
                        "category": _category_to_string(t.category),
                        "difficulty": _difficulty_to_string(t.difficulty),
                        "config_sexpr": t.config_sexpr,
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "templates": templates,
                    "count": len(templates),
                },
            )
        except Exception as e:
            logger.warning("Strategy service unavailable: %s", e)
            # Return built-in templates as fallback
            return ToolResult(
                success=True,
                data={
                    "templates": _get_builtin_templates(),
                    "count": len(_get_builtin_templates()),
                    "note": "Showing built-in templates (service unavailable)",
                },
            )


def _status_to_string(status: int) -> str:
    """Convert strategy status enum to string."""
    from llamatrade_proto.generated import strategy_pb2

    status_map: dict[int, str] = {
        int(strategy_pb2.STRATEGY_STATUS_UNSPECIFIED): "unknown",
        int(strategy_pb2.STRATEGY_STATUS_DRAFT): "draft",
        int(strategy_pb2.STRATEGY_STATUS_ACTIVE): "active",
        int(strategy_pb2.STRATEGY_STATUS_PAUSED): "paused",
        int(strategy_pb2.STRATEGY_STATUS_ARCHIVED): "archived",
    }
    return status_map.get(status, "unknown")


def _category_to_string(category: int) -> str:
    """Convert template category enum to string."""
    from llamatrade_proto.generated import strategy_pb2

    category_map: dict[int, str] = {
        int(strategy_pb2.TEMPLATE_CATEGORY_UNSPECIFIED): "other",
        int(strategy_pb2.TEMPLATE_CATEGORY_BUY_AND_HOLD): "buy-and-hold",
        int(strategy_pb2.TEMPLATE_CATEGORY_TACTICAL): "tactical",
        int(strategy_pb2.TEMPLATE_CATEGORY_FACTOR): "factor",
        int(strategy_pb2.TEMPLATE_CATEGORY_INCOME): "income",
        int(strategy_pb2.TEMPLATE_CATEGORY_TREND): "trend",
        int(strategy_pb2.TEMPLATE_CATEGORY_MEAN_REVERSION): "mean-reversion",
        int(strategy_pb2.TEMPLATE_CATEGORY_ALTERNATIVES): "alternatives",
    }
    return category_map.get(category, "other")


def _difficulty_to_string(difficulty: int) -> str:
    """Convert template difficulty enum to string."""
    from llamatrade_proto.generated import strategy_pb2

    difficulty_map: dict[int, str] = {
        int(strategy_pb2.TEMPLATE_DIFFICULTY_UNSPECIFIED): "beginner",
        int(strategy_pb2.TEMPLATE_DIFFICULTY_BEGINNER): "beginner",
        int(strategy_pb2.TEMPLATE_DIFFICULTY_INTERMEDIATE): "intermediate",
        int(strategy_pb2.TEMPLATE_DIFFICULTY_ADVANCED): "advanced",
    }
    return difficulty_map.get(difficulty, "beginner")


def _get_builtin_templates() -> list[dict[str, Any]]:
    """Get built-in strategy templates as fallback."""
    return [
        {
            "id": "builtin-60-40",
            "name": "Classic 60/40",
            "description": "Traditional 60% stocks, 40% bonds allocation",
            "category": "buy-and-hold",
            "difficulty": "beginner",
            "config_sexpr": """(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 60
      (weight :method equal
        (asset VTI)
        (asset VEA)))
    (group "Bonds" :weight 40
      (weight :method equal
        (asset BND)
        (asset BNDX)))))""",
        },
        {
            "id": "builtin-three-fund",
            "name": "Three Fund Portfolio",
            "description": "Simple three-fund diversified portfolio",
            "category": "buy-and-hold",
            "difficulty": "beginner",
            "config_sexpr": """(strategy "Three Fund Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 50)
    (asset VXUS :weight 30)
    (asset BND :weight 20)))""",
        },
        {
            "id": "builtin-momentum",
            "name": "Simple Momentum",
            "description": "Momentum-based allocation favoring recent performers",
            "category": "factor",
            "difficulty": "intermediate",
            "config_sexpr": """(strategy "Simple Momentum"
  :rebalance monthly
  :benchmark SPY
  (weight :method momentum :lookback 90 :top 3
    (asset SPY)
    (asset QQQ)
    (asset IWM)
    (asset EFA)
    (asset EEM)))""",
        },
    ]
