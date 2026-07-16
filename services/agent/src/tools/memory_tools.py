"""Memory-related tools for cross-session recall.

These tools enable the agent to access and utilize user memory:
- recall_memory: Semantic search across past conversations and facts
- get_user_profile: Get consolidated user preferences
- search_past_strategies: Find strategies user has created/discussed
"""

from __future__ import annotations

import logging
from typing import Any

from llamatrade_db import get_db, set_tenant_guc

from src.services.memory_service import MemoryService
from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class RecallMemoryTool(BaseTool):
    """Search and recall relevant information from past conversations."""

    @property
    def name(self) -> str:
        return "recall_memory"

    @property
    def description(self) -> str:
        return (
            "Search and recall relevant information from past conversations and "
            "learned user facts. Use when:\n"
            "- User references past discussions ('that strategy we discussed')\n"
            "- Personalizing recommendations based on history\n"
            "- User mentions preferences you should remember\n"
            "Returns relevant facts with category, content, confidence, and date."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query (e.g., 'user risk preferences', 'momentum strategies discussed')",
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "user_preference",
                            "risk_tolerance",
                            "investment_goal",
                            "asset_preference",
                            "strategy_decision",
                            "trading_behavior",
                            "feedback",
                        ],
                    },
                    "description": "Filter by specific fact categories",
                },
                "time_range_days": {
                    "type": "integer",
                    "description": "Limit to facts from recent N days",
                    "minimum": 1,
                    "maximum": 365,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the recall_memory tool."""
        query = arguments.get("query")
        if not query:
            return ToolResult(success=False, error="query is required")

        categories = arguments.get("categories")
        time_range_days = arguments.get("time_range_days")
        limit = arguments.get("limit", 10)

        try:
            async for db in get_db():
                await set_tenant_guc(db, context.tenant_id)
                memory_service = MemoryService(
                    db=db,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                )

                results = await memory_service.search(
                    query=query,
                    categories=categories,
                    time_range_days=time_range_days,
                    limit=limit,
                )

                if not results:
                    return ToolResult(
                        success=True,
                        data={
                            "facts": [],
                            "count": 0,
                            "message": "No relevant memories found for this query.",
                        },
                    )

                facts_data = [
                    {
                        "category": r.category,
                        "content": r.content,
                        "confidence": round(r.confidence, 2),
                        "date": r.created_at.strftime("%Y-%m-%d"),
                        "relevance_score": round(r.relevance_score, 2),
                    }
                    for r in results
                ]

                return ToolResult(
                    success=True,
                    data={
                        "facts": facts_data,
                        "count": len(facts_data),
                    },
                )

        except Exception as e:
            logger.exception("recall_memory failed: %s", e)
            return ToolResult(
                success=False,
                error=f"Failed to recall memories: {e}",
            )

        return ToolResult(
            success=True,
            data={"facts": [], "count": 0},
        )


class GetUserProfileTool(BaseTool):
    """Get consolidated user profile and preferences."""

    @property
    def name(self) -> str:
        return "get_user_profile"

    @property
    def description(self) -> str:
        return (
            "Get consolidated user profile and preferences. Use at START of strategy "
            "generation to personalize recommendations. Returns structured profile "
            "with risk tolerance, goals, asset preferences, and trading behavior."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_sections": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "risk_profile",
                            "goals",
                            "sector_preferences",
                            "trading_behavior",
                            "recent_decisions",
                        ],
                    },
                    "description": "Specific profile sections to include (default: all)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_user_profile tool."""
        include_sections = arguments.get("include_sections")

        try:
            async for db in get_db():
                await set_tenant_guc(db, context.tenant_id)
                memory_service = MemoryService(
                    db=db,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                )

                profile = await memory_service.get_user_profile(sections=include_sections)

                # Build response data based on profile
                profile_data: dict[str, Any] = {}

                if profile.risk_tolerance:
                    profile_data["risk_tolerance"] = profile.risk_tolerance

                if profile.investment_goals:
                    profile_data["investment_goals"] = profile.investment_goals

                if profile.asset_preferences or profile.asset_dislikes:
                    profile_data["asset_preferences"] = {
                        "likes": profile.asset_preferences,
                        "dislikes": profile.asset_dislikes,
                    }

                if profile.trading_behaviors:
                    profile_data["trading_behavior"] = profile.trading_behaviors

                if profile.recent_decisions:
                    profile_data["recent_decisions"] = profile.recent_decisions

                if profile.general_preferences:
                    profile_data["general_preferences"] = profile.general_preferences

                if not profile_data:
                    return ToolResult(
                        success=True,
                        data={
                            "profile": {},
                            "is_new_user": True,
                            "message": "No profile data available yet. This appears to be a new user.",
                        },
                    )

                return ToolResult(
                    success=True,
                    data={
                        "profile": profile_data,
                        "is_new_user": False,
                    },
                )

        except Exception as e:
            logger.exception("get_user_profile failed: %s", e)
            return ToolResult(
                success=False,
                error=f"Failed to get user profile: {e}",
            )

        return ToolResult(
            success=True,
            data={"profile": {}, "is_new_user": True},
        )


class SearchPastStrategiesTool(BaseTool):
    """Search strategies from user's history."""

    @property
    def name(self) -> str:
        return "search_past_strategies"

    @property
    def description(self) -> str:
        return (
            "Search strategies from user's history including created strategies "
            "and discussed strategy ideas. Use when user references a past strategy "
            "or when looking for examples of what they've built before."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text (matches name, description)",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by symbols (e.g., ['SPY', 'QQQ'])",
                },
                "strategy_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "momentum",
                            "defensive",
                            "income",
                            "buy-and-hold",
                            "tactical",
                        ],
                    },
                    "description": "Filter by strategy type",
                },
                "include_drafts": {
                    "type": "boolean",
                    "description": "Include draft strategies (default: true)",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the search_past_strategies tool."""
        query = arguments.get("query")
        symbols = arguments.get("symbols")
        strategy_types = arguments.get("strategy_types")
        include_drafts = arguments.get("include_drafts", True)

        try:
            async for db in get_db():
                await set_tenant_guc(db, context.tenant_id)
                memory_service = MemoryService(
                    db=db,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                )

                results = await memory_service.search_past_strategies(
                    query=query,
                    symbols=symbols,
                    strategy_types=strategy_types,
                    include_drafts=include_drafts,
                )

                if not results:
                    return ToolResult(
                        success=True,
                        data={
                            "strategies": [],
                            "count": 0,
                            "message": "No matching strategies found in history.",
                        },
                    )

                strategies_data = [
                    {
                        "strategy_id": str(r.strategy_id) if r.strategy_id else None,
                        "name": r.strategy_name,
                        "dsl_snippet": r.dsl_snippet,
                        "symbols": r.symbols,
                        "discussed_at": r.discussed_at.strftime("%Y-%m-%d"),
                        "context": r.context,
                        "performance": r.performance_summary,
                    }
                    for r in results
                ]

                return ToolResult(
                    success=True,
                    data={
                        "strategies": strategies_data,
                        "count": len(strategies_data),
                    },
                )

        except Exception as e:
            logger.exception("search_past_strategies failed: %s", e)
            return ToolResult(
                success=False,
                error=f"Failed to search past strategies: {e}",
            )

        return ToolResult(
            success=True,
            data={"strategies": [], "count": 0},
        )
