"""Execution lifecycle events land on the notification stream."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_events import EventEnvelope
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
)

from src.services.strategy_service import StrategyService

_E = events_pb2

pytestmark = pytest.mark.asyncio


def _published() -> list[events_pb2.NotificationEvent]:
    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    return [
        NotificationEvents.payload(EventEnvelope.FromString(value))
        for _, value in transport.published
    ]


def _execution(status: int = EXECUTION_STATUS_PENDING) -> MagicMock:
    execution = MagicMock()
    execution.id = uuid4()
    execution.tenant_id = uuid4()
    execution.strategy_id = uuid4()
    execution.status = status
    execution.sleeve_id = None
    execution.account_id = None
    execution.allocated_capital = None
    execution.credentials_id = None
    return execution


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


async def test_start_emits_execution_started(mock_db: AsyncMock) -> None:
    service = StrategyService(mock_db)
    execution = _execution()
    with patch.object(service, "_get_execution_by_id", return_value=execution):
        await service.start_execution(execution.tenant_id, execution.id)

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_EXECUTION_STARTED]
    assert events[0].execution_id == str(execution.id)


async def test_funding_failure_emits_before_raise(mock_db: AsyncMock) -> None:
    service = StrategyService(mock_db)
    execution = _execution()
    execution.allocated_capital = 1000
    execution.credentials_id = uuid4()
    ledger = AsyncMock()
    ledger.get_or_create_account.side_effect = ConnectError(
        Code.FAILED_PRECONDITION, "insufficient free cash"
    )
    with (
        patch.object(service, "_get_execution_by_id", return_value=execution),
        patch.object(service, "_get_strategy_by_id", return_value=MagicMock(name="s")),
        pytest.raises(ValueError, match="funding failed"),
    ):
        await service.start_execution(execution.tenant_id, execution.id, ledger=ledger)

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_FUNDING_FAILED]
    assert "insufficient free cash" in events[0].reason


async def test_stop_emits_execution_stopped(mock_db: AsyncMock) -> None:
    service = StrategyService(mock_db)
    execution = _execution(EXECUTION_STATUS_RUNNING)
    with patch.object(service, "_get_execution_by_id", return_value=execution):
        await service.stop_execution(execution.tenant_id, execution.id, reason="manual")

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_EXECUTION_STOPPED]
    assert events[0].reason == "manual"


async def test_deferred_sleeve_release_emits_critical_flow(mock_db: AsyncMock) -> None:
    service = StrategyService(mock_db)
    execution = _execution(EXECUTION_STATUS_RUNNING)
    execution.sleeve_id = uuid4()
    execution.account_id = uuid4()
    ledger = AsyncMock()
    ledger.close_sleeve.side_effect = ConnectError(Code.UNAVAILABLE, "ledger down")
    with patch.object(service, "_get_execution_by_id", return_value=execution):
        await service.stop_execution(execution.tenant_id, execution.id, ledger=ledger)

    categories = [e.category for e in _published()]
    assert _E.NOTIFICATION_CATEGORY_SLEEVE_RELEASE_DEFERRED in categories
    assert _E.NOTIFICATION_CATEGORY_EXECUTION_STOPPED in categories
    # The needs-release marker survives for the sweeper.
    assert execution.sleeve_id is not None


async def test_repeat_start_collapses_by_dedup_id(mock_db: AsyncMock) -> None:
    service = StrategyService(mock_db)
    execution = _execution()
    with patch.object(service, "_get_execution_by_id", return_value=execution):
        await service.start_execution(execution.tenant_id, execution.id)
        execution.status = EXECUTION_STATUS_PENDING
        await service.start_execution(execution.tenant_id, execution.id)

    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    ids = {EventEnvelope.FromString(value).id for _, value in transport.published}
    assert len(ids) == 1
