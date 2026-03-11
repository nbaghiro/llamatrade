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
    MESSAGE_ROLE_USER,
    STREAM_EVENT_TYPE_ERROR,
)

from src.grpc.servicer import AgentServicer, _validate_tenant_context

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
