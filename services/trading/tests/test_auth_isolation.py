"""Tenant-isolation tests for the trading servicer (trading-hardening 9A).

These exercise the auth adoption: the servicer derives identity from the verified
principal (the AuthMiddleware contextvar) and rejects a request whose wire
tenant_id doesn't match — closing the cross-tenant IDOR on the money path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import grpc.aio
import pytest

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_proto.generated import common_pb2, trading_pb2

pytestmark = pytest.mark.asyncio

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("33333333-3333-3333-3333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")


class MockServicerContext:
    """Mock gRPC context whose abort records the status code and raises."""

    def __init__(self) -> None:
        self.code: grpc.StatusCode | None = None
        self.details: str | None = None

    async def abort(self, code: grpc.StatusCode, details: str) -> None:
        self.code = code
        self.details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details=details,
        )

    def cancelled(self) -> bool:
        return False


@pytest.fixture
def servicer():
    from src.grpc.servicer import TradingServicer

    return TradingServicer()


def _submit_request(wire_tenant: UUID, wire_user: UUID = USER) -> trading_pb2.SubmitOrderRequest:
    return trading_pb2.SubmitOrderRequest(
        context=common_pb2.TenantContext(tenant_id=str(wire_tenant), user_id=str(wire_user)),
        session_id=str(SESSION_ID),
        symbol="AAPL",
        side=trading_pb2.ORDER_SIDE_BUY,
        type=trading_pb2.ORDER_TYPE_MARKET,
        time_in_force=trading_pb2.TIME_IN_FORCE_DAY,
        quantity=common_pb2.Decimal(value="10"),
    )


async def test_cross_tenant_submit_is_denied(servicer):
    """An authenticated tenant-A principal cannot submit with a tenant-B body."""
    ctx = MockServicerContext()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(grpc.aio.AioRpcError):
            await servicer.SubmitOrder(_submit_request(wire_tenant=TENANT_B), ctx)
    finally:
        reset_context(token)
    assert ctx.code == grpc.StatusCode.PERMISSION_DENIED


async def test_matching_tenant_submit_proceeds(servicer):
    """A tenant-A principal with a tenant-A body reaches the executor."""
    ctx = MockServicerContext()
    mock_order = MagicMock()
    mock_order.id = uuid4()
    mock_order.client_order_id = "lt-abc"
    mock_order.symbol = "AAPL"
    mock_order.side = trading_pb2.ORDER_SIDE_BUY
    mock_order.order_type = trading_pb2.ORDER_TYPE_MARKET
    mock_order.status = trading_pb2.ORDER_STATUS_SUBMITTED
    mock_order.qty = 10.0
    mock_order.filled_qty = 0
    mock_order.limit_price = None
    mock_order.stop_price = None
    mock_order.filled_avg_price = None
    mock_order.submitted_at = None

    mock_executor = MagicMock()
    mock_executor.submit_order = AsyncMock(return_value=mock_order)

    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with patch(
            "src.grpc.servicer.create_order_executor",
            new=AsyncMock(return_value=mock_executor),
        ):
            response = await servicer.SubmitOrder(_submit_request(wire_tenant=TENANT_A), ctx)
        assert response.order.symbol == "AAPL"
        mock_executor.submit_order.assert_called_once()
        # The executor is created for the *authenticated* tenant (2A creds path).
        _, kwargs = mock_executor.submit_order.call_args
        assert kwargs["tenant_id"] == TENANT_A
    finally:
        reset_context(token)


async def test_unauthenticated_submit_is_rejected(servicer):
    """No principal and an empty wire context → UNAUTHENTICATED."""
    ctx = MockServicerContext()
    request = trading_pb2.SubmitOrderRequest(
        context=common_pb2.TenantContext(tenant_id="", user_id=""),
        session_id=str(SESSION_ID),
        symbol="AAPL",
        side=trading_pb2.ORDER_SIDE_BUY,
        type=trading_pb2.ORDER_TYPE_MARKET,
        time_in_force=trading_pb2.TIME_IN_FORCE_DAY,
        quantity=common_pb2.Decimal(value="10"),
    )
    with pytest.raises(grpc.aio.AioRpcError):
        await servicer.SubmitOrder(request, ctx)
    assert ctx.code == grpc.StatusCode.UNAUTHENTICATED


async def test_service_principal_trusts_wire_tenant(servicer):
    """A service principal forwards the wire tenant (inter-service calls)."""
    ctx = MockServicerContext()
    mock_order = MagicMock()
    mock_order.id = uuid4()
    mock_order.client_order_id = "lt-svc"
    mock_order.symbol = "AAPL"
    mock_order.side = trading_pb2.ORDER_SIDE_BUY
    mock_order.order_type = trading_pb2.ORDER_TYPE_MARKET
    mock_order.status = trading_pb2.ORDER_STATUS_SUBMITTED
    mock_order.qty = 10.0
    mock_order.filled_qty = 0
    mock_order.limit_price = None
    mock_order.stop_price = None
    mock_order.filled_avg_price = None
    mock_order.submitted_at = None

    mock_executor = MagicMock()
    mock_executor.submit_order = AsyncMock(return_value=mock_order)

    token = set_context(TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True))
    try:
        with patch(
            "src.grpc.servicer.create_order_executor",
            new=AsyncMock(return_value=mock_executor),
        ):
            await servicer.SubmitOrder(_submit_request(wire_tenant=TENANT_B), ctx)
        _, kwargs = mock_executor.submit_order.call_args
        # Service principal → the wire tenant (B) is trusted, not blocked.
        assert kwargs["tenant_id"] == TENANT_B
    finally:
        reset_context(token)


async def test_cross_tenant_list_orders_is_denied(servicer):
    """The guard applies to read RPCs too, not just order placement."""
    ctx = MockServicerContext()
    request = trading_pb2.ListOrdersRequest(
        context=common_pb2.TenantContext(tenant_id=str(TENANT_B), user_id=str(USER)),
    )
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(grpc.aio.AioRpcError):
            await servicer.ListOrders(request, ctx)
    finally:
        reset_context(token)
    assert ctx.code == grpc.StatusCode.PERMISSION_DENIED
