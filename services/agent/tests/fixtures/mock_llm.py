"""Mock LLM client for testing."""

from __future__ import annotations

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


class MockLLMClient(LLMClient):
    """Mock LLM client for testing.

    This client returns predefined responses based on message content,
    allowing tests to verify agent behavior without calling the real LLM.
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        responses: list[LLMResponse] | None = None,
    ) -> None:
        """Initialize the mock client.

        Args:
            config: Configuration (ignored in mock)
            responses: List of responses to return in order
        """
        super().__init__(config)
        self._responses = responses or []
        self._response_index = 0
        self._calls: list[dict[str, Any]] = []

    def add_response(self, response: LLMResponse) -> None:
        """Add a response to the queue.

        Args:
            response: Response to add
        """
        self._responses.append(response)

    def add_simple_response(
        self,
        content: str,
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        """Add a simple text response.

        Args:
            content: Response content
            tool_calls: Optional tool calls
        """
        self._responses.append(
            LLMResponse(
                content=content,
                tool_calls=tool_calls or [],
                stop_reason="end_turn" if not tool_calls else "tool_use",
            )
        )

    def add_tool_call_response(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        content: str = "",
    ) -> None:
        """Add a response with a tool call.

        Args:
            tool_name: Name of tool to call
            tool_input: Tool input arguments
            content: Optional text content
        """
        tool_call = ToolCall(
            id=f"call_{len(self._responses)}",
            name=tool_name,
            input=tool_input,
        )
        self._responses.append(
            LLMResponse(
                content=content,
                tool_calls=[tool_call],
                stop_reason="tool_use",
            )
        )

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Get recorded calls to the client."""
        return self._calls

    def reset(self) -> None:
        """Reset the mock state."""
        self._responses = []
        self._response_index = 0
        self._calls = []

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Return the next queued response.

        Args:
            messages: Messages (recorded but ignored)
            tools: Tools (recorded but ignored)
            max_tokens: Max tokens (ignored)
            temperature: Temperature (ignored)
            system_prompt: System prompt (recorded but ignored)

        Returns:
            Next queued LLMResponse
        """
        # Record the call
        self._calls.append(
            {
                "method": "complete",
                "messages": messages,
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )

        # Return next response or a default
        if self._response_index < len(self._responses):
            response = self._responses[self._response_index]
            self._response_index += 1
            return response

        # Default response
        return LLMResponse(
            content="I'm a mock LLM. No response was configured.",
            tool_calls=[],
            stop_reason="end_turn",
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream events from the next queued response.

        Args:
            messages: Messages (recorded but ignored)
            tools: Tools (recorded but ignored)
            max_tokens: Max tokens (ignored)
            temperature: Temperature (ignored)
            system_prompt: System prompt (recorded but ignored)

        Yields:
            StreamEvent objects
        """
        # Record the call
        self._calls.append(
            {
                "method": "stream",
                "messages": messages,
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )

        # Get the response to simulate streaming
        response = await self.complete(
            messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        # Undo the index increment since complete was called
        self._response_index -= 1
        self._calls.pop()

        # Actually get the response for streaming
        if self._response_index < len(self._responses):
            response = self._responses[self._response_index]
            self._response_index += 1

        # Emit message start
        yield StreamEvent(type=StreamEventType.MESSAGE_START)

        # Emit content in chunks
        if response.content:
            # Split into chunks of ~50 chars
            chunk_size = 50
            for i in range(0, len(response.content), chunk_size):
                chunk = response.content[i : i + chunk_size]
                yield StreamEvent(
                    type=StreamEventType.CONTENT_DELTA,
                    content=chunk,
                )

        # Emit tool calls
        for tool_call in response.tool_calls:
            yield StreamEvent(
                type=StreamEventType.TOOL_USE_START,
                tool_call=ToolCall(
                    id=tool_call.id,
                    name=tool_call.name,
                    input={},
                ),
            )
            yield StreamEvent(
                type=StreamEventType.TOOL_USE_END,
                tool_call=tool_call,
            )

        # Emit message end
        yield StreamEvent(
            type=StreamEventType.MESSAGE_END,
            stop_reason=response.stop_reason,
        )


def create_mock_llm(responses: list[dict[str, Any]] | None = None) -> MockLLMClient:
    """Create a mock LLM client with optional predefined responses.

    Args:
        responses: List of response dicts with 'content' and optional 'tool_calls'

    Returns:
        Configured MockLLMClient
    """
    client = MockLLMClient()

    if responses:
        for r in responses:
            tool_calls = None
            if "tool_calls" in r:
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", f"call_{i}"),
                        name=tc["name"],
                        input=tc.get("input", {}),
                    )
                    for i, tc in enumerate(r["tool_calls"])
                ]

            client.add_simple_response(
                content=r.get("content", ""),
                tool_calls=tool_calls,
            )

    return client
