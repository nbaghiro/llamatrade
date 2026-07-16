"""Cross-tenant authorization tests for the portfolio servicers (no DB).

A user authenticated as tenant A who forges tenant B in ``request.context`` must
be rejected with ``PERMISSION_DENIED`` *before* any data access. Identity is
resolved from the verified principal (the ContextVar set by ``AuthMiddleware``),
not the wire body. These short-circuit before the servicer touches the database,
so no fixtures/Postgres are needed; the happy path and service-token path run in
the real-Postgres suite (``tests/integration/test_rls.py``).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_proto.generated import common_pb2, ledger_pb2, portfolio_pb2

from src.grpc.ledger_servicer import LedgerServicer
from src.grpc.servicer import PortfolioServicer

TENANT_A = uuid4()
TENANT_B = uuid4()
USER = uuid4()


def _wire(tenant, user=USER) -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(tenant), user_id=str(user))


async def test_portfolio_read_rejects_forged_tenant() -> None:
    """get_portfolio with a forged wire tenant → PERMISSION_DENIED (pre-DB)."""
    servicer = PortfolioServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.get_portfolio(
                portfolio_pb2.GetPortfolioRequest(context=_wire(TENANT_B)), None
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


async def test_ledger_mutation_rejects_forged_tenant() -> None:
    """deposit_funds with a forged wire tenant → PERMISSION_DENIED (pre-DB)."""
    servicer = LedgerServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.deposit_funds(
                ledger_pb2.DepositFundsRequest(
                    context=_wire(TENANT_B),
                    account_id=str(uuid4()),
                    amount=common_pb2.Decimal(value="100"),
                ),
                None,
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


async def test_missing_wire_identity_is_unauthenticated() -> None:
    """No ContextVar + empty wire context → UNAUTHENTICATED (not a crash)."""
    servicer = PortfolioServicer()
    with pytest.raises(ConnectError) as exc:
        await servicer.get_portfolio(
            portfolio_pb2.GetPortfolioRequest(context=common_pb2.TenantContext()), None
        )
    assert exc.value.code == Code.UNAUTHENTICATED
