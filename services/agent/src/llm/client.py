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

# Provider selection is config-driven and defaults to Google Gemini.
DEFAULT_PROVIDER = "google"

# Default chat models per provider (used when AGENT_LLM_MODEL is unset).
_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "google": "gemini-2.5-flash",
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-sonnet-5",
}

# Fast/cheap models per provider for extraction and summarization.
_PROVIDER_FAST_MODELS: dict[str, str] = {
    "google": "gemini-2.5-flash-lite",
    "gemini": "gemini-2.5-flash-lite",
    "anthropic": "claude-haiku-4-5",
}


def get_provider() -> str:
    """Return the configured LLM provider (lowercased)."""
    return os.getenv("AGENT_LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def default_model() -> str:
    """Resolve the main chat model from env, falling back to the provider default."""
    override = os.getenv("AGENT_LLM_MODEL")
    if override:
        return override
    return _PROVIDER_DEFAULT_MODELS.get(get_provider(), _PROVIDER_DEFAULT_MODELS["google"])


def fast_model() -> str:
    """Resolve the fast/cheap model from env, falling back to the provider default."""
    override = os.getenv("AGENT_LLM_FAST_MODEL")
    if override:
        return override
    return _PROVIDER_FAST_MODELS.get(get_provider(), _PROVIDER_FAST_MODELS["google"])


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
            self.model = default_model()


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


def create_llm_client(config: LLMConfig | None = None) -> LLMClient:
    """Create an LLM client for the configured provider.

    Provider is selected by ``AGENT_LLM_PROVIDER`` (default ``google``). Anthropic
    remains selectable as a fallback. Provider modules are imported lazily so that
    only the selected provider's SDK needs to be installed.

    Args:
        config: Optional configuration; a default is used when omitted.

    Returns:
        A provider-specific ``LLMClient`` instance.
    """
    provider = get_provider()
    cfg = config or LLMConfig()

    if provider in ("google", "gemini"):
        from src.llm.gemini import GeminiClient

        return GeminiClient(cfg)
    if provider == "anthropic":
        from src.llm.anthropic import AnthropicClient

        return AnthropicClient(cfg)

    raise ValueError(f"Unsupported AGENT_LLM_PROVIDER: {provider!r} (supported: google, anthropic)")
