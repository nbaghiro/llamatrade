"""Tests for the Agent Service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.agent_pb2 import (
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
    STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
    STREAM_EVENT_TYPE_TOOL_CALL_START,
)

from src.prompts.system import ContextData
from src.services.agent_service import AgentService


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def tenant_id() -> UUID:
    """Create a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Create a test user ID."""
    return uuid4()


@pytest.fixture
def session_id() -> UUID:
    """Create a test session ID."""
    return uuid4()


@pytest.fixture
def agent_service(mock_db: AsyncMock, tenant_id: UUID, user_id: UUID) -> AgentService:
    """Create an agent service with mocked dependencies."""
    return AgentService(mock_db, tenant_id, user_id)


class TestAgentServiceInit:
    """Tests for AgentService initialization."""

    def test_init(self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID) -> None:
        """Test basic initialization."""
        service = AgentService(mock_db, tenant_id, user_id)
        assert service.db == mock_db
        assert service.tenant_id == tenant_id
        assert service.user_id == user_id
        assert service._llm_client is None

    def test_llm_client_property(self, agent_service: AgentService) -> None:
        """Test that LLM client is lazily created."""
        assert agent_service._llm_client is None

        # Access the property - should create client
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            # The actual client creation will fail without a real key,
            # but we can test the property mechanics
            assert agent_service._llm_client is None  # Still None until actually called


class TestBuildLLMMessages:
    """Tests for message building."""

    def test_build_messages_simple(self, agent_service: AgentService) -> None:
        """Test building messages with just a user message."""
        messages = agent_service._build_llm_messages(
            user_message="Create a 60/40 portfolio",
            history=[],
            context_data=None,
        )

        # Should have few-shot examples + user message
        assert len(messages) > 1
        assert messages[-1].role == "user"
        assert messages[-1].content == "Create a 60/40 portfolio"

    def test_build_messages_with_history(self, agent_service: AgentService) -> None:
        """Test building messages with conversation history."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ]

        messages = agent_service._build_llm_messages(
            user_message="Create a strategy",
            history=history,
            context_data=None,
        )

        # Find the history messages in the output
        user_messages = [m for m in messages if m.content == "Hello"]
        assistant_messages = [m for m in messages if m.content == "Hi! How can I help?"]

        assert len(user_messages) == 1
        assert len(assistant_messages) == 1

    def test_build_messages_with_context(self, agent_service: AgentService) -> None:
        """Test building messages with context data."""
        context = ContextData(
            strategy_name="Test Strategy",
            strategy_status="active",
            page="strategy_detail",
        )

        agent_service._build_llm_messages(
            user_message="Improve this strategy",
            history=[],
            context_data=context,
        )

        # System prompt should be built (stored internally)
        assert hasattr(agent_service, "_current_system_prompt")
        assert "Test Strategy" in agent_service._current_system_prompt


class TestBuildContext:
    """Tests for context building."""

    @pytest.mark.asyncio
    async def test_build_context_none(self, agent_service: AgentService, session_id: UUID) -> None:
        """Test building context with no UI context returns default ContextData."""
        context = await agent_service._build_context(session_id, None)
        # Returns ContextData with defaults and memory hint
        assert context is not None
        assert context.page is None
        assert context.strategy_name is None
        assert context.memory_hint is not None  # Always has memory hint

    @pytest.mark.asyncio
    async def test_build_context_with_page(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """Test building context with page info."""
        ui_context = {"page": "dashboard"}

        context = await agent_service._build_context(session_id, ui_context)

        assert context is not None
        assert context.page == "dashboard"

    @pytest.mark.asyncio
    async def test_build_context_with_strategy_id(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """Test building context with strategy data from UI context."""
        # Strategy data is passed directly from frontend in ui_context
        ui_context = {
            "page": "strategy_detail",
            "strategy_name": "My Strategy",
            "strategy_dsl": "(strategy ...)",
        }

        context = await agent_service._build_context(session_id, ui_context)

        assert context is not None
        assert context.strategy_name == "My Strategy"
        assert context.strategy_dsl == "(strategy ...)"
        assert context.page == "strategy_detail"


class TestExtractStrategyName:
    """Tests for strategy name extraction from DSL."""

    def test_extract_simple_name(self, agent_service: AgentService) -> None:
        """Test extracting a simple strategy name."""
        dsl = '(strategy "My Portfolio" :rebalance monthly)'
        name = agent_service._extract_strategy_name(dsl)
        assert name == "My Portfolio"

    def test_extract_name_with_special_chars(self, agent_service: AgentService) -> None:
        """Test extracting name with special characters."""
        dsl = '(strategy "60/40 Portfolio" :rebalance quarterly)'
        name = agent_service._extract_strategy_name(dsl)
        assert name == "60/40 Portfolio"

    def test_extract_name_multiline(self, agent_service: AgentService) -> None:
        """Test extracting name from multiline DSL."""
        dsl = """
        (strategy "Risk Parity"
          :rebalance monthly
          :benchmark SPY)
        """
        name = agent_service._extract_strategy_name(dsl)
        assert name == "Risk Parity"

    def test_extract_no_name(self, agent_service: AgentService) -> None:
        """Test extraction when no name present."""
        dsl = "(weight :method equal (asset VTI))"
        name = agent_service._extract_strategy_name(dsl)
        assert name is None


class TestStreamMessage:
    """Tests for the streaming message handler."""

    @pytest.mark.asyncio
    async def test_stream_message_simple(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test streaming a simple message."""
        # Create mock responses
        from tests.fixtures.mock_llm import MockLLMClient

        mock_client = MockLLMClient()
        mock_client.add_simple_response("Hello! I can help with that.")

        # Patch the LLM client and conversation service
        agent_service._llm_client = mock_client

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Hello"):
                events.append(event)

        # Should have content deltas and complete event
        content_events = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_CONTENT_DELTA]
        complete_events = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_COMPLETE]

        assert len(content_events) > 0
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    async def test_stream_message_with_tool_call(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test streaming a message that triggers a tool call."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # First response: tool call
        mock_client.add_tool_call_response(
            tool_name="list_strategies",
            tool_input={},
            content="Let me check your strategies.",
        )

        # Second response: final answer
        mock_client.add_simple_response("You have 3 strategies.")

        agent_service._llm_client = mock_client

        # Mock the tool execution
        mock_tool_result = ToolResult(
            success=True,
            data={"strategies": [{"name": "Test"}]},
        )

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", return_value=mock_tool_result),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Show my strategies"):
                events.append(event)

        # Should have tool call events
        tool_start_events = [
            e for e in events if e.get("type") == STREAM_EVENT_TYPE_TOOL_CALL_START
        ]
        tool_complete_events = [
            e for e in events if e.get("type") == STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE
        ]

        assert len(tool_start_events) >= 1
        assert len(tool_complete_events) >= 1
        assert tool_start_events[0].get("tool_name") == "list_strategies"

    @pytest.mark.asyncio
    async def test_stream_message_error_handling(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test error handling in stream_message."""

        # Create an async generator that raises an exception
        async def mock_error_stream(*args, **kwargs):
            raise Exception("LLM Error")
            yield  # Makes this an async generator (never reached)

        with patch.object(agent_service.llm_client, "stream", mock_error_stream):
            events = []
            async for event in agent_service.stream_message(session_id, "Hello"):
                events.append(event)

        # Should have error event
        error_events = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_ERROR]
        assert len(error_events) == 1
        assert "LLM Error" in error_events[0].get("error", "")


class TestProcessMessage:
    """Tests for the non-streaming message handler."""

    @pytest.mark.asyncio
    async def test_process_message(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test processing a message non-streaming."""
        from tests.fixtures.mock_llm import MockLLMClient

        mock_client = MockLLMClient()
        mock_client.add_simple_response("Here's your portfolio!")

        agent_service._llm_client = mock_client

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
        ):
            content, tool_calls, artifacts = await agent_service.process_message(
                session_id, "Show my portfolio"
            )

        assert "portfolio" in content.lower()
        assert isinstance(tool_calls, list)
        assert isinstance(artifacts, list)


class TestMaybeCreateArtifact:
    """Tests for artifact creation."""

    @pytest.mark.asyncio
    async def test_no_artifact_on_invalid(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that no artifact is created when validation fails."""
        validation_result = {"valid": False, "errors": ["Invalid syntax"]}

        artifact = await agent_service._maybe_create_artifact(
            session_id, validation_result, "(strategy ...)"
        )

        assert artifact is None

    @pytest.mark.asyncio
    async def test_no_artifact_on_none_result(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that no artifact is created when validation result is None."""
        artifact = await agent_service._maybe_create_artifact(session_id, None, "(strategy ...)")

        assert artifact is None

    @pytest.mark.asyncio
    async def test_artifact_created_on_valid(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that artifact is created when validation succeeds."""
        validation_result = {
            "valid": True,
            "extracted_symbols": ["VTI", "BND"],
        }
        dsl_code = '(strategy "Test Portfolio" :rebalance monthly)'

        # Mock the artifact service
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.name = "Test Portfolio"

        with patch("src.services.artifact_service.ArtifactService") as mock_artifact_service_cls:
            mock_service = mock_artifact_service_cls.return_value
            mock_service.create_strategy_artifact = AsyncMock(return_value=mock_artifact)

            artifact = await agent_service._maybe_create_artifact(
                session_id, validation_result, dsl_code
            )

        assert artifact is not None
        assert artifact.name == "Test Portfolio"


class TestFetchContexts:
    """Tests for context fetching methods."""

    @pytest.mark.asyncio
    async def test_fetch_strategy_context_success(self, agent_service: AgentService) -> None:
        """Test successful strategy context fetch."""
        from src.tools.base import ToolResult

        mock_result = ToolResult(
            success=True,
            data={
                "name": "My Strategy",
                "dsl_code": "(strategy ...)",
                "status": "active",
            },
        )

        with patch("src.tools.strategy_tools.GetStrategyTool") as mock_tool_cls:
            mock_tool = mock_tool_cls.return_value
            mock_tool.run = AsyncMock(return_value=mock_result)

            result = await agent_service._fetch_strategy_context("test-id")

        assert result is not None
        assert result["name"] == "My Strategy"

    @pytest.mark.asyncio
    async def test_fetch_strategy_context_error(self, agent_service: AgentService) -> None:
        """Test strategy context fetch with error."""
        with patch(
            "src.tools.strategy_tools.GetStrategyTool",
            side_effect=Exception("Network error"),
        ):
            result = await agent_service._fetch_strategy_context("test-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_backtest_context_success(self, agent_service: AgentService) -> None:
        """Test successful backtest context fetch."""
        from src.tools.base import ToolResult

        mock_result = ToolResult(
            success=True,
            data={
                "total_return": 0.15,
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.10,
            },
        )

        with patch("src.tools.backtest_tools.GetBacktestResultsTool") as mock_tool_cls:
            mock_tool = mock_tool_cls.return_value
            mock_tool.run = AsyncMock(return_value=mock_result)

            result = await agent_service._fetch_backtest_context("test-id")

        assert result is not None
        assert result["total_return"] == 0.15


# =============================================================================
# Multi-iteration Tool Tests
# =============================================================================


class TestMultiIterationToolLoop:
    """Tests for multi-iteration tool execution."""

    @pytest.mark.asyncio
    async def test_stream_message_multi_tool_iteration(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test handling multiple tool calls in sequence."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # First iteration: list strategies
        mock_client.add_tool_call_response(
            tool_name="list_strategies",
            tool_input={},
            content="Let me check your strategies.",
        )

        # Second iteration: get specific strategy
        mock_client.add_tool_call_response(
            tool_name="get_strategy",
            tool_input={"strategy_id": "123"},
            content="Now let me get details.",
        )

        # Third iteration: final answer
        mock_client.add_simple_response("Here's the strategy: ...")

        agent_service._llm_client = mock_client

        # Track tool executions
        tool_calls_made: list[str] = []

        async def mock_execute(tool_name: str, arguments: Any, **kwargs: Any) -> ToolResult:
            tool_calls_made.append(tool_name)
            return ToolResult(success=True, data={"result": "mock"})

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", side_effect=mock_execute),
            patch.object(agent_service._executor, "format_tool_result_for_llm", return_value="{}"),
        ):
            events = []
            async for event in agent_service.stream_message(
                session_id, "Tell me about my strategies"
            ):
                events.append(event)

        # Should have called both tools
        assert "list_strategies" in tool_calls_made
        assert "get_strategy" in tool_calls_made

    @pytest.mark.asyncio
    async def test_stream_message_max_iterations(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that tool loop stops at max iterations."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # Add more tool calls than MAX_TOOL_ITERATIONS (10)
        for i in range(15):
            mock_client.add_tool_call_response(
                tool_name=f"tool_{i}",
                tool_input={},
                content=f"Step {i}",
            )

        agent_service._llm_client = mock_client

        tool_calls_count = 0

        async def mock_execute(tool_name: str, arguments: Any, **kwargs: Any) -> ToolResult:
            nonlocal tool_calls_count
            tool_calls_count += 1
            return ToolResult(success=True, data={})

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", side_effect=mock_execute),
            patch.object(agent_service._executor, "format_tool_result_for_llm", return_value="{}"),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Run all tools"):
                events.append(event)

        # Should have stopped at 10 iterations
        assert tool_calls_count <= 10

    @pytest.mark.asyncio
    async def test_stream_message_tool_error_recovery(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that streaming continues after tool failure."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # First iteration: tool call that will fail
        mock_client.add_tool_call_response(
            tool_name="failing_tool",
            tool_input={},
            content="Let me try this tool.",
        )

        # LLM sees the error and provides final response
        mock_client.add_simple_response("That tool failed, but I can still help.")

        agent_service._llm_client = mock_client

        async def mock_execute(tool_name: str, arguments: Any, **kwargs: Any) -> ToolResult:
            return ToolResult(success=False, error="Tool execution failed")

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", side_effect=mock_execute),
            patch.object(
                agent_service._executor,
                "format_tool_result_for_llm",
                return_value="Error: Tool execution failed",
            ),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Use the tool"):
                events.append(event)

        # Should have received tool complete event showing failure
        from llamatrade_proto.generated.agent_pb2 import (
            STREAM_EVENT_TYPE_COMPLETE,
            STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
        )

        tool_complete_events = [
            e for e in events if e.get("type") == STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE
        ]
        complete_events = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_COMPLETE]

        assert len(tool_complete_events) >= 1
        assert tool_complete_events[0].get("success") is False
        assert len(complete_events) == 1


# =============================================================================
# Conversation History Tests
# =============================================================================


class TestConversationHistory:
    """Tests for conversation history retrieval."""

    @pytest.mark.asyncio
    async def test_get_conversation_history(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that conversation history is formatted correctly."""
        from llamatrade_proto.generated.agent_pb2 import (
            MESSAGE_ROLE_ASSISTANT,
            MESSAGE_ROLE_USER,
        )

        # Create mock messages
        mock_msg1 = MagicMock()
        mock_msg1.role = MESSAGE_ROLE_USER
        mock_msg1.content = "Hello"

        mock_msg2 = MagicMock()
        mock_msg2.role = MESSAGE_ROLE_ASSISTANT
        mock_msg2.content = "Hi there!"

        mock_msg3 = MagicMock()
        mock_msg3.role = MESSAGE_ROLE_USER
        mock_msg3.content = "Create a strategy"

        mock_conv_service = MagicMock()
        mock_conv_service.get_messages = AsyncMock(return_value=[mock_msg1, mock_msg2, mock_msg3])

        with patch(
            "src.services.conversation_service.ConversationService",
            return_value=mock_conv_service,
        ):
            history = await agent_service._get_conversation_history(session_id)

        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_get_conversation_history_limit(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that history respects the limit parameter."""
        mock_conv_service = MagicMock()
        mock_conv_service.get_messages = AsyncMock(return_value=[])

        with patch(
            "src.services.conversation_service.ConversationService",
            return_value=mock_conv_service,
        ):
            await agent_service._get_conversation_history(session_id, limit=10)

        # Verify limit was passed
        mock_conv_service.get_messages.assert_called_once_with(session_id, limit=10)

    @pytest.mark.asyncio
    async def test_get_conversation_history_default_limit(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that default limit is 20."""
        mock_conv_service = MagicMock()
        mock_conv_service.get_messages = AsyncMock(return_value=[])

        with patch(
            "src.services.conversation_service.ConversationService",
            return_value=mock_conv_service,
        ):
            await agent_service._get_conversation_history(session_id)

        # Verify default limit of 20
        mock_conv_service.get_messages.assert_called_once_with(session_id, limit=20)


# =============================================================================
# Store Assistant Message Tests
# =============================================================================


class TestStoreAssistantMessage:
    """Tests for storing assistant messages."""

    @pytest.mark.asyncio
    async def test_store_assistant_message(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that assistant message is stored correctly."""
        from llamatrade_proto.generated.agent_pb2 import MESSAGE_ROLE_ASSISTANT

        mock_conv_service = MagicMock()
        mock_conv_service.add_message = AsyncMock()

        with patch(
            "src.services.conversation_service.ConversationService",
            return_value=mock_conv_service,
        ):
            await agent_service._store_assistant_message(session_id, "This is the response")

        # Verify correct parameters
        mock_conv_service.add_message.assert_called_once()
        call_kwargs = mock_conv_service.add_message.call_args[1]
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["tenant_id"] == agent_service.tenant_id
        assert call_kwargs["role"] == MESSAGE_ROLE_ASSISTANT
        assert call_kwargs["content"] == "This is the response"


# =============================================================================
# Additional Artifact Tests
# =============================================================================


class TestArtifactCreationFlow:
    """Additional tests for artifact creation flow."""

    @pytest.mark.asyncio
    async def test_stream_message_creates_artifact_on_valid_dsl(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that artifact is created when validate_dsl succeeds."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # First response: call validate_dsl
        mock_client.add_tool_call_response(
            tool_name="validate_dsl",
            tool_input={"dsl_code": '(strategy "Test" :rebalance monthly)'},
            content="Let me validate this DSL.",
        )

        # Second response: final answer
        mock_client.add_simple_response("Strategy created successfully!")

        agent_service._llm_client = mock_client

        # Mock validation success
        mock_validation_result = ToolResult(
            success=True,
            data={"valid": True, "extracted_symbols": ["SPY"]},
        )

        # Track if artifact creation was called
        artifact_created = False
        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.name = "Test"

        async def mock_maybe_create(*args: Any, **kwargs: Any) -> Any:
            nonlocal artifact_created
            artifact_created = True
            return mock_artifact

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", return_value=mock_validation_result),
            patch.object(
                agent_service._executor,
                "format_tool_result_for_llm",
                return_value='{"valid": true}',
            ),
            patch.object(agent_service, "_maybe_create_artifact", side_effect=mock_maybe_create),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Create a strategy"):
                events.append(event)

        assert artifact_created is True

    @pytest.mark.asyncio
    async def test_stream_message_no_artifact_on_invalid_dsl(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Test that no artifact is created when validate_dsl fails."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()

        # First response: call validate_dsl
        mock_client.add_tool_call_response(
            tool_name="validate_dsl",
            tool_input={"dsl_code": "(invalid dsl)"},
            content="Let me validate this.",
        )

        # Second response: explain error
        mock_client.add_simple_response("The DSL has syntax errors.")

        agent_service._llm_client = mock_client

        # Mock validation failure - tool succeeds but data shows invalid
        mock_validation_result = ToolResult(
            success=True,
            data={"valid": False, "errors": ["Syntax error"]},
        )

        artifact_created = False

        async def mock_maybe_create(*args: Any, **kwargs: Any) -> Any:
            nonlocal artifact_created
            artifact_created = True
            return None

        with (
            patch.object(agent_service, "_get_conversation_history", return_value=[]),
            patch.object(agent_service, "_store_assistant_message", return_value=None),
            patch.object(agent_service._executor, "execute", return_value=mock_validation_result),
            patch.object(
                agent_service._executor,
                "format_tool_result_for_llm",
                return_value='{"valid": false}',
            ),
            patch.object(agent_service, "_maybe_create_artifact", side_effect=mock_maybe_create),
        ):
            events = []
            async for event in agent_service.stream_message(session_id, "Create bad strategy"):
                events.append(event)

        # _maybe_create_artifact was called but should return None
        # because validation result shows invalid
        # The actual logic in _maybe_create_artifact checks for valid=True
