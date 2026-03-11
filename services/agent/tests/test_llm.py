"""Tests for the LLM client module."""

from __future__ import annotations

from src.llm.client import (
    LLMConfig,
    LLMResponse,
    Message,
    StreamEvent,
    StreamEventType,
    ToolCall,
)
from src.prompts.few_shot import FEW_SHOT_EXAMPLES, get_few_shot_for_task, get_few_shot_messages
from src.prompts.system import (
    COPILOT_SYSTEM_PROMPT,
    ContextData,
    build_contextual_section,
    build_system_prompt,
)


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = LLMConfig()
        assert config.max_tokens == 4096
        assert config.temperature == 0.7
        assert config.system_prompt == ""
        assert config.tools == []

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.5,
            system_prompt="Test prompt",
        )
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 2048
        assert config.temperature == 0.5
        assert config.system_prompt == "Test prompt"


class TestMessage:
    """Tests for Message class."""

    def test_simple_message(self) -> None:
        """Test creating a simple message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_message_with_tool_result(self) -> None:
        """Test message with tool result."""
        msg = Message(
            role="user",
            content='{"result": "success"}',
            tool_call_id="tool_123",
        )
        assert msg.tool_call_id == "tool_123"


class TestToolCall:
    """Tests for ToolCall class."""

    def test_tool_call_creation(self) -> None:
        """Test creating a tool call."""
        tool_call = ToolCall(
            id="call_123",
            name="get_portfolio",
            input={"symbols": ["SPY", "VTI"]},
        )
        assert tool_call.id == "call_123"
        assert tool_call.name == "get_portfolio"
        assert tool_call.input == {"symbols": ["SPY", "VTI"]}


class TestStreamEvent:
    """Tests for StreamEvent class."""

    def test_content_delta_event(self) -> None:
        """Test content delta event."""
        event = StreamEvent(
            type=StreamEventType.CONTENT_DELTA,
            content="Hello world",
        )
        assert event.type == StreamEventType.CONTENT_DELTA
        assert event.content == "Hello world"

    def test_tool_use_event(self) -> None:
        """Test tool use event."""
        tool_call = ToolCall(id="call_1", name="test", input={})
        event = StreamEvent(
            type=StreamEventType.TOOL_USE_START,
            tool_call=tool_call,
        )
        assert event.type == StreamEventType.TOOL_USE_START
        assert event.tool_call is not None
        assert event.tool_call.name == "test"

    def test_error_event(self) -> None:
        """Test error event."""
        event = StreamEvent(
            type=StreamEventType.ERROR,
            error="Connection failed",
        )
        assert event.type == StreamEventType.ERROR
        assert event.error == "Connection failed"


class TestLLMResponse:
    """Tests for LLMResponse class."""

    def test_simple_response(self) -> None:
        """Test simple text response."""
        response = LLMResponse(
            content="Hello!",
            stop_reason="end_turn",
        )
        assert response.content == "Hello!"
        assert response.tool_calls == []
        assert response.stop_reason == "end_turn"

    def test_response_with_tool_calls(self) -> None:
        """Test response with tool calls."""
        tool_call = ToolCall(id="call_1", name="list_strategies", input={})
        response = LLMResponse(
            content="",
            tool_calls=[tool_call],
            stop_reason="tool_use",
        )
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "list_strategies"
        assert response.stop_reason == "tool_use"


class TestSystemPrompt:
    """Tests for system prompt building."""

    def test_base_prompt_exists(self) -> None:
        """Test that base prompt is defined."""
        assert COPILOT_SYSTEM_PROMPT is not None
        assert len(COPILOT_SYSTEM_PROMPT) > 1000  # Should be substantial

    def test_prompt_contains_dsl_reference(self) -> None:
        """Test prompt contains DSL documentation."""
        assert "DSL Reference" in COPILOT_SYSTEM_PROMPT
        assert "(strategy" in COPILOT_SYSTEM_PROMPT
        assert "(weight :method" in COPILOT_SYSTEM_PROMPT
        assert "(asset" in COPILOT_SYSTEM_PROMPT

    def test_prompt_contains_rules(self) -> None:
        """Test prompt contains behavior rules."""
        assert "Rules You MUST Follow" in COPILOT_SYSTEM_PROMPT
        assert "validate_dsl" in COPILOT_SYSTEM_PROMPT

    def test_build_system_prompt_no_context(self) -> None:
        """Test building prompt without context."""
        prompt = build_system_prompt()
        assert "LlamaTrade Copilot" in prompt
        # No context should mean no "Current Context" section
        assert "{contextual_injection}" not in prompt

    def test_build_system_prompt_with_strategy_context(self) -> None:
        """Test building prompt with strategy context."""
        context = ContextData(
            strategy_name="My Strategy",
            strategy_status="active",
            strategy_symbols=["VTI", "BND"],
            strategy_dsl='(strategy "My Strategy" :rebalance monthly)',
        )
        prompt = build_system_prompt(context)
        assert "My Strategy" in prompt
        assert "VTI" in prompt
        assert "BND" in prompt

    def test_build_system_prompt_with_portfolio_context(self) -> None:
        """Test building prompt with portfolio context."""
        context = ContextData(
            portfolio_equity=100000.0,
            portfolio_cash=10000.0,
            portfolio_positions=[
                {
                    "symbol": "SPY",
                    "market_value": 50000,
                    "weight": 0.5,
                    "unrealized_pnl_percent": 0.05,
                }
            ],
        )
        prompt = build_system_prompt(context)
        assert "Portfolio" in prompt
        assert "$100,000" in prompt

    def test_contextual_section_strategy(self) -> None:
        """Test contextual section for strategy."""
        context = ContextData(
            strategy_name="Test",
            strategy_status="draft",
            strategy_symbols=["SPY"],
        )
        section = build_contextual_section(context)
        assert "Test" in section
        assert "draft" in section

    def test_contextual_section_backtest(self) -> None:
        """Test contextual section with backtest data."""
        context = ContextData(
            strategy_name="Test",
            backtest_total_return=0.15,
            backtest_sharpe_ratio=1.5,
            backtest_max_drawdown=-0.10,
        )
        section = build_contextual_section(context)
        assert "15.00%" in section or "+15.00%" in section
        assert "1.50" in section


class TestFewShotExamples:
    """Tests for few-shot examples."""

    def test_examples_exist(self) -> None:
        """Test that few-shot examples are defined."""
        assert len(FEW_SHOT_EXAMPLES) > 0

    def test_examples_have_correct_structure(self) -> None:
        """Test examples have role and content."""
        for example in FEW_SHOT_EXAMPLES:
            assert "role" in example
            assert "content" in example
            assert example["role"] in ["user", "assistant"]

    def test_examples_alternate_roles(self) -> None:
        """Test that examples alternate between user and assistant."""
        for i in range(0, len(FEW_SHOT_EXAMPLES) - 1, 2):
            assert FEW_SHOT_EXAMPLES[i]["role"] == "user"
            assert FEW_SHOT_EXAMPLES[i + 1]["role"] == "assistant"

    def test_assistant_examples_contain_dsl(self) -> None:
        """Test that assistant responses contain DSL code."""
        assistant_examples = [e for e in FEW_SHOT_EXAMPLES if e["role"] == "assistant"]
        for example in assistant_examples:
            # Each assistant response should contain a strategy
            assert "(strategy" in example["content"]

    def test_get_few_shot_messages(self) -> None:
        """Test getting few-shot messages."""
        messages = get_few_shot_messages()
        assert len(messages) == len(FEW_SHOT_EXAMPLES)
        for msg in messages:
            assert "role" in msg
            assert "content" in msg

    def test_get_few_shot_for_task_generate(self) -> None:
        """Test getting examples for generate task."""
        messages = get_few_shot_for_task("generate")
        assert len(messages) > 0
        # Should include strategy generation examples
        assert any("60/40" in m.get("content", "") for m in messages)

    def test_get_few_shot_for_task_edit(self) -> None:
        """Test getting examples for edit task."""
        messages = get_few_shot_for_task("edit")
        assert len(messages) > 0
        # Should include the risk-off modification example
        assert any("risk-off" in m.get("content", "").lower() for m in messages)
