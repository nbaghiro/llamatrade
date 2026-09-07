"""Table-driven mapping of servicer ``except`` blocks to Connect status codes.

Each RPC's dependency seam is made to raise, and the resulting ConnectError
code is asserted: domain ``ValueError`` maps to FAILED_PRECONDITION (session
lifecycle) or INVALID_ARGUMENT (list/order surfaces), any unexpected exception
maps to a sanitized INTERNAL, and an inner ConnectError passes through intact.
"""

from collections.abc import Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from llamatrade_proto.generated import common_pb2, trading_pb2

from src.grpc.servicer import TradingServicer

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")

SESSION_SEAM = "src.services.live_session_service.create_live_session_service"
EXECUTOR_SEAM = "src.grpc.servicer.create_order_executor"
POSITION_SEAM = "src.services.position_service.create_position_service"


def _ctx() -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(TENANT_ID), user_id=str(USER_ID))


def _start_request() -> trading_pb2.StartTradingSessionRequest:
    return trading_pb2.StartTradingSessionRequest(
        context=_ctx(),
        strategy_id=str(uuid4()),
        credentials_id=str(uuid4()),
        name="s",
    )


def _stop_request() -> trading_pb2.StopTradingSessionRequest:
    return trading_pb2.StopTradingSessionRequest(context=_ctx(), session_id=str(uuid4()))


def _pause_request() -> trading_pb2.PauseTradingSessionRequest:
    return trading_pb2.PauseTradingSessionRequest(context=_ctx(), session_id=str(uuid4()))


def _resume_request() -> trading_pb2.ResumeTradingSessionRequest:
    return trading_pb2.ResumeTradingSessionRequest(context=_ctx(), session_id=str(uuid4()))


def _get_session_request() -> trading_pb2.GetTradingSessionRequest:
    return trading_pb2.GetTradingSessionRequest(context=_ctx(), session_id=str(uuid4()))


def _list_sessions_request() -> trading_pb2.ListTradingSessionsRequest:
    return trading_pb2.ListTradingSessionsRequest(context=_ctx())


def _submit_order_request() -> trading_pb2.SubmitOrderRequest:
    return trading_pb2.SubmitOrderRequest(
        context=_ctx(),
        session_id=str(uuid4()),
        symbol="AAPL",
        side=trading_pb2.ORDER_SIDE_BUY,
        type=trading_pb2.ORDER_TYPE_MARKET,
        quantity=common_pb2.Decimal(value="10"),
    )


def _cancel_order_request() -> trading_pb2.CancelOrderRequest:
    return trading_pb2.CancelOrderRequest(context=_ctx(), order_id=str(uuid4()))


def _get_order_request() -> trading_pb2.GetOrderRequest:
    return trading_pb2.GetOrderRequest(context=_ctx(), order_id=str(uuid4()))


def _list_orders_request() -> trading_pb2.ListOrdersRequest:
    return trading_pb2.ListOrdersRequest(context=_ctx())


def _get_position_request() -> trading_pb2.GetPositionRequest:
    return trading_pb2.GetPositionRequest(context=_ctx(), session_id=str(uuid4()), symbol="AAPL")


def _list_positions_request() -> trading_pb2.ListPositionsRequest:
    return trading_pb2.ListPositionsRequest(context=_ctx(), session_id=str(uuid4()))


def _close_position_request() -> trading_pb2.ClosePositionRequest:
    return trading_pb2.ClosePositionRequest(context=_ctx(), session_id=str(uuid4()), symbol="AAPL")


CASES: list[tuple[str, Callable[[], object], str, Exception, Code]] = [
    (
        "start_session",
        _start_request,
        SESSION_SEAM,
        ValueError("no creds"),
        Code.FAILED_PRECONDITION,
    ),
    ("start_session", _start_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "stop_session",
        _stop_request,
        SESSION_SEAM,
        ValueError("bad state"),
        Code.FAILED_PRECONDITION,
    ),
    ("stop_session", _stop_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "pause_session",
        _pause_request,
        SESSION_SEAM,
        ValueError("bad state"),
        Code.FAILED_PRECONDITION,
    ),
    ("pause_session", _pause_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "resume_session",
        _resume_request,
        SESSION_SEAM,
        ValueError("bad state"),
        Code.FAILED_PRECONDITION,
    ),
    ("resume_session", _resume_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("get_session", _get_session_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "list_sessions",
        _list_sessions_request,
        SESSION_SEAM,
        ValueError("bad page"),
        Code.INVALID_ARGUMENT,
    ),
    ("list_sessions", _list_sessions_request, SESSION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("submit_order", _submit_order_request, EXECUTOR_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("cancel_order", _cancel_order_request, EXECUTOR_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("get_order", _get_order_request, EXECUTOR_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "list_orders",
        _list_orders_request,
        EXECUTOR_SEAM,
        ValueError("bad page"),
        Code.INVALID_ARGUMENT,
    ),
    ("list_orders", _list_orders_request, EXECUTOR_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("get_position", _get_position_request, POSITION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    ("list_positions", _list_positions_request, POSITION_SEAM, RuntimeError("boom"), Code.INTERNAL),
    (
        "close_position",
        _close_position_request,
        POSITION_SEAM,
        ValueError("bad qty"),
        Code.INVALID_ARGUMENT,
    ),
    ("close_position", _close_position_request, POSITION_SEAM, RuntimeError("boom"), Code.INTERNAL),
]


@pytest.fixture
def grpc_context() -> RequestContext:
    return cast(RequestContext, MagicMock(spec=RequestContext))


@pytest.mark.parametrize(
    ("rpc", "build_request", "seam", "exc", "expected_code"),
    CASES,
    ids=[f"{rpc}-{type(exc).__name__}-{code.name}" for rpc, _, _, exc, code in CASES],
)
async def test_seam_exception_maps_to_connect_code(
    grpc_context: RequestContext,
    rpc: str,
    build_request: Callable[[], object],
    seam: str,
    exc: Exception,
    expected_code: Code,
):
    servicer = TradingServicer()
    with patch(seam, new=AsyncMock(side_effect=exc)):
        with pytest.raises(ConnectError) as exc_info:
            await getattr(servicer, rpc)(build_request(), grpc_context)

    assert exc_info.value.code == expected_code
    if expected_code is Code.INTERNAL:
        assert "boom" not in str(exc_info.value)
    else:
        assert str(exc) in str(exc_info.value)


@pytest.mark.parametrize(
    ("rpc", "build_request", "seam"),
    [
        ("stop_session", _stop_request, SESSION_SEAM),
        ("get_order", _get_order_request, EXECUTOR_SEAM),
    ],
)
async def test_inner_connect_error_passes_through_unchanged(
    grpc_context: RequestContext,
    rpc: str,
    build_request: Callable[[], object],
    seam: str,
):
    inner = ConnectError(Code.NOT_FOUND, "nothing here")
    servicer = TradingServicer()
    with patch(seam, new=AsyncMock(side_effect=inner)):
        with pytest.raises(ConnectError) as exc_info:
            await getattr(servicer, rpc)(build_request(), grpc_context)

    assert exc_info.value.code == Code.NOT_FOUND
    assert "nothing here" in str(exc_info.value)
