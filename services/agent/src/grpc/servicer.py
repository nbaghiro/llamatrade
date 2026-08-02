"""Agent Connect servicer implementation.

This servicer implements the AgentService Protocol defined in agent_connect.py.
It handles session management, messaging, and artifact operations.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_common import RateLimiter, pagination_response, resolve_pagination
from llamatrade_common.connect import (
    handle_service_errors,
    parse_uuid,
    resolve_identity_connect,
)
from llamatrade_db import bind_tenant_guc, get_session_maker, tenant_session
from llamatrade_proto.generated import agent_pb2, common_pb2
from llamatrade_proto.generated.agent_pb2 import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    STREAM_EVENT_TYPE_ARTIFACT_CREATED,
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
    STREAM_EVENT_TYPE_THINKING_DELTA,
    STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
    STREAM_EVENT_TYPE_TOOL_CALL_START,
    STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED,
)
from llamatrade_proto.timestamps import to_proto_timestamp

from src.redis_client import get_redis

if TYPE_CHECKING:
    from llamatrade_db.models import AgentMessage

    from src.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

# Number of most-recent prior turns replayed into the LLM for a session.
HISTORY_MESSAGE_LIMIT = 40

# Per-tenant ceiling on LLM-calling RPCs (chat/tool turns), best-effort abuse and
# cost protection. Tunable via env; a true per-tenant cost quota is a follow-up.
LLM_RATE_LIMIT = int(os.getenv("AGENT_LLM_RATE_LIMIT", "30"))
LLM_RATE_WINDOW_SECONDS = int(os.getenv("AGENT_LLM_RATE_WINDOW_SECONDS", "60"))


def _history_from_messages(messages: list[AgentMessage]) -> list[dict[str, str]]:
    """Convert stored messages into role/content dicts for LLM replay."""
    role_map = {MESSAGE_ROLE_USER: "user", MESSAGE_ROLE_ASSISTANT: "assistant"}
    history: list[dict[str, str]] = []
    for message in messages:
        role = role_map.get(message.role)
        if role and message.content:
            history.append({"role": role, "content": message.content})
    return history


async def _load_history(
    conv_service: ConversationService, session_id: UUID
) -> list[dict[str, str]]:
    """Load the recent prior turns for LLM replay (windowed).

    Degrades to no history — rather than failing the user's message — if the
    lookup errors, so a history hiccup can't take down the conversation.
    """
    try:
        prior = await conv_service.get_recent_messages(session_id, limit=HISTORY_MESSAGE_LIMIT)
        return _history_from_messages(prior)
    except Exception:
        logger.exception("Failed to load conversation history for session %s", session_id)
        return []


def _validate_tenant_context(context: common_pb2.TenantContext) -> tuple[UUID, UUID]:
    """Verified ``(tenant_id, user_id)`` for the call.

    Derives identity from the authenticated principal (JWT via ``AuthMiddleware``),
    rejecting a request whose wire ``context`` tenant doesn't match the token.
    """
    return resolve_identity_connect(context)


def _parse_arguments_json(arguments_json: str) -> dict[str, Any]:
    """Tool arguments dict from the event's JSON payload (empty on malformed)."""
    if not arguments_json:
        return {}
    try:
        parsed = json.loads(arguments_json)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class AgentServicer:
    """Connect servicer for the Agent service.

    Implements the AgentService Protocol defined in agent_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        redis = get_redis()
        self._rate_limiter: RateLimiter | None = RateLimiter(redis) if redis is not None else None
        self._llm_rate_rules: tuple[tuple[int, int], ...] = (
            (LLM_RATE_LIMIT, LLM_RATE_WINDOW_SECONDS),
        )

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        """The session factory (lazily created; tests inject a test-DB factory)."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        return self._session_maker

    async def _enforce_llm_rate_limit(self, tenant_id: UUID) -> None:
        """Apply the per-tenant LLM ceiling; RESOURCE_EXHAUSTED when it trips.

        A no-op when Redis is unconfigured; a Redis outage fails open (the
        limiter's default) so an unavailable limiter cannot take the copilot down.
        """
        if self._rate_limiter is None:
            return
        key = f"agent:llm:{tenant_id}"
        for limit, window in self._llm_rate_rules:
            if not await self._rate_limiter.check_and_count(key, limit, window):
                raise ConnectError(
                    Code.RESOURCE_EXHAUSTED,
                    "Too many requests; slow down and retry shortly.",
                )

    # Session Management

    @handle_service_errors
    async def create_session(
        self,
        request: agent_pb2.CreateSessionRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.CreateSessionResponse:
        """Create a new agent conversation session."""
        tenant_id, user_id = _validate_tenant_context(request.context)

        # Create session in database
        from src.services.conversation_service import ConversationService

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ConversationService(db)
            session = await service.create_session(
                tenant_id=tenant_id,
                user_id=user_id,
                title=None,  # Title generated from first message
            )

            # Convert to proto
            proto_session = agent_pb2.AgentSession(
                id=str(session.id),
                tenant_id=str(session.tenant_id),
                user_id=str(session.user_id),
                title=session.title or "",
                status=session.status,
                message_count=session.message_count,
                created_at=to_proto_timestamp(session.created_at),
                last_activity_at=to_proto_timestamp(session.last_activity_at),
            )

            return agent_pb2.CreateSessionResponse(session=proto_session)

    @handle_service_errors
    async def get_session(
        self,
        request: agent_pb2.GetSessionRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.GetSessionResponse:
        """Get a session by ID with optional message history."""
        tenant_id, _ = _validate_tenant_context(request.context)
        session_id = parse_uuid(request.session_id, "session_id")

        from src.services.conversation_service import ConversationService

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ConversationService(db)
            session = await service.get_session(tenant_id, session_id)

            if not session:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Session not found: {request.session_id}",
                )

            # Get messages if requested
            messages: list[agent_pb2.AgentMessage] = []
            if request.include_messages:
                limit = request.message_limit if request.message_limit > 0 else 50
                db_messages = await service.get_messages(session_id, limit=limit)
                messages = [
                    agent_pb2.AgentMessage(
                        id=str(m.id),
                        session_id=str(m.session_id),
                        role=m.role,
                        content=m.content,
                        tool_calls=[
                            agent_pb2.ToolCall(
                                id=tc.get("id", ""),
                                name=tc.get("name", ""),
                                arguments_json=str(tc.get("arguments", {})),
                                result_json=str(tc.get("result", {})),
                                duration_ms=tc.get("duration_ms", 0),
                                success=tc.get("success", True),
                            )
                            for tc in (m.tool_calls_json or [])
                        ],
                        inline_artifact_ids=m.inline_artifact_ids or [],
                        thinking=m.thinking or "",
                        created_at=to_proto_timestamp(m.created_at),
                    )
                    for m in db_messages
                ]

            # Get pending artifacts
            artifacts: list[agent_pb2.PendingArtifact] = []
            db_artifacts = await service.get_pending_artifacts(session_id)
            artifacts = [
                agent_pb2.PendingArtifact(
                    id=str(a.id),
                    session_id=str(a.session_id),
                    artifact_type=a.artifact_type,
                    name=a.name,
                    description=a.description or "",
                    preview_json=json.dumps(a.artifact_json),
                    is_committed=a.is_committed,
                    committed_resource_id=str(a.committed_resource_id)
                    if a.committed_resource_id
                    else "",
                    created_at=to_proto_timestamp(a.created_at),
                )
                for a in db_artifacts
            ]

            proto_session = agent_pb2.AgentSession(
                id=str(session.id),
                tenant_id=str(session.tenant_id),
                user_id=str(session.user_id),
                title=session.title or "",
                status=session.status,
                message_count=session.message_count,
                created_at=to_proto_timestamp(session.created_at),
                last_activity_at=to_proto_timestamp(session.last_activity_at),
            )

            return agent_pb2.GetSessionResponse(
                session=proto_session,
                messages=messages,
                pending_artifacts=artifacts,
            )

    @handle_service_errors
    async def list_sessions(
        self,
        request: agent_pb2.ListSessionsRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.ListSessionsResponse:
        """List sessions for the current user."""
        tenant_id, user_id = _validate_tenant_context(request.context)

        from src.services.conversation_service import ConversationService

        page, page_size = resolve_pagination(request.pagination)

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ConversationService(db)
            sessions, total = await service.list_sessions(
                tenant_id=tenant_id,
                user_id=user_id,
                status=request.status_filter if request.status_filter else None,
                page=page,
                page_size=page_size,
            )

            return agent_pb2.ListSessionsResponse(
                sessions=[
                    agent_pb2.AgentSession(
                        id=str(s.id),
                        tenant_id=str(s.tenant_id),
                        user_id=str(s.user_id),
                        title=s.title or "",
                        status=s.status,
                        message_count=s.message_count,
                        created_at=to_proto_timestamp(s.created_at),
                        last_activity_at=to_proto_timestamp(s.last_activity_at),
                    )
                    for s in sessions
                ],
                pagination=common_pb2.PaginationResponse(
                    **pagination_response(total, page, page_size)
                ),
            )

    @handle_service_errors
    async def delete_session(
        self,
        request: agent_pb2.DeleteSessionRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.DeleteSessionResponse:
        """Delete a session and all its messages."""
        tenant_id, _ = _validate_tenant_context(request.context)
        session_id = parse_uuid(request.session_id, "session_id")

        from src.services.conversation_service import ConversationService

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ConversationService(db)
            success = await service.delete_session(tenant_id, session_id)

            if not success:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Session not found: {request.session_id}",
                )

            return agent_pb2.DeleteSessionResponse(success=True)

    # Messaging

    @handle_service_errors
    async def send_message(
        self,
        request: agent_pb2.SendMessageRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.SendMessageResponse:
        """Send a message and get a response (non-streaming)."""
        tenant_id, user_id = _validate_tenant_context(request.context)
        session_id = parse_uuid(request.session_id, "session_id")

        if not request.content:
            raise ConnectError(Code.INVALID_ARGUMENT, "Message content is required")

        await self._enforce_llm_rate_limit(tenant_id)

        from src.services.agent_service import AgentService
        from src.services.conversation_service import ConversationService

        async with tenant_session(tenant_id, self._maker()) as db:
            conv_service = ConversationService(db)

            # Verify session exists and belongs to tenant
            session = await conv_service.get_session(tenant_id, session_id)
            if not session:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Session not found: {request.session_id}",
                )

            # Load prior turns before persisting the new user message so the
            # current turn isn't duplicated in the replayed history.
            history = await _load_history(conv_service, session_id)

            # Store user message
            user_msg = await conv_service.add_message(
                session_id=session_id,
                tenant_id=tenant_id,
                role=MESSAGE_ROLE_USER,
                content=request.content,
            )

            # Get agent response
            agent_service = AgentService(db, tenant_id, user_id)

            # Build UI context
            ui_context = None
            if request.HasField("ui_context"):
                ui_context = {
                    "page": request.ui_context.page,
                    "strategy_id": request.ui_context.strategy_id,
                    "backtest_id": request.ui_context.backtest_id,
                }

            response_content, tool_calls, new_artifacts = await agent_service.process_message(
                session_id=session_id,
                user_message=request.content,
                ui_context=ui_context,
                history=history,
            )

            # Store assistant message (single writer for this turn)
            assistant_msg = await conv_service.add_message(
                session_id=session_id,
                tenant_id=tenant_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content=response_content,
                tool_calls=tool_calls,
                inline_artifact_ids=[str(a.id) for a in new_artifacts] or None,
            )

            # Convert messages to proto
            user_proto = agent_pb2.AgentMessage(
                id=str(user_msg.id),
                session_id=str(user_msg.session_id),
                role=user_msg.role,
                content=user_msg.content,
                created_at=to_proto_timestamp(user_msg.created_at),
            )

            assistant_proto = agent_pb2.AgentMessage(
                id=str(assistant_msg.id),
                session_id=str(assistant_msg.session_id),
                role=assistant_msg.role,
                content=assistant_msg.content,
                tool_calls=[
                    agent_pb2.ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments_json=str(tc.get("arguments", {})),
                        result_json=str(tc.get("result", {})),
                        duration_ms=tc.get("duration_ms", 0),
                        success=tc.get("success", True),
                    )
                    for tc in (assistant_msg.tool_calls_json or [])
                ],
                created_at=to_proto_timestamp(assistant_msg.created_at),
            )

            # Convert artifacts to proto
            artifact_protos = [
                agent_pb2.PendingArtifact(
                    id=str(a.id),
                    session_id=str(a.session_id),
                    artifact_type=a.artifact_type,
                    name=a.name,
                    description=a.description or "",
                    preview_json=json.dumps(a.artifact_json),
                    is_committed=a.is_committed,
                    created_at=to_proto_timestamp(a.created_at),
                )
                for a in new_artifacts
            ]

            return agent_pb2.SendMessageResponse(
                user_message=user_proto,
                assistant_message=assistant_proto,
                new_artifacts=artifact_protos,
            )

    async def stream_message(
        self,
        request: agent_pb2.SendMessageRequest,
        ctx: RequestContext[object, object],
    ) -> AsyncIterator[agent_pb2.AgentStreamEvent]:
        """Send a message and stream the response."""
        try:
            tenant_id, user_id = _validate_tenant_context(request.context)
            session_id = parse_uuid(request.session_id, "session_id")

            if not request.content:
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_ERROR,
                    session_id=str(session_id),
                    error_message="Message content is required",
                )
                return

            await self._enforce_llm_rate_limit(tenant_id)

            from src.services.agent_service import AgentService
            from src.services.conversation_service import ConversationService

            async with tenant_session(tenant_id, self._maker()) as db:
                conv_service = ConversationService(db)

                # Verify session exists
                session = await conv_service.get_session(tenant_id, session_id)
                if not session:
                    yield agent_pb2.AgentStreamEvent(
                        event_type=STREAM_EVENT_TYPE_ERROR,
                        session_id=str(session_id),
                        error_message=f"Session not found: {request.session_id}",
                    )
                    return

                # Load prior turns before persisting the new user message so the
                # current turn isn't duplicated in the replayed history.
                history = await _load_history(conv_service, session_id)

                # Store user message
                await conv_service.add_message(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    role=MESSAGE_ROLE_USER,
                    content=request.content,
                )

                # Build UI context with strategy DSL from request
                ui_context = {
                    "page": request.ui_context.page if request.HasField("ui_context") else "",
                    "strategy_id": request.ui_context.strategy_id
                    if request.HasField("ui_context")
                    else "",
                    "backtest_id": request.ui_context.backtest_id
                    if request.HasField("ui_context")
                    else "",
                    # Include strategy DSL directly from request (no DB lookup needed)
                    "strategy_dsl": request.strategy_dsl or "",
                    "strategy_name": request.strategy_name or "",
                }

                # Stream agent response; the relay maps events, persists the
                # assistant message once, and emits COMPLETE.
                agent_service = AgentService(db, tenant_id, user_id)
                events = agent_service.stream_message(
                    session_id=session_id,
                    user_message=request.content,
                    ui_context=ui_context,
                    history=history,
                )
                async for proto_event in self._relay_agent_events(
                    events, conv_service, session_id, tenant_id
                ):
                    yield proto_event

        except ConnectError:
            raise
        except Exception as e:
            logger.exception("Error in stream_message")
            yield agent_pb2.AgentStreamEvent(
                event_type=STREAM_EVENT_TYPE_ERROR,
                session_id=request.session_id,
                error_message=f"Internal error: {type(e).__name__}",
            )

    async def _relay_agent_events(
        self,
        events: AsyncIterator[dict[str, Any]],
        conv_service: ConversationService,
        session_id: UUID,
        tenant_id: UUID,
    ) -> AsyncIterator[agent_pb2.AgentStreamEvent]:
        """Map agent event dicts to proto stream events, then persist the
        assistant message once (single writer) and emit COMPLETE.

        Shared by ``stream_message`` and ``confirm_tool_call``.
        """
        full_content = ""
        full_thinking = ""
        inline_artifact_ids: list[str] = []
        proposed_tool_calls: list[dict[str, Any]] = []

        async for event in events:
            event_type = event.get("type")
            if event_type == STREAM_EVENT_TYPE_CONTENT_DELTA:
                full_content += event.get("delta", "")
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_CONTENT_DELTA,
                    session_id=str(session_id),
                    content_delta=event.get("delta", ""),
                )
            elif event_type == STREAM_EVENT_TYPE_THINKING_DELTA:
                full_thinking += event.get("delta", "")
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_THINKING_DELTA,
                    session_id=str(session_id),
                    thinking_delta=event.get("delta", ""),
                )
            elif event_type == STREAM_EVENT_TYPE_TOOL_CALL_START:
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_TOOL_CALL_START,
                    session_id=str(session_id),
                    tool_name=event.get("tool_name", ""),
                    tool_status="running",
                )
            elif event_type == STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE:
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_TOOL_CALL_COMPLETE,
                    session_id=str(session_id),
                    tool_name=event.get("tool_name", ""),
                    tool_status="complete",
                    tool_result_preview=event.get("tool_result", ""),
                )
            elif event_type == STREAM_EVENT_TYPE_ARTIFACT_CREATED:
                artifact = event.get("artifact")
                if artifact:
                    inline_artifact_ids.append(str(artifact.id))
                    yield agent_pb2.AgentStreamEvent(
                        event_type=STREAM_EVENT_TYPE_ARTIFACT_CREATED,
                        session_id=str(session_id),
                        artifact=agent_pb2.PendingArtifact(
                            id=str(artifact.id),
                            session_id=str(artifact.session_id),
                            artifact_type=artifact.artifact_type,
                            name=artifact.name,
                            description=artifact.description or "",
                            preview_json=json.dumps(artifact.artifact_json),
                            is_committed=artifact.is_committed,
                            created_at=to_proto_timestamp(artifact.created_at),
                        ),
                    )
            elif event_type == STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED:
                # Persisted with the assistant message; ConfirmToolCall executes
                # this stored proposal, never the client's echo.
                proposed_tool_calls.append(
                    {
                        "id": event.get("confirmation_id", ""),
                        "name": event.get("tool_name", ""),
                        "arguments": _parse_arguments_json(event.get("arguments_json", "")),
                        "status": "proposed",
                    }
                )
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED,
                    session_id=str(session_id),
                    tool_name=event.get("tool_name", ""),
                    tool_arguments_json=event.get("arguments_json", ""),
                    confirmation_id=event.get("confirmation_id", ""),
                )
            elif event_type == STREAM_EVENT_TYPE_ERROR:
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_ERROR,
                    session_id=str(session_id),
                    error_message=event.get("error", "Unknown error"),
                )
            elif event_type == STREAM_EVENT_TYPE_COMPLETE:
                # Completion event is emitted after the assistant message is stored.
                pass

        # Store assistant message (single writer for this turn).
        assistant_msg = await conv_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_ASSISTANT,
            content=full_content,
            tool_calls=proposed_tool_calls or None,
            inline_artifact_ids=inline_artifact_ids or None,
            thinking=full_thinking.strip() or None,
        )

        yield agent_pb2.AgentStreamEvent(
            event_type=STREAM_EVENT_TYPE_COMPLETE,
            session_id=str(session_id),
            message_id=str(assistant_msg.id),
        )

    async def confirm_tool_call(
        self,
        request: agent_pb2.ConfirmToolCallRequest,
        ctx: RequestContext[object, object],
    ) -> AsyncIterator[agent_pb2.AgentStreamEvent]:
        """Approve or deny a proposed tool call, then resume the agent turn.

        Executes the proposal persisted with the assistant message, looked up
        by ``confirmation_id`` — the client-echoed arguments are ignored and a
        mismatched echoed tool name is rejected.
        """
        try:
            tenant_id, user_id = _validate_tenant_context(request.context)
            session_id = parse_uuid(request.session_id, "session_id")

            if not request.confirmation_id:
                raise ConnectError(Code.INVALID_ARGUMENT, "confirmation_id is required")

            await self._enforce_llm_rate_limit(tenant_id)

            from src.services.agent_service import AgentService
            from src.services.conversation_service import ConversationService

            async with tenant_session(tenant_id, self._maker()) as db:
                # _consume_proposal commits mid-RPC to release the row lock,
                # which clears the transaction-local tenant GUC; bind it durably
                # so the post-commit history read, resume, and single-writer
                # persist stay tenant-scoped under the RLS role.
                bind_tenant_guc(db, tenant_id)
                conv_service = ConversationService(db)

                session = await conv_service.get_session(tenant_id, session_id)
                if not session:
                    yield agent_pb2.AgentStreamEvent(
                        event_type=STREAM_EVENT_TYPE_ERROR,
                        session_id=str(session_id),
                        error_message=f"Session not found: {request.session_id}",
                    )
                    return

                proposal = await self._consume_proposal(
                    conv_service, session_id, request.confirmation_id, request.tool_name
                )

                history = await _load_history(conv_service, session_id)

                agent_service = AgentService(db, tenant_id, user_id)
                events = agent_service.resume_with_tool(
                    session_id=session_id,
                    tool_name=proposal["name"],
                    arguments_json=json.dumps(proposal["arguments"], default=str),
                    approved=request.approved,
                    history=history,
                )
                async for proto_event in self._relay_agent_events(
                    events, conv_service, session_id, tenant_id
                ):
                    yield proto_event

        except ConnectError:
            raise
        except Exception as e:
            logger.exception("Error in confirm_tool_call")
            yield agent_pb2.AgentStreamEvent(
                event_type=STREAM_EVENT_TYPE_ERROR,
                session_id=request.session_id,
                error_message=f"Internal error: {type(e).__name__}",
            )

    async def _consume_proposal(
        self,
        conv_service: ConversationService,
        session_id: UUID,
        confirmation_id: str,
        client_tool_name: str,
    ) -> dict[str, Any]:
        """Find the stored proposal for ``confirmation_id`` and mark it consumed.

        The owning message row is locked FOR UPDATE for the whole read-modify-write
        so two concurrent confirmations of one id serialize: the loser blocks, then
        re-reads the consumed status and is refused. Raises INVALID_ARGUMENT for an
        unknown id, an already-consumed proposal, or a client-echoed tool name that
        mismatches the stored one.
        """
        message = await conv_service.lock_message_with_proposal(session_id, confirmation_id)
        if message is None:
            raise ConnectError(Code.INVALID_ARGUMENT, f"Unknown confirmation_id: {confirmation_id}")
        calls = message.tool_calls_json or []
        for index, call in enumerate(calls):
            if call.get("id") != confirmation_id:
                continue
            if call.get("status") == "consumed":
                raise ConnectError(
                    Code.INVALID_ARGUMENT,
                    f"Tool call already confirmed: {confirmation_id}",
                )
            stored_name = str(call.get("name", ""))
            if client_tool_name and client_tool_name != stored_name:
                raise ConnectError(
                    Code.INVALID_ARGUMENT,
                    "tool_name does not match the proposed tool call",
                )
            # New list assignment so the JSONB column change is tracked.
            updated = [dict(c) for c in calls]
            updated[index]["status"] = "consumed"
            message.tool_calls_json = updated
            await conv_service.db.commit()
            arguments = call.get("arguments")
            return {
                "name": stored_name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        raise ConnectError(Code.INVALID_ARGUMENT, f"Unknown confirmation_id: {confirmation_id}")

    # Artifacts

    @handle_service_errors
    async def commit_artifact(
        self,
        request: agent_pb2.CommitArtifactRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.CommitArtifactResponse:
        """Commit a pending artifact to create the actual resource."""
        tenant_id, user_id = _validate_tenant_context(request.context)
        artifact_id = parse_uuid(request.artifact_id, "artifact_id")

        logger.info(
            "CommitArtifact request: artifact_id=%s, tenant_id=%s, user_id=%s",
            artifact_id,
            tenant_id,
            user_id,
        )

        from src.services.artifact_service import ArtifactService

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ArtifactService(db, tenant_id, user_id)

            # Get overrides from proto map
            overrides = dict(request.overrides) if request.overrides else None

            result = await service.commit_artifact(artifact_id, overrides)

            if not result:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Artifact not found or already committed: {request.artifact_id}",
                )

            return agent_pb2.CommitArtifactResponse(
                success=True,
                resource_id=str(result["resource_id"]),
                resource_type=result["resource_type"],
            )

    # Context-Aware Suggestions

    @handle_service_errors
    async def get_suggested_prompts(
        self,
        request: agent_pb2.GetSuggestedPromptsRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.GetSuggestedPromptsResponse:
        """Get context-aware suggested prompts."""
        _validate_tenant_context(request.context)

        from src.prompts.context import get_suggested_actions

        page = request.ui_context.page if request.HasField("ui_context") else None

        # Build context for suggestions
        context = {
            "page": page,
            "strategy_id": request.ui_context.strategy_id
            if request.HasField("ui_context")
            else None,
            "backtest_id": request.ui_context.backtest_id
            if request.HasField("ui_context")
            else None,
        }

        prompts = get_suggested_actions(page or "dashboard", context)

        return agent_pb2.GetSuggestedPromptsResponse(prompts=prompts)

    @handle_service_errors
    async def get_artifact(
        self,
        request: agent_pb2.GetArtifactRequest,
        ctx: RequestContext[object, object],
    ) -> agent_pb2.GetArtifactResponse:
        """Get a pending artifact by ID."""
        tenant_id, user_id = _validate_tenant_context(request.context)
        artifact_id = parse_uuid(request.artifact_id, "artifact_id")

        from src.services.artifact_service import ArtifactService

        async with tenant_session(tenant_id, self._maker()) as db:
            service = ArtifactService(db, tenant_id, user_id)
            artifact = await service.get_artifact(artifact_id)

            if not artifact:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Artifact not found: {request.artifact_id}",
                )

            return agent_pb2.GetArtifactResponse(
                artifact=agent_pb2.PendingArtifact(
                    id=str(artifact.id),
                    session_id=str(artifact.session_id),
                    artifact_type=artifact.artifact_type,
                    name=artifact.name,
                    description=artifact.description or "",
                    preview_json=json.dumps(artifact.artifact_json),
                    is_committed=artifact.is_committed,
                    committed_resource_id=str(artifact.committed_resource_id)
                    if artifact.committed_resource_id
                    else "",
                    created_at=to_proto_timestamp(artifact.created_at),
                ),
            )
