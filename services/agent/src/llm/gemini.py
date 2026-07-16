"""Google Gemini LLM client implementation.

Provides the Gemini-specific implementation of the LLM client, supporting
streaming, non-streaming completion, and function (tool) calling via the
``google-genai`` SDK.

Tools use the same JSON-Schema tool-definition format as the Anthropic client
(``{"name", "description", "input_schema"}``); the schema is passed straight
through to Gemini via ``FunctionDeclaration.parameters_json_schema``. Gemini
does not use tool-call ids the way Anthropic does, so results are matched back
to their calls by function name.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from llamatrade_telemetry import metrics

from src.llm.client import (
    LLMClient,
    LLMResponse,
    Message,
    StreamEvent,
    StreamEventType,
    ToolCall,
)

if TYPE_CHECKING:
    from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# Gemini names the assistant turn "model"; function responses ride on a "user" turn.
_ROLE_MODEL = "model"
_ROLE_USER = "user"


class GeminiClient(LLMClient):
    """Google Gemini LLM client implementation."""

    def __init__(self, config: Any = None) -> None:
        """Initialize the Gemini client.

        Args:
            config: Configuration for LLM calls.
        """
        super().__init__(config)
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create the google-genai client."""
        if self._client is None:
            try:
                from google.genai import Client
            except ImportError as e:
                raise ImportError(
                    "google-genai package is required. Install with: pip install google-genai"
                ) from e

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable is required")

            self._client = Client(api_key=api_key)

        return self._client

    def _call_id(self, gemini_id: str | None, name: str, index: int) -> str:
        """Return a stable id for a tool call.

        Gemini omits ids for non-parallel calls, so we synthesize one for the
        agent's internal bookkeeping. It is never sent back to Gemini (results
        are matched by function name).
        """
        return gemini_id or f"call_{name}_{index}"

    def _wrap_tool_response(self, content: str) -> dict[str, Any]:
        """Wrap a tool result string in the dict Gemini requires for a response."""
        try:
            parsed: Any = json.loads(content)
        except json.JSONDecodeError, TypeError:
            parsed = content
        return {"result": parsed}

    def _convert_messages(self, messages: list[Message]) -> list[genai_types.Content]:
        """Convert internal messages to google-genai ``Content`` objects."""
        from google.genai import types

        contents: list[types.Content] = []
        id_to_name: dict[str, str] = {}

        for msg in messages:
            if msg.role == "system":
                continue

            if msg.role == "assistant" and msg.tool_calls:
                parts: list[types.Part] = []
                if isinstance(msg.content, str) and msg.content.strip():
                    parts.append(types.Part(text=msg.content))
                for tc in msg.tool_calls:
                    id_to_name[tc.id] = tc.name
                    parts.append(
                        types.Part(function_call=types.FunctionCall(name=tc.name, args=tc.input))
                    )
                contents.append(types.Content(role=_ROLE_MODEL, parts=parts))

            elif msg.tool_results:
                result_parts: list[types.Part] = []
                for tr in msg.tool_results:
                    name = id_to_name.get(tr["tool_call_id"], "")
                    raw = tr["content"]
                    content_str = raw if isinstance(raw, str) else json.dumps(raw)
                    result_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response=self._wrap_tool_response(content_str),
                            )
                        )
                    )
                contents.append(types.Content(role=_ROLE_USER, parts=result_parts))

            else:
                role = _ROLE_MODEL if msg.role == "assistant" else _ROLE_USER
                text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                contents.append(types.Content(role=role, parts=[types.Part(text=text)]))

        return contents

    def _extract_system_prompt(self, messages: list[Message], override: str | None) -> str:
        """Extract the system prompt from messages or use the override."""
        if override:
            return override

        for msg in messages:
            if msg.role == "system":
                return msg.content if isinstance(msg.content, str) else json.dumps(msg.content)

        return self.config.system_prompt

    def _build_tools(self, tools: list[dict[str, Any]] | None) -> list[genai_types.Tool] | None:
        """Convert JSON-Schema tool definitions to Gemini function declarations."""
        from google.genai import types

        if not tools:
            return None

        declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters_json_schema=t.get("input_schema")
                or {"type": "object", "properties": {}},
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def _build_config(
        self,
        *,
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
        temperature: float | None,
        system: str,
    ) -> genai_types.GenerateContentConfig:
        """Assemble the ``GenerateContentConfig`` for a request."""
        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if system:
            config_kwargs["system_instruction"] = system

        gemini_tools = self._build_tools(tools)
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
            # We drive the tool loop manually; disable the SDK's auto-execution.
            config_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True
            )

        return types.GenerateContentConfig(**config_kwargs)

    def _stop_reason(self, finish_reason: Any, has_tool_calls: bool) -> str:
        """Map a Gemini finish reason to the internal stop-reason vocabulary."""
        if has_tool_calls:
            return "tool_use"
        if finish_reason is None:
            return "end_turn"
        name = getattr(finish_reason, "name", str(finish_reason))
        return "end_turn" if name == "STOP" else name.lower()

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a completion using the Gemini API."""
        client = self._get_client()

        contents = self._convert_messages(messages)
        system = self._extract_system_prompt(messages, system_prompt)
        effective_tools = tools if tools is not None else self.config.tools
        config = self._build_config(
            tools=effective_tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )

        model = self.config.model
        try:
            with metrics.agent.llm_latency.time(model=model):
                response = await client.aio.models.generate_content(
                    model=model, contents=contents, config=config
                )

            candidate = response.candidates[0] if response.candidates else None
            parts = (
                candidate.content.parts
                if candidate and candidate.content and candidate.content.parts
                else []
            )

            content_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            for idx, part in enumerate(parts):
                if part.text:
                    content_parts.append(part.text)
                if part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=self._call_id(fc.id, fc.name or "", idx),
                            name=fc.name or "",
                            input=dict(fc.args) if fc.args else {},
                        )
                    )

            usage = response.usage_metadata
            input_tokens = int(usage.prompt_token_count or 0) if usage else 0
            output_tokens = int(usage.candidates_token_count or 0) if usage else 0
            metrics.agent.llm_request(model=model, result="success")
            metrics.agent.llm_tokens(model=model, direction="input", count=input_tokens)
            metrics.agent.llm_tokens(model=model, direction="output", count=output_tokens)

            return LLMResponse(
                content="\n".join(content_parts),
                tool_calls=tool_calls,
                stop_reason=self._stop_reason(
                    candidate.finish_reason if candidate else None,
                    bool(tool_calls),
                ),
                usage={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

        except Exception as e:
            metrics.agent.llm_request(model=model, result="error")
            metrics.agent.llm_error(type=type(e).__name__)
            logger.error("Gemini API error: %s", e)
            raise

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a completion using the Gemini API."""
        client = self._get_client()

        contents = self._convert_messages(messages)
        system = self._extract_system_prompt(messages, system_prompt)
        effective_tools = tools if tools is not None else self.config.tools
        config = self._build_config(
            tools=effective_tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )

        model = self.config.model
        try:
            tool_index = 0
            last_finish_reason: Any = None
            usage: Any = None

            with metrics.agent.llm_latency.time(model=model):
                yield StreamEvent(type=StreamEventType.MESSAGE_START)

                stream = await client.aio.models.generate_content_stream(
                    model=model, contents=contents, config=config
                )
                async for chunk in stream:
                    candidate = chunk.candidates[0] if chunk.candidates else None
                    parts = (
                        candidate.content.parts
                        if candidate and candidate.content and candidate.content.parts
                        else []
                    )
                    for part in parts:
                        if part.text:
                            yield StreamEvent(
                                type=StreamEventType.CONTENT_DELTA,
                                content=part.text,
                            )
                        if part.function_call:
                            fc = part.function_call
                            # Gemini emits a function call whole (not incrementally),
                            # so start and end are yielded together.
                            call = ToolCall(
                                id=self._call_id(fc.id, fc.name or "", tool_index),
                                name=fc.name or "",
                                input=dict(fc.args) if fc.args else {},
                            )
                            tool_index += 1
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_START,
                                tool_call=ToolCall(id=call.id, name=call.name, input={}),
                            )
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_END,
                                tool_call=call,
                            )

                    if candidate and candidate.finish_reason:
                        last_finish_reason = candidate.finish_reason
                    if chunk.usage_metadata:
                        usage = chunk.usage_metadata

                if usage is not None:
                    metrics.agent.llm_tokens(
                        model=model,
                        direction="input",
                        count=int(usage.prompt_token_count or 0),
                    )
                    metrics.agent.llm_tokens(
                        model=model,
                        direction="output",
                        count=int(usage.candidates_token_count or 0),
                    )

            yield StreamEvent(
                type=StreamEventType.MESSAGE_END,
                stop_reason=self._stop_reason(last_finish_reason, False),
            )
            metrics.agent.llm_request(model=model, result="success")

        except Exception as e:
            metrics.agent.llm_request(model=model, result="error")
            metrics.agent.llm_error(type=type(e).__name__)
            logger.error("Gemini streaming error: %s", e)
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=str(e),
            )
