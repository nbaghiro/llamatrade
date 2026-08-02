"""Servicer-level tests for the session lifecycle RPCs.

Covers Start/Stop/Pause/Resume/Get/List at the Connect boundary (auth resolution,
error mapping, and proto conversion) — complementing test_live_session_service.py
which exercises the service layer directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from llamatrade_proto.generated import common_pb2, trading_pb2
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)

from src.models import SessionResponse

pytestmark = pytest.mark.asyncio

TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("22222222-2222-2222-2222-222222222222")
STRATEGY = UUID("33333333-3333-3333-3333-333333333333")
SESSION = UUID("44444444-4444-4444-4444-444444444444")
CREDS = UUID("66666666-6666-6666-6666-666666666666")

_SVC_PATCH = "src.services.live_session_service.create_live_session_service"


@pytest.fixture
def ctx() -> RequestContext:
    return cast(RequestContext, MagicMock(spec=RequestContext))


@pytest.fixture
def servicer():
    from src.grpc.servicer import TradingServicer

    return TradingServicer()


def _session(*, stopped: bool = False) -> SessionResponse:
    return SessionResponse(
        id=SESSION,
        tenant_id=TENANT,
        strategy_id=STRATEGY,
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_STOPPED if stopped else EXECUTION_STATUS_RUNNING,
        started_at=datetime.now(UTC),
        stopped_at=datetime.now(UTC) if stopped else None,
        pnl=Decimal("12.5"),
        trades_count=3,
        name="Test Session",
        sleeve_id=uuid4(),
        account_id=uuid4(),
    )


def _mock_service(**methods) -> MagicMock:
    service = MagicMock()
    for name, value in methods.items():
        setattr(service, name, AsyncMock(return_value=value))
    return service


def _context() -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(TENANT), user_id=str(USER))


async def test_start_session_success(servicer, ctx):
    service = _mock_service(start_session=_session())
    request = trading_pb2.StartTradingSessionRequest(
        context=_context(),
        strategy_id=str(STRATEGY),
        credentials_id=str(CREDS),
        name="Test Session",
        symbols=["AAPL", "MSFT"],
    )
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.start_session(request, ctx)
    assert resp.session.id == str(SESSION)
    assert resp.session.is_active is True
    service.start_session.assert_awaited_once()


async def test_start_session_precondition_failure_maps_to_failed_precondition(servicer, ctx):
    service = MagicMock()
    service.start_session = AsyncMock(side_effect=ValueError("no active subscription"))
    request = trading_pb2.StartTradingSessionRequest(
        context=_context(), strategy_id=str(STRATEGY), credentials_id=str(CREDS)
    )
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        with pytest.raises(ConnectError) as exc_info:
            await servicer.start_session(request, ctx)
    assert exc_info.value.code == Code.FAILED_PRECONDITION


async def test_stop_session_success(servicer, ctx):
    service = _mock_service(stop_session=_session(stopped=True))
    request = trading_pb2.StopTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.stop_session(request, ctx)
    assert resp.session.id == str(SESSION)
    assert resp.session.HasField("ended_at")


async def test_stop_session_not_found(servicer, ctx):
    service = _mock_service(stop_session=None)
    request = trading_pb2.StopTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        with pytest.raises(ConnectError) as exc_info:
            await servicer.stop_session(request, ctx)
    assert exc_info.value.code == Code.NOT_FOUND


async def test_pause_session_success(servicer, ctx):
    service = _mock_service(pause_session=_session())
    request = trading_pb2.PauseTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.pause_session(request, ctx)
    assert resp.session.id == str(SESSION)


async def test_resume_session_success(servicer, ctx):
    service = _mock_service(resume_session=_session())
    request = trading_pb2.ResumeTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.resume_session(request, ctx)
    assert resp.session.id == str(SESSION)


async def test_get_session_success(servicer, ctx):
    service = _mock_service(get_session=_session())
    request = trading_pb2.GetTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.get_session(request, ctx)
    assert resp.session.total_trades == 3


async def test_get_session_not_found(servicer, ctx):
    service = _mock_service(get_session=None)
    request = trading_pb2.GetTradingSessionRequest(context=_context(), session_id=str(SESSION))
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_session(request, ctx)
    assert exc_info.value.code == Code.NOT_FOUND


async def test_list_sessions_success(servicer, ctx):
    service = MagicMock()
    service.list_sessions = AsyncMock(return_value=([_session(), _session(stopped=True)], 2))
    request = trading_pb2.ListTradingSessionsRequest(context=_context())
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.list_sessions(request, ctx)
    assert len(resp.sessions) == 2
    assert resp.pagination.total_items == 2


async def test_list_sessions_zero_page_size_does_not_crash(servicer, ctx):
    """A client-supplied page_size of 0 floors to a nonzero divisor (no ZeroDivisionError)."""
    service = MagicMock()
    service.list_sessions = AsyncMock(return_value=([_session()], 1))
    request = trading_pb2.ListTradingSessionsRequest(
        context=_context(),
        pagination=common_pb2.PaginationRequest(page=0, page_size=0),
    )
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        resp = await servicer.list_sessions(request, ctx)
    assert resp.pagination.page_size >= 1
    assert resp.pagination.current_page == 1
    assert resp.pagination.total_pages == 1
    assert service.list_sessions.await_args.kwargs["page_size"] >= 1


async def test_list_sessions_applies_a_valid_status_filter(servicer, ctx):
    service = MagicMock()
    service.list_sessions = AsyncMock(return_value=([_session()], 1))
    request = trading_pb2.ListTradingSessionsRequest(
        context=_context(), status=EXECUTION_STATUS_RUNNING
    )
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        await servicer.list_sessions(request, ctx)
    assert service.list_sessions.await_args.kwargs["status"] == EXECUTION_STATUS_RUNNING


async def test_list_sessions_treats_an_unset_status_as_every_status(servicer, ctx):
    """A singular proto3 enum cannot distinguish unset from UNSPECIFIED, so 0 means all."""
    service = MagicMock()
    service.list_sessions = AsyncMock(return_value=([], 0))
    request = trading_pb2.ListTradingSessionsRequest(context=_context())
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        await servicer.list_sessions(request, ctx)
    assert service.list_sessions.await_args.kwargs["status"] is None


@pytest.mark.parametrize("status", [EXECUTION_STATUS_PENDING, 99])
async def test_list_sessions_rejects_a_status_no_session_can_hold(servicer, ctx, status):
    """Sessions store a narrower set than ExecutionStatus; an unstorable filter is rejected."""
    service = MagicMock()
    service.list_sessions = AsyncMock(return_value=([], 0))
    request = trading_pb2.ListTradingSessionsRequest(context=_context(), status=status)
    with patch(_SVC_PATCH, new=AsyncMock(return_value=service)):
        with pytest.raises(ConnectError) as exc_info:
            await servicer.list_sessions(request, ctx)
    assert exc_info.value.code == Code.INVALID_ARGUMENT
    service.list_sessions.assert_not_awaited()


async def test_session_rpc_requires_authentication(servicer, ctx):
    """An empty wire context (no principal) is rejected before touching the service."""
    request = trading_pb2.GetTradingSessionRequest(
        context=common_pb2.TenantContext(tenant_id="", user_id=""),
        session_id=str(SESSION),
    )
    with pytest.raises(ConnectError) as exc_info:
        await servicer.get_session(request, ctx)
    assert exc_info.value.code == Code.UNAUTHENTICATED
