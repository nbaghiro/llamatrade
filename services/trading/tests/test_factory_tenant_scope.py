"""Tenant scoping of the gRPC-path service factories.

The factories build long-lived DB sessions, so they must bind the RLS tenant
GUC per-transaction (bind_tenant_guc) and refuse to run unscoped.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.session import bound_tenant_guc

from src.executor.order_executor import create_order_executor
from src.services.live_session_service import create_live_session_service
from src.services.position_service import create_position_service


class TestFactoriesRequireTenant:
    """tenant_id=None is an explicit error — never a silently unscoped session."""

    async def test_create_live_session_service_rejects_none(self):
        with pytest.raises(ValueError, match="tenant_id"):
            await create_live_session_service(None)

    async def test_create_order_executor_rejects_none(self):
        with pytest.raises(ValueError, match="tenant_id"):
            await create_order_executor(tenant_id=None)

    async def test_create_position_service_rejects_none(self):
        with pytest.raises(ValueError, match="tenant_id"):
            await create_position_service(None)


async def test_create_position_service_binds_tenant_guc(monkeypatch, tenant_id):
    """The factory's session carries a per-transaction tenant binding, not a one-shot GUC."""
    created: list[AsyncSession] = []

    def _make() -> AsyncSession:
        session = AsyncSession()
        created.append(session)
        return session

    monkeypatch.setattr("llamatrade_db.session.get_session_maker", lambda: _make)
    monkeypatch.setattr("src.services.position_service.get_market_data_client", lambda: MagicMock())

    service = await create_position_service(tenant_id)
    try:
        assert len(created) == 1
        assert service.db is created[0]
        assert bound_tenant_guc(created[0]) == tenant_id
    finally:
        await service.aclose()
