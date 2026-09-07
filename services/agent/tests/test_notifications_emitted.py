"""Confirmation-pending proposals land on the notification stream."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from llamatrade_events import EventEnvelope
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2
from llamatrade_proto.generated.agent_pb2 import STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED
from tests.fixtures.mock_llm import MockLLMClient

from src.services.agent_service import AgentService
from src.tools.base import ToolResult

pytestmark = pytest.mark.asyncio


def _transport() -> FakeTransport:
    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    return transport


def _published() -> list[EventEnvelope]:
    return [EventEnvelope.FromString(value) for _, value in _transport().published]


@pytest.fixture
def agent_service(mock_db_session: AsyncMock, tenant_id: UUID, user_id: UUID) -> AgentService:
    return AgentService(mock_db_session, tenant_id, user_id)


async def _stream_backtest_proposal(agent_service: AgentService, session_id: UUID) -> None:
    """Drive one turn whose only tool call is confirmation-gated (run_backtest)."""
    client = MockLLMClient()
    client.add_tool_call_response(
        tool_name="run_backtest",
        tool_input={"strategy_id": "s1"},
        content="I'll run a backtest.",
    )
    agent_service._llm_client = client

    execute = AsyncMock(return_value=ToolResult(success=True, data={}))
    with patch.object(agent_service._executor, "execute", execute):
        events = [e async for e in agent_service.stream_message(session_id, "backtest it")]

    assert any(e.get("type") == STREAM_EVENT_TYPE_TOOL_CONFIRMATION_REQUIRED for e in events)
    execute.assert_not_awaited()


async def test_confirmation_proposal_emits_pending_notification(
    agent_service: AgentService,
    tenant_id: UUID,
    user_id: UUID,
    session_id: UUID,
) -> None:
    """The proposal publishes CONFIRMATION_PENDING with tenant and user threaded."""
    await _stream_backtest_proposal(agent_service, session_id)

    envelopes = _published()
    assert len(envelopes) == 1
    envelope = envelopes[0]
    payload = NotificationEvents.payload(envelope)
    assert payload.category == events_pb2.NOTIFICATION_CATEGORY_CONFIRMATION_PENDING
    assert payload.reason == "run_backtest"
    assert envelope.tenant_id == str(tenant_id)
    assert envelope.user_id == str(user_id)


async def test_repeat_proposal_collapses_by_confirmation_id(
    agent_service: AgentService,
    session_id: UUID,
) -> None:
    """Re-proposing the same confirmation id (e.g. a dropped-and-replayed stream)
    derives the same envelope id, so the consumer dedupes to one notification."""
    await _stream_backtest_proposal(agent_service, session_id)
    await _stream_backtest_proposal(agent_service, session_id)

    envelopes = _published()
    assert len(envelopes) == 2
    assert len({e.id for e in envelopes}) == 1
