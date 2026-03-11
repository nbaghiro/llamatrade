"""Tests for ConversationService database operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.agent_pb2 import (
    AGENT_SESSION_STATUS_ACTIVE,
    AGENT_SESSION_STATUS_COMPLETED,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
)

from src.services.conversation_service import ConversationService

# =============================================================================
# Helper to create mock scalar results
# =============================================================================


def mock_scalar_one_or_none(value: Any) -> MagicMock:
    """Create a mock result that returns the value from scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def mock_scalar_one(value: Any) -> MagicMock:
    """Create a mock result that returns the value from scalar_one()."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def mock_scalars_all(values: list[Any]) -> MagicMock:
    """Create a mock result that returns values from scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result.scalars.return_value = scalars_mock
    return result


def make_mock_session(
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str | None = None,
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
    mock.created_at = datetime.now(UTC)
    mock.last_activity_at = datetime.now(UTC)
    return mock


def make_mock_message(
    message_id: UUID | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    role: int = MESSAGE_ROLE_USER,
    content: str = "Test message",
    tool_calls: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock AgentMessage."""
    mock = MagicMock()
    mock.id = message_id or uuid4()
    mock.session_id = session_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.role = role
    mock.content = content
    mock.tool_calls_json = tool_calls
    mock.created_at = datetime.now(UTC)
    return mock


# =============================================================================
# Session Operations
# =============================================================================


class TestCreateSession:
    """Tests for session creation."""

    @pytest.mark.asyncio
    async def test_create_session_success(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test creating a session with required fields."""
        # Setup mock to capture the added object
        added_session = None

        def capture_add(obj: Any) -> None:
            nonlocal added_session
            added_session = obj

        conversation_service.db.add = capture_add
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.create_session(
            tenant_id=tenant_id,
            user_id=user_id,
        )

        assert added_session is not None
        assert added_session.tenant_id == tenant_id
        assert added_session.user_id == user_id
        assert added_session.status == AGENT_SESSION_STATUS_ACTIVE
        assert added_session.message_count == 0

    @pytest.mark.asyncio
    async def test_create_session_with_title(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test creating a session with a custom title."""
        added_session = None

        def capture_add(obj: Any) -> None:
            nonlocal added_session
            added_session = obj

        conversation_service.db.add = capture_add
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.create_session(
            tenant_id=tenant_id,
            user_id=user_id,
            title="My Conversation",
        )

        assert added_session is not None
        assert added_session.title == "My Conversation"


class TestGetSession:
    """Tests for session retrieval."""

    @pytest.mark.asyncio
    async def test_get_session_exists(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test retrieving an existing session."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, tenant_id=tenant_id)

        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )

        found = await conversation_service.get_session(tenant_id, session_id)

        assert found is not None
        assert found.id == session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test retrieving a non-existent session."""
        conversation_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await conversation_service.get_session(tenant_id, uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_tenant_isolation(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test that sessions are isolated by tenant."""
        session_id = uuid4()
        # Session exists but for different tenant
        conversation_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        other_tenant = uuid4()
        result = await conversation_service.get_session(other_tenant, session_id)

        assert result is None


class TestListSessions:
    """Tests for session listing."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test listing sessions when none exist."""
        # First call returns count=0, second returns empty list
        conversation_service.db.execute = AsyncMock(
            side_effect=[
                mock_scalar_one(0),
                mock_scalars_all([]),
            ]
        )

        sessions, total = await conversation_service.list_sessions(tenant_id, user_id)

        assert sessions == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_sessions_with_data(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test listing sessions returns correct data."""
        mock_sessions = [
            make_mock_session(tenant_id=tenant_id, user_id=user_id, title="Session 1"),
            make_mock_session(tenant_id=tenant_id, user_id=user_id, title="Session 2"),
            make_mock_session(tenant_id=tenant_id, user_id=user_id, title="Session 3"),
        ]

        conversation_service.db.execute = AsyncMock(
            side_effect=[
                mock_scalar_one(3),
                mock_scalars_all(mock_sessions),
            ]
        )

        sessions, total = await conversation_service.list_sessions(tenant_id, user_id)

        assert len(sessions) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test pagination of session listing."""
        # Total is 5, but page 1 with size 2 returns 2 items
        mock_sessions = [
            make_mock_session(tenant_id=tenant_id, user_id=user_id),
            make_mock_session(tenant_id=tenant_id, user_id=user_id),
        ]

        conversation_service.db.execute = AsyncMock(
            side_effect=[
                mock_scalar_one(5),
                mock_scalars_all(mock_sessions),
            ]
        )

        sessions, total = await conversation_service.list_sessions(
            tenant_id, user_id, page=1, page_size=2
        )

        assert len(sessions) == 2
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_sessions_status_filter(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test filtering sessions by status."""
        # Return only completed sessions
        mock_sessions = [
            make_mock_session(
                tenant_id=tenant_id,
                user_id=user_id,
                status=AGENT_SESSION_STATUS_COMPLETED,
            ),
        ]

        conversation_service.db.execute = AsyncMock(
            side_effect=[
                mock_scalar_one(1),
                mock_scalars_all(mock_sessions),
            ]
        )

        sessions, total = await conversation_service.list_sessions(
            tenant_id, user_id, status=AGENT_SESSION_STATUS_COMPLETED
        )

        assert total == 1
        assert len(sessions) == 1


class TestUpdateSession:
    """Tests for session updates."""

    @pytest.mark.asyncio
    async def test_update_session_title(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test updating session title."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id)

        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        updated = await conversation_service.update_session(session_id, title="New Title")

        assert updated is not None
        assert mock_session.title == "New Title"

    @pytest.mark.asyncio
    async def test_update_session_status(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test updating session status."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id)

        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.update_session(session_id, status=AGENT_SESSION_STATUS_COMPLETED)

        assert mock_session.status == AGENT_SESSION_STATUS_COMPLETED

    @pytest.mark.asyncio
    async def test_update_session_not_found(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test updating a non-existent session."""
        conversation_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await conversation_service.update_session(uuid4(), title="New Title")

        assert result is None


class TestDeleteSession:
    """Tests for session deletion."""

    @pytest.mark.asyncio
    async def test_delete_session_success(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test deleting an existing session."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, tenant_id=tenant_id)

        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.delete = AsyncMock()
        conversation_service.db.commit = AsyncMock()

        result = await conversation_service.delete_session(tenant_id, session_id)

        assert result is True
        conversation_service.db.delete.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_delete_session_not_found(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test deleting a non-existent session."""
        conversation_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await conversation_service.delete_session(tenant_id, uuid4())

        assert result is False


# =============================================================================
# Message Operations
# =============================================================================


class TestAddMessage:
    """Tests for message creation."""

    @pytest.mark.asyncio
    async def test_add_message_user(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test adding a user message."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, message_count=0)

        added_message = None

        def capture_add(obj: Any) -> None:
            nonlocal added_message
            # Only capture the message, not the session
            if hasattr(obj, "role"):
                added_message = obj

        conversation_service.db.add = capture_add
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_USER,
            content="Hello, agent!",
        )

        assert added_message is not None
        assert added_message.role == MESSAGE_ROLE_USER
        assert added_message.content == "Hello, agent!"

    @pytest.mark.asyncio
    async def test_add_message_assistant(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test adding an assistant message."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id)
        added_message = None

        def capture_add(obj: Any) -> None:
            nonlocal added_message
            if hasattr(obj, "role"):
                added_message = obj

        conversation_service.db.add = capture_add
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_ASSISTANT,
            content="Hello! How can I help?",
        )

        assert added_message is not None
        assert added_message.role == MESSAGE_ROLE_ASSISTANT

    @pytest.mark.asyncio
    async def test_add_message_with_tool_calls(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test adding a message with tool calls."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id)
        added_message = None

        def capture_add(obj: Any) -> None:
            nonlocal added_message
            if hasattr(obj, "role"):
                added_message = obj

        conversation_service.db.add = capture_add
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        tool_calls = [{"id": "call_123", "name": "validate_dsl"}]

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_ASSISTANT,
            content="Let me validate that.",
            tool_calls=tool_calls,
        )

        assert added_message is not None
        assert added_message.tool_calls_json == tool_calls

    @pytest.mark.asyncio
    async def test_add_message_increments_count(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test that adding a message increments session message count."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, message_count=0)

        conversation_service.db.add = MagicMock()
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_USER,
            content="Message 1",
        )

        assert mock_session.message_count == 1

    @pytest.mark.asyncio
    async def test_add_message_generates_title(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test that first user message generates session title."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, title=None)

        conversation_service.db.add = MagicMock()
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_USER,
            content="Create a 60/40 portfolio",
        )

        assert mock_session.title == "Create a 60/40 portfolio"

    @pytest.mark.asyncio
    async def test_add_message_title_truncation(
        self,
        conversation_service: ConversationService,
        tenant_id: UUID,
    ) -> None:
        """Test that long messages are truncated for title."""
        session_id = uuid4()
        mock_session = make_mock_session(session_id=session_id, title=None)

        conversation_service.db.add = MagicMock()
        conversation_service.db.execute = AsyncMock(
            return_value=mock_scalar_one_or_none(mock_session)
        )
        conversation_service.db.commit = AsyncMock()
        conversation_service.db.refresh = AsyncMock()

        long_message = "A" * 100

        await conversation_service.add_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role=MESSAGE_ROLE_USER,
            content=long_message,
        )

        assert mock_session.title == "A" * 50 + "..."
        assert len(mock_session.title) == 53


class TestGetMessages:
    """Tests for message retrieval."""

    @pytest.mark.asyncio
    async def test_get_messages_empty(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test getting messages from empty session."""
        session_id = uuid4()

        conversation_service.db.execute = AsyncMock(return_value=mock_scalars_all([]))

        messages = await conversation_service.get_messages(session_id)

        assert messages == []

    @pytest.mark.asyncio
    async def test_get_messages_ordered(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test that messages are returned in chronological order."""
        session_id = uuid4()
        mock_messages = [
            make_mock_message(session_id=session_id, content="First"),
            make_mock_message(session_id=session_id, content="Second"),
            make_mock_message(session_id=session_id, content="Third"),
        ]

        conversation_service.db.execute = AsyncMock(return_value=mock_scalars_all(mock_messages))

        messages = await conversation_service.get_messages(session_id)

        assert len(messages) == 3
        assert messages[0].content == "First"
        assert messages[1].content == "Second"
        assert messages[2].content == "Third"

    @pytest.mark.asyncio
    async def test_get_messages_limit(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test that limit parameter restricts results."""
        session_id = uuid4()
        # Return 3 messages when limit is applied
        mock_messages = [
            make_mock_message(session_id=session_id, content=f"Message {i}") for i in range(3)
        ]

        conversation_service.db.execute = AsyncMock(return_value=mock_scalars_all(mock_messages))

        messages = await conversation_service.get_messages(session_id, limit=3)

        assert len(messages) == 3


# =============================================================================
# Artifact Operations
# =============================================================================


class TestGetPendingArtifacts:
    """Tests for pending artifact retrieval."""

    @pytest.mark.asyncio
    async def test_get_pending_artifacts_empty(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test getting artifacts from session with none."""
        session_id = uuid4()

        conversation_service.db.execute = AsyncMock(return_value=mock_scalars_all([]))

        artifacts = await conversation_service.get_pending_artifacts(session_id)

        assert artifacts == []

    @pytest.mark.asyncio
    async def test_get_pending_artifacts_returns_uncommitted(
        self,
        conversation_service: ConversationService,
    ) -> None:
        """Test that uncommitted artifacts are returned."""
        session_id = uuid4()

        mock_artifact = MagicMock()
        mock_artifact.id = uuid4()
        mock_artifact.name = "Test Strategy"
        mock_artifact.is_committed = False

        conversation_service.db.execute = AsyncMock(return_value=mock_scalars_all([mock_artifact]))

        artifacts = await conversation_service.get_pending_artifacts(session_id)

        assert len(artifacts) == 1
        assert artifacts[0].name == "Test Strategy"
