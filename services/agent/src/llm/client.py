"""LLM client abstraction for the agent service.

This module provides a base abstraction for LLM clients, supporting
both streaming and non-streaming responses with tool use.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(Enum):
    """Types of events that can be emitted during streaming."""

    CONTENT_DELTA = "content_delta"
    TOOL_USE_START = "tool_use_start"
    TOOL_USE_DELTA = "tool_use_delta"
    TOOL_USE_END = "tool_use_end"
    MESSAGE_START = "message_start"
    MESSAGE_END = "message_end"
    ERROR = "error"


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class StreamEvent:
    """An event emitted during streaming response."""

    type: StreamEventType
    content: str = ""
    tool_call: ToolCall | None = None
    error: str | None = None
    stop_reason: str | None = None


@dataclass
class LLMResponse:
    """Complete response from an LLM call."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class Message:
    """A message in the conversation."""

    role: str  # "user", "assistant", "system"
    content: str | list[dict[str, Any]]  # Can be string or content blocks
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None  # For single tool result (backwards compat)
    tool_results: list[dict[str, Any]] | None = None  # For multiple tool results


@dataclass
class LLMConfig:
    """Configuration for LLM calls."""

    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    system_prompt: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Set default model from environment if not specified."""
        if not self.model:
            self.model = os.getenv("AGENT_LLM_MODEL", "claude-sonnet-4-20250514")


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """Initialize the LLM client.

        Args:
            config: Configuration for LLM calls. If None, uses defaults.
        """
        self.config = config or LLMConfig()

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given messages.

        Args:
            messages: The conversation history.
            tools: Tool definitions to make available.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system_prompt: System prompt to use.

        Returns:
            The complete response including any tool calls.
        """

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a completion for the given messages.

        Args:
            messages: The conversation history.
            tools: Tool definitions to make available.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system_prompt: System prompt to use.

        Yields:
            Stream events as they arrive.
        """
        # This is needed to make this an async generator
        if False:
            yield StreamEvent(type=StreamEventType.CONTENT_DELTA)

    def with_config(self, **kwargs: Any) -> LLMClient:
        """Create a new client with updated configuration.

        Args:
            **kwargs: Configuration values to update.

        Returns:
            A new client with the updated configuration.
        """
        new_config = LLMConfig(
            model=kwargs.get("model", self.config.model),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            temperature=kwargs.get("temperature", self.config.temperature),
            system_prompt=kwargs.get("system_prompt", self.config.system_prompt),
            tools=kwargs.get("tools", self.config.tools),
        )
        return self.__class__(new_config)
