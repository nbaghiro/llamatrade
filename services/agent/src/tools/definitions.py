"""Tool definitions for Claude API.

This module provides tool definitions in the format expected by Claude's
tool use API. These definitions are used to inform the model about
available tools and their parameters.
"""

from __future__ import annotations

from typing import Any

from src.tools.executor import get_executor


def get_tool_definitions() -> list[dict[str, Any]]:
    """Get all tool definitions for Claude API.

    Returns:
        List of tool definitions in Claude's expected format:
        [
            {
                "name": "tool_name",
                "description": "Tool description",
                "input_schema": { ... JSON Schema ... }
            },
            ...
        ]
    """
    executor = get_executor()
    return executor.get_tool_definitions()


# Static tool definitions for reference and testing
# These should match the tools registered in executor.py

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_portfolio_summary",
        "description": (
            "Get the user's current portfolio including total equity, cash, "
            "positions, and P&L. Use this to understand the user's current "
            "holdings before making recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_portfolio_performance",
        "description": (
            "Get portfolio performance metrics including returns, volatility, "
            "and drawdown over specified time periods."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["1d", "1w", "1m", "3m", "6m", "1y", "ytd", "all"],
                    "description": "Time period for performance calculation (default: 1m)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_positions",
        "description": (
            "Get detailed information about current portfolio positions "
            "including cost basis, P&L, and allocation weights."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter to specific symbols (optional)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_strategies",
        "description": (
            "List the user's existing strategies with status, symbols, and performance summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "active", "paused", "draft", "archived"],
                    "description": "Filter strategies by status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum strategies to return (default: 20)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_strategy",
        "description": (
            "Get full details of a specific strategy including the DSL code, "
            "performance metrics, and execution history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of the strategy to retrieve",
                },
            },
            "required": ["strategy_id"],
        },
    },
    {
        "name": "list_templates",
        "description": (
            "Get pre-built strategy templates. Use this to find examples or "
            "starting points for user requests."
        ),
        "input_schema": {
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
                    "description": "Filter by category",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                    "description": "Filter by difficulty",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_asset_info",
        "description": (
            "Get fundamental information about assets. Use this to validate "
            "symbols exist and get context about assets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols (max 20)",
                },
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "validate_dsl",
        "description": (
            "Parse and validate DSL code. ALWAYS use this before presenting "
            "a strategy to the user to ensure it's valid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dsl_code": {
                    "type": "string",
                    "description": "The S-expression DSL code to validate",
                },
            },
            "required": ["dsl_code"],
        },
    },
    {
        "name": "get_backtest_results",
        "description": (
            "Get backtest results for a strategy. Use this to inform optimization suggestions."
        ),
        "input_schema": {
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
        },
    },
    {
        "name": "list_backtests",
        "description": (
            "List all backtests for a strategy. Use this to see the history of backtest runs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of the strategy",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum backtests to return (default: 10)",
                },
            },
            "required": ["strategy_id"],
        },
    },
    {
        "name": "run_backtest",
        "description": (
            "Run a backtest on a strategy. Use this when user wants to see historical performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy_id": {
                    "type": "string",
                    "description": "UUID of existing strategy, OR",
                },
                "dsl_code": {
                    "type": "string",
                    "description": "DSL code to backtest (for pending strategies)",
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
                },
            },
            "required": [],
        },
    },
]
