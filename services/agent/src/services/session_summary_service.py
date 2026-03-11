"""Session summarization service for generating conversation summaries.

This service handles:
- Triggering summarization based on session events
- Generating summaries via LLM (Haiku)
- Extracting topics, strategies, and decisions
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import AgentMessage, AgentSession, AgentSessionSummary
from llamatrade_proto.generated.agent_pb2 import (
    AGENT_SESSION_STATUS_COMPLETED,
    MESSAGE_ROLE_USER,
)

logger = logging.getLogger(__name__)

# Summarization triggers
MESSAGE_COUNT_THRESHOLD = 20  # Summarize after 20 messages
INACTIVITY_TIMEOUT_MINUTES = 30  # Summarize after 30 min inactivity

# LLM configuration
SUMMARY_MODEL = "claude-3-5-haiku-20241022"


@dataclass
class SummaryTrigger:
    """Represents a reason to summarize a session."""

    should_summarize: bool
    reason: str | None = None


SUMMARIZATION_PROMPT = """Analyze this conversation and extract a structured summary.

Conversation:
{conversation}

Return a JSON object with these fields:
{{
    "summary_short": "1-2 sentence summary of what was discussed",
    "summary_detailed": "Detailed summary (3-5 sentences) covering main topics and outcomes",
    "topics": ["topic1", "topic2", ...],  // Key topics discussed (max 5)
    "strategies_discussed": ["strategy_name1", ...],  // Names of strategies mentioned or created
    "decisions": ["decision1", ...]  // Key decisions the user made (max 3)
}}

Focus on:
- What the user wanted to accomplish
- What strategies were discussed or created
- What preferences or decisions were expressed
- Any action items or next steps

Return only valid JSON, no other text."""


class SessionSummaryService:
    """Service for generating and managing session summaries.

    Summaries are generated when:
    1. Session status changes to COMPLETED
    2. Inactivity timeout (30 minutes)
    3. Message count exceeds threshold (20)
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Initialize the service.

        Args:
            db: Async database session
            tenant_id: Tenant UUID
            user_id: User UUID
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._llm_client: Any = None

    async def check_summarization_triggers(
        self,
        session_id: UUID,
    ) -> SummaryTrigger:
        """Check if a session should be summarized.

        Args:
            session_id: Session to check

        Returns:
            SummaryTrigger indicating if summarization needed
        """
        # Get session
        stmt = select(AgentSession).where(
            and_(
                AgentSession.id == session_id,
                AgentSession.tenant_id == self.tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session:
            return SummaryTrigger(should_summarize=False)

        # Check if already summarized at current message count
        summary_stmt = select(AgentSessionSummary).where(
            AgentSessionSummary.session_id == session_id
        )
        summary_result = await self.db.execute(summary_stmt)
        existing_summary = summary_result.scalar_one_or_none()

        if existing_summary:
            # Already summarized and no new messages
            if existing_summary.message_count_at_summary >= session.message_count:
                return SummaryTrigger(should_summarize=False)

        # Trigger 1: Session completed
        if session.status == AGENT_SESSION_STATUS_COMPLETED:
            return SummaryTrigger(
                should_summarize=True,
                reason="session_completed",
            )

        # Trigger 2: Message count threshold
        if session.message_count >= MESSAGE_COUNT_THRESHOLD:
            return SummaryTrigger(
                should_summarize=True,
                reason="message_threshold",
            )

        # Trigger 3: Inactivity timeout
        inactivity_threshold = datetime.now(UTC) - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
        if session.last_activity_at < inactivity_threshold:
            return SummaryTrigger(
                should_summarize=True,
                reason="inactivity_timeout",
            )

        return SummaryTrigger(should_summarize=False)

    async def maybe_summarize_session(
        self,
        session_id: UUID,
        force: bool = False,
    ) -> AgentSessionSummary | None:
        """Summarize a session if triggers are met.

        Args:
            session_id: Session to summarize
            force: Force summarization regardless of triggers

        Returns:
            AgentSessionSummary if created/updated, None otherwise
        """
        if not force:
            trigger = await self.check_summarization_triggers(session_id)
            if not trigger.should_summarize:
                return None

            logger.info(
                "Summarizing session %s (trigger: %s)",
                session_id,
                trigger.reason,
            )

        # Get session messages
        messages = await self._get_session_messages(session_id)
        if not messages:
            return None

        # Generate summary via LLM
        summary_data = await self._generate_summary(messages)
        if not summary_data:
            return None

        # Store summary
        from src.services.memory_service import MemoryService

        memory_service = MemoryService(
            db=self.db,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
        )

        return await memory_service.store_session_summary(
            session_id=session_id,
            summary_short=summary_data["summary_short"],
            summary_detailed=summary_data["summary_detailed"],
            topics=summary_data["topics"],
            strategies_discussed=summary_data["strategies_discussed"],
            decisions=summary_data["decisions"],
            message_count=len(messages),
        )

    async def _get_session_messages(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, str]]:
        """Get messages for a session.

        Args:
            session_id: Session UUID
            limit: Maximum messages to fetch

        Returns:
            List of message dicts with role and content
        """
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.asc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        return [
            {
                "role": "user" if m.role == MESSAGE_ROLE_USER else "assistant",
                "content": m.content,
            }
            for m in messages
        ]

    async def _generate_summary(
        self,
        messages: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """Generate summary from conversation via LLM.

        Args:
            messages: Conversation messages

        Returns:
            Summary data dict or None on failure
        """
        if not messages:
            return None

        # Format conversation
        conversation = "\n\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in messages)

        # Truncate if too long (Haiku has ~200k context but keep it reasonable)
        if len(conversation) > 50000:
            conversation = conversation[:50000] + "\n\n[... conversation truncated ...]"

        prompt = SUMMARIZATION_PROMPT.format(conversation=conversation)

        try:
            # Use Haiku for cost efficiency
            response = await self._call_llm(prompt)
            if not response:
                return None

            # Parse JSON response
            content = response.strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n?", "", content)
                content = re.sub(r"\n?```$", "", content)

            parsed = json.loads(content)

            # Validate required fields
            required = [
                "summary_short",
                "summary_detailed",
                "topics",
                "strategies_discussed",
                "decisions",
            ]
            for field in required:
                if field not in parsed:
                    logger.warning("Summary missing field: %s", field)
                    parsed[field] = (
                        [] if field in ["topics", "strategies_discussed", "decisions"] else ""
                    )

            # Ensure lists
            for list_field in ["topics", "strategies_discussed", "decisions"]:
                if not isinstance(parsed.get(list_field), list):
                    parsed[list_field] = []

            return parsed

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse summary JSON: %s", e)
            return None
        except Exception as e:
            logger.exception("Summary generation failed: %s", e)
            return None

    async def _call_llm(self, prompt: str) -> str | None:
        """Call LLM API for summary generation.

        Args:
            prompt: Prompt to send

        Returns:
            LLM response text or None
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic()

            response = await client.messages.create(
                model=SUMMARY_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            if response.content and len(response.content) > 0:
                block = response.content[0]
                # Use getattr to safely access text attribute (only TextBlock has it)
                text = getattr(block, "text", None)
                if text is not None:
                    return str(text)

            return None

        except Exception as e:
            logger.exception("LLM call failed: %s", e)
            return None


async def summarize_stale_sessions(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    max_sessions: int = 10,
) -> list[AgentSessionSummary]:
    """Background job to summarize stale sessions.

    Args:
        db: Database session
        tenant_id: Tenant UUID
        user_id: User UUID
        max_sessions: Maximum sessions to process

    Returns:
        List of created summaries
    """
    # Find sessions needing summarization
    inactivity_threshold = datetime.now(UTC) - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)

    # Get sessions that:
    # 1. Are inactive for 30+ minutes
    # 2. Have 20+ messages
    # 3. Don't have an up-to-date summary
    stmt = (
        select(AgentSession)
        .outerjoin(
            AgentSessionSummary,
            AgentSession.id == AgentSessionSummary.session_id,
        )
        .where(
            and_(
                AgentSession.tenant_id == tenant_id,
                AgentSession.user_id == user_id,
                (
                    (AgentSession.last_activity_at < inactivity_threshold)
                    | (AgentSession.message_count >= MESSAGE_COUNT_THRESHOLD)
                ),
                (
                    (AgentSessionSummary.id.is_(None))
                    | (AgentSessionSummary.message_count_at_summary < AgentSession.message_count)
                ),
            )
        )
        .limit(max_sessions)
    )

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    summaries: list[AgentSessionSummary] = []

    for session in sessions:
        service = SessionSummaryService(db, tenant_id, user_id)
        summary = await service.maybe_summarize_session(session.id, force=True)
        if summary:
            summaries.append(summary)

    logger.info("Summarized %d stale sessions", len(summaries))
    return summaries
