"""Core agent service for message processing and orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import PendingArtifact
from llamatrade_proto.generated.agent_pb2 import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    STREAM_EVENT_TYPE_ARTIFACT_CREATED,
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
    STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
    STREAM_EVENT_TYPE_TOOL_CALL_START,
)

from src.llm import AnthropicClient, LLMConfig, Message, StreamEventType, ToolCall
from src.prompts.few_shot import get_few_shot_messages
from src.prompts.system import ContextData, MemorySummary, build_memory_hint, build_system_prompt
from src.tools.executor import get_executor

logger = logging.getLogger(__name__)

# Maximum iterations for tool execution loop
MAX_TOOL_ITERATIONS = 10


class AgentService:
    """Core orchestration service for the AI Strategy Agent.

    This service:
    - Builds conversation context for LLM calls
    - Executes tool calls from LLM responses
    - Manages the tool execution loop
    - Creates pending artifacts from generated strategies
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Initialize the agent service.

        Args:
            db: Async database session
            tenant_id: Current tenant UUID
            user_id: Current user UUID
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._llm_client: AnthropicClient | None = None
        self._executor = get_executor()

    @property
    def llm_client(self) -> AnthropicClient:
        """Get or create the LLM client."""
        if self._llm_client is None:
            config = LLMConfig(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0.3,  # Lower for consistent DSL generation
            )
            self._llm_client = AnthropicClient(config)
        return self._llm_client

    async def process_message(
        self,
        session_id: UUID,
        user_message: str,
        ui_context: dict[str, Any] | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[PendingArtifact]]:
        """Process a user message and return the agent response.

        This is the non-streaming version that returns the complete response.

        Args:
            session_id: Session UUID
            user_message: User's message content
            ui_context: Optional UI context data

        Returns:
            Tuple of (response content, tool calls, new artifacts)
        """
        # Collect all events from streaming
        response_content = ""
        tool_calls: list[dict[str, Any]] = []
        new_artifacts: list[PendingArtifact] = []

        async for event in self.stream_message(session_id, user_message, ui_context):
            event_type = event.get("type")
            if event_type == STREAM_EVENT_TYPE_CONTENT_DELTA:
                response_content += event.get("delta", "")
            elif event_type == STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE:
                tool_calls.append(
                    {
                        "name": event.get("tool_name"),
                        "result": event.get("tool_result"),
                    }
                )
            elif event_type == STREAM_EVENT_TYPE_ARTIFACT_CREATED:
                artifact = event.get("artifact")
                if artifact:
                    new_artifacts.append(artifact)

        return response_content, tool_calls, new_artifacts

    async def stream_message(
        self,
        session_id: UUID,
        user_message: str,
        ui_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a user message and stream the response.

        This is the streaming version that yields events as they occur.
        Each request is stateless - context is passed directly, not loaded from DB.

        Args:
            session_id: Session UUID
            user_message: User's message content
            ui_context: Optional UI context data (includes strategy_dsl)

        Yields:
            Stream events with type and data
        """
        try:
            # Build context from request data (no DB lookup needed for strategy)
            context_data = await self._build_context(session_id, ui_context)

            # Skip history loading - each request is fresh with full context
            # The UI doesn't persist history, so we don't load it
            history: list[dict[str, Any]] = []

            # Build messages for LLM
            messages = self._build_llm_messages(user_message, history, context_data)

            # Get tool definitions
            tool_definitions = self._executor.get_tool_definitions()

            # Tool execution loop
            iteration = 0
            full_response = ""

            while iteration < MAX_TOOL_ITERATIONS:
                iteration += 1
                current_content = ""
                tool_calls_in_response: list[dict[str, Any]] = []

                # Stream LLM response
                async for event in self.llm_client.stream(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                ):
                    if event.type == StreamEventType.CONTENT_DELTA:
                        current_content += event.content or ""
                        yield {
                            "type": STREAM_EVENT_TYPE_CONTENT_DELTA,
                            "delta": event.content,
                        }

                    elif event.type == StreamEventType.TOOL_USE_START:
                        if event.tool_call:
                            yield {
                                "type": STREAM_EVENT_TYPE_TOOL_CALL_START,
                                "tool_name": event.tool_call.name,
                            }

                    elif event.type == StreamEventType.TOOL_USE_END:
                        if event.tool_call:
                            tool_calls_in_response.append(
                                {
                                    "id": event.tool_call.id,
                                    "name": event.tool_call.name,
                                    "input": event.tool_call.input,
                                }
                            )

                    elif event.type == StreamEventType.ERROR:
                        yield {
                            "type": STREAM_EVENT_TYPE_ERROR,
                            "error": event.error,
                        }
                        return

                full_response += current_content

                # If no tool calls, we're done
                if not tool_calls_in_response:
                    break

                # Execute tool calls and add results to messages
                # IMPORTANT: Include tool_calls so the tool_result messages have matching tool_use blocks
                messages.append(
                    Message(
                        role="assistant",
                        content=current_content,
                        tool_calls=[
                            ToolCall(id=tc["id"], name=tc["name"], input=tc["input"])
                            for tc in tool_calls_in_response
                        ],
                    )
                )

                # Execute all tool calls and collect results
                tool_results: list[dict[str, Any]] = []
                for tool_call in tool_calls_in_response:
                    # Execute the tool
                    result = await self._executor.execute(
                        tool_name=tool_call["name"],
                        arguments=tool_call["input"],
                        tenant_id=self.tenant_id,
                        user_id=self.user_id,
                        session_id=session_id,
                    )

                    # Format result for LLM
                    result_str = self._executor.format_tool_result_for_llm(result)

                    yield {
                        "type": STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
                        "tool_name": tool_call["name"],
                        "tool_result": result_str[:500],  # Truncate for preview
                        "success": result.success,
                    }

                    # Collect tool result for adding to messages
                    tool_results.append(
                        {
                            "tool_call_id": tool_call["id"],
                            "content": result_str,
                        }
                    )

                    # Check if this is a strategy validation that succeeded
                    if tool_call["name"] == "validate_dsl" and result.success:
                        artifact = await self._maybe_create_artifact(
                            session_id=session_id,
                            validation_result=result.data,
                            dsl_code=tool_call["input"].get("dsl_code", ""),
                        )
                        if artifact:
                            yield {
                                "type": STREAM_EVENT_TYPE_ARTIFACT_CREATED,
                                "artifact": artifact,
                            }

                # Add all tool results as a single user message with multiple results
                # Anthropic API requires all tool_results to be in one user message
                messages.append(
                    Message(
                        role="user",
                        content="",  # Content is in tool_results
                        tool_results=tool_results,
                    )
                )

            # Store the assistant response
            await self._store_assistant_message(session_id, full_response)

            # Extract and store memories (fire-and-forget)
            asyncio.create_task(
                self._extract_and_store_memories(session_id, user_message, full_response)
            )

            yield {
                "type": STREAM_EVENT_TYPE_COMPLETE,
                "session_id": str(session_id),
            }

        except Exception as e:
            logger.exception("Error in stream_message: %s", e)
            yield {
                "type": STREAM_EVENT_TYPE_ERROR,
                "error": str(e),
            }

    async def _extract_and_store_memories(
        self,
        session_id: UUID,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Extract and store memory facts from conversation (background task).

        This runs as fire-and-forget to not block the response stream.

        Args:
            session_id: Session UUID
            user_message: User's message
            assistant_response: Agent's response
        """
        try:
            from src.services.extraction_service import ExtractionContext, extract_facts_heuristic
            from src.services.memory_service import MemoryService

            # Extract facts from user message only (user's preferences matter most)
            context = ExtractionContext(
                current_page=None,  # Could be passed from UI context
            )

            facts = extract_facts_heuristic(user_message, context)

            if not facts:
                return

            # Store extracted facts
            memory_service = MemoryService(
                db=self.db,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
            )

            await memory_service.store_facts(
                facts=facts,
                session_id=session_id,
            )

            logger.debug(
                "Extracted and stored %d memory facts from session %s",
                len(facts),
                session_id,
            )

        except Exception as e:
            # Don't fail the main flow for memory extraction errors
            logger.warning("Memory extraction failed: %s", e)

    def _build_llm_messages(
        self,
        user_message: str,
        history: list[dict[str, Any]],
        context_data: ContextData | None,
    ) -> list[Message]:
        """Build the full message list for LLM.

        Args:
            user_message: Current user message
            history: Conversation history
            context_data: Optional context data

        Returns:
            List of Message objects for LLM
        """
        messages: list[Message] = []

        # System prompt is passed separately to the LLM
        # But we build it here for reference
        self._current_system_prompt = build_system_prompt(context_data)

        # Add few-shot examples
        few_shot = get_few_shot_messages()
        for example in few_shot:
            messages.append(
                Message(
                    role=example["role"],
                    content=example["content"],
                )
            )

        # Add conversation history
        for msg in history:
            messages.append(
                Message(
                    role=msg["role"],
                    content=msg["content"],
                )
            )

        # Add current user message
        messages.append(Message(role="user", content=user_message))

        return messages

    async def _build_context(
        self,
        session_id: UUID,
        ui_context: dict[str, Any] | None = None,
    ) -> ContextData:
        """Build context data for the LLM call.

        Context data (strategy DSL, name) is passed directly from the frontend,
        not looked up from DB. This keeps each request stateless.

        Args:
            session_id: Session UUID
            ui_context: Optional UI context data (includes strategy_dsl, strategy_name)

        Returns:
            ContextData object
        """
        # Build ContextData from UI context - DSL is passed directly, no DB lookup
        context = ContextData(
            page=ui_context.get("page") if ui_context else None,
            strategy_name=ui_context.get("strategy_name") if ui_context else None,
            strategy_dsl=ui_context.get("strategy_dsl") if ui_context else None,
        )

        # Load memory hint for personalization
        memory_hint = await self._get_memory_hint()
        context.memory_hint = memory_hint

        # Fetch backtest context if viewing backtest results (still needed for metrics)
        if ui_context:
            backtest_id = ui_context.get("backtest_id")
            if backtest_id:
                backtest_data = await self._fetch_backtest_context(backtest_id)
                if backtest_data:
                    context.backtest_total_return = backtest_data.get("total_return")
                    context.backtest_sharpe_ratio = backtest_data.get("sharpe_ratio")
                    context.backtest_max_drawdown = backtest_data.get("max_drawdown")

        return context

    async def _get_memory_hint(self) -> str:
        """Get lightweight memory hint for system prompt.

        Returns:
            Memory hint string for system prompt injection
        """
        try:
            from src.services.memory_service import MemoryService

            memory_service = MemoryService(
                db=self.db,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
            )

            hint_data = await memory_service.get_memory_hint()

            memory_summary = MemorySummary(
                is_new_user=hint_data.is_new_user,
                session_count=hint_data.session_count,
                risk_tolerance=hint_data.risk_tolerance,
                goal_summary=hint_data.goal_summary,
                recent_strategies=hint_data.recent_strategies,
            )

            return build_memory_hint(memory_summary)

        except Exception as e:
            logger.warning("Failed to load memory hint: %s", e)
            # Return new user hint as fallback
            return build_memory_hint(None)

    async def _fetch_strategy_context(
        self,
        strategy_id: str,
    ) -> dict[str, Any] | None:
        """Fetch strategy data for context injection.

        Args:
            strategy_id: Strategy UUID string

        Returns:
            Strategy data dict or None
        """
        try:
            from src.tools.base import ToolContext
            from src.tools.strategy_tools import GetStrategyTool

            tool = GetStrategyTool()
            context = ToolContext(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                session_id=UUID("00000000-0000-0000-0000-000000000000"),  # Dummy
            )
            result = await tool.run({"strategy_id": strategy_id}, context)
            if result.success and result.data:
                return result.data
        except Exception as e:
            logger.warning("Failed to fetch strategy context: %s", e)
        return None

    async def _fetch_backtest_context(
        self,
        backtest_id: str,
    ) -> dict[str, Any] | None:
        """Fetch backtest data for context injection.

        Args:
            backtest_id: Backtest UUID string

        Returns:
            Backtest data dict or None
        """
        try:
            from src.tools.backtest_tools import GetBacktestResultsTool
            from src.tools.base import ToolContext

            tool = GetBacktestResultsTool()
            context = ToolContext(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                session_id=UUID("00000000-0000-0000-0000-000000000000"),  # Dummy
            )
            result = await tool.run({"backtest_id": backtest_id}, context)
            if result.success and result.data:
                return result.data
        except Exception as e:
            logger.warning("Failed to fetch backtest context: %s", e)
        return None

    async def _get_conversation_history(
        self,
        session_id: UUID,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent conversation history for context.

        Args:
            session_id: Session UUID
            limit: Maximum messages to include

        Returns:
            List of message dictionaries
        """
        from src.services.conversation_service import ConversationService

        conv_service = ConversationService(self.db)
        messages = await conv_service.get_messages(session_id, limit=limit)

        return [
            {
                "role": "user" if m.role == MESSAGE_ROLE_USER else "assistant",
                "content": m.content,
            }
            for m in messages
        ]

    async def _store_assistant_message(
        self,
        session_id: UUID,
        content: str,
    ) -> None:
        """Store the assistant's response message.

        Args:
            session_id: Session UUID
            content: Message content
        """
        from src.services.conversation_service import ConversationService

        conv_service = ConversationService(self.db)
        await conv_service.add_message(
            session_id=session_id,
            tenant_id=self.tenant_id,
            role=MESSAGE_ROLE_ASSISTANT,
            content=content,
        )

    async def _maybe_create_artifact(
        self,
        session_id: UUID,
        validation_result: dict[str, Any] | None,
        dsl_code: str,
    ) -> PendingArtifact | None:
        """Create a pending artifact if validation succeeded.

        Args:
            session_id: Session UUID
            validation_result: Result from validate_dsl tool
            dsl_code: The DSL code that was validated

        Returns:
            Created PendingArtifact or None
        """
        if not validation_result or not validation_result.get("valid"):
            return None

        # Extract strategy name and description from DSL
        name = self._extract_strategy_name(dsl_code)
        if not name:
            name = "Generated Strategy"

        description = self._extract_strategy_description(dsl_code)

        # Create the artifact
        from src.services.artifact_service import ArtifactService

        artifact_service = ArtifactService(self.db, self.tenant_id, self.user_id)

        return await artifact_service.create_strategy_artifact(
            session_id=session_id,
            name=name,
            description=description,
            dsl_code=dsl_code,
            symbols=validation_result.get("extracted_symbols", []),
        )

    def _extract_strategy_name(self, dsl_code: str) -> str | None:
        """Extract strategy name from DSL code.

        Args:
            dsl_code: DSL code string

        Returns:
            Strategy name or None
        """
        # Simple extraction: find (strategy "Name" ...)
        import re

        match = re.search(r'\(strategy\s+"([^"]+)"', dsl_code)
        if match:
            return match.group(1)
        return None

    def _extract_strategy_description(self, dsl_code: str) -> str | None:
        """Extract strategy description from DSL code.

        Args:
            dsl_code: DSL code string

        Returns:
            Strategy description or None
        """
        import re

        # Look for :description "..." in DSL
        match = re.search(r':description\s+"([^"]*)"', dsl_code)
        if match:
            return match.group(1)
        return None
