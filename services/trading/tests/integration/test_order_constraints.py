"""Real-Postgres proof that ``orders.client_order_id`` is unique.

``client_order_id`` is the exactly-once submission key and the seed of the
ledger fill's deterministic ``event_id``; the app-level dedup lookup
(``_find_order_by_client_id``) can race under concurrent submits, so the
database constraint is the backstop. Requires Docker (testcontainers Postgres);
skips cleanly otherwise (see ``conftest``).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.trading import Order, TradingSession
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_PENDING,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)


async def _session_row(db: AsyncSession, tenant_id: UUID) -> TradingSession:
    session = TradingSession(
        tenant_id=tenant_id,
        strategy_id=uuid4(),
        strategy_version=1,
        credentials_id=uuid4(),
        name="Constraint Test",
        mode=EXECUTION_MODE_PAPER,
        config={},
        symbols=["SPY"],
        created_by=uuid4(),
    )
    db.add(session)
    await db.commit()
    return session


def _order(tenant_id: UUID, session_id: UUID, client_order_id: str) -> Order:
    return Order(
        tenant_id=tenant_id,
        session_id=session_id,
        client_order_id=client_order_id,
        symbol="SPY",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("10"),
        status=ORDER_STATUS_PENDING,
        filled_qty=Decimal("0"),
    )


class TestClientOrderIdUniqueness:
    async def test_duplicate_client_order_id_is_rejected(self, db: AsyncSession) -> None:
        tenant = uuid4()
        session = await _session_row(db, tenant)
        client_order_id = f"lt-{uuid4().hex[:16]}"

        db.add(_order(tenant, session.id, client_order_id))
        await db.commit()

        db.add(_order(tenant, session.id, client_order_id))
        with pytest.raises(IntegrityError, match="uq_orders_client_order_id"):
            await db.commit()
        await db.rollback()

    async def test_duplicate_rejected_even_across_tenants(self, db: AsyncSession) -> None:
        """The key seeds a GLOBAL ledger event id, so uniqueness is global too."""
        tenant_a, tenant_b = uuid4(), uuid4()
        session_a = await _session_row(db, tenant_a)
        session_b = await _session_row(db, tenant_b)
        client_order_id = f"lt-{uuid4().hex[:16]}"

        db.add(_order(tenant_a, session_a.id, client_order_id))
        await db.commit()

        db.add(_order(tenant_b, session_b.id, client_order_id))
        with pytest.raises(IntegrityError, match="uq_orders_client_order_id"):
            await db.commit()
        await db.rollback()

    async def test_distinct_client_order_ids_both_insert(self, db: AsyncSession) -> None:
        tenant = uuid4()
        session = await _session_row(db, tenant)

        db.add(_order(tenant, session.id, f"lt-{uuid4().hex[:16]}"))
        db.add(_order(tenant, session.id, f"lt-{uuid4().hex[:16]}"))
        await db.commit()
