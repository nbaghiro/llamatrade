"""Anthropic/Claude LLM client implementation.

This module provides the Anthropic-specific implementation of the LLM client,
supporting Claude models with streaming and tool use.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from src.llm.client import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    Message,
    StreamEvent,
    StreamEventType,
    ToolCall,
)

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    """Anthropic/Claude LLM client implementation."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """Initialize the Anthropic client.

        Args:
            config: Configuration for LLM calls.
        """
        super().__init__(config)
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create the Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable is required")

                self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError as e:
                raise ImportError(
                    "anthropic package is required. Install with: pip install anthropic"
                ) from e

        return self._client

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to Anthropic API format.

        Args:
            messages: List of Message objects.

        Returns:
            List of message dicts in Anthropic format.
        """
        result = []
        for msg in messages:
            if msg.role == "system":
                # System messages are handled separately
                continue

            converted: dict[str, Any] = {"role": msg.role}

            # Handle assistant messages with tool calls
            if msg.role == "assistant" and msg.tool_calls:
                content_blocks: list[dict[str, Any]] = []

                # Add text content if present
                if msg.content:
                    content_text = (
                        msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                    )
                    if content_text.strip():
                        content_blocks.append({"type": "text", "text": content_text})

                # Add tool_use blocks
                for tc in msg.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.input,
                        }
                    )

                converted["content"] = content_blocks

            # Handle tool results (multiple results in one message)
            elif msg.tool_results:
                content_blocks = []
                for tr in msg.tool_results:
                    content_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tr["tool_call_id"],
                            "content": tr["content"]
                            if isinstance(tr["content"], str)
                            else json.dumps(tr["content"]),
                        }
                    )
                converted["content"] = content_blocks

            # Handle single tool result (backwards compat)
            elif msg.tool_call_id:
                converted["content"] = [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content
                        if isinstance(msg.content, str)
                        else json.dumps(msg.content),
                    }
                ]

            # Handle regular content
            else:
                if isinstance(msg.content, str):
                    converted["content"] = msg.content
                else:
                    converted["content"] = msg.content

            result.append(converted)

        return result

    def _extract_system_prompt(self, messages: list[Message], override: str | None) -> str:
        """Extract system prompt from messages or use override.

        Args:
            messages: List of messages.
            override: Optional system prompt override.

        Returns:
            The system prompt to use.
        """
        if override:
            return override

        for msg in messages:
            if msg.role == "system":
                return msg.content if isinstance(msg.content, str) else json.dumps(msg.content)

        return self.config.system_prompt

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a completion using the Anthropic API.

        Args:
            messages: The conversation history.
            tools: Tool definitions to make available.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system_prompt: System prompt to use.

        Returns:
            The complete response including any tool calls.
        """
        client = self._get_client()

        # Prepare parameters
        api_messages = self._convert_messages(messages)
        system = self._extract_system_prompt(messages, system_prompt)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "messages": api_messages,
        }

        if system:
            kwargs["system"] = system

        if temperature is not None:
            kwargs["temperature"] = temperature
        elif self.config.temperature != 0.7:  # Only set if non-default
            kwargs["temperature"] = self.config.temperature

        effective_tools = tools or self.config.tools
        if effective_tools:
            kwargs["tools"] = effective_tools

        try:
            response = await client.messages.create(**kwargs)

            # Extract content and tool calls
            content_parts = []
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            input=block.input,
                        )
                    )

            return LLMResponse(
                content="\n".join(content_parts),
                tool_calls=tool_calls,
                stop_reason=response.stop_reason or "end_turn",
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        except Exception as e:
            logger.error("Anthropic API error: %s", e)
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
        """Stream a completion using the Anthropic API.

        Args:
            messages: The conversation history.
            tools: Tool definitions to make available.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system_prompt: System prompt to use.

        Yields:
            Stream events as they arrive.
        """
        client = self._get_client()

        # Prepare parameters
        api_messages = self._convert_messages(messages)
        system = self._extract_system_prompt(messages, system_prompt)

        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "messages": api_messages,
        }

        if system:
            kwargs["system"] = system

        if temperature is not None:
            kwargs["temperature"] = temperature
        elif self.config.temperature != 0.7:
            kwargs["temperature"] = self.config.temperature

        effective_tools = tools or self.config.tools
        if effective_tools:
            kwargs["tools"] = effective_tools

        try:
            # Track current tool use for accumulating input
            current_tool_id: str | None = None
            current_tool_name: str | None = None
            current_tool_input: str = ""

            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    # Handle different event types
                    if event.type == "message_start":
                        yield StreamEvent(type=StreamEventType.MESSAGE_START)

                    elif event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_id = block.id
                            current_tool_name = block.name
                            current_tool_input = ""
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_START,
                                tool_call=ToolCall(
                                    id=block.id,
                                    name=block.name,
                                    input={},
                                ),
                            )

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield StreamEvent(
                                type=StreamEventType.CONTENT_DELTA,
                                content=delta.text,
                            )
                        elif delta.type == "input_json_delta":
                            current_tool_input += delta.partial_json
                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_DELTA,
                                content=delta.partial_json,
                            )

                    elif event.type == "content_block_stop":
                        if current_tool_id and current_tool_name:
                            # Parse accumulated JSON input
                            try:
                                tool_input = (
                                    json.loads(current_tool_input) if current_tool_input else {}
                                )
                            except json.JSONDecodeError:
                                tool_input = {}

                            yield StreamEvent(
                                type=StreamEventType.TOOL_USE_END,
                                tool_call=ToolCall(
                                    id=current_tool_id,
                                    name=current_tool_name,
                                    input=tool_input,
                                ),
                            )
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_input = ""

                    elif event.type == "message_stop":
                        yield StreamEvent(
                            type=StreamEventType.MESSAGE_END,
                            stop_reason=stream.current_message_snapshot.stop_reason,
                        )

        except Exception as e:
            logger.error("Anthropic streaming error: %s", e)
            yield StreamEvent(
                type=StreamEventType.ERROR,
                error=str(e),
            )
