"""Tests for the AgentServicer gRPC endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_proto.generated import agent_pb2, common_pb2
from llamatrade_proto.generated.agent_pb2 import (
    AGENT_SESSION_STATUS_ACTIVE,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    STREAM_EVENT_TYPE_ARTIFACT_CREATED,
    STREAM_EVENT_TYPE_COMPLETE,
    STREAM_EVENT_TYPE_CONTENT_DELTA,
    STREAM_EVENT_TYPE_ERROR,
)

from src.grpc.servicer import (
    HISTORY_MESSAGE_LIMIT,
    AgentServicer,
    _history_from_messages,
    _validate_tenant_context,
)

# =============================================================================
# Helper Functions
# =============================================================================


def make_mock_db_session() -> MagicMock:
    """Create a mock database session that works as async context manager."""
    mock_db = AsyncMock()

    @asynccontextmanager
    async def mock_session_context():
        yield mock_db

    return mock_session_context()


def make_mock_session(
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str = "",
    status: int = AGENT_SESSION_STATUS_ACTIVE,
    message_count: int = 0,
) -> MagicMock:
    """Create a mock AgentSession."""
    mock = MagicMock()
    mock.id = session_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.title = title
    mock.status = status
    mock.message_count = message_count
    mock.created_at = MagicMock()
    mock.created_at.timestamp.return_value = datetime.now(UTC).timestamp()
    mock.last_activity_at = MagicMock()
    mock.last_activity_at.timestamp.return_value = datetime.now(UTC).timestamp()
    return mock


def make_mock_message(
    message_id: UUID | None = None,
    session_id: UUID | None = None,
    role: int = MESSAGE_ROLE_USER,
    content: str = "Test message",
) -> MagicMock:
    """Create a mock AgentMessage."""
    mock = MagicMock()
    mock.id = message_id or uuid4()
    mock.session_id = session_id or uuid4()
    mock.role = role
    mock.content = content
    mock.tool_calls_json = None
    mock.created_at = MagicMock()
    mock.created_at.timestamp.return_value = datetime.now(UTC).timestamp()
    return mock


# =============================================================================
# Context Validation Tests
# =============================================================================


class TestValidateTenantContext:
    """Tests for tenant context validation helper."""

    def test_validate_context_valid(self) -> None:
        """Test that valid UUIDs are accepted."""
        context = common_pb2.TenantContext(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
        )

        tenant_id, user_id = _validate_tenant_context(context)

        assert isinstance(tenant_id, UUID)
        assert isinstance(user_id, UUID)

    def test_validate_context_missing_tenant(self) -> None:
        """Test that missing tenant_id raises UNAUTHENTICATED."""
        context = common_pb2.TenantContext(
            tenant_id="",
            user_id=str(uuid4()),
        )

        with pytest.raises(ConnectError) as exc_info:
            _validate_tenant_context(context)

        assert exc_info.value.code == Code.UNAUTHENTICATED

    def test_validate_context_missing_user(self) -> None:
        """Test that missing user_id raises UNAUTHENTICATED."""
        context = common_pb2.TenantContext(
            tenant_id=str(uuid4()),
            user_id="",
        )

        with pytest.raises(ConnectError) as exc_info:
            _validate_tenant_context(context)

        assert exc_info.value.code == Code.UNAUTHENTICATED

    def test_validate_context_nil_uuid(self) -> None:
        """Test that nil UUID raises UNAUTHENTICATED."""
        nil_uuid = "00000000-0000-0000-0000-000000000000"
        context = common_pb2.TenantContext(
            tenant_id=nil_uuid,
            user_id=str(uuid4()),
        )

        with pytest.raises(ConnectError) as exc_info:
            _validate_tenant_context(context)

        assert exc_info.value.code == Code.UNAUTHENTICATED
        assert "nil UUID" in str(exc_info.value.message)

    def test_validate_context_invalid_uuid(self) -> None:
        """Test that invalid UUID format raises INVALID_ARGUMENT."""
        context = common_pb2.TenantContext(
            tenant_id="not-a-uuid",
            user_id=str(uuid4()),
        )

        with pytest.raises(ConnectError) as exc_info:
            _validate_tenant_context(context)

        assert exc_info.value.code == Code.INVALID_ARGUMENT


# =============================================================================
# Create Session Tests
# =============================================================================


class TestCreateSession:
    """Tests for create_session endpoint."""

    @pytest.mark.asyncio
    async def test_create_session_invalid_context(
        self,
        mock_request_context: MagicMock,
    ) -> None:
        """Test that invalid context raises UNAUTHENTICATED."""
        servicer = AgentServicer()

        request = agent_pb2.CreateSessionRequest(
            context=common_pb2.TenantContext(
                tenant_id="",
                user_id="",
            ),
        )

        with pytest.raises(ConnectError) as exc_info:
            await servicer.create_session(request, mock_request_context)

        assert exc_info.value.code == Code.UNAUTHENTICATED


# =============================================================================
# Get Session Tests
# =============================================================================


class TestGetSession:
    """Tests for get_session endpoint."""

    @pytest.mark.asyncio
    async def test_get_session_invalid_uuid(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test that INVALID_ARGUMENT is raised for invalid session_id."""
        servicer = AgentServicer()

        request = agent_pb2.GetSessionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            ),
            session_id="not-a-uuid",
        )

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_session(request, mock_request_context)

        assert exc_info.value.code == Code.INVALID_ARGUMENT


# =============================================================================
# Send Message Tests
# =============================================================================


class TestSendMessage:
    """Tests for send_message endpoint."""

    @pytest.mark.asyncio
    async def test_send_message_empty_content(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test that empty content raises INVALID_ARGUMENT."""
        servicer = AgentServicer()

        request = agent_pb2.SendMessageRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            ),
            session_id=str(uuid4()),
            content="",
        )

        with pytest.raises(ConnectError) as exc_info:
            await servicer.send_message(request, mock_request_context)

        assert exc_info.value.code == Code.INVALID_ARGUMENT


# =============================================================================
# Stream Message Tests
# =============================================================================


class TestStreamMessage:
    """Tests for stream_message endpoint."""

    @pytest.mark.asyncio
    async def test_stream_message_empty_content(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test that empty content yields ERROR event."""
        servicer = AgentServicer()

        request = agent_pb2.SendMessageRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            ),
            session_id=str(uuid4()),
            content="",
        )

        events = []
        async for event in servicer.stream_message(request, mock_request_context):
            events.append(event)

        assert len(events) == 1
        assert events[0].event_type == STREAM_EVENT_TYPE_ERROR
        assert "required" in events[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_stream_message_invalid_context(
        self,
        mock_request_context: MagicMock,
    ) -> None:
        """Test that invalid context raises UNAUTHENTICATED ConnectError."""
        servicer = AgentServicer()

        request = agent_pb2.SendMessageRequest(
            context=common_pb2.TenantContext(
                tenant_id="",
                user_id="",
            ),
            session_id=str(uuid4()),
            content="Hello",
        )

        with pytest.raises(ConnectError) as exc_info:
            async for _event in servicer.stream_message(request, mock_request_context):
                pass

        assert exc_info.value.code == Code.UNAUTHENTICATED

    @pytest.mark.asyncio
    async def test_stream_message_replays_history_and_single_writes(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Prior turns are loaded before the user write and replayed; the
        assistant message is written exactly once with artifact links."""
        servicer = AgentServicer()
        session_uuid = uuid4()

        # Prior conversation returned by get_recent_messages (excludes the new turn).
        prior = [
            make_mock_message(role=MESSAGE_ROLE_USER, content="Earlier question"),
            make_mock_message(role=MESSAGE_ROLE_ASSISTANT, content="Earlier answer"),
        ]

        mock_conv = MagicMock()
        mock_conv.get_session = AsyncMock(return_value=make_mock_session(session_id=session_uuid))
        mock_conv.get_recent_messages = AsyncMock(return_value=prior)
        mock_conv.add_message = AsyncMock(return_value=make_mock_message())

        # Draft artifact emitted mid-stream.
        artifact = MagicMock()
        artifact.id = uuid4()
        artifact.session_id = session_uuid
        artifact.artifact_type = 1
        artifact.name = "Draft"
        artifact.description = "d"
        artifact.artifact_json = {}
        artifact.is_committed = False
        artifact.created_at = MagicMock()
        artifact.created_at.timestamp.return_value = datetime.now(UTC).timestamp()

        captured: dict[str, object] = {}

        async def fake_stream(**kwargs: object):
            captured["history"] = kwargs.get("history")
            yield {"type": STREAM_EVENT_TYPE_CONTENT_DELTA, "delta": "Here you go"}
            yield {"type": STREAM_EVENT_TYPE_ARTIFACT_CREATED, "artifact": artifact}
            yield {"type": STREAM_EVENT_TYPE_COMPLETE, "session_id": str(session_uuid)}

        mock_agent = MagicMock()
        mock_agent.stream_message = fake_stream

        request = agent_pb2.SendMessageRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            ),
            session_id=str(session_uuid),
            content="Build me a strategy",
        )

        with (
            patch.object(servicer, "_maker", return_value=MagicMock()),
            patch("src.grpc.servicer.tenant_session", return_value=make_mock_db_session()),
            patch(
                "src.services.conversation_service.ConversationService",
                return_value=mock_conv,
            ),
            patch("src.services.agent_service.AgentService", return_value=mock_agent),
        ):
            events = [e async for e in servicer.stream_message(request, mock_request_context)]

        # History was loaded (windowed) and the converted prior turns were replayed —
        # crucially WITHOUT the current user message.
        mock_conv.get_recent_messages.assert_awaited_once_with(
            session_uuid, limit=HISTORY_MESSAGE_LIMIT
        )
        assert captured["history"] == [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ]

        # Exactly two writes: the user turn and a single assistant turn (no double-write).
        assert mock_conv.add_message.await_count == 2
        user_call = mock_conv.add_message.await_args_list[0].kwargs
        assistant_call = mock_conv.add_message.await_args_list[1].kwargs
        assert user_call["role"] == MESSAGE_ROLE_USER
        assert assistant_call["role"] == MESSAGE_ROLE_ASSISTANT
        # The drafted artifact is linked to the stored assistant message.
        assert assistant_call["inline_artifact_ids"] == [str(artifact.id)]

        # The stream surfaced the artifact and completed.
        assert any(e.event_type == STREAM_EVENT_TYPE_ARTIFACT_CREATED for e in events)
        assert any(e.event_type == STREAM_EVENT_TYPE_COMPLETE for e in events)

    @pytest.mark.asyncio
    async def test_stream_message_degrades_when_history_load_fails(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """A history-load failure degrades to no history; the turn still completes."""
        servicer = AgentServicer()
        session_uuid = uuid4()

        mock_conv = MagicMock()
        mock_conv.get_session = AsyncMock(return_value=make_mock_session(session_id=session_uuid))
        mock_conv.get_recent_messages = AsyncMock(side_effect=RuntimeError("db hiccup"))
        mock_conv.add_message = AsyncMock(return_value=make_mock_message())

        captured: dict[str, object] = {}

        async def fake_stream(**kwargs: object):
            captured["history"] = kwargs.get("history")
            yield {"type": STREAM_EVENT_TYPE_COMPLETE, "session_id": str(session_uuid)}

        mock_agent = MagicMock()
        mock_agent.stream_message = fake_stream

        request = agent_pb2.SendMessageRequest(
            context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(user_id)),
            session_id=str(session_uuid),
            content="Hello again",
        )

        with (
            patch.object(servicer, "_maker", return_value=MagicMock()),
            patch("src.grpc.servicer.tenant_session", return_value=make_mock_db_session()),
            patch(
                "src.services.conversation_service.ConversationService",
                return_value=mock_conv,
            ),
            patch("src.services.agent_service.AgentService", return_value=mock_agent),
        ):
            events = [e async for e in servicer.stream_message(request, mock_request_context)]

        # History degraded to empty, but the turn still ran and persisted both messages.
        assert captured["history"] == []
        assert any(e.event_type == STREAM_EVENT_TYPE_COMPLETE for e in events)
        assert mock_conv.add_message.await_count == 2


class TestConfirmToolCall:
    """Tests for the ConfirmToolCall resume endpoint."""

    @pytest.mark.asyncio
    async def test_confirm_tool_call_resumes_and_single_writes(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Approval threads the proposal to resume_with_tool and stores one
        assistant message via the shared relay."""
        servicer = AgentServicer()
        session_uuid = uuid4()

        mock_conv = MagicMock()
        mock_conv.get_session = AsyncMock(return_value=make_mock_session(session_id=session_uuid))
        mock_conv.get_recent_messages = AsyncMock(return_value=[])
        mock_conv.add_message = AsyncMock(return_value=make_mock_message())

        captured: dict[str, object] = {}

        async def fake_resume(**kwargs: object):
            captured.update(kwargs)
            yield {"type": STREAM_EVENT_TYPE_CONTENT_DELTA, "delta": "Backtest started."}
            yield {"type": STREAM_EVENT_TYPE_COMPLETE, "session_id": str(session_uuid)}

        mock_agent = MagicMock()
        mock_agent.resume_with_tool = fake_resume

        request = agent_pb2.ConfirmToolCallRequest(
            context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(user_id)),
            session_id=str(session_uuid),
            confirmation_id="c1",
            tool_name="run_backtest",
            tool_arguments_json='{"strategy_id": "s1"}',
            approved=True,
        )

        with (
            patch.object(servicer, "_maker", return_value=MagicMock()),
            patch("src.grpc.servicer.tenant_session", return_value=make_mock_db_session()),
            patch(
                "src.services.conversation_service.ConversationService",
                return_value=mock_conv,
            ),
            patch("src.services.agent_service.AgentService", return_value=mock_agent),
        ):
            events = [e async for e in servicer.confirm_tool_call(request, mock_request_context)]

        assert captured["approved"] is True
        assert captured["tool_name"] == "run_backtest"
        assert captured["arguments_json"] == '{"strategy_id": "s1"}'
        assert mock_conv.add_message.await_count == 1
        assert any(e.event_type == STREAM_EVENT_TYPE_COMPLETE for e in events)

    @pytest.mark.asyncio
    async def test_confirm_tool_call_requires_tool_name(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """A missing tool_name yields an ERROR event."""
        servicer = AgentServicer()
        request = agent_pb2.ConfirmToolCallRequest(
            context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(user_id)),
            session_id=str(uuid4()),
            approved=True,
        )

        events = [e async for e in servicer.confirm_tool_call(request, mock_request_context)]

        assert len(events) == 1
        assert events[0].event_type == STREAM_EVENT_TYPE_ERROR


class TestHistoryFromMessages:
    """Tests for the message → LLM-history conversion helper."""

    def test_maps_roles_and_skips_empty(self) -> None:
        """User/assistant roles map to strings; empty-content rows are dropped."""
        messages = [
            make_mock_message(role=MESSAGE_ROLE_USER, content="hi"),
            make_mock_message(role=MESSAGE_ROLE_ASSISTANT, content="hello"),
            make_mock_message(role=MESSAGE_ROLE_USER, content=""),
        ]

        history = _history_from_messages(messages)

        assert history == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]


# =============================================================================
# Suggested Prompts Tests
# =============================================================================


class TestGetSuggestedPrompts:
    """Tests for get_suggested_prompts endpoint."""

    @pytest.mark.asyncio
    async def test_get_suggested_prompts_dashboard(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test getting prompts for dashboard page."""
        servicer = AgentServicer()

        with patch(
            "src.prompts.context.get_suggested_actions",
            return_value=["Create a strategy", "Show my portfolio"],
        ):
            request = agent_pb2.GetSuggestedPromptsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                ),
            )

            response = await servicer.get_suggested_prompts(request, mock_request_context)

        assert len(response.prompts) == 2
        assert "Create a strategy" in response.prompts

    @pytest.mark.asyncio
    async def test_get_suggested_prompts_with_ui_context(
        self,
        mock_request_context: MagicMock,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test that UI context is passed to suggestion generator."""
        servicer = AgentServicer()
        strategy_id = str(uuid4())

        with patch(
            "src.prompts.context.get_suggested_actions",
            return_value=["Run backtest"],
        ) as mock_fn:
            request = agent_pb2.GetSuggestedPromptsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                ),
                ui_context=agent_pb2.AgentContextData(
                    page="strategy_detail",
                    strategy_id=strategy_id,
                ),
            )

            await servicer.get_suggested_prompts(request, mock_request_context)

        # Verify context was passed
        call_args = mock_fn.call_args
        assert call_args[0][0] == "strategy_detail"
        assert call_args[0][1]["strategy_id"] == strategy_id
