"""Token-vs-wire identity test for the strategy servicer (no DB).

A user authenticated as tenant A who forges tenant B in ``request.context`` must
be rejected with ``PERMISSION_DENIED`` before any data access. Identity is
resolved from the verified principal (the ContextVar set by ``AuthMiddleware``),
not the wire body, exercising the middleware-populated branch of
``resolve_identity``. The forged call short-circuits before the servicer touches
the database, so no fixtures/Postgres are needed.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_proto.generated import common_pb2, strategy_pb2

from src.grpc.servicer import StrategyServicer

pytestmark = pytest.mark.asyncio

TENANT_A = uuid4()
TENANT_B = uuid4()
USER = uuid4()


async def test_get_strategy_rejects_forged_wire_tenant() -> None:
    """GetStrategy with a token for tenant A and wire tenant B → PERMISSION_DENIED."""
    servicer = StrategyServicer()
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            await servicer.get_strategy(
                strategy_pb2.GetStrategyRequest(
                    context=common_pb2.TenantContext(tenant_id=str(TENANT_B), user_id=str(USER)),
                    strategy_id=str(uuid4()),
                ),
                None,
            )
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)
