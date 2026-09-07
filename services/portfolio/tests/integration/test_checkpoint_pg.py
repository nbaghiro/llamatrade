"""Checkpoint-store upsert semantics against real Postgres.

The forward-only ``ON CONFLICT`` predicate is what stops a stale writer from
regressing a checkpoint; the unit suite only pins the compiled SQL string, so
this exercises the actual conflict behavior on real rows.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ledger import checkpoint_store
from src.ledger.projection import AccountProjection, ReservationState

pytestmark = pytest.mark.integration

D = Decimal


def _projection(cash: str) -> AccountProjection:
    projection = AccountProjection()
    projection.sleeve("s1").cash = D(cash)
    return projection


async def _save(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    account_id: UUID,
    sequence: int,
    cash: str,
) -> None:
    async with session_factory() as db:
        await checkpoint_store.save(
            db, tenant_id, account_id, sequence, _projection(cash), ReservationState(), {}
        )
        await db.commit()


async def _load(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID, account_id: UUID
) -> tuple[int, str]:
    async with session_factory() as db:
        loaded = await checkpoint_store.load(db, tenant_id, account_id)
    assert loaded is not None
    sequence, projection, _reservations, _lots = loaded
    return sequence, str(projection.sleeve("s1").cash)


async def test_checkpoint_upsert_advances_and_never_regresses(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id, account_id = uuid4(), uuid4()

    await _save(session_factory, tenant_id, account_id, 5, "500")
    assert await _load(session_factory, tenant_id, account_id) == (5, "500")

    # A stale writer at a lower sequence must be a no-op: neither sequence nor state move.
    await _save(session_factory, tenant_id, account_id, 3, "300")
    assert await _load(session_factory, tenant_id, account_id) == (5, "500")

    # An equal-sequence save DOES apply (repairs a corrupt state row in place).
    await _save(session_factory, tenant_id, account_id, 5, "555")
    assert await _load(session_factory, tenant_id, account_id) == (5, "555")

    # A newer sequence advances normally.
    await _save(session_factory, tenant_id, account_id, 7, "700")
    assert await _load(session_factory, tenant_id, account_id) == (7, "700")


async def test_checkpoint_rows_are_scoped_per_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The conflict target is (tenant, account): a second account upserts its own row."""
    tenant_id = uuid4()
    account_a, account_b = uuid4(), uuid4()

    await _save(session_factory, tenant_id, account_a, 5, "500")
    await _save(session_factory, tenant_id, account_b, 2, "200")

    assert await _load(session_factory, tenant_id, account_a) == (5, "500")
    assert await _load(session_factory, tenant_id, account_b) == (2, "200")


async def test_checkpoint_load_missing_row_is_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        assert await checkpoint_store.load(db, uuid4(), uuid4()) is None
