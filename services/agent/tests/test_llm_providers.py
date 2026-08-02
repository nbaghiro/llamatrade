"""Contract tests for the Anthropic and Gemini LLM clients.

Fake SDK objects pin the response shapes each client depends on (content
blocks, streaming deltas, usage, finish reasons) so an SDK bump that moves a
field fails here instead of in production.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm.anthropic import AnthropicClient
from src.llm.client import LLMConfig, Message, StreamEvent, StreamEventType, ToolCall
from src.llm.gemini import GeminiClient

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "validate_dsl",
        "description": "Validate strategy DSL",
        "input_schema": {"type": "object", "properties": {"dsl_code": {"type": "string"}}},
    }
]


async def _collect(stream: AsyncIterator[StreamEvent]) -> list[StreamEvent]:
    return [event async for event in stream]


# =============================================================================
# Anthropic fakes (stripe of the SDK surface the client touches)
# =============================================================================


@dataclass
class _AntBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class _AntDelta:
    type: str
    text: str = ""
    partial_json: str = ""


@dataclass
class _AntUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _AntSnapshot:
    stop_reason: str | None
    usage: _AntUsage | None


@dataclass
class _AntEvent:
    type: str
    content_block: _AntBlock | None = None
    delta: _AntDelta | None = None


@dataclass
class _AntResponse:
    content: list[_AntBlock]
    stop_reason: str | None
    usage: _AntUsage


class _AntStream:
    """Stands in for the SDK's MessageStreamManager + MessageStream."""

    def __init__(self, events: list[_AntEvent], snapshot: _AntSnapshot) -> None:
        self._events = events
        self.current_message_snapshot = snapshot

    async def __aenter__(self) -> _AntStream:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[_AntEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[_AntEvent]:
        for event in self._events:
            yield event


def _anthropic_client_with(sdk: MagicMock) -> AnthropicClient:
    client = AnthropicClient(LLMConfig(model="claude-test"))
    client._client = sdk
    return client


class TestAnthropicComplete:
    """Non-streaming response assembly."""

    @pytest.mark.asyncio
    async def test_text_and_tool_use_blocks(self) -> None:
        sdk = MagicMock()
        sdk.messages.create = AsyncMock(
            return_value=_AntResponse(
                content=[
                    _AntBlock(type="text", text="Validating now."),
                    _AntBlock(
                        type="tool_use",
                        id="tu_1",
                        name="validate_dsl",
                        input={"dsl_code": "(strategy)"},
                    ),
                ],
                stop_reason="tool_use",
                usage=_AntUsage(input_tokens=12, output_tokens=7),
            )
        )
        client = _anthropic_client_with(sdk)

        response = await client.complete(
            [Message(role="user", content="validate this")], tools=TOOL_DEFS
        )

        assert response.content == "Validating now."
        assert response.tool_calls == [
            ToolCall(id="tu_1", name="validate_dsl", input={"dsl_code": "(strategy)"})
        ]
        assert response.stop_reason == "tool_use"
        assert response.usage == {"input_tokens": 12, "output_tokens": 7}

        kwargs = sdk.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-test"
        assert kwargs["tools"] == TOOL_DEFS

    @pytest.mark.asyncio
    async def test_api_error_propagates(self) -> None:
        sdk = MagicMock()
        sdk.messages.create = AsyncMock(side_effect=RuntimeError("overloaded"))
        client = _anthropic_client_with(sdk)

        with pytest.raises(RuntimeError, match="overloaded"):
            await client.complete([Message(role="user", content="hi")])


class TestAnthropicMessageConversion:
    """Tool-call block assembly sent to the API."""

    def test_assistant_tool_calls_become_tool_use_blocks(self) -> None:
        client = AnthropicClient(LLMConfig(model="claude-test"))
        converted = client._convert_messages(
            [
                Message(
                    role="assistant",
                    content="Running it.",
                    tool_calls=[ToolCall(id="tu_1", name="validate_dsl", input={"a": 1})],
                )
            ]
        )
        assert converted == [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Running it."},
                    {"type": "tool_use", "id": "tu_1", "name": "validate_dsl", "input": {"a": 1}},
                ],
            }
        ]

    def test_tool_results_become_tool_result_blocks(self) -> None:
        client = AnthropicClient(LLMConfig(model="claude-test"))
        converted = client._convert_messages(
            [
                Message(
                    role="user",
                    content="",
                    tool_results=[
                        {"tool_call_id": "tu_1", "content": "ok"},
                        {"tool_call_id": "tu_2", "content": {"valid": True}},
                    ],
                )
            ]
        )
        assert converted == [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"},
                    {"type": "tool_result", "tool_use_id": "tu_2", "content": '{"valid": true}'},
                ],
            }
        ]

    def test_system_messages_are_skipped_and_extracted(self) -> None:
        client = AnthropicClient(LLMConfig(model="claude-test"))
        messages = [
            Message(role="system", content="be terse"),
            Message(role="user", content="hi"),
        ]
        assert client._convert_messages(messages) == [{"role": "user", "content": "hi"}]
        assert client._extract_system_prompt(messages, None) == "be terse"
        assert client._extract_system_prompt(messages, "override") == "override"


class TestAnthropicStream:
    """Streaming delta mapping to StreamEvent."""

    @pytest.mark.asyncio
    async def test_full_stream_mapping(self) -> None:
        events = [
            _AntEvent(type="message_start"),
            _AntEvent(
                type="content_block_delta",
                delta=_AntDelta(type="text_delta", text="Working"),
            ),
            _AntEvent(
                type="content_block_start",
                content_block=_AntBlock(type="tool_use", id="tu_1", name="validate_dsl"),
            ),
            _AntEvent(
                type="content_block_delta",
                delta=_AntDelta(type="input_json_delta", partial_json='{"dsl_'),
            ),
            _AntEvent(
                type="content_block_delta",
                delta=_AntDelta(type="input_json_delta", partial_json='code": "x"}'),
            ),
            _AntEvent(type="content_block_stop"),
            _AntEvent(type="message_stop"),
        ]
        snapshot = _AntSnapshot(
            stop_reason="tool_use", usage=_AntUsage(input_tokens=3, output_tokens=4)
        )
        sdk = MagicMock()
        sdk.messages.stream = MagicMock(return_value=_AntStream(events, snapshot))
        client = _anthropic_client_with(sdk)

        collected = await _collect(
            client.stream([Message(role="user", content="go")], tools=TOOL_DEFS)
        )

        types = [event.type for event in collected]
        assert types == [
            StreamEventType.MESSAGE_START,
            StreamEventType.CONTENT_DELTA,
            StreamEventType.TOOL_USE_START,
            StreamEventType.TOOL_USE_DELTA,
            StreamEventType.TOOL_USE_DELTA,
            StreamEventType.TOOL_USE_END,
            StreamEventType.MESSAGE_END,
        ]
        assert collected[1].content == "Working"
        start = collected[2].tool_call
        assert start is not None and start.input == {}
        end = collected[5].tool_call
        assert end is not None
        assert end == ToolCall(id="tu_1", name="validate_dsl", input={"dsl_code": "x"})
        assert collected[6].stop_reason == "tool_use"

    @pytest.mark.asyncio
    async def test_malformed_tool_json_maps_to_empty_input(self) -> None:
        events = [
            _AntEvent(
                type="content_block_start",
                content_block=_AntBlock(type="tool_use", id="tu_1", name="validate_dsl"),
            ),
            _AntEvent(
                type="content_block_delta",
                delta=_AntDelta(type="input_json_delta", partial_json="{not json"),
            ),
            _AntEvent(type="content_block_stop"),
        ]
        sdk = MagicMock()
        sdk.messages.stream = MagicMock(
            return_value=_AntStream(events, _AntSnapshot(stop_reason=None, usage=None))
        )
        client = _anthropic_client_with(sdk)

        collected = await _collect(client.stream([Message(role="user", content="go")]))

        ends = [e for e in collected if e.type == StreamEventType.TOOL_USE_END]
        assert len(ends) == 1
        assert ends[0].tool_call is not None and ends[0].tool_call.input == {}

    @pytest.mark.asyncio
    async def test_stream_error_maps_to_error_event(self) -> None:
        sdk = MagicMock()
        sdk.messages.stream = MagicMock(side_effect=RuntimeError("connection reset"))
        client = _anthropic_client_with(sdk)

        collected = await _collect(client.stream([Message(role="user", content="go")]))

        assert len(collected) == 1
        assert collected[0].type == StreamEventType.ERROR
        assert collected[0].error is not None and "connection reset" in collected[0].error


# =============================================================================
# Gemini fakes
# =============================================================================


@dataclass
class _GemFunctionCall:
    name: str | None
    args: dict[str, Any] | None
    id: str | None = None


@dataclass
class _GemPart:
    text: str | None = None
    function_call: _GemFunctionCall | None = None


@dataclass
class _GemContent:
    parts: list[_GemPart]


@dataclass
class _GemFinishReason:
    name: str


@dataclass
class _GemCandidate:
    content: _GemContent | None
    finish_reason: _GemFinishReason | None = None


@dataclass
class _GemUsage:
    prompt_token_count: int | None
    candidates_token_count: int | None


@dataclass
class _GemResponse:
    candidates: list[_GemCandidate]
    usage_metadata: _GemUsage | None = None


def _gemini_client_with(sdk: MagicMock) -> GeminiClient:
    client = GeminiClient(LLMConfig(model="gemini-test"))
    client._client = sdk
    return client


async def _chunks(items: list[_GemResponse]) -> AsyncIterator[_GemResponse]:
    for item in items:
        yield item


class TestGeminiComplete:
    """Non-streaming response assembly."""

    @pytest.mark.asyncio
    async def test_text_and_function_call_parts(self) -> None:
        sdk = MagicMock()
        sdk.aio.models.generate_content = AsyncMock(
            return_value=_GemResponse(
                candidates=[
                    _GemCandidate(
                        content=_GemContent(
                            parts=[
                                _GemPart(text="Checking."),
                                _GemPart(
                                    function_call=_GemFunctionCall(
                                        name="validate_dsl", args={"dsl_code": "x"}
                                    )
                                ),
                            ]
                        ),
                        finish_reason=_GemFinishReason(name="STOP"),
                    )
                ],
                usage_metadata=_GemUsage(prompt_token_count=9, candidates_token_count=2),
            )
        )
        client = _gemini_client_with(sdk)

        response = await client.complete(
            [Message(role="user", content="validate")], tools=TOOL_DEFS
        )

        assert response.content == "Checking."
        assert response.tool_calls == [
            ToolCall(id="call_validate_dsl_1", name="validate_dsl", input={"dsl_code": "x"})
        ]
        assert response.stop_reason == "tool_use"
        assert response.usage == {"input_tokens": 9, "output_tokens": 2}

    @pytest.mark.asyncio
    async def test_non_stop_finish_reason_is_lowercased(self) -> None:
        sdk = MagicMock()
        sdk.aio.models.generate_content = AsyncMock(
            return_value=_GemResponse(
                candidates=[
                    _GemCandidate(
                        content=_GemContent(parts=[_GemPart(text="truncat")]),
                        finish_reason=_GemFinishReason(name="MAX_TOKENS"),
                    )
                ],
            )
        )
        client = _gemini_client_with(sdk)

        response = await client.complete([Message(role="user", content="hi")])

        assert response.stop_reason == "max_tokens"

    @pytest.mark.asyncio
    async def test_api_error_propagates(self) -> None:
        sdk = MagicMock()
        sdk.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("quota"))
        client = _gemini_client_with(sdk)

        with pytest.raises(RuntimeError, match="quota"):
            await client.complete([Message(role="user", content="hi")])


class TestGeminiMessageConversion:
    """Conversion into google-genai Content objects."""

    def test_tool_call_and_result_round_trip(self) -> None:
        client = GeminiClient(LLMConfig(model="gemini-test"))
        contents = client._convert_messages(
            [
                Message(role="user", content="validate"),
                Message(
                    role="assistant",
                    content="On it.",
                    tool_calls=[ToolCall(id="call_1", name="validate_dsl", input={"a": 1})],
                ),
                Message(
                    role="user",
                    content="",
                    tool_results=[{"tool_call_id": "call_1", "content": '{"valid": true}'}],
                ),
            ]
        )

        assert [c.role for c in contents] == ["user", "model", "user"]
        model_parts = contents[1].parts
        assert model_parts is not None
        assert model_parts[0].text == "On it."
        call = model_parts[1].function_call
        assert call is not None and call.name == "validate_dsl" and call.args == {"a": 1}

        result_parts = contents[2].parts
        assert result_parts is not None
        fn_response = result_parts[0].function_response
        assert fn_response is not None
        # Results are matched back by function name, and JSON content is parsed.
        assert fn_response.name == "validate_dsl"
        assert fn_response.response == {"result": {"valid": True}}

    def test_wrap_tool_response_falls_back_to_raw_string(self) -> None:
        client = GeminiClient(LLMConfig(model="gemini-test"))
        assert client._wrap_tool_response("not json") == {"result": "not json"}
        assert client._wrap_tool_response('{"a": 1}') == {"result": {"a": 1}}

    def test_tool_defs_become_function_declarations(self) -> None:
        client = GeminiClient(LLMConfig(model="gemini-test"))
        tools = client._build_tools(TOOL_DEFS)
        assert tools is not None and len(tools) == 1
        declarations = tools[0].function_declarations
        assert declarations is not None
        assert declarations[0].name == "validate_dsl"
        assert declarations[0].parameters_json_schema == TOOL_DEFS[0]["input_schema"]
        assert client._build_tools(None) is None


class TestGeminiStream:
    """Streaming chunk mapping to StreamEvent."""

    @pytest.mark.asyncio
    async def test_full_stream_mapping(self) -> None:
        chunks = [
            _GemResponse(
                candidates=[_GemCandidate(content=_GemContent(parts=[_GemPart(text="Thinking ")]))]
            ),
            _GemResponse(
                candidates=[
                    _GemCandidate(
                        content=_GemContent(
                            parts=[
                                _GemPart(
                                    function_call=_GemFunctionCall(
                                        name="validate_dsl", args={"dsl_code": "x"}
                                    )
                                )
                            ]
                        ),
                        finish_reason=_GemFinishReason(name="STOP"),
                    )
                ],
                usage_metadata=_GemUsage(prompt_token_count=5, candidates_token_count=6),
            ),
        ]
        sdk = MagicMock()
        sdk.aio.models.generate_content_stream = AsyncMock(return_value=_chunks(chunks))
        client = _gemini_client_with(sdk)

        collected = await _collect(
            client.stream([Message(role="user", content="go")], tools=TOOL_DEFS)
        )

        types = [event.type for event in collected]
        assert types == [
            StreamEventType.MESSAGE_START,
            StreamEventType.CONTENT_DELTA,
            StreamEventType.TOOL_USE_START,
            StreamEventType.TOOL_USE_END,
            StreamEventType.MESSAGE_END,
        ]
        assert collected[1].content == "Thinking "
        end = collected[3].tool_call
        assert end is not None
        # Gemini omits ids, so a synthetic per-turn id is minted.
        assert end == ToolCall(
            id="call_validate_dsl_0", name="validate_dsl", input={"dsl_code": "x"}
        )
        assert collected[4].stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_stream_error_maps_to_error_event(self) -> None:
        sdk = MagicMock()
        sdk.aio.models.generate_content_stream = AsyncMock(side_effect=RuntimeError("stream broke"))
        client = _gemini_client_with(sdk)

        collected = await _collect(client.stream([Message(role="user", content="go")]))

        assert collected[0].type == StreamEventType.MESSAGE_START
        assert collected[-1].type == StreamEventType.ERROR
        assert collected[-1].error is not None and "stream broke" in collected[-1].error
