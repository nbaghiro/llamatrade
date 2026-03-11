"""Tests for the tool framework."""

from uuid import uuid4

import pytest

from src.tools.base import BaseTool, ToolContext, ToolResult
from src.tools.executor import ToolExecutor


class MockTool(BaseTool):
    """Mock tool for testing."""

    @property
    def name(self) -> str:
        return "mock_tool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Test input",
                },
            },
            "required": ["input"],
        }

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        if arguments.get("input") == "error":
            return ToolResult(success=False, error="Mock error")
        return ToolResult(
            success=True,
            data={"echo": arguments.get("input"), "tenant": str(context.tenant_id)},
        )


class FailingTool(BaseTool):
    """Tool that raises exceptions."""

    @property
    def name(self) -> str:
        return "failing_tool"

    @property
    def description(self) -> str:
        return "A tool that always fails"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        raise ValueError("Intentional failure")


@pytest.fixture
def tool_context() -> ToolContext:
    """Create a test tool context."""
    return ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        session_id=uuid4(),
    )


@pytest.fixture
def mock_tool() -> MockTool:
    """Create a mock tool."""
    return MockTool()


@pytest.fixture
def executor() -> ToolExecutor:
    """Create a tool executor with mock tools."""
    executor = ToolExecutor()
    executor.register(MockTool())
    executor.register(FailingTool())
    return executor


class TestToolResult:
    """Tests for ToolResult."""

    def test_success_result(self) -> None:
        """Test creating a successful result."""
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self) -> None:
        """Test creating an error result."""
        result = ToolResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.data is None
        assert result.error == "Something went wrong"

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = ToolResult(success=True, data={"test": 123}, duration_ms=50)
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == {"test": 123}
        assert d["duration_ms"] == 50
        assert "error" not in d


class TestBaseTool:
    """Tests for BaseTool base class."""

    async def test_tool_execute_success(
        self, mock_tool: MockTool, tool_context: ToolContext
    ) -> None:
        """Test successful tool execution."""
        result = await mock_tool.execute({"input": "hello"}, tool_context)
        assert result.success is True
        assert result.data["echo"] == "hello"
        assert result.data["tenant"] == str(tool_context.tenant_id)

    async def test_tool_execute_error(self, mock_tool: MockTool, tool_context: ToolContext) -> None:
        """Test tool returning error."""
        result = await mock_tool.execute({"input": "error"}, tool_context)
        assert result.success is False
        assert result.error == "Mock error"

    async def test_tool_run_with_timing(
        self, mock_tool: MockTool, tool_context: ToolContext
    ) -> None:
        """Test that run() includes timing."""
        result = await mock_tool.run({"input": "test"}, tool_context)
        assert result.success is True
        assert result.duration_ms >= 0

    async def test_tool_run_catches_exceptions(self, tool_context: ToolContext) -> None:
        """Test that run() catches and wraps exceptions."""
        tool = FailingTool()
        result = await tool.run({}, tool_context)
        assert result.success is False
        assert "Intentional failure" in result.error

    def test_to_claude_tool_definition(self, mock_tool: MockTool) -> None:
        """Test converting tool to Claude API format."""
        definition = mock_tool.to_claude_tool_definition()
        assert definition["name"] == "mock_tool"
        assert definition["description"] == "A mock tool for testing"
        assert definition["input_schema"]["type"] == "object"
        assert "input" in definition["input_schema"]["properties"]


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def test_register_tool(self, executor: ToolExecutor) -> None:
        """Test registering a tool."""
        assert "mock_tool" in executor.list_tools()
        assert "failing_tool" in executor.list_tools()

    def test_get_tool(self, executor: ToolExecutor) -> None:
        """Test getting a registered tool."""
        tool = executor.get_tool("mock_tool")
        assert tool is not None
        assert tool.name == "mock_tool"

    def test_get_unknown_tool(self, executor: ToolExecutor) -> None:
        """Test getting an unregistered tool."""
        tool = executor.get_tool("nonexistent")
        assert tool is None

    async def test_execute_tool(self, executor: ToolExecutor) -> None:
        """Test executing a tool through the executor."""
        tenant_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()

        result = await executor.execute(
            tool_name="mock_tool",
            arguments={"input": "test_value"},
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

        assert result.success is True
        assert result.data["echo"] == "test_value"

    async def test_execute_unknown_tool(self, executor: ToolExecutor) -> None:
        """Test executing an unknown tool."""
        result = await executor.execute(
            tool_name="nonexistent",
            arguments={},
            tenant_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
        )

        assert result.success is False
        assert "Unknown tool" in result.error

    def test_get_tool_definitions(self, executor: ToolExecutor) -> None:
        """Test getting tool definitions for Claude API."""
        definitions = executor.get_tool_definitions()
        assert len(definitions) > 0

        # Check that mock_tool is in definitions
        mock_def = next((d for d in definitions if d["name"] == "mock_tool"), None)
        assert mock_def is not None
        assert "description" in mock_def
        assert "input_schema" in mock_def

    def test_format_tool_result_success(self, executor: ToolExecutor) -> None:
        """Test formatting successful result for LLM."""
        result = ToolResult(success=True, data={"key": "value"})
        formatted = executor.format_tool_result_for_llm(result)
        assert '"key"' in formatted
        assert '"value"' in formatted

    def test_format_tool_result_error(self, executor: ToolExecutor) -> None:
        """Test formatting error result for LLM."""
        result = ToolResult(success=False, error="Something failed")
        formatted = executor.format_tool_result_for_llm(result)
        assert "Error: Something failed" in formatted


class TestDefaultTools:
    """Tests for default tool registration."""

    def test_default_tools_registered(self) -> None:
        """Test that default tools are registered."""
        executor = ToolExecutor()
        tools = executor.list_tools()

        # Check key tools are registered
        assert "list_strategies" in tools
        assert "get_strategy" in tools
        assert "list_templates" in tools
        assert "get_portfolio_summary" in tools
        assert "validate_dsl" in tools
        assert "get_backtest_results" in tools

    def test_all_tools_have_valid_definitions(self) -> None:
        """Test that all tools have valid Claude API definitions."""
        executor = ToolExecutor()
        definitions = executor.get_tool_definitions()

        for definition in definitions:
            assert "name" in definition
            assert "description" in definition
            assert "input_schema" in definition
            assert definition["input_schema"]["type"] == "object"
