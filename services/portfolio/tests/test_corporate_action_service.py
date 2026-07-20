"""Tests for the corporate-action driver (fan-out across sleeves, idempotent)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from src.ledger.projection import AccountProjection, PositionState
from src.services.corporate_action_service import CorporateActionService

pytestmark = pytest.mark.asyncio

TENANT = uuid4()
ACCOUNT = uuid4()


class _FakeStore:
    """``ports.LedgerStore`` fake: static projection + event_id-deduped appends."""

    def __init__(self, projection: AccountProjection) -> None:
        self._projection = projection
        self.appended: dict[object, tuple] = {}

    async def project_account(self, tenant_id, account_id) -> AccountProjection:
        return self._projection

    async def append(
        self,
        *,
        tenant_id,
        account_id,
        event_type,
        data,
        sleeve_id=None,
        event_id=None,
        occurred_at=None,
    ):
        self.appended[event_id] = (event_type, sleeve_id, data)  # ON CONFLICT DO NOTHING
        return object()


async def test_apply_split_fans_across_holders_and_is_idempotent() -> None:
    s1, s2 = uuid4(), uuid4()
    proj = AccountProjection()
    proj.sleeve(str(s1)).positions["SPY"] = PositionState(
        qty=Decimal("10"), cost_basis=Decimal("1500")
    )
    proj.sleeve(str(s2)).positions["SPY"] = PositionState(
        qty=Decimal("5"), cost_basis=Decimal("750")
    )
    svc = CorporateActionService(store := _FakeStore(proj))

    n = await svc.apply_split(
        tenant_id=TENANT, account_id=ACCOUNT, symbol="SPY", ratio=Decimal("2")
    )
    assert n == 2
    deltas = {d["sleeve_id"]: d["qty_delta"] for _, _, d in store.appended.values()}
    assert deltas[str(s1)] == "10"  # qty * (ratio - 1) for a 2-for-1
    assert deltas[str(s2)] == "5"

    # Re-applying the same split maps to the same deterministic event ids → deduped.
    n2 = await svc.apply_split(
        tenant_id=TENANT, account_id=ACCOUNT, symbol="SPY", ratio=Decimal("2")
    )
    assert n2 == 2
    assert len(store.appended) == 2


async def test_apply_symbol_change_carries_qty_and_cost() -> None:
    s1 = uuid4()
    proj = AccountProjection()
    proj.sleeve(str(s1)).positions["META"] = PositionState(
        qty=Decimal("3"), cost_basis=Decimal("900")
    )
    svc = CorporateActionService(store := _FakeStore(proj))

    # No holders of the old symbol → nothing appended.
    assert (
        await svc.apply_symbol_change(
            tenant_id=TENANT, account_id=ACCOUNT, old_symbol="FB", new_symbol="META"
        )
        == 0
    )

    assert (
        await svc.apply_symbol_change(
            tenant_id=TENANT, account_id=ACCOUNT, old_symbol="META", new_symbol="METX"
        )
        == 1
    )
    ((_, _, data),) = store.appended.values()
    assert data["old_symbol"] == "META"
    assert data["new_symbol"] == "METX"
    assert data["qty"] == "3"
    assert data["cost_basis"] == "900"


async def test_apply_split_rejects_nonpositive_ratio() -> None:
    proj = AccountProjection()
    proj.sleeve(str(uuid4())).positions["SPY"] = PositionState(qty=Decimal("1"))
    svc = CorporateActionService(_FakeStore(proj))
    with pytest.raises(ValueError, match="ratio"):
        await svc.apply_split(
            tenant_id=TENANT, account_id=ACCOUNT, symbol="SPY", ratio=Decimal("0")
        )
