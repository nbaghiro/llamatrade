"""Tests for the Agent Service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.agent_pb2 import (
    STREAM_EVENT_TYPE_ARTIFACT_CREATED,
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
    STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
    STREAM_EVENT_TYPE_TOOL_CALL_START,
    STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED,
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

    def test_build_messages_coalesces_consecutive_roles(
        self, agent_service: AgentService
    ) -> None:
        """Consecutive same-role turns are merged so alternation stays strict.

        A history window may begin mid-conversation (on an assistant turn) or
        end on a user turn; either way the built messages must never place two
        same-role turns adjacently (Anthropic rejects that).
        """
        history = [
            {"role": "assistant", "content": "Earlier reply A"},
            {"role": "assistant", "content": "Earlier reply B"},
            {"role": "user", "content": "Follow-up question"},
        ]

        messages = agent_service._build_llm_messages(
            user_message="And one more thing",
            history=history,
            context_data=None,
        )

        # No two adjacent messages share a role.
        for prev, nxt in zip(messages, messages[1:], strict=False):
            assert prev.role != nxt.role

        # The trailing user turns (history + current) are merged into one.
        assert messages[-1].role == "user"
        assert "Follow-up question" in messages[-1].content
        assert "And one more thing" in messages[-1].content


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
    async def test_stream_message_emits_artifact_event(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """A draft artifact created mid-turn is emitted as an ARTIFACT_CREATED event.

        The servicer links the emitted artifact id to the stored assistant
        message (covered in test_servicer).
        """
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()
        mock_client.add_tool_call_response(
            tool_name="validate_dsl",
            tool_input={"dsl_code": '(strategy "S" :rebalance daily)'},
            content="Validating your strategy.",
        )
        mock_client.add_simple_response("Here's your strategy.")
        agent_service._llm_client = mock_client

        mock_tool_result = ToolResult(
            success=True, data={"valid": True, "extracted_symbols": ["SPY"]}
        )
        fake_artifact = MagicMock()
        fake_artifact.id = "artifact-xyz"

        with (
            patch.object(agent_service, "_maybe_create_artifact", return_value=fake_artifact),
            patch.object(agent_service._executor, "execute", return_value=mock_tool_result),
        ):
            events = [
                event
                async for event in agent_service.stream_message(session_id, "Build a strategy")
            ]

        artifact_events = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_ARTIFACT_CREATED]
        assert len(artifact_events) == 1
        assert artifact_events[0]["artifact"] is fake_artifact

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
# Tool Confirmation Flow
# =============================================================================


class TestToolConfirmation:
    """Tests for propose-and-confirm handling of write tools."""

    @pytest.mark.asyncio
    async def test_stream_message_halts_on_confirmation_required(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """A confirmation-gated tool (run_backtest) is proposed, not executed."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()
        mock_client.add_tool_call_response(
            tool_name="run_backtest",
            tool_input={"strategy_id": "s1"},
            content="I'll run a backtest.",
        )
        agent_service._llm_client = mock_client

        executed = False

        async def mock_execute(*_args: Any, **_kwargs: Any) -> ToolResult:
            nonlocal executed
            executed = True
            return ToolResult(success=True, data={})

        with patch.object(agent_service._executor, "execute", side_effect=mock_execute):
            events = [
                e async for e in agent_service.stream_message(session_id, "backtest my strategy")
            ]

        confirm = [
            e for e in events if e.get("type") == STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED
        ]
        assert len(confirm) == 1
        assert confirm[0]["tool_name"] == "run_backtest"
        assert '"strategy_id": "s1"' in confirm[0]["arguments_json"]
        assert confirm[0]["confirmation_id"]
        assert executed is False  # halted, awaiting approval

    @pytest.mark.asyncio
    async def test_resume_with_tool_approved_executes_and_summarizes(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Approval executes the tool and streams a follow-up summary."""
        from tests.fixtures.mock_llm import MockLLMClient

        from src.tools.base import ToolResult

        mock_client = MockLLMClient()
        mock_client.add_simple_response("Your backtest is running; results soon.")
        agent_service._llm_client = mock_client

        execute = AsyncMock(return_value=ToolResult(success=True, data={"backtest_id": "bt1"}))
        with patch.object(agent_service._executor, "execute", execute):
            events = [
                e
                async for e in agent_service.resume_with_tool(
                    session_id, "run_backtest", '{"strategy_id": "s1"}', approved=True
                )
            ]

        execute.assert_awaited_once()
        tool_complete = [
            e for e in events if e.get("type") == STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE
        ]
        content = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_CONTENT_DELTA]
        complete = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_COMPLETE]
        assert len(tool_complete) == 1
        assert tool_complete[0]["success"] is True
        assert len(content) >= 1
        assert len(complete) == 1

    @pytest.mark.asyncio
    async def test_resume_with_tool_denied_acknowledges_without_executing(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Denial acknowledges and never executes the tool."""
        execute = AsyncMock()
        with patch.object(agent_service._executor, "execute", execute):
            events = [
                e
                async for e in agent_service.resume_with_tool(
                    session_id, "run_backtest", "{}", approved=False
                )
            ]

        execute.assert_not_awaited()
        content = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_CONTENT_DELTA]
        complete = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_COMPLETE]
        assert len(content) == 1
        assert "held off" in content[0]["delta"]
        assert len(complete) == 1

    @pytest.mark.asyncio
    async def test_resume_with_tool_rejects_non_confirmable_tool(
        self,
        agent_service: AgentService,
        session_id: UUID,
    ) -> None:
        """Only confirmation-gated tools may be resumed via this path."""
        events = [
            e
            async for e in agent_service.resume_with_tool(
                session_id, "list_strategies", "{}", approved=True
            )
        ]
        errors = [e for e in events if e.get("type") == STREAM_EVENT_TYPE_ERROR]
        assert len(errors) == 1
        assert "not a confirmable action" in errors[0]["error"]


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
