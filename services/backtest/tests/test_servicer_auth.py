"""Cross-tenant authorization tests for the backtest servicer (no DB).

A user authenticated as tenant A who forges tenant B in ``request.context`` must
be rejected with ``PERMISSION_DENIED`` *before* any data access. Identity is
resolved from the verified principal (the ContextVar set by ``AuthMiddleware``),
not the wire body. These short-circuit before the servicer touches the database,
so no fixtures/Postgres are needed; the happy path runs in the e2e/RLS suites.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_proto.generated import backtest_pb2, common_pb2

from src.grpc.servicer import BacktestServicer

pytestmark = pytest.mark.asyncio

TENANT_A = uuid4()
TENANT_B = uuid4()
USER = uuid4()


def _wire(tenant, user=USER) -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(tenant), user_id=str(user))


async def test_get_backtest_rejects_forged_tenant() -> None:
    """GetBacktest with a forged wire tenant → PERMISSION_DENIED (pre-DB)."""
    servicer = BacktestServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.get_backtest(
                backtest_pb2.GetBacktestRequest(context=_wire(TENANT_B), backtest_id=str(uuid4())),
                None,
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


async def test_list_backtests_rejects_forged_tenant() -> None:
    """ListBacktests with a forged wire tenant → PERMISSION_DENIED (pre-DB)."""
    servicer = BacktestServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.list_backtests(
                backtest_pb2.ListBacktestsRequest(context=_wire(TENANT_B)), None
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


async def test_run_backtest_rejects_forged_tenant() -> None:
    """RunBacktest with a forged wire tenant → PERMISSION_DENIED (pre-config, pre-DB)."""
    servicer = BacktestServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.run_backtest(
                backtest_pb2.RunBacktestRequest(context=_wire(TENANT_B)), None
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


async def test_missing_wire_identity_is_unauthenticated() -> None:
    """No ContextVar + empty wire context → UNAUTHENTICATED (not a crash)."""
    servicer = BacktestServicer()
    with pytest.raises(ConnectError) as exc:
        await servicer.get_backtest(
            backtest_pb2.GetBacktestRequest(context=common_pb2.TenantContext()), None
        )
    assert exc.value.code == Code.UNAUTHENTICATED
