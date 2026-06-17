"""Context-aware prompt generation.

This module provides utilities for generating contextual prompts and
suggestions based on the current UI state and user data.
"""

from typing import Any


def get_suggested_actions(page: str, context: dict[str, Any]) -> list[str]:
    """Get suggested actions based on current page and context.

    Args:
        page: Current UI page identifier
        context: Additional context data (strategy_id, backtest_id, etc.)

    Returns:
        List of suggested prompt strings
    """
    suggestions: dict[str, list[str]] = {
        "strategy_detail": [
            "Analyze this strategy's logic",
            "Suggest improvements based on backtest results",
            "Add conditional logic for risk management",
            "Compare to similar templates",
        ],
        "backtest_results": [
            "Explain why drawdown occurred during specific periods",
            "Suggest parameter optimizations",
            "Compare performance to benchmark",
            "Identify which conditions triggered most trades",
        ],
        "portfolio": [
            "Create a strategy to replicate current holdings",
            "Suggest rebalancing based on current allocation",
            "Recommend strategies for underweight sectors",
            "Analyze portfolio risk exposure",
        ],
        "strategy_list": [
            "Compare performance across strategies",
            "Suggest a new strategy based on best performers",
            "Identify strategies that need attention",
            "Create a new strategy",
        ],
        "dashboard": [
            "Summarize portfolio and strategy performance",
            "Identify opportunities for improvement",
            "Create a new strategy based on goals",
            "Show me my best performing strategy",
        ],
    }

    # Default suggestions if page not found
    default_suggestions = [
        "Create a 60/40 portfolio",
        "Build a momentum strategy",
        "Show me my portfolio",
        "Explain how indicators work",
    ]

    return suggestions.get(page, default_suggestions)
