"""Tests for the fire-and-forget memory write path in AgentService.

_extract_and_store_memories runs after the request session closes, so it must
open a fresh tenant-scoped session (RLS WITH CHECK), never propagate failures,
and be scheduled as a background task rather than awaited inline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from llamatrade_proto.generated.agent_pb2 import (
    STREAM_EVENT_TYPE_COMPLETE,
)

from src.llm.client import StreamEvent, StreamEventType
from src.services.agent_service import AgentService

pytestmark = pytest.mark.asyncio

FACT_MESSAGE = "My risk tolerance is aggressive and I want to retire in 20 years."
NO_FACT_MESSAGE = "hello"


@pytest.fixture
def agent_service(mock_db_session: AsyncMock, tenant_id: UUID, user_id: UUID) -> AgentService:
    return AgentService(db=mock_db_session, tenant_id=tenant_id, user_id=user_id)


def _tenant_session_double(session: AsyncMock, calls: list[UUID]) -> Any:
    """A tenant_session replacement recording the tenant id it was opened for."""

    @asynccontextmanager
    async def fake_tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncMock]:
        calls.append(tenant_id)
        yield session

    return fake_tenant_session


def _memory_write_session() -> AsyncMock:
    """A session whose queries report no existing facts, so writes proceed."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


class TestExtractAndStoreMemories:
    """Direct tests of the background write coroutine."""

    async def test_opens_fresh_tenant_scoped_session(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """Writes go through a new GUC-bound session, not the request session."""
        write_session = _memory_write_session()
        opened_for: list[UUID] = []
        with patch(
            "llamatrade_db.tenant_session",
            _tenant_session_double(write_session, opened_for),
        ):
            await agent_service._extract_and_store_memories(
                session_id, FACT_MESSAGE, "assistant response"
            )

        assert opened_for == [agent_service.tenant_id]
        write_session.add.assert_called()
        write_session.commit.assert_awaited()
        request_session_add = agent_service.db.add
        assert isinstance(request_session_add, MagicMock)
        request_session_add.assert_not_called()

    async def test_stored_facts_carry_identity_and_source_session(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """Persisted rows are stamped with tenant, user, and source session."""
        write_session = _memory_write_session()
        with patch(
            "llamatrade_db.tenant_session",
            _tenant_session_double(write_session, []),
        ):
            await agent_service._extract_and_store_memories(
                session_id, FACT_MESSAGE, "assistant response"
            )

        stored_rows = [call.args[0] for call in write_session.add.call_args_list]
        assert stored_rows
        for row in stored_rows:
            assert row.tenant_id == agent_service.tenant_id
            assert row.user_id == agent_service.user_id
            assert row.source_session_id == session_id

    async def test_no_facts_skips_session_entirely(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """A message with nothing extractable never opens a DB session."""
        opened_for: list[UUID] = []
        with patch(
            "llamatrade_db.tenant_session",
            _tenant_session_double(_memory_write_session(), opened_for),
        ):
            await agent_service._extract_and_store_memories(
                session_id, NO_FACT_MESSAGE, "assistant response"
            )

        assert opened_for == []

    async def test_session_open_failure_is_swallowed(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """A broken session factory must never propagate out of the task."""

        @asynccontextmanager
        async def broken_tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncMock]:
            raise RuntimeError("pool exhausted")
            yield AsyncMock()

        with patch("llamatrade_db.tenant_session", broken_tenant_session):
            await agent_service._extract_and_store_memories(
                session_id, FACT_MESSAGE, "assistant response"
            )

    async def test_store_failure_is_swallowed(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """A commit error inside the write is logged, not raised."""
        write_session = _memory_write_session()
        write_session.commit = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "llamatrade_db.tenant_session",
            _tenant_session_double(write_session, []),
        ):
            await agent_service._extract_and_store_memories(
                session_id, FACT_MESSAGE, "assistant response"
            )


class TestStreamMessageScheduling:
    """stream_message schedules the memory write as a background task."""

    async def test_memory_write_scheduled_via_create_task(
        self, agent_service: AgentService, session_id: UUID
    ) -> None:
        """The write coroutine is handed to create_task with the turn's content,
        asserted by running the captured task — no sleeping on the loop."""

        async def fake_stream(
            **kwargs: object,
        ) -> AsyncIterator[StreamEvent]:
            yield StreamEvent(type=StreamEventType.CONTENT_DELTA, content="All set.")

        llm_client = MagicMock()
        llm_client.stream = fake_stream
        agent_service._llm_client = llm_client

        # New-user memory hint: the context build stops at the session count.
        hint_result = MagicMock()
        hint_result.scalar_one.return_value = 0
        agent_service.db.execute = AsyncMock(return_value=hint_result)

        scheduled: list[Coroutine[Any, Any, None]] = []

        def capture_task(coro: Coroutine[Any, Any, None]) -> MagicMock:
            scheduled.append(coro)
            return MagicMock()

        extract_mock = AsyncMock()
        with (
            patch.object(agent_service, "_extract_and_store_memories", extract_mock),
            patch(
                "src.services.agent_service.asyncio.create_task",
                side_effect=capture_task,
            ),
        ):
            events = [
                event async for event in agent_service.stream_message(session_id, FACT_MESSAGE)
            ]
            assert len(scheduled) == 1
            await scheduled[0]

        assert any(e["type"] == STREAM_EVENT_TYPE_COMPLETE for e in events)
        extract_mock.assert_awaited_once_with(session_id, FACT_MESSAGE, "All set.")
