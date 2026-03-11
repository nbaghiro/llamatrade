"""Tool executor for orchestrating tool calls.

The executor manages tool registration, execution, and result formatting.
It provides the interface between the LLM and the underlying tools.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Orchestrates tool execution for the agent.

    Manages a registry of available tools and handles tool calls
    from the LLM, returning formatted results.
    """

    def __init__(self) -> None:
        """Initialize the executor with default tools."""
        self._tools: dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # Strategy tools
        from src.tools.strategy_tools import (
            GetStrategyTool,
            ListStrategiesTool,
            ListTemplatesTool,
        )

        self.register(ListStrategiesTool())
        self.register(GetStrategyTool())
        self.register(ListTemplatesTool())

        # Portfolio tools
        from src.tools.portfolio_tools import (
            GetPortfolioPerformanceTool,
            GetPortfolioSummaryTool,
            GetPositionsTool,
        )

        self.register(GetPortfolioSummaryTool())
        self.register(GetPortfolioPerformanceTool())
        self.register(GetPositionsTool())

        # Validation tools
        from src.tools.validation_tools import GetAssetInfoTool, ValidateDSLTool

        self.register(ValidateDSLTool())
        self.register(GetAssetInfoTool())

        # Backtest tools
        from src.tools.backtest_tools import (
            GetBacktestResultsTool,
            ListBacktestsTool,
            RunBacktestTool,
        )

        self.register(GetBacktestResultsTool())
        self.register(ListBacktestsTool())
        self.register(RunBacktestTool())

        # Memory tools
        from src.tools.memory_tools import (
            GetSessionSummaryTool,
            GetUserProfileTool,
            RecallMemoryTool,
            SearchPastStrategiesTool,
        )

        self.register(RecallMemoryTool())
        self.register(GetUserProfileTool())
        self.register(SearchPastStrategiesTool())
        self.register(GetSessionSummaryTool())

        logger.info("Registered %d tools", len(self._tools))

    def register(self, tool: BaseTool) -> None:
        """Register a tool with the executor.

        Args:
            tool: Tool instance to register
        """
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool: %s", tool.name)
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions for Claude API.

        Returns:
            List of tool definitions in Claude's expected format
        """
        return [tool.to_claude_tool_definition() for tool in self._tools.values()]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
    ) -> ToolResult:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            tenant_id: Tenant UUID for multi-tenancy
            user_id: User UUID
            session_id: Session UUID for context

        Returns:
            ToolResult with execution outcome
        """
        tool = self._tools.get(tool_name)
        if not tool:
            logger.warning("Unknown tool requested: %s", tool_name)
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        context = ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

        logger.info(
            "Executing tool %s for tenant %s, session %s",
            tool_name,
            tenant_id,
            session_id,
        )

        result = await tool.run(arguments, context)

        if result.success:
            logger.debug("Tool %s completed successfully", tool_name)
        else:
            logger.warning("Tool %s failed: %s", tool_name, result.error)

        return result

    def format_tool_result_for_llm(self, result: ToolResult) -> str:
        """Format a tool result for LLM consumption.

        Args:
            result: Tool execution result

        Returns:
            Formatted string suitable for including in LLM context
        """
        import json

        if result.success and result.data is not None:
            return json.dumps(result.data, indent=2, default=str)
        elif result.error:
            return f"Error: {result.error}"
        else:
            return "Tool executed but returned no data"


# Global executor instance
_executor: ToolExecutor | None = None


def get_executor() -> ToolExecutor:
    """Get or create the global tool executor."""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor
