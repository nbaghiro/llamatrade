"""Core agent service for message processing and orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import PendingArtifact
from llamatrade_proto.generated.agent_pb2 import (
    STREAM_EVENT_TYPE_ARTIFACT_CREATED,
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
    STREAM_EVENT_TYPE_THINKING_DELTA,
    STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
    STREAM_EVENT_TYPE_TOOL_CALL_START,
    STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED,
)

from src.llm import LLMClient, LLMConfig, Message, StreamEventType, ToolCall, create_llm_client
from src.llm.thinking import THINKING, ThinkingSplitter
from src.prompts.few_shot import get_few_shot_messages
from src.prompts.system import ContextData, MemorySummary, build_memory_hint, build_system_prompt
from src.tools.executor import get_executor

logger = logging.getLogger(__name__)

# Maximum iterations for tool execution loop
MAX_TOOL_ITERATIONS = 10


def _route_text_segments(
    segments: list[tuple[str, str]],
) -> list[tuple[dict[str, Any], str]]:
    """Map splitter (channel, text) segments to (stream-event, answer-text) pairs.

    The second element is the text to fold into the persisted answer — empty for
    thinking segments so reasoning never leaks into the assistant message content.
    """
    routed: list[tuple[dict[str, Any], str]] = []
    for channel, text in segments:
        if channel == THINKING:
            routed.append(({"type": STREAM_EVENT_TYPE_THINKING_DELTA, "delta": text}, ""))
        else:
            routed.append(({"type": STREAM_EVENT_TYPE_CONTENT_DELTA, "delta": text}, text))
    return routed


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
        self._llm_client: LLMClient | None = None
        self._executor = get_executor()
        self._current_system_prompt = ""

    @property
    def llm_client(self) -> LLMClient:
        """Get or create the LLM client for the configured provider."""
        if self._llm_client is None:
            config = LLMConfig(
                max_tokens=4096,
                temperature=0.3,  # Lower for consistent DSL generation
            )
            self._llm_client = create_llm_client(config)
        return self._llm_client

    async def process_message(
        self,
        session_id: UUID,
        user_message: str,
        ui_context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], list[PendingArtifact]]:
        """Process a user message and return the agent response.

        This is the non-streaming version that returns the complete response.

        Args:
            session_id: Session UUID
            user_message: User's message content
            ui_context: Optional UI context data
            history: Prior conversation turns to replay (role/content dicts)

        Returns:
            Tuple of (response content, tool calls, new artifacts)
        """
        # Collect all events from streaming
        response_content = ""
        tool_calls: list[dict[str, Any]] = []
        new_artifacts: list[PendingArtifact] = []

        async for event in self.stream_message(session_id, user_message, ui_context, history):
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
        history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a user message and stream the response.

        This is the streaming version that yields events as they occur. Prior
        conversation turns are supplied by the caller (loaded before the current
        user message was persisted, so it isn't duplicated here).

        Args:
            session_id: Session UUID
            user_message: User's message content
            ui_context: Optional UI context data (includes strategy_dsl)
            history: Prior conversation turns to replay (role/content dicts)

        Yields:
            Stream events with type and data
        """
        try:
            # Build context from request data (no DB lookup needed for strategy)
            context_data = await self._build_context(session_id, ui_context)

            # Build messages for LLM (few-shot + prior turns + current message)
            messages = self._build_llm_messages(user_message, history or [], context_data)

            # Get tool definitions
            tool_definitions = self._executor.get_tool_definitions()

            # Tool execution loop
            iteration = 0
            full_response = ""

            while iteration < MAX_TOOL_ITERATIONS:
                iteration += 1
                current_content = ""
                splitter = ThinkingSplitter()
                tool_calls_in_response: list[dict[str, Any]] = []

                # Stream LLM response
                async for event in self.llm_client.stream(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                    system_prompt=self._current_system_prompt,
                ):
                    if event.type == StreamEventType.CONTENT_DELTA:
                        for stream_event, answer_text in _route_text_segments(
                            splitter.feed(event.content or "")
                        ):
                            current_content += answer_text
                            yield stream_event

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

                # Emit any text held back for a partial tag at stream end.
                for stream_event, answer_text in _route_text_segments(splitter.flush()):
                    current_content += answer_text
                    yield stream_event

                full_response += current_content

                # If no tool calls, we're done
                if not tool_calls_in_response:
                    break

                # Include tool_calls so the tool_result messages have matching tool_use blocks.
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
                awaiting_confirmation = False
                for tool_call in tool_calls_in_response:
                    # Write actions are proposed, not auto-run: emit a confirmation
                    # request and halt. The user approves via ConfirmToolCall, which
                    # resumes the turn and executes the tool.
                    if self._executor.requires_confirmation(tool_call["name"]):
                        yield {
                            "type": STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED,
                            "tool_name": tool_call["name"],
                            "arguments_json": json.dumps(tool_call["input"], default=str),
                            "confirmation_id": tool_call["id"],
                        }
                        awaiting_confirmation = True
                        break

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

                # Turn paused for user approval of a proposed write action.
                if awaiting_confirmation:
                    break

                # Anthropic API requires all tool_results in one user message.
                messages.append(
                    Message(
                        role="user",
                        content="",  # Content is in tool_results
                        tool_results=tool_results,
                    )
                )

            # The caller persists the assistant message (with turn artifact links).

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

    async def resume_with_tool(
        self,
        session_id: UUID,
        tool_name: str,
        arguments_json: str,
        approved: bool,
        history: list[dict[str, Any]] | None = None,
        ui_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume a turn after the user approves/denies a proposed tool call.

        On approval, executes the (confirmation-gated) tool and streams a
        plain-language follow-up. On denial, streams a brief acknowledgement.
        Either way the caller persists the resulting assistant message.

        Args:
            session_id: Session UUID
            tool_name: Proposed tool name (echoed back by the client)
            arguments_json: Proposed tool arguments as JSON (echoed back)
            approved: Whether the user approved the action
            history: Prior conversation turns to replay
            ui_context: Optional UI context data

        Yields:
            Stream events with type and data
        """
        try:
            if not approved:
                yield {
                    "type": STREAM_EVENT_TYPE_CONTENT_DELTA,
                    "delta": (
                        "Okay — I've held off on that action. Tell me if you'd like "
                        "to adjust it or try something else."
                    ),
                }
                yield {"type": STREAM_EVENT_TYPE_COMPLETE, "session_id": str(session_id)}
                return

            # Only confirmation-gated tools may be resumed this way.
            if not self._executor.requires_confirmation(tool_name):
                yield {
                    "type": STREAM_EVENT_TYPE_ERROR,
                    "error": f"Tool '{tool_name}' is not a confirmable action",
                }
                return

            arguments = json.loads(arguments_json) if arguments_json else {}

            yield {"type": STREAM_EVENT_TYPE_TOOL_CALL_START, "tool_name": tool_name}
            result = await self._executor.execute(
                tool_name=tool_name,
                arguments=arguments,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                session_id=session_id,
            )
            result_str = self._executor.format_tool_result_for_llm(result)
            yield {
                "type": STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
                "tool_name": tool_name,
                "tool_result": result_str[:500],
                "success": result.success,
            }

            # Feed the result back to the LLM for a plain-language summary. No
            # further tools this pass, so an approved action can't chain into
            # another unconfirmed one.
            context_data = await self._build_context(session_id, ui_context)
            resume_prompt = (
                f"The user approved running the `{tool_name}` tool. Here is its result:\n\n"
                f"{result_str}\n\n"
                "Summarize the outcome for the user in plain language and suggest a "
                "sensible next step."
            )
            messages = self._build_llm_messages(resume_prompt, history or [], context_data)

            splitter = ThinkingSplitter()
            async for event in self.llm_client.stream(
                messages=messages,
                tools=None,
                system_prompt=self._current_system_prompt,
            ):
                if event.type == StreamEventType.CONTENT_DELTA:
                    for stream_event, _ in _route_text_segments(splitter.feed(event.content or "")):
                        yield stream_event
                elif event.type == StreamEventType.ERROR:
                    yield {"type": STREAM_EVENT_TYPE_ERROR, "error": event.error}
                    return

            for stream_event, _ in _route_text_segments(splitter.flush()):
                yield stream_event

            yield {"type": STREAM_EVENT_TYPE_COMPLETE, "session_id": str(session_id)}

        except Exception as e:
            logger.exception("Error in resume_with_tool: %s", e)
            yield {"type": STREAM_EVENT_TYPE_ERROR, "error": str(e)}

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
            from llamatrade_db import tenant_session

            from src.services.extraction_service import ExtractionContext, extract_facts_heuristic
            from src.services.memory_service import MemoryService

            # Extract facts from user message only (user's preferences matter most)
            context = ExtractionContext(
                current_page=None,  # Could be passed from UI context
            )

            facts = extract_facts_heuristic(user_message, context)

            if not facts:
                return

            # Fresh tenant-scoped session: this runs fire-and-forget after the
            # request session closes, and the RLS GUC must be bound for the
            # agent_memory_facts INSERT to pass WITH CHECK.
            async with tenant_session(self.tenant_id) as db:
                memory_service = MemoryService(
                    db=db,
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                )
                await memory_service.store_facts(
                    facts=facts,
                    session_id=session_id,
                )
                await db.commit()

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

        Few-shot examples, prior conversation turns, and the current user
        message are concatenated, then consecutive same-role turns are merged so
        providers that require strict user/assistant alternation (e.g. Anthropic)
        accept the request regardless of where the history window starts.

        Args:
            user_message: Current user message
            history: Conversation history (role/content dicts)
            context_data: Optional context data

        Returns:
            List of Message objects for LLM
        """
        # Built here for reference; passed separately to the LLM.
        self._current_system_prompt = build_system_prompt(context_data)

        raw: list[Message] = []

        # Few-shot examples
        for example in get_few_shot_messages():
            raw.append(Message(role=example["role"], content=example["content"]))

        # Prior conversation history
        for msg in history:
            raw.append(Message(role=msg["role"], content=msg["content"]))

        # Current user message
        raw.append(Message(role="user", content=user_message))

        # Coalesce consecutive same-role turns to preserve strict alternation.
        messages: list[Message] = []
        for msg in raw:
            if messages and messages[-1].role == msg.role:
                messages[-1] = Message(
                    role=msg.role,
                    content=f"{messages[-1].content}\n\n{msg.content}",
                )
            else:
                messages.append(msg)

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
