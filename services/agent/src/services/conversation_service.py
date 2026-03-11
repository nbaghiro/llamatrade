"""Conversation service for session and message persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import AgentMessage, AgentSession, PendingArtifact
from llamatrade_proto.generated import agent_pb2
from llamatrade_proto.generated.agent_pb2 import AGENT_SESSION_STATUS_ACTIVE


class ConversationService:
    """Service for managing agent conversations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the service.

        Args:
            db: Async database session
        """
        self.db = db

    # =========================================================================
    # Session Operations
    # =========================================================================

    async def create_session(
        self,
        tenant_id: UUID,
        user_id: UUID,
        title: str | None = None,
    ) -> AgentSession:
        """Create a new agent session.

        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            title: Optional session title

        Returns:
            Created AgentSession
        """
        now = datetime.now(UTC)
        session = AgentSession(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            status=AGENT_SESSION_STATUS_ACTIVE,
            message_count=0,
            last_activity_at=now,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> AgentSession | None:
        """Get a session by ID.

        Args:
            tenant_id: Tenant UUID for isolation
            session_id: Session UUID

        Returns:
            AgentSession if found, None otherwise
        """
        stmt = select(AgentSession).where(
            (AgentSession.id == session_id) & (AgentSession.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        tenant_id: UUID,
        user_id: UUID,
        status: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AgentSession], int]:
        """List sessions for a user.

        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            status: Optional status filter
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (sessions list, total count)
        """
        # Base query
        base_query = select(AgentSession).where(
            (AgentSession.tenant_id == tenant_id) & (AgentSession.user_id == user_id)
        )

        if status is not None and status > 0:
            base_query = base_query.where(AgentSession.status == status)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Get paginated results
        offset = (page - 1) * page_size
        paginated_query = (
            base_query.order_by(AgentSession.last_activity_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(paginated_query)
        sessions = list(result.scalars().all())

        return sessions, total

    async def update_session(
        self,
        session_id: UUID,
        title: str | None = None,
        status: agent_pb2.AgentSessionStatus.ValueType | None = None,
    ) -> AgentSession | None:
        """Update session metadata.

        Args:
            session_id: Session UUID
            title: New title (if provided)
            status: New status (if provided)

        Returns:
            Updated session or None if not found
        """
        stmt = select(AgentSession).where(AgentSession.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            return None

        if title is not None:
            session.title = title
        if status is not None:
            session.status = status

        session.last_activity_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def delete_session(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> bool:
        """Delete a session and all associated data.

        Args:
            tenant_id: Tenant UUID for isolation
            session_id: Session UUID

        Returns:
            True if deleted, False if not found
        """
        session = await self.get_session(tenant_id, session_id)
        if not session:
            return False

        await self.db.delete(session)
        await self.db.commit()
        return True

    # =========================================================================
    # Message Operations
    # =========================================================================

    async def add_message(
        self,
        session_id: UUID,
        tenant_id: UUID,
        role: int,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> AgentMessage:
        """Add a message to a session.

        Args:
            session_id: Session UUID
            tenant_id: Tenant UUID
            role: Message role (proto int value)
            content: Message content
            tool_calls: Optional list of tool calls

        Returns:
            Created AgentMessage
        """
        message = AgentMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            tool_calls_json=tool_calls,
        )
        self.db.add(message)

        # Update session message count and activity
        stmt = select(AgentSession).where(AgentSession.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if session:
            session.message_count += 1
            session.last_activity_at = datetime.now(UTC)

            # Generate title from first user message if not set
            if not session.title and role == 1:  # MESSAGE_ROLE_USER
                session.title = content[:50] + "..." if len(content) > 50 else content

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 50,
        before_id: UUID | None = None,
    ) -> list[AgentMessage]:
        """Get messages for a session.

        Args:
            session_id: Session UUID
            limit: Maximum messages to return
            before_id: Get messages before this ID (for pagination)

        Returns:
            List of messages ordered by created_at ascending
        """
        query = select(AgentMessage).where(AgentMessage.session_id == session_id)

        if before_id:
            query = query.where(AgentMessage.id < before_id)

        query = query.order_by(AgentMessage.created_at.asc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Artifact Operations
    # =========================================================================

    async def get_pending_artifacts(
        self,
        session_id: UUID,
        include_committed: bool = False,
    ) -> list[PendingArtifact]:
        """Get pending artifacts for a session.

        Args:
            session_id: Session UUID
            include_committed: Include already committed artifacts

        Returns:
            List of pending artifacts
        """
        query = select(PendingArtifact).where(PendingArtifact.session_id == session_id)

        if not include_committed:
            query = query.where(PendingArtifact.is_committed.is_(False))

        query = query.order_by(PendingArtifact.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
