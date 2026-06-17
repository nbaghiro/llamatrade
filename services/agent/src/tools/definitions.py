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
