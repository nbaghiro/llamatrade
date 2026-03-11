"""Agent Connect servicer implementation.

This servicer implements the AgentService Protocol defined in agent_connect.py.
It handles session management, messaging, and artifact operations.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_proto.generated import agent_pb2, common_pb2
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

from src.grpc.error_handler import handle_service_errors, parse_uuid
from src.services.database import get_session_maker

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Nil UUID used to detect missing/invalid context
_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


def _validate_tenant_context(context: common_pb2.TenantContext) -> tuple[UUID, UUID]:
    """Validate and extract tenant_id and user_id from context.

    Raises:
        ConnectError: If context is invalid (empty or nil UUIDs)
    """
    if not context.tenant_id or not context.user_id:
        raise ConnectError(
            Code.UNAUTHENTICATED,
            "Valid tenant context is required",
        )

    try:
        tenant_id = UUID(context.tenant_id)
        user_id = UUID(context.user_id)
    except ValueError as e:
        raise ConnectError(
            Code.INVALID_ARGUMENT,
            f"Invalid UUID in context: {e}",
        )

    if tenant_id == _NIL_UUID or user_id == _NIL_UUID:
        raise ConnectError(
            Code.UNAUTHENTICATED,
            "Valid tenant context is required (nil UUID not allowed)",
        )

    return tenant_id, user_id


def _timestamp_to_proto(dt: datetime) -> common_pb2.Timestamp:
    """Convert datetime to proto Timestamp."""
    return common_pb2.Timestamp(seconds=int(dt.timestamp()))


class AgentServicer:
    """Connect servicer for the Agent service.

    Implements the AgentService Protocol defined in agent_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    def _get_db(self) -> AsyncSession:
        """Get a database session.

        Returns an AsyncSession that should be used with `async with`.
        The session automatically handles commit/rollback on exit.
        """
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        assert self._session_maker is not None
        return self._session_maker()

    # =========================================================================
    # Session Management
    # =========================================================================

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

        async with self._get_db() as db:
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
                created_at=_timestamp_to_proto(session.created_at),
                last_activity_at=_timestamp_to_proto(session.last_activity_at),
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

        async with self._get_db() as db:
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
                        created_at=_timestamp_to_proto(m.created_at),
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
                    created_at=_timestamp_to_proto(a.created_at),
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
                created_at=_timestamp_to_proto(session.created_at),
                last_activity_at=_timestamp_to_proto(session.last_activity_at),
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

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with self._get_db() as db:
            service = ConversationService(db)
            sessions, total = await service.list_sessions(
                tenant_id=tenant_id,
                user_id=user_id,
                status=request.status_filter if request.status_filter else None,
                page=page,
                page_size=page_size,
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return agent_pb2.ListSessionsResponse(
                sessions=[
                    agent_pb2.AgentSession(
                        id=str(s.id),
                        tenant_id=str(s.tenant_id),
                        user_id=str(s.user_id),
                        title=s.title or "",
                        status=s.status,
                        message_count=s.message_count,
                        created_at=_timestamp_to_proto(s.created_at),
                        last_activity_at=_timestamp_to_proto(s.last_activity_at),
                    )
                    for s in sessions
                ],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
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

        async with self._get_db() as db:
            service = ConversationService(db)
            success = await service.delete_session(tenant_id, session_id)

            if not success:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Session not found: {request.session_id}",
                )

            return agent_pb2.DeleteSessionResponse(success=True)

    # =========================================================================
    # Messaging
    # =========================================================================

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

        from src.services.agent_service import AgentService
        from src.services.conversation_service import ConversationService

        async with self._get_db() as db:
            conv_service = ConversationService(db)

            # Verify session exists and belongs to tenant
            session = await conv_service.get_session(tenant_id, session_id)
            if not session:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Session not found: {request.session_id}",
                )

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
            )

            # Store assistant message
            assistant_msg = await conv_service.add_message(
                session_id=session_id,
                tenant_id=tenant_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content=response_content,
                tool_calls=tool_calls,
            )

            # Convert messages to proto
            user_proto = agent_pb2.AgentMessage(
                id=str(user_msg.id),
                session_id=str(user_msg.session_id),
                role=user_msg.role,
                content=user_msg.content,
                created_at=_timestamp_to_proto(user_msg.created_at),
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
                created_at=_timestamp_to_proto(assistant_msg.created_at),
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
                    created_at=_timestamp_to_proto(a.created_at),
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

            from src.services.agent_service import AgentService
            from src.services.conversation_service import ConversationService

            async with self._get_db() as db:
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

                # Stream agent response
                agent_service = AgentService(db, tenant_id, user_id)
                full_content = ""

                async for event in agent_service.stream_message(
                    session_id=session_id,
                    user_message=request.content,
                    ui_context=ui_context,
                ):
                    event_type = event.get("type")
                    if event_type == STREAM_EVENT_TYPE_CONTENT_DELTA:
                        full_content += event.get("delta", "")
                        yield agent_pb2.AgentStreamEvent(
                            event_type=STREAM_EVENT_TYPE_CONTENT_DELTA,
                            session_id=str(session_id),
                            content_delta=event.get("delta", ""),
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
                                    created_at=_timestamp_to_proto(artifact.created_at),
                                ),
                            )
                    elif event_type == STREAM_EVENT_TYPE_ERROR:
                        yield agent_pb2.AgentStreamEvent(
                            event_type=STREAM_EVENT_TYPE_ERROR,
                            session_id=str(session_id),
                            error_message=event.get("error", "Unknown error"),
                        )
                    elif event_type == STREAM_EVENT_TYPE_COMPLETE:
                        # Completion event is handled after the loop
                        pass

                # Store assistant message
                assistant_msg = await conv_service.add_message(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    role=MESSAGE_ROLE_ASSISTANT,
                    content=full_content,
                )

                # Send completion event
                yield agent_pb2.AgentStreamEvent(
                    event_type=STREAM_EVENT_TYPE_COMPLETE,
                    session_id=str(session_id),
                    message_id=str(assistant_msg.id),
                )

        except ConnectError:
            raise
        except Exception as e:
            logger.exception("Error in stream_message")
            yield agent_pb2.AgentStreamEvent(
                event_type=STREAM_EVENT_TYPE_ERROR,
                session_id=request.session_id,
                error_message=f"Internal error: {type(e).__name__}",
            )

    # =========================================================================
    # Artifacts
    # =========================================================================

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

        async with self._get_db() as db:
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

    # =========================================================================
    # Context-Aware Suggestions
    # =========================================================================

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
