"""Base tool abstraction for agent tools.

All agent tools inherit from BaseTool and implement the execute method.
Tools are responsible for calling external services and returning results
in a format suitable for LLM consumption.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Context passed to tool execution."""

    tenant_id: UUID
    user_id: UUID
    session_id: UUID
    # Additional context can be added here
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from tool execution."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        result["duration_ms"] = self.duration_ms
        return result


class BaseTool(ABC):
    """Base class for all agent tools.

    Tools encapsulate interactions with external services and provide
    a consistent interface for the agent to use.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does (for LLM context)."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            arguments: Tool arguments matching parameters_schema
            context: Execution context with tenant/user info

        Returns:
            ToolResult with success status and data or error
        """
        ...

    async def run(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Run the tool with timing and error handling.

        This is the main entry point that wraps execute with
        logging, timing, and exception handling.
        """
        start_time = time.perf_counter()
        try:
            result = await self.execute(arguments, context)
            result.duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "Tool %s executed successfully in %dms",
                self.name,
                result.duration_ms,
            )
            return result
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Tool %s failed: %s", self.name, e)
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {type(e).__name__}: {e}",
                duration_ms=duration_ms,
            )

    def to_claude_tool_definition(self) -> dict[str, Any]:
        """Convert to Claude tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }
